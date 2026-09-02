"""One-way migration: sources/generated/*.yaml + mappings/target_catalogs/*.yaml -> Postgres.

Idempotent and re-runnable (refuses to run over an existing catalog_source row for the same
source_name+kind unless --force). Loads the RAW catalog YAML (yaml.safe_load, no annotation
merge — annotations stay YAML, merged only at read time, out of scope for this migration) and
saves it via core.catalog_db.save_catalog. After loading, runs a parity check comparing the
migrated Postgres data back against the original YAML.

CLI:  python -m core.catalog_db.migrate_from_yaml                # migrate all sources+targets
      python -m core.catalog_db.migrate_from_yaml --force        # allow re-run over existing data
      python -m core.catalog_db.migrate_from_yaml --name "ALM Bank"  # just one
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.catalog_db.repository import DATASET_STAT_FIELDS, ELEMENT_STAT_FIELDS, load_catalog, save_catalog
from core.glossary_db.db import session_scope
from core.shared.models import CatalogSource

_PROJECT_FILE = _ROOT / "project.yaml"


def _project() -> dict:
    with _PROJECT_FILE.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _catalog_dir(kind: str, project: dict) -> Path:
    paths = project.get("paths", {}) or {}
    key = "source_catalogs" if kind == "source" else "target_catalogs"
    return _ROOT / paths.get(key, "sources/generated/" if kind == "source" else "mappings/target_catalogs/")


def _load_raw_yaml(name: str, kind: str, project: dict) -> dict | None:
    path = _catalog_dir(kind, project) / f"{name}.yaml"
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _existing_source(session, name: str, kind: str) -> CatalogSource | None:
    return session.execute(
        select(CatalogSource).where(CatalogSource.source_name == name, CatalogSource.kind == kind)
    ).scalar_one_or_none()


# ── parity check ─────────────────────────────────────────────────────────────

def _normalize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        # JSON has no native date type -- Postgres correctly stores these as ISO strings
        # inside JSONB. Normalize both sides to the same ISO representation for comparison.
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    return value


def _values_equal(a: Any, b: Any, tol: float = 1e-6) -> bool:
    a, b = _normalize(a), _normalize(b)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
        a, b = float(a), float(b)
        # Relative tolerance: float64 only carries ~15-17 significant digits, so an absolute
        # tolerance is meaningless once values reach large magnitudes (e.g. an averaged
        # big-integer-like ID column) -- both sides are only as precise as float64 allows.
        scale = max(abs(a), abs(b), 1.0)
        return abs(a - b) <= scale * 1e-9
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(_values_equal(a[k], b[k], tol) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_values_equal(x, y, tol) for x, y in zip(a, b))
    return a == b


def _diff_fields(yaml_dict: dict, pg_dict: dict, fields: tuple[str, ...], label: str) -> list[str]:
    """Compare only fields present as a key in *yaml_dict* (older/simpler catalogs may lack
    newer fields entirely — that's not a discrepancy, just absence)."""
    mismatches = []
    for f in fields:
        if f not in yaml_dict:
            continue
        if not _values_equal(yaml_dict.get(f), pg_dict.get(f)):
            mismatches.append(f"{label}.{f}: yaml={yaml_dict.get(f)!r} != pg={pg_dict.get(f)!r}")
    return mismatches


def check_parity(name: str, kind: str, project: dict) -> list[str]:
    """Return a list of mismatch descriptions (empty = parity confirmed)."""
    raw = _load_raw_yaml(name, kind, project)
    if raw is None:
        return [f"{name}: source YAML file not found"]
    migrated = load_catalog(name, kind, catalog_dir=None)
    if not migrated:
        return [f"{name}: nothing found in Postgres after migration"]

    mismatches: list[str] = []
    yaml_tables = {
        (s.get("name") or tbl.get("schema_name"), tbl.get("table_name")): tbl
        for s in raw.get("schemas", []) for tbl in s.get("tables", [])
    }
    pg_tables = {
        (s.get("name"), tbl.get("table_name")): tbl
        for s in migrated.get("schemas", []) for tbl in s.get("tables", [])
    }
    if set(yaml_tables) != set(pg_tables):
        mismatches.append(
            f"{name}: table set differs — only in yaml: {set(yaml_tables) - set(pg_tables)}, "
            f"only in pg: {set(pg_tables) - set(yaml_tables)}"
        )
    for key, y_tbl in yaml_tables.items():
        p_tbl = pg_tables.get(key)
        if p_tbl is None:
            continue
        label = f"{name}:{key[0]}.{key[1]}"
        mismatches.extend(_diff_fields(y_tbl, p_tbl, DATASET_STAT_FIELDS, label))

        y_cols = {c.get("name"): c for c in y_tbl.get("columns", []) if c.get("name")}
        p_cols = {c.get("name"): c for c in p_tbl.get("columns", []) if c.get("name")}
        if set(y_cols) != set(p_cols):
            mismatches.append(
                f"{label}: column set differs — only in yaml: {set(y_cols) - set(p_cols)}, "
                f"only in pg: {set(p_cols) - set(y_cols)}"
            )
        for cname, y_col in y_cols.items():
            p_col = p_cols.get(cname)
            if p_col is None:
                continue
            mismatches.extend(_diff_fields(y_col, p_col, ELEMENT_STAT_FIELDS, f"{label}.{cname}"))
    return mismatches


# ── migration ────────────────────────────────────────────────────────────────

def migrate_one(name: str, kind: str, project: dict, *, force: bool) -> tuple[bool, list[str]]:
    """Returns (migrated, parity_mismatches)."""
    raw = _load_raw_yaml(name, kind, project)
    if raw is None:
        print(f"  SKIP {name} ({kind}): no YAML file found")
        return False, []

    with session_scope() as s:
        existing = _existing_source(s, name, kind)
        if existing is not None and not force:
            print(f"  SKIP {name} ({kind}): already migrated, pass --force to re-run")
            return False, []

    save_catalog(
        name, kind=kind,
        connector_type=raw.get("connector_type"), connection_ref=raw.get("connection"),
        version=raw.get("version"), schema_hash=raw.get("schema_hash"),
        generated_at=raw.get("generated_at"), schemas=raw.get("schemas") or [],
    )
    mismatches = check_parity(name, kind, project)
    status = "PARITY PASS" if not mismatches else f"PARITY MISMATCH ({len(mismatches)})"
    print(f"  MIGRATED {name} ({kind}): {status}")
    for m in mismatches:
        print(f"    - {m}")
    return True, mismatches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="re-run over an already-migrated source/target")
    parser.add_argument("--name", help="migrate just this one source/target name")
    args = parser.parse_args()

    project = _project()
    total_mismatches = 0
    total_migrated = 0

    print("Sources:")
    for src in project.get("sources", []):
        name = src["name"]
        if args.name and name != args.name:
            continue
        migrated, mismatches = migrate_one(name, "source", project, force=args.force)
        total_migrated += int(migrated)
        total_mismatches += len(mismatches)

    print("Targets:")
    for tgt in project.get("targets", []):
        name = tgt["name"]
        if args.name and name != args.name:
            continue
        migrated, mismatches = migrate_one(name, "target", project, force=args.force)
        total_migrated += int(migrated)
        total_mismatches += len(mismatches)

    print(f"\n{total_migrated} migrated, {total_mismatches} total parity mismatch(es).")
    return 1 if total_mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())

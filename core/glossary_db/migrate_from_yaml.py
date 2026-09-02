"""One-way migration: glossary/glossary.yaml (+ glossary_meta.yaml) -> PostgreSQL.

Idempotent and re-runnable. Truncates the glossary tables then loads; refuses to run against
a non-empty store unless ``force=True`` (so it can never silently wipe live data after a
future cutover). Resolution mirrors the Phase-1a linkage profile EXACTLY so the migrated
granularity counts can be validated against it.

CLI:  python -m core.glossary_db.migrate_from_yaml            # migrate dev 'adm', print+write report
      python -m core.glossary_db.migrate_from_yaml --force    # allow re-run over existing data
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.glossary_db import db as gdb
from core.shared.models import (
    Glossary, GlossaryGroupMeta, Linkage, LinkageTriage, LifecycleTransition,
    Term, TermRelation, TermVersion,
)
from core.glossary_db.repository import GlossaryRepository, _granularity, _parse_ref

GLOSSARY_YAML = _ROOT / "glossary" / "glossary.yaml"
GLOSSARY_META = _ROOT / "glossary" / "glossary_meta.yaml"

# Phase-1a linkage granularity profile (analysis/linkage_profile.py). The migration must
# reproduce these numbers exactly — divergence means two parsers disagree.
# NOTE: updated 2026-07-24 to drop one blank-id/blank-title ghost draft term (0 usable
# fields, one stray linkage to raw_faker.home_credit_credit_card.sk_id_curr) found during
# Business Glossary v2 UI validation and removed from glossary/glossary.yaml as bad data —
# terms 181->180, source_column 104->103, source_column_resolved 91->90,
# distinct_source_columns 61->60.
EXPECTED_1A = {
    "source_column": 103, "source_table": 8,
    "target_column": 47, "target_table": 46,
    "free_text": 62,
    "source_column_resolved": 90, "source_column_unresolved": 13,
    "source_table_resolved": 6, "source_table_unresolved": 2,
    "target_table_resolved": 46, "target_column_unresolved": 47,
    "distinct_source_columns": 60, "total_source_columns": 2290,
    "terms": 180, "terms_with_ref": 176,
}

# Canonical status enum (01a D3). draft/approved present in data; the rest are defensive.
_STATUS_MAP = {
    "draft": "draft", "approved": "approved", "retired": "deprecated",
    "confirmed": "approved", "published": "approved",
    "in_review": "in_review", "deprecated": "deprecated", "rejected": "rejected",
}
# DQ term_status bonus buckets (dq_scoring_config.yaml term_status scale; others -> 0).
_DQ_BONUS = {"published": 4, "approved": 3, "confirmed": 2, "draft": 1}
_BOOST = {"approved", "confirmed", "published"}  # element.py _GLOSSARY_CONFIRMED_STATUSES


def _canon(status: str | None) -> str:
    return _STATUS_MAP.get((status or "draft").strip().lower(), "draft")


def _parse_dt(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v))
    except ValueError:
        return None


def _now():
    return datetime.now(timezone.utc)


# ── catalog indexes (identical to analysis/linkage_profile.py) ────────────────

# Process-level cache: catalogs are static within a migration run (and the CLI runs once),
# so parse+index each catalog only once even across repeated migrations (test speed).
_INDEX_CACHE: dict[str, dict] = {}


def _project_paths() -> tuple[Path, Path]:
    with (_ROOT / "project.yaml").open(encoding="utf-8") as fh:
        p = (yaml.safe_load(fh) or {}).get("paths", {})
    return (_ROOT / p.get("source_catalogs", "sources/generated"),
            _ROOT / p.get("target_catalogs", "mappings/target_catalogs"))


def _build_index(path: Path) -> dict:
    key = str(path)
    cached = _INDEX_CACHE.get(key)
    if cached is not None:
        return cached
    if not path.exists():
        _INDEX_CACHE[key] = {"exists": False}
        return _INDEX_CACHE[key]
    with path.open(encoding="utf-8") as fh:
        cat = yaml.safe_load(fh) or {}
    cols, tables, table_names, col_by_table = set(), set(), set(), set()
    for sc in cat.get("schemas", []):
        sname = sc.get("name", "")
        for t in sc.get("tables", []):
            tname = t.get("table_name", t.get("name", ""))
            tables.add((sname, tname)); table_names.add(tname)
            for c in t.get("columns", []):
                cname = c.get("name", "")
                cols.add((sname, tname, cname)); col_by_table.add((tname, cname))
    _INDEX_CACHE[key] = {"exists": True, "cols": cols, "tables": tables,
                         "table_names": table_names, "col_by_table": col_by_table}
    return _INDEX_CACHE[key]


class _Resolver:
    def __init__(self):
        self.sources_dir, self.targets_dir = _project_paths()
        self._cache: dict[tuple[str, str], dict] = {}

    def _idx(self, kind: str, dataset: str) -> dict:
        key = (kind, dataset)
        if key not in self._cache:
            base = self.sources_dir if kind == "source" else self.targets_dir
            self._cache[key] = _build_index(base / f"{dataset}.yaml")
        return self._cache[key]

    def resolve(self, kind: str, dataset: str, segs: list[str]) -> tuple[bool, str]:
        if kind not in ("source", "target"):
            return False, f"unknown kind '{kind}'"
        idx = self._idx(kind, dataset)
        if not idx.get("exists"):
            return False, f"catalog '{dataset}.yaml' not found"
        g = _granularity(segs)
        if g == "column":
            schema, table, col = segs[0], segs[1], ".".join(segs[2:])
            if (schema, table, col) in idx["cols"] or (table, col) in idx["col_by_table"]:
                return True, ""
            return False, "table not found" if table not in idx["table_names"] else "column not found"
        if g == "table":
            schema, table = segs[0], segs[1]
            if (schema, table) in idx["tables"] or table in idx["table_names"]:
                return True, ""
            return False, "table not found"
        return True, ""  # dataset-level: catalog exists

    def total_source_columns(self) -> int:
        total = 0
        for f in sorted(self.sources_dir.glob("*.yaml")):
            if f.name.endswith(".annotations.yaml"):
                continue
            idx = _build_index(f)
            total += len(idx.get("cols", set())) if idx.get("exists") else 0
        return total


# ── report ────────────────────────────────────────────────────────────────────

@dataclass
class MigrationReport:
    terms_in: int = 0
    terms_out: int = 0
    domains_in: int = 0
    domains_out: int = 0
    categories_in: int = 0
    categories_out: int = 0
    synonyms_in: int = 0
    synonyms_out: int = 0
    tags_in: int = 0
    tags_out: int = 0
    gran: Counter = field(default_factory=Counter)           # e.g. 'source/column/resolved'
    triage_by_reason: Counter = field(default_factory=Counter)
    distinct_source_columns: int = 0
    total_source_columns: int = 0
    status_before: Counter = field(default_factory=Counter)
    status_after: Counter = field(default_factory=Counter)
    status_changed: list = field(default_factory=list)       # (slug, old, new)
    dq_changed: list = field(default_factory=list)           # (slug, old, new)
    validation_mismatches: list = field(default_factory=list)

    def render(self) -> str:
        lines = ["=" * 72, "GLOSSARY YAML -> POSTGRES MIGRATION REPORT", "=" * 72]
        lines.append(f"terms:       in={self.terms_in}  out={self.terms_out}")
        lines.append(f"domains:     in={self.domains_in}  out={self.domains_out}")
        lines.append(f"categories:  in={self.categories_in}  out={self.categories_out}")
        lines.append(f"synonyms:    in={self.synonyms_in}  out={self.synonyms_out}")
        lines.append(f"tags:        in={self.tags_in}  out={self.tags_out}")
        lines.append("")
        lines.append("linkage granularity (kind/granularity/status -> count):")
        for k in sorted(self.gran):
            lines.append(f"  {k:40s} {self.gran[k]}")
        lines.append("")
        cov = (100.0 * self.distinct_source_columns / self.total_source_columns
               if self.total_source_columns else 0.0)
        lines.append(f"column-level coverage: {self.distinct_source_columns}/"
                     f"{self.total_source_columns} = {cov:.1f}%")
        lines.append("")
        lines.append("triage (unresolvable catalog refs) by reason:")
        for r in sorted(self.triage_by_reason):
            lines.append(f"  {r:45s} {self.triage_by_reason[r]}")
        lines.append(f"  TOTAL triaged: {sum(self.triage_by_reason.values())}")
        lines.append("")
        lines.append(f"status before canonicalisation: {dict(self.status_before)}")
        lines.append(f"status after  canonicalisation: {dict(self.status_after)}")
        lines.append(f"terms whose status changed: {len(self.status_changed)}")
        for slug, o, n in self.status_changed[:20]:
            lines.append(f"  {slug}: {o} -> {n}")
        lines.append(f"terms whose DQ contribution changed: {len(self.dq_changed)}")
        for slug, o, n in self.dq_changed[:20]:
            lines.append(f"  {slug}: {o} -> {n}")
        lines.append("")
        if self.validation_mismatches:
            lines.append("!! VALIDATION vs Phase-1a profile FAILED:")
            for m in self.validation_mismatches:
                lines.append(f"  {m}")
        else:
            lines.append("validation vs Phase-1a profile: PASS (all counts match)")
        lines.append("=" * 72)
        return "\n".join(lines)


def _dq_bucket(status: str) -> tuple[int, bool]:
    s = (status or "").strip().lower()
    return _DQ_BONUS.get(s, 0), s in _BOOST


# ── migration ──────────────────────────────────────────────────────────────────

_GLOSSARY_TABLES = ("linkage_triage", "glossary_group_meta", "linkage", "term_relation",
                    "term_version", "term", "lifecycle_transition", "glossary")


def _load_yaml_terms() -> list[dict]:
    from agents.glossary_agent import GlossaryTerm
    with GLOSSARY_YAML.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return [GlossaryTerm.from_dict(t).to_dict() for t in data.get("terms", [])]


def run_migration(session: Session, *, force: bool = False) -> MigrationReport:
    existing = session.execute(select(func.count()).select_from(Term)).scalar_one()
    if existing and not force:
        raise SystemExit(f"Refusing to migrate: {existing} terms already present. Use --force to overwrite.")
    session.execute(text(f"TRUNCATE {', '.join(_GLOSSARY_TABLES)} RESTART IDENTITY CASCADE"))

    terms = _load_yaml_terms()
    resolver = _Resolver()
    rep = MigrationReport()
    rep.terms_in = len(terms)

    g = Glossary(key="business", name="Business Glossary")
    session.add(g)
    session.flush()

    domains, categories = set(), set()
    linked_source_cols: set[tuple[str, str, str]] = set()

    for d in terms:
        old_status = (d.get("status") or "draft")
        new_status = _canon(old_status)
        rep.status_before[old_status.strip().lower()] += 1
        rep.status_after[new_status] += 1
        if old_status.strip().lower() != new_status:
            rep.status_changed.append((d["id"], old_status, new_status))
        old_dq, old_boost = _dq_bucket(old_status)
        new_dq, new_boost = _dq_bucket(new_status)
        if (old_dq, old_boost) != (new_dq, new_boost):
            rep.dq_changed.append((d["id"], old_status, new_status))

        if d.get("domain"):
            domains.add(d["domain"])
        if d.get("category"):
            categories.add(d["category"])
        rep.synonyms_in += len(d.get("synonyms") or [])
        rep.tags_in += len(d.get("tags") or [])

        approved = new_status == "approved"
        last_updated = _parse_dt(d.get("last_updated"))
        term = Term(
            glossary_id=g.id, slug=d["id"], domain=d.get("domain") or None,
            category=d.get("category") or None, steward=d.get("steward") or None,
            status=new_status, last_reviewed=_parse_dt(d.get("last_reviewed")),
            updated_at=last_updated or _now(),
        )
        session.add(term)
        session.flush()

        session.add(TermVersion(
            term_id=term.id, version_no=1, title=d.get("title") or "",
            business_description=d.get("business_description") or None,
            detailed_description=d.get("detailed_description") or None,
            synonyms=list(d.get("synonyms") or []), tags=list(d.get("tags") or []),
            ai_generated_fields=list(d.get("ai_generated_fields") or []),
            attributes={"crr3_context": d.get("CRR_context") or "",
                        "dpm2_context": d.get("DPM_context") or ""},
            status="approved" if approved else "draft", is_current_approved=approved,
            valid_from=last_updated,
        ))
        session.add(LifecycleTransition(
            subject_type="glossary_term", subject_ref=d["id"],
            from_status=None, to_status=new_status, actor="migration",
        ))

        for ref in d.get("related_objects") or []:
            parsed = _parse_ref(ref)
            if parsed and parsed[0] in ("source", "target"):
                kind, dataset, segs = parsed
                gran = _granularity(segs)
                ok, reason = resolver.resolve(kind, dataset, segs)
                rep.gran[f"{kind}/{gran}/{'resolved' if ok else 'unresolved'}"] += 1
                schema = segs[0] if segs else None
                table = segs[1] if len(segs) >= 2 else None
                column = ".".join(segs[2:]) if len(segs) >= 3 else None
                session.add(Linkage(
                    term_id=term.id, kind=kind, granularity=gran, dataset=dataset,
                    schema_name=schema, table_name=table, column_name=column,
                    raw_ref=ref, status="active" if ok else "stale",
                    origin="migrated", resolved=ok,
                ))
                if ok and kind == "source" and gran == "column":
                    linked_source_cols.add((schema, table, column))
                if not ok:
                    rep.triage_by_reason[f"{kind}/{gran}: {reason}"] += 1
                    session.add(LinkageTriage(
                        term_slug=d["id"], raw_ref=ref, kind=kind, dataset=dataset, reason=reason,
                    ))
            else:
                rep.gran["free_text"] += 1
                session.add(TermRelation(from_term_id=term.id, relation_type="related", to_label=ref))

    # glossary_meta.yaml -> glossary_group_meta
    if GLOSSARY_META.exists():
        with GLOSSARY_META.open(encoding="utf-8") as fh:
            meta = yaml.safe_load(fh) or {}
        for gtype, singular in (("domains", "domain"), ("categories", "category")):
            for name, desc in (meta.get(gtype) or {}).items():
                session.add(GlossaryGroupMeta(
                    glossary_id=g.id, group_type=singular, name=name, description=desc,
                ))
    session.flush()

    # ── totals / coverage ──
    rep.domains_in = len(domains)
    rep.categories_in = len(categories)
    rep.terms_out = session.execute(select(func.count()).select_from(Term)).scalar_one()
    rep.domains_out = session.execute(
        select(func.count(func.distinct(Term.domain))).where(Term.domain.isnot(None))).scalar_one()
    rep.categories_out = session.execute(
        select(func.count(func.distinct(Term.category))).where(Term.category.isnot(None))).scalar_one()
    rep.synonyms_out = sum(
        len(v.synonyms or []) for v in session.execute(select(TermVersion)).scalars())
    rep.tags_out = sum(
        len(v.tags or []) for v in session.execute(select(TermVersion)).scalars())
    rep.distinct_source_columns = len(linked_source_cols)
    rep.total_source_columns = resolver.total_source_columns()

    _validate_against_1a(rep)
    return rep


def _validate_against_1a(rep: MigrationReport) -> None:
    src_col = rep.gran["source/column/resolved"] + rep.gran["source/column/unresolved"]
    src_tbl = rep.gran["source/table/resolved"] + rep.gran["source/table/unresolved"]
    tgt_col = rep.gran["target/column/resolved"] + rep.gran["target/column/unresolved"]
    tgt_tbl = rep.gran["target/table/resolved"] + rep.gran["target/table/unresolved"]
    actual = {
        "source_column": src_col, "source_table": src_tbl,
        "target_column": tgt_col, "target_table": tgt_tbl,
        "free_text": rep.gran["free_text"],
        "source_column_resolved": rep.gran["source/column/resolved"],
        "source_column_unresolved": rep.gran["source/column/unresolved"],
        "source_table_resolved": rep.gran["source/table/resolved"],
        "source_table_unresolved": rep.gran["source/table/unresolved"],
        "target_table_resolved": rep.gran["target/table/resolved"],
        "target_column_unresolved": rep.gran["target/column/unresolved"],
        "distinct_source_columns": rep.distinct_source_columns,
        "total_source_columns": rep.total_source_columns,
        "terms": rep.terms_in,
    }
    for key, exp in EXPECTED_1A.items():
        if key == "terms_with_ref":
            continue
        if actual.get(key) != exp:
            rep.validation_mismatches.append(f"{key}: expected {exp}, got {actual.get(key)}")


# ── parity harness ─────────────────────────────────────────────────────────────

_PARITY_FIELDS = ("domain", "category", "title", "business_description", "detailed_description",
                  "steward", "status", "CRR_context", "DPM_context")
_PARITY_LISTS = ("synonyms", "tags", "ai_generated_fields", "related_objects")


def parity_check(session: Session) -> list[str]:
    """Field-by-field YAML vs Postgres for all terms. Returns a list of divergences.

    status is compared through the canonical mapping (YAML 'retired' == PG 'deprecated').
    related_objects is compared as a set (order not preserved by design; contents must match).
    """
    repo = GlossaryRepository(session)
    yaml_terms = {d["id"]: d for d in _load_yaml_terms()}
    div: list[str] = []
    for slug, y in yaml_terms.items():
        p = repo.get_term(slug)
        if p is None:
            div.append(f"{slug}: MISSING in Postgres")
            continue
        for f in _PARITY_FIELDS:
            yv = _canon(y.get(f)) if f == "status" else (y.get(f) or "")
            pv = p.get(f) or ""
            if yv != pv:
                div.append(f"{slug}.{f}: yaml={yv!r} pg={pv!r}")
        for f in _PARITY_LISTS:
            if set(y.get(f) or []) != set(p.get(f) or []):
                div.append(f"{slug}.{f}: yaml={sorted(y.get(f) or [])} pg={sorted(p.get(f) or [])}")
    return div


def main() -> None:
    ap = argparse.ArgumentParser(description="Migrate glossary.yaml into PostgreSQL")
    ap.add_argument("--force", action="store_true", help="overwrite a non-empty store")
    args = ap.parse_args()

    with gdb.session_scope() as session:
        rep = run_migration(session, force=args.force)
    print(rep.render())

    out = _ROOT / "docs" / "architecture" / "Glossary Rebuild" / "reports" / "03-migration-stats.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(rep.render(), encoding="utf-8")
    print(f"\nreport written to {out}")

    with gdb.session_scope() as session:
        div = parity_check(session)
    if div:
        print(f"\nPARITY: {len(div)} divergence(s):")
        for d in div[:50]:
            print("  " + d)
    else:
        print("\nPARITY: PASS — all terms field-for-field identical (related_objects as set).")


if __name__ == "__main__":
    main()

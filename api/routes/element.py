"""Element workspace API — aggregated view of a single source column.

GET  /element/{source}/{table}/{column}       → full element view
PATCH /element/{source}/{table}/{column}/state → lifecycle state change
GET  /element/{source}/tables                 → all tables in a source catalog
"""
from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Callable, Optional

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.deps import get_paths, get_audit_store, get_element_state, get_semantic_type_store, get_dq_service, get_connections, get_reference_set_store, get_reference_code_repo, get_reference_binding_review_repo
from api.llm_errors import format_llm_error
from api.sse_utils import format_sse, stream_with_progress
from core.assessment import assess_table
from core.audit import AuditStore
from core.audit import events as audit_events
from core.element_state import ASSESSMENT_SCOPE_VALUES, ElementStateStore, LifecycleState
from core.element_lifecycle_repo import element_backend
from core.reference_code_repo import (
    ReferenceCodeRepo, derive_set_status, make_key as _refdata_key, refdata_backend, set_badge,
)
from core.governance_events import emit as emit_governance_event
from core.catalog import load_catalog_dispatch
from core.dq_service import DQProgressStatus
from core.semantic_resolver import ColumnProgressStatus, SemanticResolver, domain_role_to_legacy_bucket, normalise_type_id
from core.semantic_type_store import SemanticTypeStore
from core.catalog_db import is_profiled
router = APIRouter(prefix="/element", tags=["element"])
logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent.parent
_GLOSSARY_PATH = _ROOT / "glossary" / "glossary.yaml"
_GLOSSARY_INDEX_CACHE: dict[str, dict] | None = None  # related_object -> term, parsed once
_GLOSSARY_CACHE_MTIME: float | None = None  # glossary.yaml mtime the cache was built from
_PG_INDEX_CACHE: dict[str, dict] | None = None  # related_object -> term (postgres backend)
_PG_INDEX_TS: float = 0.0  # monotonic time the pg index was built
_PG_INDEX_TTL: float = 5.0  # seconds a pg-built index is reused (bursty scoring runs)

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ── helpers ──────────────────────────────────────────────────────────────────

# Canonical statuses map to 5 display buckets. Legacy yaml states (initiated/saved/defined)
# are normalised so old data doesn't need migrating.
_GOV_DISPLAY_BUCKET = {
    "empty": "empty", "initiated": "empty",
    "draft": "draft", "saved": "draft", "defined": "draft",
    "in_review": "in_review",
    "returned": "bounced", "rejected": "bounced", "withdrawn": "bounced", "revoked": "bounced",
    "approved": "approved",
}


def _gov_display_bucket(state: str) -> str:
    """Fold a canonical or legacy lifecycle status into one of five display buckets."""
    return _GOV_DISPLAY_BUCKET.get(state, "draft")

_GOV_BUCKET_ZERO: dict[str, int] = {"empty": 0, "draft": 0, "in_review": 0, "approved": 0, "bounced": 0}


# Canonical lifecycle bucketing for the governance-summary coverage card (5b.3.2):
# empty / draft / in_review / approved — matches the canonical ladder, unlike the
# legacy Draft/Defined/Approved buckets above (still used by the Asset Workspace
# governance bars + semantic×governance matrix, pending their own visual pass).
_CANONICAL_GOV_BUCKET = {
    "empty": "empty", "initiated": "empty",
    "draft": "draft", "saved": "draft", "defined": "draft",
    "returned": "draft", "rejected": "draft", "withdrawn": "draft", "revoked": "draft",
    "in_review": "in_review",
    "approved": "approved",
}


def _canonical_gov_bucket(state: str) -> str:
    """Fold a lifecycle status into the canonical Empty/Draft/In-Review/Approved bucket."""
    return _CANONICAL_GOV_BUCKET.get(state, "draft")


def _load_source_catalog(sources_dir: Path, source: str) -> dict:
    path = sources_dir / f"{source}.yaml"
    # Shared mtime-cached loader (also used by the startup pre-warm + insights/catalogs
    # routes): a large catalog is parsed once and every route reads the same warm copy.
    # The cache self-invalidates when the catalog or its annotations overlay changes on
    # disk, so profile refreshes / bulk rebuilds are picked up on the very next request.
    # Respects catalog_backend (Phase 6) — in postgres mode there's no on-disk file to
    # gate on, so 404 is decided from the dispatched result, not path.exists().
    catalog = load_catalog_dispatch(path)
    if not catalog:
        raise HTTPException(status_code=404, detail=f"Source catalog '{source}' not found")
    return catalog


def _resolve_table_column(
    catalog: dict, table: str, column: str, schema: Optional[str] = None
) -> tuple[dict, str, dict] | None:
    """Return (column_dict, schema_name, table_dict) or None."""
    for sc in catalog.get("schemas", []):
        if schema and sc.get("name") != schema:
            continue
        for tbl in sc.get("tables", []):
            if tbl.get("table_name") != table:
                continue
            for col in tbl.get("columns", []):
                if col.get("name") == column:
                    return col, sc.get("name", ""), tbl
    return None


# Connector type → steward-readable label for the source-info connection panel.
_CONNECTION_TYPE_LABELS = {
    "duckdb": "DuckDB (embedded)",
    "yaml": "YAML catalog",
}


def _find_connection_config(connections: dict, connection_id: str) -> dict | None:
    """Look up a named entry in the parsed ``connections.yaml`` (real config,
    not a guess) so the source-info panel can show the actual connector type,
    database/file, scoped schemas and read-only flag instead of hardcoded
    placeholders.
    """
    for cfg in (connections or {}).get("connections", []):
        if cfg.get("name") == connection_id:
            return cfg
    return None


def _find_glossary_term(source: str, schema: str, table: str, column: str) -> dict | None:
    # related_objects format: "source|{dataset}|{schema}.{table}.{column}".
    # Uses the mtime-cached index so scoring a whole source never re-parses the
    # glossary file once per column (it previously opened+parsed it every call).
    index = _glossary_related_index()
    for key in (
        f"source|{source}|{schema}.{table}.{column}",
        f"source|{source}|{table}.{column}",
    ):
        term = index.get(key)
        if term is not None:
            return term
    return None


# Glossary term statuses that count as confirmed (mirror the DQ scorer / element
# detail). Anything else (draft/proposed) is pending Steward review.
from core.glossary_db.status import CONFIRMED_STATUSES as _GLOSSARY_CONFIRMED_STATUSES


def _glossary_related_index() -> dict[str, dict]:
    """Map every related_object string to its glossary term (backend-aware, cached).

    Postgres backend: built from the repository and reused for a short TTL so a
    per-column lookup (DQ scoring a whole source) never round-trips the DB per column.
    YAML backend: parsed once and reused until the file's mtime changes.
    """
    from core.glossary_db.db import backend
    if backend() == "postgres":
        global _PG_INDEX_CACHE, _PG_INDEX_TS
        import time
        now = time.monotonic()
        if _PG_INDEX_CACHE is not None and (now - _PG_INDEX_TS) < _PG_INDEX_TTL:
            return _PG_INDEX_CACHE
        from core.glossary_db.read_api import glossary_terms
        index: dict[str, dict] = {}
        for term in glossary_terms():
            for ro in term.get("related_objects") or []:
                index.setdefault(ro, term)
        _PG_INDEX_CACHE = index
        _PG_INDEX_TS = now
        return index

    global _GLOSSARY_INDEX_CACHE, _GLOSSARY_CACHE_MTIME
    if not _GLOSSARY_PATH.exists():
        return {}
    mtime = _GLOSSARY_PATH.stat().st_mtime
    if _GLOSSARY_INDEX_CACHE is not None and _GLOSSARY_CACHE_MTIME == mtime:
        return _GLOSSARY_INDEX_CACHE
    with _GLOSSARY_PATH.open(encoding="utf-8") as fh:
        gl = yaml.safe_load(fh) or {}
    index = {}
    for term in gl.get("terms", []):
        for ro in term.get("related_objects") or []:
            index.setdefault(ro, term)
    _GLOSSARY_INDEX_CACHE = index
    _GLOSSARY_CACHE_MTIME = mtime
    return index


# Mapping result files are parsed once and reused until their mtime changes — the
# element view was re-reading + re-parsing every file in mappings/results/ on EVERY
# column click (measured ~3s/click). Keyed by path; invalidated when a file is rewritten.
_MAPPING_FILE_CACHE: dict[str, tuple[float, dict]] = {}

#: Minimum mapping-candidate confidence surfaced on the Mapping tab, as a PERCENTAGE
#: (app convention — confidence is always expressed in %, never a 0-1 decimal).
_MIN_MAPPING_CONFIDENCE_PCT = 80


def _load_mapping_file(mp: Path) -> dict:
    mtime = mp.stat().st_mtime
    cached = _MAPPING_FILE_CACHE.get(str(mp))
    if cached is not None and cached[0] == mtime:
        return cached[1]
    with mp.open(encoding="utf-8") as fh:
        parsed = yaml.safe_load(fh) or {}
    _MAPPING_FILE_CACHE[str(mp)] = (mtime, parsed)
    return parsed


def _find_mapping_candidates(
    mappings_dir: Path, source: str, schema: str, table: str, column: str
) -> list[dict]:
    if not mappings_dir.exists():
        return []
    candidates: list[dict] = []
    for mp in sorted(mappings_dir.glob("*.yaml")):
        mapping = _load_mapping_file(mp)
        if mapping.get("source") != source:
            continue
        for tbl_map in mapping.get("tables", []):
            for col_map in tbl_map.get("columns", []):
                if (
                    (col_map.get("source_schema") or "") == schema
                    and col_map.get("source_table") == table
                    and col_map.get("source_column") == column
                ):
                    # Surface only high-confidence candidates (>= 80%). App convention:
                    # confidence is expressed as a PERCENTAGE, never a 0-1 decimal — the
                    # stored value is 0-1, so scale to % before thresholding at 80.
                    conf_pct = (col_map.get("confidence") or 0) * 100
                    if conf_pct < _MIN_MAPPING_CONFIDENCE_PCT:
                        continue
                    candidates.append({
                        "target": mapping.get("target"),
                        "target_schema": tbl_map.get("target_schema"),
                        "target_table": tbl_map.get("target_table"),
                        "target_framework": tbl_map.get("target_framework"),
                        "target_column": col_map.get("target_column"),
                        "confidence": col_map.get("confidence"),
                        "rationale": col_map.get("rationale") or "",
                        "transformation_type": col_map.get("transformation_type") or "",
                        "status": col_map.get("status") or "",
                        "notes": col_map.get("notes") or "",
                    })
    return candidates


# ── helpers ──────────────────────────────────────────────────────────────────

def _default_business_name(column: str) -> str:
    """Derive a Title Case business name from a snake_case technical column name."""
    return " ".join(w.capitalize() for w in column.replace("-", "_").split("_") if w)


def _store_type_id(store: SemanticTypeStore, source: str, schema: str | None, table: str, column: str) -> str:
    rec = store.get(source, schema, table, column)
    return normalise_type_id(rec.get("type_id")) if rec else "unresolved"


_RESOLVER_SINGLETON: SemanticResolver | None = None


def _get_resolver(semantic_store: SemanticTypeStore) -> SemanticResolver:
    """Return a module-level resolver reusing the shared vocabulary and store."""
    global _RESOLVER_SINGLETON
    if _RESOLVER_SINGLETON is None or _RESOLVER_SINGLETON.store is not semantic_store:
        _RESOLVER_SINGLETON = SemanticResolver(store=semantic_store)
    return _RESOLVER_SINGLETON


def _resolve_table_once(
    *,
    source: str,
    schema: str | None,
    table_dict: dict,
    semantic_store: SemanticTypeStore,
    progress_cb: Callable[[int, int, str, ColumnProgressStatus], None] | None = None,
) -> dict[str, dict]:
    """Resolve all columns for a table and return a dict keyed by column name.

    Handles fingerprinting internally — only re-resolves columns whose profile
    has changed. Accepted records are never overwritten.
    """
    resolver = _get_resolver(semantic_store)
    result = resolver.resolve_table(
        source=source,
        schema=schema,
        table=table_dict,
        include_ai=False,
        persist=True,
        progress_cb=progress_cb,
    )
    return {rec.get("key", "").split("|")[-1]: rec for rec in result["columns"]}


def _store_bucket_for_column(
    source: str,
    schema: str | None,
    table: str,
    column_name: str,
    semantic_store: SemanticTypeStore,
) -> str:
    """Read from store only — no auto-resolve. Fast path for aggregated views."""
    record = semantic_store.get(source, schema, table, column_name)
    return domain_role_to_legacy_bucket(record.get("domain_role") if record else None)


def _heuristic_bucket(col: dict) -> str:
    """Lightweight heuristic fallback — mirrors the original _infer_semantic_type logic.
    Used for chart computation when a column has not yet been resolved by the store.
    """
    dtype = (col.get("data_type") or "").upper()
    pattern = col.get("inferred_pattern") or ""
    name = col.get("name", "").lower()
    distinct = col.get("distinct_count") or 0
    row_count = col.get("row_count") or 1
    if "IBAN" in pattern or "LEI" in pattern or "UUID" in pattern:
        return "identifier"
    if "DATE" in dtype or "TIME" in dtype:
        return "date"
    if any(x in dtype for x in ("DECIMAL", "NUMERIC", "FLOAT", "DOUBLE")):
        if any(x in name for x in ("amt", "amount", "balance", "bal", "rate", "pct")):
            return "monetary"
        return "other"
    if "INT" in dtype and distinct <= 50:
        return "coded"
    if any(x in dtype for x in ("VARCHAR", "CHAR", "TEXT")):
        if distinct <= 50 and row_count > 100:
            return "coded"
        if name.endswith("_id") or name.endswith("id"):
            return "identifier"
    return "other"


def _column_pii(col_record: dict | None, catalog_col: dict | None) -> bool:
    """True when a column is PII by either signal: the governed semantic type
    (vocabulary ``is_pii``) or the profiler's value-pattern (``inferred_pattern == 'PII'``).

    A business ID (e.g. Y-Tunnus) is never eligible here at all — the profiler tags it
    ``BUSINESS_ID``, a distinct pattern name from ``PII`` (Henkilötunnus, a real person's
    ID), so it structurally never matches this check. Nothing to do with semantic-type
    detection/acceptance/submission — the exclusion happens at profiling time, not here."""
    if (col_record or {}).get("pii"):
        return True
    return (catalog_col or {}).get("inferred_pattern") == "PII"


def _column_pii_category(col_record: dict | None, catalog_col: dict | None) -> str | None:
    cat = (col_record or {}).get("pii_category")
    if cat:
        return cat
    if (catalog_col or {}).get("inferred_pattern") == "PII":
        return "personal_identity"
    return None


def _semantic_display_state(col_record: dict | None) -> str:
    """Derived, display-only semantic-type disposition: 'unresolved' | 'pending' | 'accepted'.

    Replaces the retired persisted ``state`` word (2026-08-20, tech-debt #13/#36/#45) — the only
    real axes left are ``type_id`` (unresolved or a real governed type) and ``accepted_at``
    (whether a person has accepted it). Collapses the old proposed/suggested split into one
    'pending' bucket, since nothing on the frontend ever distinguished them beyond a cosmetic
    word in one tooltip.
    """
    rec = col_record or {}
    type_id = rec.get("type_id") or "unresolved"
    if type_id == "unresolved":
        return "unresolved"
    return "accepted" if rec.get("accepted_at") else "pending"


def _semantic_state_counts(
    semantic_store: SemanticTypeStore, source: str, column_count: int
) -> dict[str, int]:
    """Source-wide accepted/pending/unresolved tally for the Dashboard's own card.

    One bulk query; columns that have never been resolved have no row at all, so they are
    added to ``unresolved`` here against the catalog's real column count.
    """
    try:
        counts = semantic_store.semantic_states_for_source(source)
    except Exception:
        return {"accepted": 0, "pending": 0, "unresolved": column_count}
    tallied = counts["accepted"] + counts["pending"] + counts["unresolved"]
    counts["unresolved"] += max(0, column_count - tallied)
    return counts


# Un-collapsed labels for the source-level semantic-type charts. The legacy
# 5-bucket mapping (`domain_role_to_legacy_bucket`) folds name/address/text/
# technical/unresolved all into one "other" catch-all, which hides real
# distinctions the resolver already knows. This keeps every governed domain
# role (and the heuristic fallback's own guesses) as its own category.
_HEURISTIC_TO_DOMAIN_ROLE_LABEL = {
    "identifier": "surrogate_id",   # ambiguous identifier-shaped columns default to Surrogate ID
    "coded": "code",
    "date": "temporal",
    "monetary": "measure",
    "other": "unresolved",
}

# Legacy domain_role values persisted on confirmed records before the Natural/
# Surrogate split. Normalised at read time so charts group them under the new
# domains without a data migration ("key" stays a tag; plain "identifier" -> surrogate).
_LEGACY_DOMAIN_ROLE_NORMALISE = {"identifier": "surrogate_id"}


def _hybrid_domain_role(
    source: str,
    schema: str | None,
    table: str,
    col: dict,
    semantic_store: SemanticTypeStore,
) -> str:
    """Real semantic-type domain: store-backed domain_role when resolved
    (natural_id/surrogate_id/key/code/temporal/measure/rate/name/address/text/
    technical), the heuristic guess (relabelled to match) otherwise. Never
    collapses everything unresolved/descriptive into a single "other" bucket.
    """
    record = semantic_store.get(source, schema, table, col.get("name", ""))
    if record:
        dr = record.get("domain_role") or "unresolved"
        return _LEGACY_DOMAIN_ROLE_NORMALISE.get(dr, dr)
    return _HEURISTIC_TO_DOMAIN_ROLE_LABEL.get(_heuristic_bucket(col), "unresolved")


def _hybrid_domain_role_from_map(key: str, col: dict, domain_roles: dict[str, str]) -> str:
    """Same logic as ``_hybrid_domain_role``, fed from a bulk-fetched ``{key: domain_role}``
    map (``SemanticTypeStore.domain_roles_for_source``) instead of one store read per column
    -- used by the Source Profile page's aggregation loop, which scans every column across
    every table in a source (found live 2026-08-14: ~1,900 individual reads for a large
    source dominated that page's load time).
    """
    dr = domain_roles.get(key)
    if dr is not None:
        dr = dr or "unresolved"
        return _LEGACY_DOMAIN_ROLE_NORMALISE.get(dr, dr)
    return _HEURISTIC_TO_DOMAIN_ROLE_LABEL.get(_heuristic_bucket(col), "unresolved")


def _dq_badge_view(record: dict | None, *, full: bool) -> dict | None:
    """Shape a persisted DQ record (core.dq_score_store) for the API.

    ``full`` returns the whole breakdown (component line-items + evidence) for
    the element card; the compact form (score + band + data·governance split)
    is enough for the rail/grid badges. Un-scored columns (out-of-scope, empty)
    return their ``state``/``reason`` so the UI can show a neutral placeholder.
    """
    if not record:
        return None
    state = record.get("state")
    if state != "scored":
        return {"state": state or "unscored", "reason": record.get("reason")}
    compact = {
        "state": "scored",
        "dq_score": record.get("dq_score"),
        "grade_label": record.get("grade_label"),
        "grade_color_intent": record.get("grade_color_intent"),
        "data_score": record.get("data_score"),
        "governance_score": record.get("governance_score"),
        "archetype": record.get("archetype"),
        # Count-only (not the full actions list) so the compact form used by
        # columns_summary rows stays light while still surfacing "how many
        # improvement actions" — e.g. the dataset roll-up's "columns dragging
        # the score down" list reads this straight off the element-level badge.
        "action_count": len(record.get("actions") or []),
    }
    if not full:
        return compact
    compact.update({
        "archetype_reason": record.get("archetype_reason"),
        "applicable_components": record.get("applicable_components"),
        "inapplicable_components": record.get("inapplicable_components"),
        "reallocation_factor": record.get("reallocation_factor"),
        "model_version": record.get("model_version"),
        "scored_at": record.get("scored_at"),
        "components": record.get("components"),
        "actions": record.get("actions"),
        "path_to_next_grade": record.get("path_to_next_grade"),
    })
    return compact


def _dq_badge(
    dq_service,
    source: str,
    schema: str | None,
    table: str,
    column: str,
    *,
    full: bool = False,
) -> dict | None:
    """Read the stored DQ badge, scoring on first view (U2b Task 1).

    Never recomputes on every read: the service serves the persisted record
    and only scores-and-persists the first time a column is viewed unscored.
    Returns ``None`` when DQ scoring is unavailable (guarded startup failure).
    """
    if dq_service is None:
        return None
    try:
        record = dq_service.get_or_score(source, schema, table, column)
    except Exception:
        return None
    return _dq_badge_view(record, full=full)


def _dataset_dq_badge_view(record: dict | None, *, full: bool) -> dict | None:
    """Shape a persisted dataset DQ record (§15) for the API.

    ``full`` returns the whole roll-up (column contributions + integrity
    line-items) for the dataset card; the compact form (score + band + profile)
    is enough for a header chip. Un-scored datasets (fully-descoped, no scored
    columns) return their ``state``/``reason`` for a neutral placeholder.
    """
    if not record:
        return None
    state = record.get("state")
    if state != "scored":
        return {"state": state or "unscored", "reason": record.get("reason")}
    compact = {
        "state": "scored",
        "dq_score": record.get("dq_score"),
        "grade_label": record.get("grade_label"),
        "grade_color_intent": record.get("grade_color_intent"),
        "integrity_profile": record.get("integrity_profile"),
        "column_count": record.get("column_count"),
    }
    if not full:
        return compact
    compact.update({
        "applicable_components": record.get("applicable_components"),
        "reallocation_factor": record.get("reallocation_factor"),
        "model_version": record.get("model_version"),
        "scored_at": record.get("scored_at"),
        "components": record.get("components"),
    })
    return compact


def _dataset_dq_badge(
    dq_service,
    source: str,
    schema: str | None,
    table: str,
    *,
    full: bool = False,
    with_trend: bool = False,
) -> dict | None:
    """Read the stored dataset DQ badge, rolling up on first view (§15).

    Optionally attaches a ``trend`` list (chronological score history) for the
    sparkline. Returns ``None`` when DQ scoring is unavailable.
    """
    if dq_service is None:
        return None
    try:
        record = dq_service.get_or_score_dataset(source, schema, table)
    except Exception:
        return None
    view = _dataset_dq_badge_view(record, full=full)
    if view is None:
        return None
    if with_trend:
        try:
            history = dq_service.dataset_history(source, schema, table)
        except Exception:
            history = []
        view["trend"] = [
            {"dq_score": h.get("dq_score"), "scored_at": h.get("scored_at"),
             "state": h.get("state")}
            for h in history
        ]
    return view


# ── routes ───────────────────────────────────────────────────────────────────

@router.get("/{source}/tables")
async def list_tables(
    source: str,
    paths: dict = Depends(get_paths),
    element_state: ElementStateStore = Depends(get_element_state),
    dq_service=Depends(get_dq_service),
    semantic_store: SemanticTypeStore = Depends(get_semantic_type_store),
):
    """Return all schemas+tables (with columns) for a source catalog."""
    catalog = _load_source_catalog(paths["sources"], source)
    result = []
    glossary_index = _glossary_related_index()
    all_items = [
        (sc.get("name", ""), tbl.get("table_name", ""), c.get("name"))
        for sc in catalog.get("schemas", [])
        for tbl in sc.get("tables", [])
        for c in tbl.get("columns", [])
    ]
    # One atomic write for the ENTIRE source scan: the bulk DQ read/score-on-first-view
    # below and the per-table dataset warms further down both nest inside this single
    # batch (nested batches coalesce), so scoring a whole source writes the scores file
    # once instead of once per table/column.
    scoring_batch = dq_service.batch() if dq_service is not None else nullcontext()
    with scoring_batch:
        # Bulk-fetch/score every column's DQ record for the whole source in ONE query,
        # instead of one Postgres round-trip per column (measured: ~20ms/column, e.g.
        # 39s for ALM Bank's 1,910 columns).
        dq_by_item = dq_service.get_or_score_many(source, all_items) if dq_service is not None else {}
        for sc in catalog.get("schemas", []):
            for tbl in sc.get("tables", []):
                try:
                    assessment = assess_table(tbl, include_ai=False)
                    all_findings = assessment.get("findings", [])
                except Exception:
                    all_findings = []

                finding_counts: dict[str, int] = {}
                for f in all_findings:
                    t = f.get("target", "")
                    finding_counts[t] = finding_counts.get(t, 0) + 1

                schema_name = sc.get("name", "")
                # Warm the whole table's DQ scores in one batched write: this scores
                # every column + the dataset roll-up with a single file save, so the
                # per-column dq_by_item lookups below are all cache hits (no per-column
                # writes). A cheap no-op once the table is already scored.
                if dq_service is not None:
                    dq_service.get_or_score_dataset(source, schema_name, tbl.get("table_name", ""))
                columns = []
                for c in tbl.get("columns", []):
                    col_name = c.get("name")
                    fc = finding_counts.get(col_name, 0)
                    lifecycle_state = element_state.get(source, schema_name, tbl.get("table_name", ""), col_name)
                    gl_term = (
                        glossary_index.get(f"source|{source}|{schema_name}.{tbl.get('table_name', '')}.{col_name}")
                        or glossary_index.get(f"source|{source}|{tbl.get('table_name', '')}.{col_name}")
                    )
                    dq_record = dq_by_item.get((schema_name, tbl.get("table_name", ""), col_name))
                    sem_record = semantic_store.get(source, schema_name, tbl.get("table_name", ""), col_name)
                    columns.append({
                        "name": col_name,
                        "data_type": c.get("data_type"),
                        "finding_count": fc,
                        "dq": _dq_badge_view(dq_record, full=False),
                        "distinct_count": c.get("distinct_count"),
                        "lifecycle_state": lifecycle_state,
                        "business_name": element_state.get_business_name(source, schema_name, tbl.get("table_name", ""), col_name),
                        "pii": _column_pii(sem_record, c),
                        "semantic_state": _semantic_display_state(sem_record),
                        "glossary_term_id": (gl_term or {}).get("id"),
                        "glossary_term_title": (gl_term or {}).get("title"),
                        "glossary_term_status": (gl_term or {}).get("status"),
                    })

                result.append({
                    "schema": schema_name,
                    "table_name": tbl.get("table_name"),
                    "description": tbl.get("description"),
                    "row_count": tbl.get("row_count"),
                    "columns": columns,
                })
    return result


def _build_source_info(
    source: str,
    paths: dict,
    element_state: ElementStateStore,
    semantic_store: SemanticTypeStore,
    dq_service,
    connections: dict,
    *,
    emit: Callable[[str, dict], None] = lambda *_a: None,
) -> dict:
    """Build source-level metadata including connection info and aggregated dataset stats.

    ``emit(event, data)`` reports real checkpoints only (never on a timer):
    ``emit("progress", {"completed": n})`` fires once a whole stage genuinely
    finishes (n = how many of the 4 stages are now done); ``emit("detail",
    {"text": ...})`` fires for live sub-progress within the CURRENT stage (e.g.
    "12/40 tables"), without advancing the stage count. The plain GET route
    below ignores both (default no-op emit).
    """
    catalog = _load_source_catalog(paths["sources"], source)
    emit("progress", {"completed": 1})  # stage 0: connected

    schemas = catalog.get("schemas", [])
    connection_id = catalog.get("connection", "")
    table_total = sum(len(sc.get("tables", [])) for sc in schemas)

    # Pre-warm every table's DQ scores for this source in a SINGLE batched write,
    # so the per-table _dataset_dq_badge reads in the aggregation loop below are
    # all cache hits (no per-table writes). One file save for the whole source
    # on a cold rebuild, instead of one save per table.
    if dq_service is not None:
        with dq_service.batch():
            done = 0
            for _sc in schemas:
                for _tbl in _sc.get("tables", []):
                    dq_service.get_or_score_dataset(source, _sc.get("name", ""), _tbl.get("table_name", ""))
                    done += 1
                    if table_total:
                        emit("detail", {"text": f"({done}/{table_total} tables)", "index": done, "total": table_total})
    emit("progress", {"completed": 2})  # stage 1: governance tallied

    # Bulk-fetch every column's domain_role for this source in ONE query instead of one
    # store read per column (found live 2026-08-14: ~1,900 individual reads dominated this
    # page's load time for a large source). Columns with no row at all (never resolved)
    # are simply absent -- _hybrid_domain_role_from_map falls back to the same heuristic
    # the per-column path already used.
    domain_roles = semantic_store.domain_roles_for_source(source)

    # Aggregate stats across all tables/columns
    table_count = 0
    column_count = 0
    total_row_count = 0
    # Most recent per-table profiled_at across the source, None if not one table has ever
    # been profiled (fresh onboarding, or every table freshly reset) — a genuine "has this
    # source actually been profiled" signal, unlike catalog["generated_at"] below (which is
    # just the onboarding/schema-sync timestamp and never reflects profiling at all).
    latest_profiled_at: str | None = None
    # No preset keys — categories are the real domain roles present in this
    # source (see _hybrid_domain_role), so nothing gets forced into "other".
    type_counts: dict[str, int] = {}
    gov_counts: dict[str, int] = dict(_GOV_BUCKET_ZERO)
    # Cross-tab of the same two column-level facts already aggregated above
    # (semantic-type bucket × governance state) — e.g. "how many 'identifier'
    # columns are still Draft vs Approved". Real counts, no extra profiling.
    sem_gov_matrix: dict[str, dict[str, int]] = {}
    datasets_summary: list[dict] = []
    # Conceptual data model edges — PK/FK relationships between datasets in
    # this source (declared DB constraints + name/type-inferred fallbacks,
    # same `relations`/`inferred_relations` data the dataset-overview FK rows
    # read). "from" = the child table holding the FK (the "many" side); "to" =
    # the referenced parent table (the "one" side) — cardinality is always
    # 1:N by construction of a PK/FK pair, no extra data profiling needed.
    relationships: list[dict] = []

    for sc in schemas:
        schema_name = sc.get("name", "")
        for tbl in sc.get("tables", []):
            table_count += 1
            row_count = tbl.get("row_count") or 0
            total_row_count += row_count
            tbl_col_count = len(tbl.get("columns", []))
            tbl_name = tbl.get("table_name", "")
            tbl_profiled_at = tbl.get("profiled_at")
            if tbl_profiled_at and (latest_profiled_at is None or tbl_profiled_at > latest_profiled_at):
                latest_profiled_at = tbl_profiled_at

            for rel in tbl.get("relations", []) or []:
                ref_table = rel.get("reference_table")
                if not ref_table:
                    continue
                relationships.append({
                    "from_table": tbl_name,
                    "from_schema": schema_name,
                    "from_columns": rel.get("columns", []) or [],
                    "to_table": ref_table,
                    "to_schema": schema_name,
                    "to_columns": rel.get("reference_table_columns", []) or [],
                    "declared": True,
                })
            for rel in tbl.get("inferred_relations", []) or []:
                ref_table = rel.get("reference_table")
                if not ref_table:
                    continue
                relationships.append({
                    "from_table": tbl_name,
                    "from_schema": schema_name,
                    "from_columns": [rel.get("column")] if rel.get("column") else [],
                    "to_table": ref_table,
                    "to_schema": schema_name,
                    "to_columns": [rel.get("reference_column")] if rel.get("reference_column") else [],
                    "declared": False,
                    "confidence": rel.get("confidence"),
                })

            tbl_gov: dict[str, int] = dict(_GOV_BUCKET_ZERO)
            for col in tbl.get("columns", []):
                column_count += 1
                col_name = col.get("name", "")
                # Real domain role when resolved, relabelled heuristic guess
                # otherwise — never collapsed into a single "other" bucket.
                key = SemanticTypeStore.key(source, schema_name, tbl_name, col_name)
                sem_type = _hybrid_domain_role_from_map(key, col, domain_roles)
                # Source-level chart harmonisation (user decision): Natural ID and
                # Surrogate ID are both Identifiers, and Key is a per-column addendum,
                # not a primary domain — fold all three into one "identifier" bucket.
                if sem_type in ("natural_id", "surrogate_id", "key"):
                    sem_type = "identifier"
                type_counts[sem_type] = type_counts.get(sem_type, 0) + 1

                state = element_state.get(source, schema_name, tbl_name, col_name)
                bucket = _gov_display_bucket(state)
                gov_counts[bucket] = gov_counts.get(bucket, 0) + 1
                tbl_gov[bucket] = tbl_gov.get(bucket, 0) + 1
                sem_gov_matrix.setdefault(sem_type, dict(_GOV_BUCKET_ZERO))
                sem_gov_matrix[sem_type][bucket] = sem_gov_matrix[sem_type].get(bucket, 0) + 1

            story = element_state.get_data_story(source, schema_name, tbl_name)
            datasets_summary.append({
                "schema": schema_name,
                "table_name": tbl_name,
                "description": tbl.get("description"),
                "row_count": row_count,
                "column_count": tbl_col_count,
                "governance": {k: v for k, v in tbl_gov.items() if v > 0},
                "has_story": story is not None and bool(story.get("narrative")),
                "story_is_ai": story.get("is_ai_generated", False) if story else False,
                # Same stored roll-up the dataset overview/header chip reads
                # (§15) — keeps this table's DQ score always in sync with the
                # dataset-level score rather than recomputing separately.
                "dataset_dq": _dataset_dq_badge(dq_service, source, schema_name, tbl_name, full=False),
                # Whether a key is available (declared or inferred) — the same
                # check a future onboarding flow would run before offering to
                # draw a conceptual data model.
                "has_primary_key": bool(tbl.get("primary_key") or tbl.get("inferred_primary_key")),
                # D11's single authoritative "has this table been profiled" check —
                # false for a freshly-onboarded table and for one reset back to its
                # pre-profiling baseline. Drives the "never profiled" badge in the
                # Datasets table (and, when every dataset is false, the same badge
                # next to the source name in the header).
                "is_profiled": is_profiled(source, schema_name, tbl_name),
            })
            if table_total:
                emit("detail", {"text": f"({table_count}/{table_total} tables)", "index": table_count, "total": table_total})
    emit("progress", {"completed": 3})  # stage 2: datasets scanned

    # Distinct colour per real domain role (governed vocabulary roles from
    # semantic_resolver.get_vocabulary_structure(), plus the heuristic
    # fallback's own "unresolved" label) — no shared/merged "other" colour.
    type_colors = {
        "identifier": "#0d5c54",
        "code": "#8b5cf6",
        "temporal": "#2f5d8a",
        "measure": "#2f6b3a",
        "rate": "#c77d2e",
        "name": "#a9651b",
        "address": "#147a82",
        "text": "#5b7a99",
        "technical": "#6b6f76",
        "unresolved": "#b0aca3",
    }
    # Stable, meaningful display order (governed roles first, unresolved last)
    # rather than dict/insertion order, which would otherwise vary by which
    # table happened to be scanned first.
    _TYPE_ORDER = ["identifier", "code", "temporal", "measure", "rate", "name", "address", "text", "technical", "unresolved"]
    # Charts group by domain. Natural/Surrogate/Key are folded into "Identifier"
    # above (Key is a per-column addendum, not a domain). Readable domain labels.
    _TYPE_LABELS = {
        "identifier": "Identifier",
        "code": "Code",
        "temporal": "Date-time",
        "measure": "Measure",
        "rate": "Rate",
        "name": "Name",
        "address": "Address",
        "text": "Text",
        "technical": "Technical",
        "unresolved": "Unresolved",
    }
    ordered_types = sorted(
        (t for t, c in type_counts.items() if c > 0),
        key=lambda t: (_TYPE_ORDER.index(t) if t in _TYPE_ORDER else len(_TYPE_ORDER)),
    )
    semantic_type_mix = [
        {"type": t, "label": _TYPE_LABELS.get(t), "count": type_counts[t], "color": type_colors.get(t, "#86827a")}
        for t in ordered_types
    ]
    # Rows ordered to match `semantic_type_mix` (types with at least one
    # column), each with counts for all three governance states (0 when none).
    semantic_governance_matrix = [
        {
            "type": t,
            "label": _TYPE_LABELS.get(t),
            "color": type_colors.get(t, "#86827a"),
            "empty": sem_gov_matrix.get(t, {}).get("empty", 0),
            "draft": sem_gov_matrix.get(t, {}).get("draft", 0),
            "in_review": sem_gov_matrix.get(t, {}).get("in_review", 0),
            "approved": sem_gov_matrix.get(t, {}).get("approved", 0),
            "bounced": sem_gov_matrix.get(t, {}).get("bounced", 0),
        }
        for t in ordered_types
    ]

    observation_summary: list[dict] = []

    # Connection metadata — read from the actual connections.yaml entry (real
    # connector type, database/file path, scoped schemas, read-only flag)
    # rather than hardcoded placeholders. Falls back to catalog-derived values
    # when the connection is no longer present (e.g. renamed/removed).
    conn_cfg = _find_connection_config(connections, connection_id) or {}
    conn_type = conn_cfg.get("type")
    scoped_schemas = conn_cfg.get("schemas") or [sc.get("name") for sc in schemas]
    connection = {
        "source_system": str(connection_id),
        # str(...) coerces the (untyped) config value to a valid str dict key; falls back
        # to the raw type, then "Unknown", exactly as before.
        "system_type": _CONNECTION_TYPE_LABELS.get(str(conn_type or ""), conn_type or "Unknown"),
        "database": conn_cfg.get("database") or conn_cfg.get("file"),
        "schema": ", ".join(scoped_schemas) if scoped_schemas else None,
        "access_mode": "Read-only" if conn_cfg.get("read_only") else "Read-write",
    }

    emit("progress", {"completed": 4})  # stage 3: workspace ready
    return {
        "source": source,
        "connection": connection,
        "generated_at": catalog.get("generated_at"),
        # Real "has any table in this source ever been profiled" signal — the most recent
        # per-table profiled_at, or None if every table is unprofiled (fresh onboarding, or
        # all freshly reset). No catalog-generation fallback, unlike generated_at above.
        "last_profiled_at": latest_profiled_at,
        "schema_hash": catalog.get("schema_hash"),
        "table_count": table_count,
        "column_count": column_count,
        "total_row_count": total_row_count,
        "schemas": [sc.get("name") for sc in schemas],
        "semantic_type_mix": semantic_type_mix,
        "semantic_governance_matrix": semantic_governance_matrix,
        "governance_state": gov_counts,
        "semantic_state": _semantic_state_counts(semantic_store, source, column_count),
        "observation_summary": observation_summary,
        "datasets": datasets_summary,
        "relationships": relationships,
    }


@router.get("/{source}/info")
async def get_source_info(
    source: str,
    paths: dict = Depends(get_paths),
    element_state: ElementStateStore = Depends(get_element_state),
    semantic_store: SemanticTypeStore = Depends(get_semantic_type_store),
    dq_service=Depends(get_dq_service),
    connections: dict = Depends(get_connections),
):
    """Return source-level metadata including connection info and aggregated dataset stats."""
    return _build_source_info(source, paths, element_state, semantic_store, dq_service, connections)


@router.post("/{source}/info/stream")
async def stream_source_info(
    source: str,
    paths: dict = Depends(get_paths),
    element_state: ElementStateStore = Depends(get_element_state),
    semantic_store: SemanticTypeStore = Depends(get_semantic_type_store),
    dq_service=Depends(get_dq_service),
    connections: dict = Depends(get_connections),
):
    """Same data as GET /{source}/info, streamed as SSE with real progress checkpoints."""
    loop = asyncio.get_event_loop()

    def work(emit):
        return _build_source_info(source, paths, element_state, semantic_store, dq_service, connections, emit=emit)

    async def generate():
        async for event, data in stream_with_progress(loop, work):
            yield format_sse(event, data)

    return StreamingResponse(
        generate(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.get("/{source}/{table}/overview")
async def get_table_overview(
    source: str,
    table: str,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    element_state: ElementStateStore = Depends(get_element_state),
    semantic_store: SemanticTypeStore = Depends(get_semantic_type_store),
    dq_service=Depends(get_dq_service),
):
    """Return dataset-level overview with aggregated stats, governance state, and observation matrix."""
    return _build_table_overview(source, table, schema, paths, element_state, semantic_store, dq_service)


@router.post("/{source}/{table}/overview/stream")
async def stream_table_overview(
    source: str,
    table: str,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    element_state: ElementStateStore = Depends(get_element_state),
    semantic_store: SemanticTypeStore = Depends(get_semantic_type_store),
    dq_service=Depends(get_dq_service),
):
    """Same data as GET .../overview, streamed as SSE with real progress checkpoints
    (including live per-column semantic-resolution progress)."""
    loop = asyncio.get_event_loop()

    def work(emit):
        return _build_table_overview(source, table, schema, paths, element_state, semantic_store, dq_service, emit=emit)

    async def generate():
        async for event, data in stream_with_progress(loop, work):
            yield format_sse(event, data)

    return StreamingResponse(
        generate(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


def _build_table_overview(
    source: str,
    table: str,
    schema: str | None,
    paths: dict,
    element_state: ElementStateStore,
    semantic_store: SemanticTypeStore,
    dq_service,
    *,
    emit: Callable[[str, dict], None] = lambda *_a: None,
) -> dict:
    """Build dataset-level overview with aggregated stats, governance state, and findings.

    Same real-checkpoint ``emit`` contract as ``_build_source_info`` (6 stages here).
    """
    catalog = _load_source_catalog(paths["sources"], source)

    # Find the table
    tbl_dict = None
    resolved_schema = None
    for sc in catalog.get("schemas", []):
        if schema and sc.get("name") != schema:
            continue
        for t in sc.get("tables", []):
            if t.get("table_name") == table:
                tbl_dict = t
                resolved_schema = sc.get("name", "")
                break
        if tbl_dict:
            break

    if tbl_dict is None:
        raise HTTPException(status_code=404, detail=f"Table '{table}' not found in '{source}'")
    emit("progress", {"completed": 1})  # stage 0: table opened

    columns = tbl_dict.get("columns", [])
    row_count = tbl_dict.get("row_count") or 0

    # Foreign key relationships — same `relations` data Discovery's Orphan FK stat uses,
    # so the two views can never disagree about what references what. Merged with
    # name/type-inferred relationships (for sources with no DB-declared constraints),
    # tagged `declared: false` so the UI can render them distinctly.
    fk_by_column: dict[str, dict] = {}
    for rel in tbl_dict.get("relations", []) or []:
        ref_table = rel.get("reference_table")
        for fk_col, ref_col in zip(rel.get("columns", []) or [], rel.get("reference_table_columns", []) or []):
            fk_by_column[fk_col] = {
                "references_table": ref_table,
                "references_column": ref_col,
                "declared": True,
                "orphan_count": rel.get("orphan_count"),
            }
    for rel in tbl_dict.get("inferred_relations", []) or []:
        col_name = rel.get("column")
        if col_name and col_name not in fk_by_column:
            fk_by_column[col_name] = {
                "references_table": rel.get("reference_table"),
                "references_column": rel.get("reference_column"),
                "declared": False,
                "confidence": rel.get("confidence"),
                "basis": rel.get("basis"),
                "orphan_count": rel.get("orphan_count"),
            }
    foreign_keys = [{"column": col_name, **info} for col_name, info in fk_by_column.items()]

    # Reverse lookup — which other tables in this source declare (or name/type-infer)
    # a FK pointing at this table.
    referenced_by: list[dict] = []
    for sc in catalog.get("schemas", []):
        for t in sc.get("tables", []):
            other_name = t.get("table_name")
            if other_name == table:
                continue
            for rel in t.get("relations", []) or []:
                if rel.get("reference_table") == table:
                    referenced_by.append({
                        "table": other_name,
                        "schema": sc.get("name", ""),
                        "columns": rel.get("columns", []) or [],
                        "references_column": rel.get("reference_table_columns", []) or [],
                        "declared": True,
                    })
            for rel in t.get("inferred_relations", []) or []:
                if rel.get("reference_table") == table:
                    referenced_by.append({
                        "table": other_name,
                        "schema": sc.get("name", ""),
                        "columns": [rel.get("column")],
                        "references_column": [rel.get("reference_column")],
                        "declared": False,
                        "confidence": rel.get("confidence"),
                        "basis": rel.get("basis"),
                    })
    emit("progress", {"completed": 2})  # stage 1: column layout read

    # Compute aggregated stats
    completeness_vals = [1.0 - (c.get("null_pct") or 0.0) for c in columns if c.get("null_pct") is not None]
    # No column has ever been profiled (fresh onboarding, or post-reset) — report "not yet
    # measured" (None) rather than defaulting to a false 100%, which previously looked
    # identical to "checked, and everything is complete".
    overall_completeness = sum(completeness_vals) / len(completeness_vals) if completeness_vals else None
    duplicate_rows = tbl_dict.get("duplicate_count") or 0

    # Resolve the whole table once — fingerprinted, only re-runs on changed columns.
    def _on_resolve_progress(index: int, total: int, column_name: str, status: ColumnProgressStatus) -> None:
        if not total:
            return
        if status == "recheck":
            text = f"Re-computing {column_name} — {index}/{total} columns"
        elif status == "first_time":
            text = f"Classifying {column_name} for the first time — {index}/{total} columns"
        else:
            # Cache hit: still a real per-column fingerprint comparison, not literally nothing —
            # name it honestly rather than showing a bare counter (user request, 2026-08-15).
            text = f"Verifying per-column fingerprint match — {index}/{total} columns"
        emit("detail", {"text": text, "index": index, "total": total})

    # D11: never run/persist semantic-type auto-resolution merely from viewing the Overview
    # tab of a dataset that has not been profiled (fresh onboarding, or post-reset) — every
    # column must stay 'unresolved' until an explicit Refresh Profile, not silently gain a
    # governed type just because someone opened the page.
    if is_profiled(source, resolved_schema, table):
        resolved_records = _resolve_table_once(
            source=source, schema=resolved_schema, table_dict=tbl_dict, semantic_store=semantic_store,
            progress_cb=_on_resolve_progress,
        )
    else:
        resolved_records = {}
    emit("progress", {"completed": 3})  # stage 2: semantic meaning resolved

    # Semantic type mix — use resolved record when available, heuristic fallback otherwise.
    type_counts: dict[str, int] = {"identifier": 0, "coded": 0, "date": 0, "monetary": 0, "other": 0}
    for col in columns:
        record = resolved_records.get(col.get("name") or "")
        if record:
            sem_type = domain_role_to_legacy_bucket(record.get("domain_role"))
        else:
            sem_type = _heuristic_bucket(col)
        type_counts[sem_type] = type_counts.get(sem_type, 0) + 1

    type_colors = {"identifier": "#0d5c54", "coded": "#8b5cf6", "date": "#2f5d8a", "monetary": "#2f6b3a", "other": "#86827a"}
    semantic_type_mix = [
        {"type": t, "count": c, "color": type_colors.get(t, "#86827a")}
        for t, c in type_counts.items() if c > 0
    ]

    # Governance state
    gov_counts = dict(_GOV_BUCKET_ZERO)
    _pg_lifecycle = element_backend() == "postgres"
    for col in columns:
        state = element_state.get(source, resolved_schema, table, col.get("name"))
        gov_counts[_gov_display_bucket(state)] = gov_counts.get(_gov_display_bucket(state), 0) + 1

    # Findings — feeds each column's observation_count (rail warning badges,
    # the "observations" scoping filter). The dataset-level severity×provenance
    # rollup table this used to also feed ("Observation Summary") was removed:
    # it was built with include_ai=False, so its AI column was always 0, and
    # it duplicated what the DQ Insights findings list already shows per-item.
    try:
        assessment = assess_table(tbl_dict, include_ai=False)
        all_findings = assessment.get("findings", [])
    except Exception:
        all_findings = []

    finding_counts: dict[str, int] = {}
    for f in all_findings:
        target = f.get("target", "")
        finding_counts[target] = finding_counts.get(target, 0) + 1
    emit("progress", {"completed": 4})  # stage 3: observations gathered

    # Warm the whole table's DQ scores in one batched write before reading each
    # column's badge below — a single file save instead of one save per column.
    def _on_dq_progress(index: int, total: int, column_name: str, status: DQProgressStatus) -> None:
        if not total:
            return
        if status == "recheck":
            text = f"Re-scoring {column_name} — quality rules were updated — {index}/{total} columns"
        elif status == "first_time":
            text = f"Scoring {column_name}'s quality for the first time — {index}/{total} columns"
        else:
            text = f"({index}/{total} columns)"
        emit("detail", {"text": text, "index": index, "total": total})

    if dq_service is not None:
        dq_service.get_or_score_dataset(source, resolved_schema, table, progress_cb=_on_dq_progress)
    emit("progress", {"completed": 5})  # stage 4: data quality checked

    # Columns summary
    columns_summary = []
    for col in columns:
        col_name = col.get("name")
        fc = finding_counts.get(col_name, 0)
        null_pct = col.get("null_pct")
        col_meta = element_state.get_metadata(source, resolved_schema, table, col_name)
        col_lifecycle = element_state.get(source, resolved_schema, table, col_name)

        # Heal-on-read: advance draft → defined if a stored description exists
        # (yaml backend only — postgres mode never auto-advances the set lifecycle;
        # the status moves only on an explicit Save/Submit action, per Phase-5 design).
        if col_lifecycle == 'draft' and not _pg_lifecycle:
            col_desc_stored = element_state.get_description(source, resolved_schema, table, col_name)
            if not col_desc_stored:
                col_desc_stored = col.get('user_description') or col.get('description')
            if col_desc_stored and col_desc_stored.strip():
                # Heal-on-read: yaml-backend draft with a stored description advances to 'defined'
                # (a legacy state). Both 'draft' and 'defined' map to the 'draft' display bucket,
                # so the gov_counts tally is unchanged; only the stored state changes.
                element_state.set(source, resolved_schema, table, col_name, 'defined')
                col_lifecycle = 'defined'

        col_record = resolved_records.get(col_name) or {}
        columns_summary.append({
            "name": col_name,
            "data_type": col.get("data_type"),
            "semantic_type": normalise_type_id(col_record.get("type_id")),
            "semantic_domain_role": col_record.get("domain_role", "unresolved"),
            "semantic_state": _semantic_display_state(col_record),
            # Not yet profiled — report None ("not yet measured"), not a false 100%.
            "completeness": (1.0 - (null_pct or 0.0)) if null_pct is not None else None,
            "lifecycle_state": col_lifecycle,
            "observation_count": fc,
            "dq": _dq_badge(dq_service, source, resolved_schema, table, col_name),
            "assessment_scope": element_state.get_assessment_scope(source, resolved_schema, table, col_name),
            "distinct_count": col.get("distinct_count"),
            "pii": _column_pii(col_record, col),
            "description": element_state.get_description(source, resolved_schema, table, col_name),
            "description_is_ai": col_meta.get("is_ai_generated", False),
            "business_name": element_state.get_business_name(source, resolved_schema, table, col_name),
            "business_name_is_ai": col_meta.get("business_name_is_ai", False),
            "foreign_key": fk_by_column.get(col_name),
        })

    emit("progress", {"completed": 6})  # stage 5: profile assembled
    return {
        "source": source,
        "schema": resolved_schema,
        "table_name": table,
        "description": tbl_dict.get("description"),
        "row_count": row_count,
        "column_count": len(columns),
        "completeness": overall_completeness,
        "duplicate_rows": duplicate_rows,
        "primary_key": tbl_dict.get("primary_key") or [],
        "inferred_primary_key": tbl_dict.get("inferred_primary_key") or [],
        # TD#26: this dataset's OWN last-profiled time, not catalog["generated_at"] (which
        # moves on every table's write across the whole source and would misreport staleness).
        # Still falls back to the catalog timestamp so "Reset Profile"'s own visibility
        # check (same field, pre-existing behavior) keeps working unchanged.
        "generated_at": tbl_dict.get("profiled_at") or catalog.get("generated_at"),
        # Real "has this table ever been profiled" timestamp, no catalog fallback — never
        # profiled or freshly reset both correctly report None here, so the "Last profiled
        # at" label doesn't misreport a catalog sync as a profiling run.
        "profiled_at": tbl_dict.get("profiled_at"),
        # D11's authoritative "has this table been profiled" flag — drives the
        # "never profiled" badge next to the dataset name in this header,
        # same signal used for the Datasets table/source-header badges.
        "is_profiled": is_profiled(source, resolved_schema, table),
        "semantic_type_mix": semantic_type_mix,
        "governance_state": gov_counts,
        "columns_summary": columns_summary,
        "foreign_keys": foreign_keys,
        "referenced_by": referenced_by,
        "dataset_dq": _dataset_dq_badge(
            dq_service, source, resolved_schema, table, full=True, with_trend=True
        ),
    }


# ── Data Story routes (must be before /{source}/{table}/{column}) ───────────

@router.get("/{source}/{table}/dataset-dq")
async def get_dataset_dq(
    source: str,
    table: str,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    dq_service=Depends(get_dq_service),
):
    """Return the dataset-level DQ roll-up (§15) with its score-history trend.

    Rolls up on first view, then serves the persisted record; a member column's
    change re-rolls it via the governance event bus. Must be declared before the
    catch-all ``/{source}/{table}/{column}`` route.
    """
    catalog = _load_source_catalog(paths["sources"], source)
    found = _resolve_table_for_bulk(catalog, table, schema)
    if found is None:
        raise HTTPException(status_code=404, detail=f"Table '{table}' not found in '{source}'")
    resolved_schema, _ = found
    badge = _dataset_dq_badge(dq_service, source, resolved_schema, table, full=True, with_trend=True)
    if badge is None:
        raise HTTPException(status_code=503, detail="DQ scoring is unavailable")
    return badge


@router.get("/{source}/{table}/data-story")
async def get_data_story(
    source: str,
    table: str,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    element_state: ElementStateStore = Depends(get_element_state),
):
    """Return the persisted Data Story for a dataset, or a null record if none exists."""
    catalog = _load_source_catalog(paths["sources"], source)
    found = _resolve_table_for_bulk(catalog, table, schema)
    if found is None:
        raise HTTPException(status_code=404, detail=f"Table '{table}' not found in '{source}'")
    resolved_schema, _ = found
    story = element_state.get_data_story(source, resolved_schema, table)
    return story or {"tagline": None, "narrative": None, "is_ai_generated": False, "generated_at": None}


@router.post("/{source}/{table}/draft-data-story")
async def draft_data_story(
    source: str,
    table: str,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    element_state: ElementStateStore = Depends(get_element_state),
    semantic_store: SemanticTypeStore = Depends(get_semantic_type_store),
):
    """Generate and persist a Data Story (tagline + narrative) for a dataset using AI."""
    import json as _json
    catalog = _load_source_catalog(paths["sources"], source)
    found = _resolve_table_for_bulk(catalog, table, schema)
    if found is None:
        raise HTTPException(status_code=404, detail=f"Table '{table}' not found in '{source}'")
    resolved_schema, tbl_dict = found

    client, model = _get_ai_client_config()
    _empty = {"tagline": None, "narrative": None, "is_ai_generated": False, "generated_at": None}
    if not client:
        return _empty

    columns = tbl_dict.get("columns", [])
    pk = tbl_dict.get("primary_key") or []
    row_count = tbl_dict.get("row_count") or "unknown"
    col_lines = "\n".join(
        f"  - {c.get('name')} ({c.get('data_type', '?')}, "
        f"{_store_type_id(semantic_store, source, resolved_schema, table, c.get('name') or '')})"
        for c in columns[:30]
    )

    system_prompt = (
        "You are a data analyst writing concise documentation for a data governance platform. "
        "Given table metadata, produce exactly two lines:\n"
        "TAGLINE: A single sentence (≤20 words) starting with the grain "
        "('Each row represents …'). If grain cannot be determined, write: DATA_STORY_EMPTY\n"
        "NARRATIVE: 2–4 sentences expanding on the tagline — what entity each row describes, "
        "key things the columns reveal, and any notable scope. "
        "If TAGLINE is DATA_STORY_EMPTY, also write: DATA_STORY_EMPTY\n"
        "Never fabricate. Respond ONLY with the two labelled lines."
    )
    user_prompt = (
        f"Table: {tbl_dict.get('table_name')}\n"
        f"Description: {tbl_dict.get('description') or 'none'}\n"
        f"Row count: {row_count}\n"
        f"Primary key: {', '.join(pk) if pk else 'not declared'}\n"
        f"Columns ({len(columns)}):\n{col_lines}"
    )

    try:
        response = client.responses.create(
            model=model, instructions=system_prompt, input=user_prompt, temperature=0,
        )
        raw = response.output_text.strip()
    except Exception:
        return _empty

    tagline: str | None = None
    narrative: str | None = None
    for line in raw.splitlines():
        if line.startswith("TAGLINE:"):
            val = line[len("TAGLINE:"):].strip()
            tagline = None if val == "DATA_STORY_EMPTY" else val
        elif line.startswith("NARRATIVE:"):
            val = line[len("NARRATIVE:"):].strip()
            narrative = None if val == "DATA_STORY_EMPTY" else val

    if tagline:
        element_state.set_data_story(
            source, resolved_schema, table, tagline, narrative or "", is_ai_generated=True
        )
        from datetime import datetime as _dt
        return {"tagline": tagline, "narrative": narrative, "is_ai_generated": True,
                "generated_at": _dt.now().isoformat()}
    return _empty


class SaveDataStoryBody(BaseModel):
    tagline: str
    narrative: str


@router.put("/{source}/{table}/data-story")
async def save_data_story(
    source: str,
    table: str,
    body: SaveDataStoryBody,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    element_state: ElementStateStore = Depends(get_element_state),
):
    """Persist a user-edited Data Story (not AI-generated)."""
    catalog = _load_source_catalog(paths["sources"], source)
    found = _resolve_table_for_bulk(catalog, table, schema)
    if found is None:
        raise HTTPException(status_code=404, detail=f"Table '{table}' not found in '{source}'")
    resolved_schema, _ = found
    element_state.set_data_story(
        source, resolved_schema, table, body.tagline, body.narrative, is_ai_generated=False
    )
    from datetime import datetime as _dt
    return {"tagline": body.tagline, "narrative": body.narrative,
            "is_ai_generated": False, "generated_at": _dt.now().isoformat()}


# ── Column-level routes ─────────────────────────────────────────────────────

@router.get("/{source}/{table}/{column}")
async def get_element(
    source: str,
    table: str,
    column: str,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    element_state: ElementStateStore = Depends(get_element_state),
    audit_store: AuditStore = Depends(get_audit_store),
    semantic_store: SemanticTypeStore = Depends(get_semantic_type_store),
    dq_service=Depends(get_dq_service),
):
    return _build_element(source, table, column, schema, paths, element_state, audit_store, semantic_store, dq_service)


@router.post("/{source}/{table}/{column}/stream")
async def stream_element(
    source: str,
    table: str,
    column: str,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    element_state: ElementStateStore = Depends(get_element_state),
    audit_store: AuditStore = Depends(get_audit_store),
    semantic_store: SemanticTypeStore = Depends(get_semantic_type_store),
    dq_service=Depends(get_dq_service),
):
    """Same data as GET /{source}/{table}/{column}, streamed as SSE with real progress checkpoints."""
    loop = asyncio.get_event_loop()

    def work(emit):
        return _build_element(source, table, column, schema, paths, element_state, audit_store, semantic_store, dq_service, emit=emit)

    async def generate():
        async for event, data in stream_with_progress(loop, work):
            yield format_sse(event, data)

    return StreamingResponse(
        generate(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


def _build_element(
    source: str,
    table: str,
    column: str,
    schema: str | None,
    paths: dict,
    element_state: ElementStateStore,
    audit_store: AuditStore,
    semantic_store: SemanticTypeStore,
    dq_service,
    *,
    emit: Callable[[str, dict], None] = lambda *_a: None,
) -> dict:
    """Build the full single-column detail payload.

    Same real-checkpoint ``emit`` contract as ``_build_source_info`` (4 stages here).
    """
    catalog = _load_source_catalog(paths["sources"], source)
    result = _resolve_table_column(catalog, table, column, schema)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Column '{column}' not found in '{source}.{table}'",
        )
    col_dict, resolved_schema, tbl_dict = result

    lifecycle_state = element_state.get(source, resolved_schema, table, column)

    # Foreign key relationship for this column, if any (same `relations` source
    # the table overview and Discovery's Orphan FK stat both use). Falls back to
    # a name/type-inferred relationship when no DB-declared constraint exists.
    foreign_key = None
    for rel in tbl_dict.get("relations", []) or []:
        cols = rel.get("columns", []) or []
        if column in cols:
            idx = cols.index(column)
            ref_cols = rel.get("reference_table_columns", []) or []
            foreign_key = {
                "references_table": rel.get("reference_table"),
                "references_column": ref_cols[idx] if idx < len(ref_cols) else None,
                "declared": True,
                "orphan_count": rel.get("orphan_count"),
            }
            break
    if foreign_key is None:
        for rel in tbl_dict.get("inferred_relations", []) or []:
            if rel.get("column") == column:
                foreign_key = {
                    "references_table": rel.get("reference_table"),
                    "references_column": rel.get("reference_column"),
                    "declared": False,
                    "confidence": rel.get("confidence"),
                    "basis": rel.get("basis"),
                    "orphan_count": rel.get("orphan_count"),
                }
                break

    # Heal-on-read: advance draft → defined if a description already exists.
    # Fixes elements saved before auto-transition was in place, or via any
    # path that stored the description without updating the lifecycle state.
    # (yaml backend only — postgres mode never auto-advances; Phase-5 design.)
    if lifecycle_state == 'draft' and element_backend() != "postgres":
        stored_desc = element_state.get_description(source, resolved_schema, table, column)
        if not stored_desc:
            stored_desc = col_dict.get('user_description') or col_dict.get('description')
        if stored_desc and stored_desc.strip():
            element_state.set(source, resolved_schema, table, column, 'defined')
            lifecycle_state = 'defined'
            # Also persist catalog description so frontend never shows empty
            if not element_state.get_description(source, resolved_schema, table, column):
                element_state.set_description(source, resolved_schema, table, column,
                                              stored_desc, is_ai_generated=False)
    emit("progress", {"completed": 1})  # stage 0: column opened

    glossary_term = _find_glossary_term(source, resolved_schema, table, column)
    mapping_candidates = _find_mapping_candidates(
        paths["mappings"], source, resolved_schema, table, column
    )

    subject_id = f"{source}:{resolved_schema}.{table}.{column}"
    try:
        history = audit_store.list_events(subject_id=subject_id, limit=10)
    except Exception:
        history = []

    try:
        assessment = assess_table(tbl_dict, include_ai=False)
        col_findings = [f for f in assessment.get("findings", []) if f.get("target") == column]
    except Exception:
        col_findings = []
    emit("progress", {"completed": 2})  # stage 1: glossary/mapping links checked


    null_pct = col_dict.get("null_pct")
    element_metadata = element_state.get_metadata(source, resolved_schema, table, column)
    stored_business_name = element_state.get_business_name(source, resolved_schema, table, column)

    # Enrich col_dict with governance signals so the resolver can use them as evidence.
    # This is the only place where glossary link, definition state, and catalog stats
    # co-exist, allowing the resolver to boost confidence for steward-approved governance.
    col_dict_enriched = dict(col_dict)
    if glossary_term and glossary_term.get("status") in {"approved", "confirmed", "published"}:
        col_dict_enriched["_glossary_domain"] = "confirmed"
        col_dict_enriched["_glossary_title"] = glossary_term.get("title", "")

    # Approved definition signal — if lifecycle is approved and description exists
    stored_desc = element_state.get_description(source, resolved_schema, table, column)
    if lifecycle_state == "approved" and stored_desc and stored_desc.strip():
        col_dict_enriched["_definition_state"] = "approved"
        preview = stored_desc[:50] + "…" if len(stored_desc) > 50 else stored_desc
        col_dict_enriched["_definition_preview"] = preview

    # D11: same rule as the Overview tab — never run/persist semantic-type auto-resolution
    # merely from clicking into a column's detail panel before the dataset has been profiled.
    if is_profiled(source, resolved_schema, table):
        sem_record = _get_resolver(semantic_store).resolve_column(
            source=source,
            schema=resolved_schema,
            table=table,
            column=col_dict_enriched,
            table_facts=tbl_dict,
            persist=True,
        )
    else:
        sem_record = {}

    # Evidence is now computed by the resolver (fingerprint includes governance signals).
    # For already-accepted records (a steward decision is sticky), late evidence
    # may still need injection — but that's a rare edge case handled separately.
    sem_evidence = list(sem_record.get("evidence") or [])


    # DQ badge (U2b) — computed after semantic resolution so an accepted type
    # drives the archetype. First-view populate; served from the store after.
    dq_badge = _dq_badge(dq_service, source, resolved_schema, table, column, full=True)
    emit("progress", {"completed": 3})  # stage 2: meaning + quality score worked out

    result_payload = {
        "source": source,
        "schema": resolved_schema,
        "table": table,
        "column": column,
        "data_type": col_dict.get("data_type"),
        "is_primary_key": column in (tbl_dict.get("primary_key") or tbl_dict.get("inferred_primary_key") or []),
        "foreign_key": foreign_key,
        "semantic_type": normalise_type_id(sem_record.get("type_id")),
        "semantic_domain_role": sem_record.get("domain_role", "unresolved"),
        "semantic_confidence": sem_record.get("confidence"),
        "semantic_state": _semantic_display_state(sem_record),
        "semantic_source": sem_record.get("source", "rule"),
        "semantic_tier": sem_record.get("tier", 0),
        "semantic_type_value_conflict": bool(sem_record.get("type_value_conflict") or sem_record.get("conflict", False)),
        "semantic_type_datatype_difference": bool(sem_record.get("type_datatype_difference") or sem_record.get("storage_mismatch", False)),
        "semantic_scope": sem_record.get("scope"),
        "semantic_entity": sem_record.get("entity"),
        "semantic_pii": bool(sem_record.get("pii", False)),
        "semantic_pii_category": sem_record.get("pii_category"),
        "pii": _column_pii(sem_record, col_dict),
        "pii_category": _column_pii_category(sem_record, col_dict),
        "semantic_evidence": sem_evidence,
        "semantic_candidates": sem_record.get("candidates") or [],
        "semantic_ai_available": bool(sem_record.get("ai_available", False)),
        "business_name": stored_business_name or _default_business_name(column),
        "stats": {
            "null_pct": null_pct,
            "distinct_count": col_dict.get("distinct_count"),
            "min_value": col_dict.get("min_value"),
            "max_value": col_dict.get("max_value"),
            "row_count": tbl_dict.get("row_count"),
            "sample_values": col_dict.get("sample_values") or [],
            "duplicate_count": col_dict.get("duplicate_count"),
            "placeholder_count": col_dict.get("placeholder_count"),
            "uniqueness_pct": col_dict.get("uniqueness_pct"),
            "top_values": col_dict.get("top_values") or [],
            "numeric_avg": col_dict.get("numeric_avg"),
            "numeric_median": col_dict.get("numeric_median"),
            "numeric_stddev": col_dict.get("numeric_stddev"),
            "length_min": col_dict.get("length_min"),
            "length_max": col_dict.get("length_max"),
            "length_avg": col_dict.get("length_avg"),
            "inferred_pattern": col_dict.get("inferred_pattern"),
            "pattern_confidence": col_dict.get("pattern_confidence"),
        },
        "lifecycle_state": lifecycle_state,
        "dq": dq_badge,
        "assessment_scope": element_state.get_assessment_scope(source, resolved_schema, table, column),
        "findings": col_findings,
        "glossary_term": glossary_term,
        "mapping_candidates": mapping_candidates,
        "audit_history": history,
        "table_description": tbl_dict.get("description"),
        "column_description": (
            element_state.get_description(source, resolved_schema, table, column)
            or col_dict.get("user_description")
            or col_dict.get("description")
        ),
        "metadata": {
            "created_by": element_metadata.get("created_by"),
            "created_at": element_metadata.get("created_at"),
            "updated_at": element_metadata.get("updated_at"),
            "is_ai_generated": element_metadata.get("is_ai_generated", False),
            "business_name_is_ai": element_metadata.get("business_name_is_ai",
                                                         stored_business_name is None),
            "mapping_instructions": element_metadata.get("mapping_instructions"),
        },
        "submission": element_state.get_submission_status(source, resolved_schema, table, column),
        "last_status": element_state.get_last_status(source, resolved_schema, table, column),
    }
    emit("progress", {"completed": 4})  # stage 3: response assembled
    return result_payload


@router.get("/{source}/{table}/{column}/dq")
async def get_element_dq(
    source: str,
    table: str,
    column: str,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    dq_service=Depends(get_dq_service),
):
    """Return the persisted DQ badge for a column, scoring on first view (U2b).

    Score-present → served from the store; score-absent → scored-and-persisted
    once, then returned. Never recomputes on every read.
    """
    catalog = _load_source_catalog(paths["sources"], source)
    result = _resolve_table_column(catalog, table, column, schema)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Column '{column}' not found in '{source}.{table}'",
        )
    _, resolved_schema, _ = result
    badge = _dq_badge(dq_service, source, resolved_schema, table, column, full=True)
    if badge is None:
        raise HTTPException(status_code=503, detail="DQ scoring is unavailable")
    return badge


@router.post("/{source}/{table}/{column}/dq/refresh")
async def refresh_element_dq(
    source: str,
    table: str,
    column: str,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    dq_service=Depends(get_dq_service),
):
    """Force a fresh DQ score for one column (Polish Batch Task 6).

    ``GET .../dq`` deliberately never recomputes on every read (U2b) — this is
    the manual escape hatch: it always calls ``score_and_persist`` directly,
    bypassing the cached/heal path, so a steward can clear a stale record on
    demand. Same re-score path assessment-scope changes and semantic
    confirm/reject already trigger via governance events; this just exposes it
    on demand for one column. Not audited — the existing profile-refresh
    endpoint (``POST /discovery/{{dataset}}/{{table}}/refresh``) this mirrors
    isn't audited either, so this stays consistent with that precedent.
    """
    catalog = _load_source_catalog(paths["sources"], source)
    result = _resolve_table_column(catalog, table, column, schema)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Column '{column}' not found in '{source}.{table}'",
        )
    _, resolved_schema, _ = result
    if dq_service is None:
        raise HTTPException(status_code=503, detail="DQ scoring is unavailable")
    try:
        record = dq_service.score_and_persist(source, resolved_schema, table, column)
    except Exception:
        raise HTTPException(status_code=503, detail="DQ scoring is unavailable")
    badge = _dq_badge_view(record, full=True)
    if badge is None:
        raise HTTPException(status_code=503, detail="DQ scoring is unavailable")
    # A manual per-column re-evaluate doesn't fire the governance event that
    # normally re-rolls the dataset (semantic confirm/reject, scope change —
    # see DQScoringService._on_rescore_event), so this would leave the dataset
    # roll-up (score + "columns dragging the score down") stale until some
    # other event happened to touch it. Re-roll it here too, exception-isolated
    # so a roll-up failure never breaks the column re-score response.
    try:
        dq_service.score_and_persist_dataset(source, resolved_schema, table)
    except Exception:
        logger.exception(
            "DQ dataset re-roll failed after manual column refresh source=%r "
            "table=%r column=%r", source, table, column,
        )
    return badge


class ScopeUpdateRequest(BaseModel):
    columns: list[str]
    scope: str
    scope_reason: str | None = None
    scoped_by: str | None = None


@router.post("/{source}/{table}/scope")
async def set_assessment_scope(
    source: str,
    table: str,
    body: ScopeUpdateRequest,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    element_state: ElementStateStore = Depends(get_element_state),
    audit_store: AuditStore = Depends(get_audit_store),
):
    """Set the assessment scope for one or more columns of a table (D1 / U2c).

    A single column is just a one-element ``columns`` list; stewards typically
    descope several platform-technical columns at once. For each changed column
    the fact is persisted, an ``ASSESSMENT_SCOPE_CHANGED`` audit event is logged,
    and a governance event is emitted so the DQ service re-evaluates the column
    (descope → the column's DQ record becomes ``unscored``; re-scope → scored
    again). The re-score reuses the existing event→re-score path.
    """
    if body.scope not in ASSESSMENT_SCOPE_VALUES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid scope {body.scope!r}; expected one of {ASSESSMENT_SCOPE_VALUES}",
        )
    if not body.columns:
        raise HTTPException(status_code=422, detail="No columns supplied")

    catalog = _load_source_catalog(paths["sources"], source)
    updated: list[dict] = []
    for column in body.columns:
        result = _resolve_table_column(catalog, table, column, schema)
        if result is None:
            raise HTTPException(
                status_code=404,
                detail=f"Column '{column}' not found in '{source}.{table}'",
            )
        _, resolved_schema, _ = result

        prior_scope = element_state.get_assessment_scope(source, resolved_schema, table, column)
        record = element_state.set_assessment_scope(
            source, resolved_schema, table, column, body.scope,
            scope_reason=body.scope_reason, scoped_by=body.scoped_by,
        )

        audit_store.log_business(
            event_type=audit_events.ASSESSMENT_SCOPE_CHANGED,
            subject_type="column",
            subject_id=f"{source}:{resolved_schema}.{table}.{column}",
            payload={
                "source": source,
                "schema": resolved_schema,
                "table": table,
                "column": column,
                "prior_scope": prior_scope,
                "new_scope": body.scope,
                "scope_reason": body.scope_reason,
                "scoped_by": body.scoped_by,
            },
        )
        emit_governance_event(
            audit_events.ASSESSMENT_SCOPE_CHANGED,
            {
                "source": source,
                "schema": resolved_schema,
                "table": table,
                "column": column,
                "prior_scope": prior_scope,
                "new_scope": body.scope,
            },
        )
        updated.append({
            "column": column,
            "schema": resolved_schema,
            "assessment_scope": record.get("scope"),
            "scope_reason": record.get("scope_reason"),
            "scoped_by": record.get("scoped_by"),
            "scoped_at": record.get("scoped_at"),
        })

    return {"source": source, "table": table, "updated": updated}


class LifecycleUpdateRequest(BaseModel):
    state: LifecycleState


@router.patch("/{source}/{table}/{column}/state")
async def update_lifecycle_state(
    source: str,
    table: str,
    column: str,
    body: LifecycleUpdateRequest,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    element_state: ElementStateStore = Depends(get_element_state),
    audit_store: AuditStore = Depends(get_audit_store),
):
    catalog = _load_source_catalog(paths["sources"], source)
    result = _resolve_table_column(catalog, table, column, schema)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Column '{column}' not found in '{source}.{table}'",
        )
    _, resolved_schema, _ = result

    element_state.set(source, resolved_schema, table, column, body.state)

    audit_store.log_business(
        event_type=audit_events.ELEMENT_STATE_CHANGED,
        subject_type="element",
        subject_id=f"{source}:{resolved_schema}.{table}.{column}",
        payload={
            "new_state": body.state,
            "source": source,
            "schema": resolved_schema,
            "table": table,
            "column": column,
        },
    )

    return {
        "source": source,
        "schema": resolved_schema,
        "table": table,
        "column": column,
        "lifecycle_state": body.state,
    }


class DescriptionUpdateRequest(BaseModel):
    description: str
    is_ai_generated: bool = False  # Defaults to False; set to True only for AI-generated drafts


@router.patch("/{source}/{table}/{column}/description")
async def update_description(
    source: str,
    table: str,
    column: str,
    body: DescriptionUpdateRequest,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    element_state: ElementStateStore = Depends(get_element_state),
    audit_store: AuditStore = Depends(get_audit_store),
):
    catalog = _load_source_catalog(paths["sources"], source)
    result = _resolve_table_column(catalog, table, column, schema)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Column '{column}' not found in '{source}.{table}'",
        )
    _, resolved_schema, _ = result

    # Save description and track if it's AI-generated
    element_state.set_description(source, resolved_schema, table, column, body.description,
                                 is_ai_generated=body.is_ai_generated)

    # Auto-transition: draft→defined when description added, defined→draft when description cleared
    # (yaml backend only — postgres mode never auto-advances the set lifecycle; Phase-5 design).
    current_state = element_state.get(source, resolved_schema, table, column)
    new_state = current_state

    if element_backend() != "postgres":
        description_is_empty = not body.description or not body.description.strip()

        if description_is_empty and current_state != 'draft':
            # Revert to draft when clearing description
            try:
                element_state.set(source, resolved_schema, table, column, 'draft')
                new_state = 'draft'
            except Exception as e:
                print(f"Error transitioning to draft: {e}")
                new_state = current_state
        elif not description_is_empty and current_state == 'draft':
            # Advance to defined when adding description to draft
            try:
                element_state.set(source, resolved_schema, table, column, 'defined')
                new_state = 'defined'
            except Exception as e:
                print(f"Error transitioning to defined: {e}")
                new_state = current_state

    audit_store.log_business(
        event_type=audit_events.ELEMENT_DESCRIPTION_UPDATED,
        subject_type="element",
        subject_id=f"{source}:{resolved_schema}.{table}.{column}",
        payload={
            "source": source,
            "schema": resolved_schema,
            "table": table,
            "column": column,
            "description_length": len(body.description),
            "is_ai_generated": body.is_ai_generated,
            "new_lifecycle_state": new_state,
        },
    )

    return {
        "source": source,
        "schema": resolved_schema,
        "table": table,
        "column": column,
        "column_description": body.description,
        "lifecycle_state": new_state,
    }


@router.post("/{source}/{table}/{column}/draft-description")
async def draft_description(
    source: str,
    table: str,
    column: str,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
):
    catalog = _load_source_catalog(paths["sources"], source)
    result = _resolve_table_column(catalog, table, column, schema)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Column '{column}' not found in '{source}.{table}'",
        )
    col_dict, resolved_schema, tbl_dict = result

    try:
        import json
        import os
        import yaml as _yaml
        from foundry_client import create_foundry_client

        with (_ROOT / "project.yaml").open(encoding="utf-8") as fh:
            project = _yaml.safe_load(fh) or {}
        agent_cfg = project.get("agent", {})
        api_key = os.environ.get(agent_cfg.get("api_key_env", "AZURE_FOUNDRY_KEY"), "")
        model = agent_cfg.get("model", "gpt-5.4-mini")

        try:
            assessment = assess_table(tbl_dict, include_ai=False)
            col_findings = [f for f in assessment.get("findings", []) if f.get("target") == column]
        except Exception:
            col_findings = []

        system_prompt = (
            "You are a data steward writing business-friendly column descriptions for a "
            "regulatory data governance platform. Write a concise (1-3 sentence) business "
            "description for the given column. Use plain language a business analyst understands. "
            "Do NOT reference technical implementation details. Respond with just the description text, "
            "no JSON wrapper, no prefix."
        )
        user_prompt = (
            f"Table: {tbl_dict.get('table_name')} ({tbl_dict.get('description') or 'no table description'})\n"
            f"Column: {column}\n"
            f"Data type: {col_dict.get('data_type')}\n"
            f"Sample values: {json.dumps((col_dict.get('sample_values') or [])[:8])}\n"
        )
        if col_findings:
            user_prompt += f"Quality observations: {json.dumps([f['title'] for f in col_findings[:3]])}\n"

        client = create_foundry_client(
            api_key=api_key,
            api_key_env=agent_cfg.get("api_key_env", "AZURE_FOUNDRY_KEY"),
        )
        response = client.responses.create(
            model=model,
            instructions=system_prompt,
            input=user_prompt,
            temperature=0,
        )
        draft = response.output_text.strip()
    except Exception as exc:
        return {"draft": "", "error": format_llm_error(exc)}

    return {"draft": draft}


class BusinessNameUpdateRequest(BaseModel):
    business_name: str
    is_ai_generated: bool = False


@router.patch("/{source}/{table}/{column}/business-name")
async def update_business_name(
    source: str,
    table: str,
    column: str,
    body: BusinessNameUpdateRequest,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    element_state: ElementStateStore = Depends(get_element_state),
):
    catalog = _load_source_catalog(paths["sources"], source)
    result = _resolve_table_column(catalog, table, column, schema)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Column '{column}' not found in '{source}.{table}'",
        )
    _, resolved_schema, _ = result

    element_state.set_business_name(
        source, resolved_schema, table, column,
        body.business_name, is_ai_generated=body.is_ai_generated,
    )

    return {
        "source": source,
        "schema": resolved_schema,
        "table": table,
        "column": column,
        "business_name": body.business_name,
        "business_name_is_ai": body.is_ai_generated,
    }


@router.post("/{source}/{table}/{column}/draft-business-name")
async def draft_business_name(
    source: str,
    table: str,
    column: str,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
):
    catalog = _load_source_catalog(paths["sources"], source)
    result = _resolve_table_column(catalog, table, column, schema)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Column '{column}' not found in '{source}.{table}'",
        )
    col_dict, _, tbl_dict = result

    try:
        import os
        import yaml as _yaml
        from foundry_client import create_foundry_client

        with (_ROOT / "project.yaml").open(encoding="utf-8") as fh:
            project = _yaml.safe_load(fh) or {}
        agent_cfg = project.get("agent", {})
        api_key = os.environ.get(agent_cfg.get("api_key_env", "AZURE_FOUNDRY_KEY"), "")
        model = agent_cfg.get("model", "gpt-5.4-mini")

        system_prompt = (
            "You are a data governance expert naming data fields for a business catalog. "
            "Given a technical column name and context, return a short (2–5 words) "
            "Title Case business name that a business analyst would immediately recognise. "
            "Expand common abbreviations: _id → Identifier, _amt → Amount, _dt → Date, "
            "_cd → Code, _nm → Name, _pct → Percentage, _flg → Flag. "
            "Respond with ONLY the business name — no explanation, no punctuation."
        )
        user_prompt = (
            f"Table: {tbl_dict.get('table_name')} ({tbl_dict.get('description') or 'no description'})\n"
            f"Column: {column}\n"
            f"Data type: {col_dict.get('data_type')}\n"
            f"Sample values: {(col_dict.get('sample_values') or [])[:5]}\n"
        )

        client = create_foundry_client(
            api_key=api_key,
            api_key_env=agent_cfg.get("api_key_env", "AZURE_FOUNDRY_KEY"),
        )
        response = client.responses.create(
            model=model,
            instructions=system_prompt,
            input=user_prompt,
            temperature=0,
        )
        draft = response.output_text.strip()
    except Exception as exc:
        return {"draft": _default_business_name(column), "error": format_llm_error(exc)}

    return {"draft": draft}


def _get_ai_client_config() -> tuple:
    """Return (client, model) or (None, None) if AI is unavailable."""
    try:
        import os
        import yaml as _yaml
        from foundry_client import create_foundry_client
        with (_ROOT / "project.yaml").open(encoding="utf-8") as fh:
            project = _yaml.safe_load(fh) or {}
        agent_cfg = project.get("agent", {})
        api_key = os.environ.get(agent_cfg.get("api_key_env", "AZURE_FOUNDRY_KEY"), "")
        model = agent_cfg.get("model", "gpt-5.4-mini")
        client = create_foundry_client(
            api_key=api_key,
            api_key_env=agent_cfg.get("api_key_env", "AZURE_FOUNDRY_KEY"),
        )
        return client, model
    except Exception:
        return None, None


def _resolve_table_for_bulk(
    catalog: dict, table: str, schema: Optional[str] = None
) -> tuple[str, dict] | None:
    """Return (resolved_schema, tbl_dict) for the given table."""
    for sc in catalog.get("schemas", []):
        if schema and sc.get("name") != schema:
            continue
        for tbl in sc.get("tables", []):
            if tbl.get("table_name") == table:
                return sc.get("name", ""), tbl
    return None


@router.post("/{source}/{table}/bulk-draft-descriptions")
async def bulk_draft_descriptions(
    source: str,
    table: str,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    element_state: ElementStateStore = Depends(get_element_state),
):
    """Generate and save AI descriptions for all columns in a table that have none."""
    import json
    catalog = _load_source_catalog(paths["sources"], source)
    found = _resolve_table_for_bulk(catalog, table, schema)
    if found is None:
        raise HTTPException(status_code=404, detail=f"Table '{table}' not found in '{source}'")
    resolved_schema, tbl_dict = found

    client, model = _get_ai_client_config()
    system_prompt = (
        "You are a data steward writing business-friendly column descriptions for a "
        "regulatory data governance platform. Write a concise (1-3 sentence) business "
        "description for the given column. Use plain language a business analyst understands. "
        "Do NOT reference technical implementation details. Respond with just the description text, "
        "no JSON wrapper, no prefix."
    )

    generated, skipped = 0, 0
    error = None
    if client is None:
        error = format_llm_error(ValueError("The AI service isn't configured or couldn't be reached."))
    for col_dict in tbl_dict.get("columns", []):
        col_name = col_dict.get("name", "")
        existing_desc = (
            element_state.get_description(source, resolved_schema, table, col_name)
            or col_dict.get("description")
        )
        current_state = element_state.get(source, resolved_schema, table, col_name)
        if existing_desc and current_state != 'draft':
            skipped += 1
            continue
        draft = ""
        if client:
            try:
                try:
                    assessment = assess_table(tbl_dict, include_ai=False)
                    col_findings = [f for f in assessment.get("findings", []) if f.get("target") == col_name]
                except Exception:
                    col_findings = []
                user_prompt = (
                    f"Table: {tbl_dict.get('table_name')} ({tbl_dict.get('description') or 'no table description'})\n"
                    f"Column: {col_name}\n"
                    f"Data type: {col_dict.get('data_type')}\n"
                    f"Sample values: {json.dumps((col_dict.get('sample_values') or [])[:8])}\n"
                )
                if col_findings:
                    user_prompt += f"Quality observations: {json.dumps([f['title'] for f in col_findings[:3]])}\n"
                response = client.responses.create(
                    model=model, instructions=system_prompt, input=user_prompt, temperature=0,
                )
                draft = response.output_text.strip()
            except Exception as exc:
                if error is None:
                    error = format_llm_error(exc)
                draft = ""
        if draft:
            element_state.set_description(source, resolved_schema, table, col_name, draft, is_ai_generated=True)
            # Mirror single-column logic: draft → defined when description added
            # (yaml backend only — postgres mode never auto-advances; Phase-5 design).
            if element_backend() != "postgres" and element_state.get(source, resolved_schema, table, col_name) == 'draft':
                try:
                    element_state.set(source, resolved_schema, table, col_name, 'defined')
                except Exception:
                    pass
            generated += 1

    resp: dict[str, Any] = {"generated": generated, "skipped": skipped, "total": generated + skipped}
    if error:
        resp["error"] = error
    return resp


@router.post("/{source}/{table}/bulk-draft-business-names")
async def bulk_draft_business_names(
    source: str,
    table: str,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    element_state: ElementStateStore = Depends(get_element_state),
):
    """Generate and save AI business names for all columns in a table that have none."""
    catalog = _load_source_catalog(paths["sources"], source)
    found = _resolve_table_for_bulk(catalog, table, schema)
    if found is None:
        raise HTTPException(status_code=404, detail=f"Table '{table}' not found in '{source}'")
    resolved_schema, tbl_dict = found

    client, model = _get_ai_client_config()
    system_prompt = (
        "You are a data governance expert naming data fields for a business catalog. "
        "Given a technical column name and context, return a short (2–5 words) "
        "Title Case business name that a business analyst would immediately recognise. "
        "Expand common abbreviations: _id → Identifier, _amt → Amount, _dt → Date, "
        "_cd → Code, _nm → Name, _pct → Percentage, _flg → Flag. "
        "Respond with ONLY the business name — no explanation, no punctuation."
    )

    generated, skipped = 0, 0
    error = None
    if client is None:
        error = format_llm_error(ValueError("The AI service isn't configured or couldn't be reached."))
    for col_dict in tbl_dict.get("columns", []):
        col_name = col_dict.get("name", "")
        if element_state.get_business_name(source, resolved_schema, table, col_name):
            skipped += 1
            continue
        draft = ""
        if client:
            try:
                user_prompt = (
                    f"Table: {tbl_dict.get('table_name')} ({tbl_dict.get('description') or 'no description'})\n"
                    f"Column: {col_name}\n"
                    f"Data type: {col_dict.get('data_type')}\n"
                    f"Sample values: {(col_dict.get('sample_values') or [])[:5]}\n"
                )
                response = client.responses.create(
                    model=model, instructions=system_prompt, input=user_prompt, temperature=0,
                )
                draft = response.output_text.strip()
            except Exception as exc:
                if error is None:
                    error = format_llm_error(exc)
                draft = ""
        if not draft:
            draft = _default_business_name(col_name)
        element_state.set_business_name(source, resolved_schema, table, col_name, draft, is_ai_generated=True)
        generated += 1

    resp: dict[str, Any] = {"generated": generated, "skipped": skipped, "total": generated + skipped}
    if error:
        resp["error"] = error
    return resp


@router.post("/{source}/bulk-draft-data-stories")
async def source_bulk_draft_data_stories(
    source: str,
    paths: dict = Depends(get_paths),
    element_state: ElementStateStore = Depends(get_element_state),
    semantic_store: SemanticTypeStore = Depends(get_semantic_type_store),
):
    """For every table in the source, generate a Data Story using AI if one does not already exist."""
    catalog = _load_source_catalog(paths["sources"], source)
    tables_list = [
        (schema_entry.get("name", ""), tbl)
        for schema_entry in catalog.get("schemas", [])
        for tbl in schema_entry.get("tables", [])
    ]

    # Count how many already have stories
    already_have = 0
    missing = []
    for schema_name, tbl_dict in tables_list:
        tbl_name = tbl_dict.get("table_name") or tbl_dict.get("name", "")
        tbl_schema = tbl_dict.get("schema", "") or schema_name
        existing = element_state.get_data_story(source, tbl_schema, tbl_name)
        if existing and existing.get("narrative"):
            already_have += 1
        else:
            missing.append((tbl_schema, tbl_dict))

    client, model = _get_ai_client_config()
    if not client:
        return {
            "generated": 0,
            "already_existed": already_have,
            "failed": len(missing),
            "total": len(tables_list),
            "ai_unavailable": True,
        }

    from datetime import datetime as _dt

    generated = 0
    failed = 0
    _system_prompt = (
        "You are a data analyst writing concise documentation for a data governance platform. "
        "Given table metadata, produce exactly two lines:\n"
        "TAGLINE: A single sentence (≤20 words) starting with the grain "
        "('Each row represents …'). If grain cannot be determined, write: DATA_STORY_EMPTY\n"
        "NARRATIVE: 2–4 sentences expanding on the tagline — what entity each row describes, "
        "key things the columns reveal, and any notable scope. "
        "If TAGLINE is DATA_STORY_EMPTY, also write: DATA_STORY_EMPTY\n"
        "Never fabricate. Respond ONLY with the two labelled lines."
    )
    for tbl_schema, tbl_dict in missing:
        tbl_name = tbl_dict.get("table_name") or tbl_dict.get("name", "")
        columns = tbl_dict.get("columns", [])
        pk = tbl_dict.get("primary_key") or []
        row_count = tbl_dict.get("row_count") or "unknown"
        col_lines = "\n".join(
            f"  - {c.get('name')} ({c.get('data_type', '?')}, "
            f"{_store_type_id(semantic_store, source, tbl_schema, tbl_name, c.get('name') or '')})"
            for c in columns[:30]
        )
        user_prompt = (
            f"Table: {tbl_name}\n"
            f"Description: {tbl_dict.get('description') or 'none'}\n"
            f"Row count: {row_count}\n"
            f"Primary key: {', '.join(pk) if pk else 'not declared'}\n"
            f"Columns ({len(columns)}):\n{col_lines}"
        )
        try:
            response = client.responses.create(
                model=model, instructions=_system_prompt, input=user_prompt, temperature=0,
            )
            raw = response.output_text.strip()
        except Exception:
            failed += 1
            continue
        tagline: str | None = None
        narrative: str | None = None
        for line in raw.splitlines():
            if line.startswith("TAGLINE:"):
                val = line[len("TAGLINE:"):].strip()
                tagline = None if val == "DATA_STORY_EMPTY" else val
            elif line.startswith("NARRATIVE:"):
                val = line[len("NARRATIVE:"):].strip()
                narrative = None if val == "DATA_STORY_EMPTY" else val
        if tagline:
            element_state.set_data_story(source, tbl_schema, tbl_name, tagline, narrative or "", is_ai_generated=True)
            generated += 1
        else:
            failed += 1

    return {
        "generated": generated,
        "already_existed": already_have,
        "failed": failed,
        "total": len(tables_list),
        "ai_unavailable": False,
    }


@router.post("/{source}/{table}/bulk-draft-data-stories")
async def bulk_draft_data_stories(
    source: str,
    table: str,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    element_state: ElementStateStore = Depends(get_element_state),
):
    """Skipped — dataset has at most one Data Story; generation is triggered per-table only if missing."""
    catalog = _load_source_catalog(paths["sources"], source)
    found = _resolve_table_for_bulk(catalog, table, schema)
    if found is None:
        raise HTTPException(status_code=404, detail=f"Table '{table}' not found in '{source}'")
    resolved_schema, _ = found
    existing = element_state.get_data_story(source, resolved_schema, table)
    if existing and existing.get("narrative"):
        return {"generated": 0, "skipped": 1, "total": 1}
    return {"generated": 0, "skipped": 0, "total": 1}


@router.get("/{source}/search")
async def search_elements(
    source: str,
    state: Optional[str] = Query(default=None),
    text: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    element_state: ElementStateStore = Depends(get_element_state),
):
    """Multi-filter search for elements in a source"""
    results = element_state.search_multi_filter(source=source, state=state, description_text=text)
    return {
        "source": source,
        "filters": {"state": state, "text": text},
        "results": results,
        "count": len(results),
    }


@router.get("/{source}/{table}/element-search")
async def search_table_elements(
    source: str,
    table: str,
    state: Optional[str] = Query(default=None),
    text: Optional[str] = Query(default=None),
    schema: Optional[str] = Query(default=None),
    element_state: ElementStateStore = Depends(get_element_state),
):
    """Search elements within a specific table"""
    all_results = element_state.search_multi_filter(source=source, state=state, description_text=text)
    # Filter by table
    filtered = [
        r for r in all_results
        if r['key'].split('|')[2] == table and (not schema or r['key'].split('|')[1] == schema)
    ]
    return {
        "source": source,
        "table": table,
        "schema": schema,
        "filters": {"state": state, "text": text},
        "results": filtered,
        "count": len(filtered),
    }


def _key_is_in_scope(element_state: ElementStateStore, key: str) -> bool:
    """True when a ``source|schema|table|column`` element key is in assessment scope (D1).

    Out-of-scope columns drop from both numerator and denominator of the SD
    coverage metrics (U3c Task 1). Malformed keys default to in-scope.
    """
    parts = key.split("|", 3)
    if len(parts) != 4:
        return True
    src, schema, table, column = parts
    return element_state.get_assessment_scope(src, schema or None, table, column) != "out_of_scope"


def _catalog_element_keys(paths: dict, source: str, element_state: ElementStateStore) -> list[tuple[str, dict]]:
    """Enumerate every ``(element_key, column_dict)`` pair across the FULL catalog for a
    source, filtered to in-scope columns.

    This is the catalog-wide truth, unlike ``element_state.find_in_source()``/
    ``semantic_store.find_in_source()`` which are sparse and only return columns that
    already have a saved governance record — using those alone as the coverage
    denominator silently excludes every column nobody has touched yet (tech-debt #17).
    """
    catalog = _load_source_catalog(paths["sources"], source)
    out: list[tuple[str, dict]] = []
    for sc in catalog.get("schemas", []):
        schema_name = sc.get("name") or ""
        for tbl in sc.get("tables", []):
            table_name = tbl.get("table_name")
            for col in tbl.get("columns", []):
                col_name = col.get("name")
                key = f"{source}|{schema_name}|{table_name}|{col_name}"
                if _key_is_in_scope(element_state, key):
                    out.append((key, col))
    return out


@router.get("/{source}/governance-summary")
async def get_governance_summary(
    source: str,
    paths: dict = Depends(get_paths),
    element_state: ElementStateStore = Depends(get_element_state),
    semantic_store: SemanticTypeStore = Depends(get_semantic_type_store),
    reference_code_repo: ReferenceCodeRepo = Depends(get_reference_code_repo),
    reference_binding_review_repo=Depends(get_reference_binding_review_repo),
):
    """Return governance and semantic-type coverage for a source.

    Provides per-state counts for definition lifecycle, semantic type
    disposition, and reference-code (coded column) submission, plus
    pending-review queue depth.

    Coverage denominators are **catalog-wide** (tech-debt #17): every in-scope
    column in the source's catalog counts toward the total, whether or not
    anyone has ever opened it — columns with no saved record default to
    'empty' (definition) / 'unresolved' (semantic type) / not-submitted
    (reference codes), rather than being silently dropped from the denominator.

    They are also **scope-aware** (D1 / U3c Task 1): columns marked
    ``out_of_scope`` drop from both the numerator and the denominator.
    """
    all_cols = _catalog_element_keys(paths, source, element_state)
    total = len(all_cols)

    # ── Definition (interpretation) lifecycle — bulk state map, default 'empty' ──
    state_map = element_state.all_states(source)
    empty_count = draft_count = in_review_count = approved_count = 0
    for key, _col in all_cols:
        bucket = _canonical_gov_bucket(state_map.get(key, "empty"))
        if bucket == "empty":
            empty_count += 1
        elif bucket == "draft":
            draft_count += 1
        elif bucket == "in_review":
            in_review_count += 1
        elif bucket == "approved":
            approved_count += 1
    pending_review_count = len(element_state.get_pending_review(source))

    # ── Semantic type disposition — bulk record map, default 'unresolved' ──
    sem_map = {str(r.get("key") or ""): r for r in semantic_store.find_in_source(source)}
    sem_accepted = sem_unresolved = 0
    for key, _col in all_cols:
        record = sem_map.get(key)
        if record and record.get("accepted_at"):
            sem_accepted += 1
        elif not record or (record.get("type_id") or "unresolved") == "unresolved":
            sem_unresolved += 1
    sem_pending = total - sem_accepted - sem_unresolved

    # ── Reference codes (coded columns) — "coded" is purely the profiled ─────────
    # cardinality rule already used by the reference-data endpoint
    # (distinct_count <= 50), independent of what semantic type it resolved to,
    # per steward instruction: "all codes, not only reference_codes".
    binding_map = reference_binding_review_repo.all_states(source)
    coded_total = coded_submitted = 0
    for key, col in all_cols:
        distinct = col.get("distinct_count") or 0
        if distinct > 50:
            continue
        coded_total += 1
        code_status = reference_code_repo.summary(key).get("status")
        bind_status = binding_map.get(key)
        if code_status in ("under_review", "approved") or bind_status in ("in_review", "approved"):
            coded_submitted += 1

    return {
        "source": source,
        "total_elements": total,
        "definition": {
            "empty": empty_count,
            "draft": draft_count,
            "in_review": in_review_count,
            "approved": approved_count,
            "pending_review": pending_review_count,
        },
        "definition_submitted_pct": round(
            (in_review_count + approved_count) / total * 100 if total else 0, 1
        ),
        "definition_approved_pct": round(
            approved_count / total * 100 if total else 0, 1
        ),
        "semantic_type": {
            "total_resolved": total,
            "accepted": sem_accepted,
            "pending": sem_pending,
            "unresolved": sem_unresolved,
        },
        "semantic_accepted_pct": round(
            sem_accepted / total * 100 if total else 0, 1
        ),
        "reference_codes": {
            "total_coded": coded_total,
            "submitted": coded_submitted,
        },
        "reference_codes_submitted_pct": round(
            coded_submitted / coded_total * 100 if coded_total else 0, 1
        ),
    }


@router.get("/{source}/{table}/{column}/reference-data")
async def get_reference_data(
    source: str,
    table: str,
    column: str,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    element_state: ElementStateStore = Depends(get_element_state),
    semantic_store: SemanticTypeStore = Depends(get_semantic_type_store),
    reference_set_store=Depends(get_reference_set_store),
    reference_code_repo: ReferenceCodeRepo = Depends(get_reference_code_repo),
    reference_binding_review_repo=Depends(get_reference_binding_review_repo),
):
    """Return reference data for a coded column (distinct_count ≤ 50).

    Phase 5b.2 — when ``refdata_backend='postgres'`` an *unbound* coded field returns per-code
    rows (Value / Meaning / Origin / Status) from the ``reference_code`` table, a whole-tab
    ``set_badge`` (partially-approved until 100%), and a ``semantic_accepted`` gate (Submit is
    disabled until the semantic type is Accepted).

    *Bound* fields (2026-08-16 redesign): every code the bound set recognises is returned
    read-only with the set's own meaning/value (``governed: true``, no per-code review of its
    own); any code the set does NOT recognise still gets the normal editable per-code treatment
    (``governed: false``) so a genuinely new/unexpected value can still be documented and
    reviewed on its own. The binding decision itself has its own submit/approve status,
    reported as ``binding_status``/``binding_submitted_at``/etc.
    """
    catalog = _load_source_catalog(paths["sources"], source)
    result = _resolve_table_column(catalog, table, column, schema)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Column '{column}' not found in '{source}.{table}'",
        )
    col_dict, resolved_schema, tbl_dict = result

    distinct = col_dict.get("distinct_count") or 0
    row_count = tbl_dict.get("row_count") or 1

    record = semantic_store.get(source, resolved_schema, table, column)
    semantic_accepted = bool(record and record.get("accepted_at"))

    if distinct > 50:
        return {
            "source": source,
            "schema": resolved_schema,
            "table": table,
            "column": column,
            "is_coded": False,
            "status": None,
            "codes": [],
            "bound_set_id": None,
            "set_kind": "local",
            "backend": refdata_backend(),
            "semantic_accepted": semantic_accepted,
            "set_badge": "empty",
            "binding_status": None,
        }

    samples = col_dict.get("sample_values") or []
    code_values = col_dict.get("code_values")

    # U2b Task 4 — build the code list from the profiler's full `code_values`
    # (all distinct values with true frequencies over the whole column, U0),
    # not the 20-capped `sample_values`. This corrects the shipped undercount
    # for coded columns with 20 < distinct_count ≤ 50 and lets the DQ Reference
    # Data component score against the honest denominator. Falls back to
    # `sample_values` only for legacy catalogs profiled before `code_values`.
    if code_values:
        codes = [
            {
                "code": str(row.get("value")) if row.get("value") is not None else "(null)",
                "value": None,
                "meaning": None,
                "share_pct": round((row.get("count") or 0) / row_count * 100, 1),
            }
            for row in sorted(code_values, key=lambda r: -(r.get("count") or 0))
        ]
    else:
        freq: dict[str, int] = {}
        for v in samples:
            k = str(v) if v is not None else "(null)"
            freq[k] = freq.get(k, 0) + 1
        total_samples = len(samples) if samples else 1
        codes = [
            {"code": code, "value": None, "meaning": None, "share_pct": round(count / total_samples * 100, 1)}
            for code, count in sorted(freq.items(), key=lambda x: -x[1])
        ]

    # Whole-field status is derived from the per-code rows (reference_code_repo.derive_set_status)
    # for unbound fields; bound fields get their status from the binding's own review lifecycle,
    # set below. Default before any code is documented.
    stored_status: str = "candidate"

    # The binding itself — fixed 2026-08-16 to read the real binding (was stuck reading a
    # metadata key that stopped being populated once element_content_backend moved to
    # Postgres, silently breaking every bound field's display).
    bound_set_id = element_state.get_reference_binding(source, resolved_schema, table, column)
    bound_set = reference_set_store.get(bound_set_id) if bound_set_id else None
    binding_status = binding_submitted_at = binding_submitted_by = None
    binding_decided_at = binding_decided_by = binding_decision = None
    if bound_set is not None:
        set_kind = bound_set["kind"]
        recognised_meanings = reference_set_store.meanings(bound_set_id)
        recognised_values = reference_set_store.values(bound_set_id)
        recognised_codes = {e["code"] for e in bound_set["entries"]}

        key = _refdata_key(source, resolved_schema, table, column)
        binding_status = reference_binding_review_repo.get_status(key)
        review = reference_binding_review_repo.get_review(key)
        binding_submitted_at, binding_submitted_by = review["submitted_at"], review["submitted_by"]
        binding_decided_at, binding_decided_by = review["decided_at"], review["decided_by"]
        binding_decision = review["decision"]
        stored_status = binding_status

        stored_rows = reference_code_repo.get_codes(key) if refdata_backend() == "postgres" else []
        tombs = reference_code_repo.tombstones(key) if refdata_backend() == "postgres" else {}
        by_code = {r["code"]: r for r in stored_rows}
        unrecognised_seen: list[dict] = []
        for c in codes:
            if c["code"] in recognised_codes:
                c["meaning"] = recognised_meanings.get(c["code"])
                c["value"] = recognised_values.get(c["code"])
                c["governed"] = True
                c["status"] = "governed"
                c["origin"] = "master_list"
                c["in_source"] = True
            else:
                row = by_code.get(c["code"])
                c["value"] = row["value"] if row else None
                c["meaning"] = row["meaning"] if row else None
                c["origin"] = row["origin"] if row else "profiled"
                c["status"] = row["status"] if row else "empty"
                c["governed"] = False
                c["in_source"] = True
                c["tombstone"] = (tombs.get(c["code"]) or {}).get("action")
                c["tombstone_at"] = (tombs.get(c["code"]) or {}).get("at")
                unrecognised_seen.append(c)
        seen = {c["code"] for c in codes}
        for row in stored_rows:
            if row["code"] in seen or row["code"] in recognised_codes:
                continue
            # A declared unrecognised code the profiler never observed.
            codes.append({
                "code": row["code"], "value": row["value"], "meaning": row["meaning"],
                "share_pct": None, "origin": row["origin"], "status": row["status"],
                "governed": False, "in_source": False,
                "tombstone": (tombs.get(row["code"]) or {}).get("action"),
                "tombstone_at": (tombs.get(row["code"]) or {}).get("at"),
            })
        # Whole-tab badge folds the binding's own status together with any leftover
        # unrecognised codes still needing their own review (2026-08-16 redesign).
        unrecognised_rows = [r for r in stored_rows if r["code"] not in recognised_codes]
        codes_badge = set_badge(unrecognised_rows) if unrecognised_rows else "empty"
        if binding_status == "approved" and codes_badge in ("empty", "approved"):
            set_badge_value = "approved"
        elif binding_status == "in_review" or codes_badge == "in_review":
            set_badge_value = "in_review"
        else:
            set_badge_value = codes_badge if codes_badge != "empty" else "draft"
    else:
        bound_set_id = None
        set_kind = "local"
        set_badge_value = "empty"
        if refdata_backend() == "postgres":
            key = _refdata_key(source, resolved_schema, table, column)
            stored_rows = reference_code_repo.get_codes(key)
            tombs = reference_code_repo.tombstones(key)  # 5b.3.2 — withdrawn/revoked trace
            by_code = {r["code"]: r for r in stored_rows}
            for c in codes:
                row = by_code.get(c["code"])
                c["value"] = row["value"] if row else None
                c["meaning"] = row["meaning"] if row else None
                c["origin"] = row["origin"] if row else "profiled"
                c["status"] = row["status"] if row else "empty"
                c["governed"] = False
                c["in_source"] = True
                c["tombstone"] = (tombs.get(c["code"]) or {}).get("action")
                c["tombstone_at"] = (tombs.get(c["code"]) or {}).get("at")
            seen = {c["code"] for c in codes}
            for row in stored_rows:
                if row["code"] in seen:
                    continue
                codes.append({
                    "code": row["code"], "value": row["value"], "meaning": row["meaning"],
                    "share_pct": None, "origin": row["origin"], "status": row["status"],
                    "governed": False, "in_source": False,
                    "tombstone": (tombs.get(row["code"]) or {}).get("action"),
                    "tombstone_at": (tombs.get(row["code"]) or {}).get("at"),
                })
            set_badge_value = set_badge(stored_rows)
            # Whole-field Candidate/Under Review/Approved status, derived losslessly from the
            # same per-code rows (replaces the retired whole-field refdata_status column).
            derived = derive_set_status(stored_rows)
            stored_status = "candidate" if derived == "none" else derived

    return {
        "source": source,
        "schema": resolved_schema,
        "table": table,
        "column": column,
        "is_coded": True,
        "status": stored_status,
        "codes": codes,
        "bound_set_id": bound_set_id,
        "set_kind": set_kind,
        "backend": refdata_backend(),
        "semantic_accepted": semantic_accepted,
        "set_badge": set_badge_value,
        "binding_status": binding_status,
        "binding_submitted_at": binding_submitted_at,
        "binding_submitted_by": binding_submitted_by,
        "binding_decided_at": binding_decided_at,
        "binding_decided_by": binding_decided_by,
        "binding_decision": binding_decision,
    }


class ReferenceDataUpdateRequest(BaseModel):
    meanings: dict[str, str] | None = None  # {code: meaning}
    values: dict[str, str] | None = None    # {code: value} — the code's expanded/full-word form
    status: str | None = None               # candidate | under_review | approved
    bound_set_id: str | None = None         # bind field to this reference set (Phase 3)
    unbind: bool = False                    # clear any existing reference-set binding


@router.patch("/{source}/{table}/{column}/reference-data")
async def update_reference_data(
    source: str,
    table: str,
    column: str,
    body: ReferenceDataUpdateRequest,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    element_state: ElementStateStore = Depends(get_element_state),
    audit_store: AuditStore = Depends(get_audit_store),
    reference_set_store=Depends(get_reference_set_store),
    reference_code_repo: ReferenceCodeRepo = Depends(get_reference_code_repo),
    reference_binding_review_repo=Depends(get_reference_binding_review_repo),
):
    """Update reference data meanings and/or status for a coded column."""
    catalog = _load_source_catalog(paths["sources"], source)
    result = _resolve_table_column(catalog, table, column, schema)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Column '{column}' not found in '{source}.{table}'",
        )
    _, resolved_schema, _ = result

    key = _refdata_key(source, resolved_schema, table, column)
    update: dict = {}

    # Inline meanings/values edits land as per-code draft saves — same entity the dedicated
    # per-code endpoints below write to, just addressed by a {code: value} dict here.
    if body.meanings is not None or body.values is not None:
        by_code: dict[str, dict] = {}
        for code, meaning in (body.meanings or {}).items():
            by_code.setdefault(code, {})["meaning"] = meaning
        for code, value in (body.values or {}).items():
            by_code.setdefault(code, {})["value"] = value
        edits = [{"code": code, **fields} for code, fields in by_code.items()]
        reference_code_repo.save_codes(key, edits)
        update["meanings"] = body.meanings
        update["values"] = body.values

    # Whole-field status transitions bulk-apply the matching per-code lifecycle action to every
    # currently-eligible code, rather than writing a separate whole-field status value.
    if body.status is not None:
        if body.status == "under_review":
            reference_code_repo.submit_codes(key)
        elif body.status == "approved":
            in_review = [r["code"] for r in reference_code_repo.get_codes(key) if r["status"] == "in_review"]
            if in_review:
                reference_code_repo.approve_codes(key, in_review)
        elif body.status == "candidate":
            rows = reference_code_repo.get_codes(key)
            in_review = [r["code"] for r in rows if r["status"] == "in_review"]
            approved = [r["code"] for r in rows if r["status"] == "approved"]
            if in_review:
                reference_code_repo.withdraw_codes(key, in_review)
            if approved:
                reference_code_repo.revoke_codes(key, approved)
        update["status"] = body.status

    # Phase 3: bind/unbind this field to a governed reference set. Handled
    # separately from metadata merge so a binding can be cleared (delete key).
    binding_changed: str | None = None
    if body.unbind:
        element_state.clear_reference_binding(source, resolved_schema, table, column)
        binding_changed = "unbound"
    elif body.bound_set_id is not None:
        if reference_set_store.get(body.bound_set_id) is None:
            raise HTTPException(
                status_code=404,
                detail=f"Reference set '{body.bound_set_id}' not found",
            )
        element_state.set_reference_binding(source, resolved_schema, table, column, body.bound_set_id)
        # A fresh bind resets any leftover submit/approve state from a PRIOR different set —
        # that earlier decision does not carry over to a newly-chosen set (2026-08-16 redesign).
        key = _refdata_key(source, resolved_schema, table, column)
        reference_binding_review_repo.reset_to_draft(key)
        binding_changed = body.bound_set_id

    if update or binding_changed is not None:
        audit_store.log_business(
            event_type=audit_events.ELEMENT_STATE_CHANGED,
            subject_type="element",
            subject_id=f"{source}:{resolved_schema}.{table}.{column}",
            payload={
                "event": "reference_data_updated",
                "source": source,
                "schema": resolved_schema,
                "table": table,
                "column": column,
                "meanings_updated": bool(body.meanings),
                "values_updated": bool(body.values),
                "status": body.status,
                "binding": binding_changed,
            },
        )

    final_rows = reference_code_repo.get_codes(key)
    final_status = derive_set_status(final_rows)
    return {
        "source": source,
        "schema": resolved_schema,
        "table": table,
        "column": column,
        "refdata_status": "candidate" if final_status == "none" else final_status,
        "meanings_count": sum(1 for r in final_rows if r.get("meaning")),
        "values_count": sum(1 for r in final_rows if r.get("value")),
        "bound_set_id": element_state.get_reference_binding(source, resolved_schema, table, column),
    }


# ── Reference Data — per-code save/submit (Phase 5b.2, Postgres backend) ─────


class ReferenceCodeEdit(BaseModel):
    code: str
    value: str | None = None
    meaning: str | None = None
    origin: str | None = None  # 'profiled' (default) | 'declared'


class ReferenceCodeSaveRequest(BaseModel):
    codes: list[ReferenceCodeEdit]
    actor: str | None = None
    actor_role: str | None = None


class ReferenceCodeSubmitRequest(BaseModel):
    codes: list[str] | None = None  # None → submit every eligible draft
    actor: str | None = None
    actor_role: str | None = None


class ReferenceCodeActionRequest(BaseModel):
    codes: list[str]  # the code values the bulk action targets
    actor: str | None = None
    actor_role: str | None = None


def _require_pg_refdata() -> None:
    """Guard the per-code endpoints — Postgres backend only."""
    if refdata_backend() != "postgres":
        raise HTTPException(
            status_code=409,
            detail="Per-code Reference Data is only available on the Postgres backend.",
        )


def _recognised_codes(reference_set_store, bound_set_id: str | None) -> set[str]:
    """Codes the bound reference set recognises — these are read-only (governed by the
    master list) and must never get their own ``reference_code`` row (2026-08-16 redesign).
    """
    if not bound_set_id:
        return set()
    bound_set = reference_set_store.get(bound_set_id)
    return {e["code"] for e in bound_set["entries"]} if bound_set else set()


@router.put("/{source}/{table}/{column}/reference-data/codes")
async def save_reference_codes(
    source: str,
    table: str,
    column: str,
    body: ReferenceCodeSaveRequest,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    element_state: ElementStateStore = Depends(get_element_state),
    audit_store: AuditStore = Depends(get_audit_store),
    reference_code_repo: ReferenceCodeRepo = Depends(get_reference_code_repo),
    reference_set_store=Depends(get_reference_set_store),
):
    """Save draft edits for a set of codes (Value / Meaning / Origin). Empty codes that gain
    content move to ``draft``; ``in_review`` / ``approved`` codes are locked and left unchanged.

    A code the field's bound reference set recognises is never saved here — it is governed by
    the master list and rendered read-only; only genuinely unrecognised codes reach this
    endpoint in normal use, but any recognised code slipped in is dropped defensively.
    """
    catalog = _load_source_catalog(paths["sources"], source)
    result = _resolve_table_column(catalog, table, column, schema)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Column '{column}' not found in '{source}.{table}'")
    _, resolved_schema, _ = result
    _require_pg_refdata()

    bound_set_id = element_state.get_reference_binding(source, resolved_schema, table, column)
    recognised = _recognised_codes(reference_set_store, bound_set_id)

    key = _refdata_key(source, resolved_schema, table, column)
    edits = [e.model_dump(exclude_none=False) for e in body.codes if e.code not in recognised]
    rows = reference_code_repo.save_codes(
        key, edits, actor=body.actor, actor_role=body.actor_role)
    audit_store.log_business(
        event_type=audit_events.ELEMENT_STATE_CHANGED,
        subject_type="element",
        subject_id=f"{source}:{resolved_schema}.{table}.{column}",
        payload={
            "event": "reference_codes_saved",
            "source": source, "schema": resolved_schema, "table": table, "column": column,
            "codes_saved": len(edits),
        },
    )
    return {"codes": rows, "set_badge": set_badge(rows)}


@router.post("/{source}/{table}/{column}/reference-data/submit-codes")
async def submit_reference_codes(
    source: str,
    table: str,
    column: str,
    body: ReferenceCodeSubmitRequest | None = None,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    element_state: ElementStateStore = Depends(get_element_state),
    semantic_store: SemanticTypeStore = Depends(get_semantic_type_store),
    audit_store: AuditStore = Depends(get_audit_store),
    reference_code_repo: ReferenceCodeRepo = Depends(get_reference_code_repo),
    reference_binding_review_repo=Depends(get_reference_binding_review_repo),
):
    """Partial Submit — move filled ``draft`` codes to ``in_review``.

    Gated on an Accepted semantic type (a coded field cannot be submitted for review while its
    semantic type is unresolved), matching the interpretation-set submit gate.

    2026-08-16 redesign — ONE COMBINED ACTION (user decision): when the field is bound, this
    same click also submits the binding decision itself for steward review (draft → in_review),
    alongside whichever unrecognised codes were filled in. A pure binding (no leftover
    unrecognised codes at all) still submits cleanly — ``payload.codes``/eligible drafts may be
    empty, that only affects the per-code half of this action.
    """
    catalog = _load_source_catalog(paths["sources"], source)
    result = _resolve_table_column(catalog, table, column, schema)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Column '{column}' not found in '{source}.{table}'")
    _, resolved_schema, _ = result
    _require_pg_refdata()

    record = semantic_store.get(source, resolved_schema, table, column)
    if not (record and record.get("accepted_at")):
        raise HTTPException(
            status_code=409,
            detail="The semantic type must be Accepted before submitting reference codes.",
        )

    payload = body or ReferenceCodeSubmitRequest()
    key = _refdata_key(source, resolved_schema, table, column)
    outcome = reference_code_repo.submit_codes(
        key, payload.codes, actor=payload.actor, actor_role=payload.actor_role)

    bound_set_id = element_state.get_reference_binding(source, resolved_schema, table, column)
    binding_submitted = False
    if bound_set_id and reference_binding_review_repo.get_status(key) == "draft":
        reference_binding_review_repo.submit(key, actor=payload.actor, actor_role=payload.actor_role)
        binding_submitted = True

    audit_store.log_business(
        event_type=audit_events.ELEMENT_STATE_CHANGED,
        subject_type="element",
        subject_id=f"{source}:{resolved_schema}.{table}.{column}",
        payload={
            "event": "reference_codes_submitted",
            "source": source, "schema": resolved_schema, "table": table, "column": column,
            "submitted": outcome["submitted"],
            "binding_submitted": binding_submitted,
        },
    )
    rows = reference_code_repo.get_codes(key)
    return {**outcome, "codes": rows, "set_badge": set_badge(rows), "binding_submitted": binding_submitted}


@router.post("/{source}/{table}/{column}/reference-data/withdraw-codes")
async def withdraw_reference_codes(
    source: str,
    table: str,
    column: str,
    body: ReferenceCodeActionRequest,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    audit_store: AuditStore = Depends(get_audit_store),
    reference_code_repo: ReferenceCodeRepo = Depends(get_reference_code_repo),
):
    """Withdraw submitted codes — ``in_review`` → editable ``draft`` (analyst pull-back)."""
    catalog = _load_source_catalog(paths["sources"], source)
    result = _resolve_table_column(catalog, table, column, schema)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Column '{column}' not found in '{source}.{table}'")
    _, resolved_schema, _ = result
    _require_pg_refdata()

    key = _refdata_key(source, resolved_schema, table, column)
    outcome = reference_code_repo.withdraw_codes(
        key, body.codes, actor=body.actor, actor_role=body.actor_role)
    audit_store.log_business(
        event_type=audit_events.ELEMENT_STATE_CHANGED,
        subject_type="element",
        subject_id=f"{source}:{resolved_schema}.{table}.{column}",
        payload={
            "event": "reference_codes_withdrawn",
            "source": source, "schema": resolved_schema, "table": table, "column": column,
            "withdrawn": outcome["withdrawn"],
        },
    )
    rows = reference_code_repo.get_codes(key)
    return {**outcome, "codes": rows, "set_badge": set_badge(rows)}


@router.post("/{source}/{table}/{column}/reference-data/revoke-codes")
async def revoke_reference_codes(
    source: str,
    table: str,
    column: str,
    body: ReferenceCodeActionRequest,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    audit_store: AuditStore = Depends(get_audit_store),
    reference_code_repo: ReferenceCodeRepo = Depends(get_reference_code_repo),
):
    """Revoke approved codes — ``approved`` → editable ``draft`` (analyst pull-back)."""
    catalog = _load_source_catalog(paths["sources"], source)
    result = _resolve_table_column(catalog, table, column, schema)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Column '{column}' not found in '{source}.{table}'")
    _, resolved_schema, _ = result
    _require_pg_refdata()

    key = _refdata_key(source, resolved_schema, table, column)
    outcome = reference_code_repo.revoke_codes(
        key, body.codes, actor=body.actor, actor_role=body.actor_role)
    audit_store.log_business(
        event_type=audit_events.ELEMENT_STATE_CHANGED,
        subject_type="element",
        subject_id=f"{source}:{resolved_schema}.{table}.{column}",
        payload={
            "event": "reference_codes_revoked",
            "source": source, "schema": resolved_schema, "table": table, "column": column,
            "revoked": outcome["revoked"],
        },
    )
    rows = reference_code_repo.get_codes(key)
    return {**outcome, "codes": rows, "set_badge": set_badge(rows)}


@router.post("/{source}/{table}/{column}/reference-data/remove-codes")
async def remove_reference_codes(
    source: str,
    table: str,
    column: str,
    body: ReferenceCodeActionRequest,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    audit_store: AuditStore = Depends(get_audit_store),
    reference_code_repo: ReferenceCodeRepo = Depends(get_reference_code_repo),
):
    """Remove editable (``empty`` / ``draft``) codes outright; frozen rows are skipped."""
    catalog = _load_source_catalog(paths["sources"], source)
    result = _resolve_table_column(catalog, table, column, schema)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Column '{column}' not found in '{source}.{table}'")
    _, resolved_schema, _ = result
    _require_pg_refdata()

    key = _refdata_key(source, resolved_schema, table, column)
    outcome = reference_code_repo.remove_codes(
        key, body.codes, actor=body.actor, actor_role=body.actor_role)
    audit_store.log_business(
        event_type=audit_events.ELEMENT_STATE_CHANGED,
        subject_type="element",
        subject_id=f"{source}:{resolved_schema}.{table}.{column}",
        payload={
            "event": "reference_codes_removed",
            "source": source, "schema": resolved_schema, "table": table, "column": column,
            "removed": outcome["removed"],
        },
    )
    rows = reference_code_repo.get_codes(key)
    return {**outcome, "codes": rows, "set_badge": set_badge(rows)}


@router.post("/{source}/{table}/{column}/reference-data/approve-codes")
async def approve_reference_codes(
    source: str,
    table: str,
    column: str,
    body: ReferenceCodeActionRequest,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    element_state: ElementStateStore = Depends(get_element_state),
    audit_store: AuditStore = Depends(get_audit_store),
    reference_code_repo: ReferenceCodeRepo = Depends(get_reference_code_repo),
    reference_binding_review_repo=Depends(get_reference_binding_review_repo),
):
    """Steward approves submitted codes — ``in_review`` → ``approved`` (5b.3.2).

    2026-08-16 redesign — ONE COMBINED ACTION (user decision, symmetric with Submit): when the
    field is bound and its binding is currently ``in_review``, this same Approve click also
    approves the binding decision itself, alongside whichever unrecognised codes were selected
    (``body.codes`` may be empty — a pure binding approval with no codes to approve is valid).
    """
    catalog = _load_source_catalog(paths["sources"], source)
    result = _resolve_table_column(catalog, table, column, schema)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Column '{column}' not found in '{source}.{table}'")
    _, resolved_schema, _ = result
    _require_pg_refdata()

    key = _refdata_key(source, resolved_schema, table, column)
    outcome = reference_code_repo.approve_codes(
        key, body.codes, actor=body.actor, actor_role=body.actor_role)

    bound_set_id = element_state.get_reference_binding(source, resolved_schema, table, column)
    binding_approved = False
    if bound_set_id and reference_binding_review_repo.get_status(key) == "in_review":
        reference_binding_review_repo.approve(key, decided_by=body.actor, decided_by_role=body.actor_role)
        binding_approved = True

    audit_store.log_business(
        event_type=audit_events.ELEMENT_STATE_CHANGED,
        subject_type="element",
        subject_id=f"{source}:{resolved_schema}.{table}.{column}",
        payload={
            "event": "reference_codes_approved",
            "source": source, "schema": resolved_schema, "table": table, "column": column,
            "approved": outcome["approved"],
            "binding_approved": binding_approved,
        },
    )
    rows = reference_code_repo.get_codes(key)
    return {**outcome, "codes": rows, "set_badge": set_badge(rows), "binding_approved": binding_approved}



# ── Definition governance endpoints ─────────────────────────────────────────


class SubmitDefinitionRequest(BaseModel):
    submitted_by: str | None = None
    submitted_by_role: str | None = None


class ApproveDefinitionRequest(BaseModel):
    decided_by: str | None = None
    decided_by_role: str | None = None


class RejectDefinitionRequest(BaseModel):
    decided_by: str | None = None
    decided_by_role: str | None = None
    reason: str | None = None


@router.post("/{source}/{table}/{column}/submit")
async def submit_definition_for_review(
    source: str,
    table: str,
    column: str,
    body: SubmitDefinitionRequest | None = None,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    element_state: ElementStateStore = Depends(get_element_state),
    semantic_store: SemanticTypeStore = Depends(get_semantic_type_store),
    audit_store: AuditStore = Depends(get_audit_store),
):
    """Submit a definition for steward review.

    Records submitted_at and submitted_by in the submission_overlay.
    Gated on description + business name + an Accepted semantic type, matching the
    frontend's own submitGateMet and the same 409 precedent as submit_reference_codes.
    """
    catalog = _load_source_catalog(paths["sources"], source)
    result = _resolve_table_column(catalog, table, column, schema)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Column '{column}' not found in '{source}.{table}'")
    _, resolved_schema, _ = result

    description = element_state.get_description(source, resolved_schema, table, column)
    business_name = element_state.get_business_name(source, resolved_schema, table, column)
    record = semantic_store.get(source, resolved_schema, table, column)
    if not ((description or "").strip() and (business_name or "").strip() and record and record.get("accepted_at")):
        raise HTTPException(
            status_code=409,
            detail="A description, a business name, and an Accepted semantic type are required before submitting.",
        )

    payload = body or SubmitDefinitionRequest()
    element_state.submit_for_review(
        source, resolved_schema, table, column, submitted_by=payload.submitted_by,
        submitted_by_role=payload.submitted_by_role,
    )

    # B1 D1: open a new Interpretation Set submission history window (no-op while
    # semantic_backend stays 'yaml' -- see SemanticTypeStore.record_submission). The
    # accepted snapshot is read straight off the current record inside the repo itself;
    # only the machine's own, possibly-overridden opinion needs to be supplied here.
    deduced = record.get("system_deduced_type") or {
        "type_id": record.get("type_id"),
        "domain_role": record.get("domain_role"),
        "confidence": record.get("confidence"),
    }
    semantic_store.record_submission(
        source, resolved_schema, table, column,
        deduced_type_id=deduced.get("type_id") or record.get("type_id") or "unresolved",
        deduced_domain_role=deduced.get("domain_role"),
        deduced_confidence=deduced.get("confidence"),
        deduced_tier=record.get("tier"),
        deduced_resolver_version=record.get("resolver_version"),
        submitted_by=payload.submitted_by,
    )

    audit_store.log_business(
        event_type=audit_events.ELEMENT_DEFINITION_SUBMITTED,
        subject_type="element",
        subject_id=f"{source}:{resolved_schema}.{table}.{column}",
        payload={
            "source": source, "schema": resolved_schema, "table": table, "column": column,
            "submitted_by": payload.submitted_by,
        },
    )

    return {
        "source": source,
        "schema": resolved_schema,
        "table": table,
        "column": column,
        "submission": element_state.get_submission_status(source, resolved_schema, table, column),
        "last_status": element_state.get_last_status(source, resolved_schema, table, column),
    }


@router.post("/{source}/{table}/{column}/approve")
async def approve_definition(
    source: str,
    table: str,
    column: str,
    body: ApproveDefinitionRequest | None = None,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    element_state: ElementStateStore = Depends(get_element_state),
    audit_store: AuditStore = Depends(get_audit_store),
):
    """Approve a submitted definition.

    Sets the lifecycle state to 'approved' and records the decision in the overlay.
    """
    catalog = _load_source_catalog(paths["sources"], source)
    result = _resolve_table_column(catalog, table, column, schema)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Column '{column}' not found in '{source}.{table}'")
    _, resolved_schema, _ = result

    payload = body or ApproveDefinitionRequest()
    element_state.approve(source, resolved_schema, table, column, decided_by=payload.decided_by,
                          decided_by_role=payload.decided_by_role)

    audit_store.log_business(
        event_type=audit_events.ELEMENT_DEFINITION_APPROVED,
        subject_type="element",
        subject_id=f"{source}:{resolved_schema}.{table}.{column}",
        payload={
            "source": source, "schema": resolved_schema, "table": table, "column": column,
            "decided_by": payload.decided_by,
            "decided_by_role": payload.decided_by_role,
        },
    )

    return {
        "source": source,
        "schema": resolved_schema,
        "table": table,
        "column": column,
        "lifecycle_state": "approved",
        "submission": element_state.get_submission_status(source, resolved_schema, table, column),
        "last_status": element_state.get_last_status(source, resolved_schema, table, column),
    }


@router.post("/{source}/{table}/{column}/reject")
async def reject_definition(
    source: str,
    table: str,
    column: str,
    body: RejectDefinitionRequest | None = None,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    element_state: ElementStateStore = Depends(get_element_state),
    audit_store: AuditStore = Depends(get_audit_store),
):
    """Reject a submitted definition.

    Reverts the lifecycle state to 'defined' and records the decision (with optional
    reason) in the overlay so the author can iterate.
    """
    catalog = _load_source_catalog(paths["sources"], source)
    result = _resolve_table_column(catalog, table, column, schema)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Column '{column}' not found in '{source}.{table}'")
    _, resolved_schema, _ = result

    payload = body or RejectDefinitionRequest()
    element_state.reject(
        source, resolved_schema, table, column,
        decided_by=payload.decided_by,
        decided_by_role=payload.decided_by_role,
        reason=payload.reason,
    )

    audit_store.log_business(
        event_type=audit_events.ELEMENT_DEFINITION_REJECTED,
        subject_type="element",
        subject_id=f"{source}:{resolved_schema}.{table}.{column}",
        payload={
            "source": source, "schema": resolved_schema, "table": table, "column": column,
            "decided_by": payload.decided_by,
            "decided_by_role": payload.decided_by_role,
            "reason": payload.reason,
        },
    )

    return {
        "source": source,
        "schema": resolved_schema,
        "table": table,
        "column": column,
        "lifecycle_state": "defined",
        "submission": element_state.get_submission_status(source, resolved_schema, table, column),
        "last_status": element_state.get_last_status(source, resolved_schema, table, column),
    }


# ── Phase 5b.1 canonical interpretation-set lifecycle endpoints ──────────────
# The canonical vocabulary (core.lifecycle) endpoints the new Interpretation tab
# drives. They branch to Postgres via the ElementStateStore facade; the legacy
# PATCH /state + per-facet endpoints above stay for YAML mode until the flip.


class SaveInterpretationRequest(BaseModel):
    description: str | None = None
    description_is_ai: bool = False
    business_name: str | None = None
    business_name_is_ai: bool = False
    actor: str | None = None
    actor_role: str | None = None


class WithdrawRequest(BaseModel):
    actor: str | None = None
    actor_role: str | None = None


@router.post("/{source}/{table}/{column}/save")
async def save_interpretation(
    source: str,
    table: str,
    column: str,
    body: SaveInterpretationRequest | None = None,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    element_state: ElementStateStore = Depends(get_element_state),
    audit_store: AuditStore = Depends(get_audit_store),
):
    """Holistic Save of the interpretation set (single 'Save draft' button).

    Persists the Definition and Business Name text (whichever is supplied) and
    advances the set Empty → Draft. Semantic Type and Glossary picks are
    persisted by their own actions and are NOT rewritten here.
    """
    catalog = _load_source_catalog(paths["sources"], source)
    result = _resolve_table_column(catalog, table, column, schema)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Column '{column}' not found in '{source}.{table}'")
    _, resolved_schema, _ = result

    payload = body or SaveInterpretationRequest()
    if payload.description is not None:
        element_state.set_description(source, resolved_schema, table, column,
                                      payload.description, is_ai_generated=payload.description_is_ai)
    if payload.business_name is not None:
        element_state.set_business_name(source, resolved_schema, table, column,
                                        payload.business_name, is_ai_generated=payload.business_name_is_ai)
    element_state.save(source, resolved_schema, table, column,
                       actor=payload.actor, actor_role=payload.actor_role)

    audit_store.log_business(
        event_type=audit_events.ELEMENT_SAVED,
        subject_type="element",
        subject_id=f"{source}:{resolved_schema}.{table}.{column}",
        payload={
            "source": source, "schema": resolved_schema, "table": table, "column": column,
            "actor": payload.actor, "actor_role": payload.actor_role,
        },
    )

    return {
        "source": source,
        "schema": resolved_schema,
        "table": table,
        "column": column,
        "lifecycle_state": element_state.get(source, resolved_schema, table, column),
        "submission": element_state.get_submission_status(source, resolved_schema, table, column),
        "last_status": element_state.get_last_status(source, resolved_schema, table, column),
    }


@router.post("/{source}/{table}/{column}/withdraw")
async def withdraw_interpretation(
    source: str,
    table: str,
    column: str,
    body: WithdrawRequest | None = None,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    element_state: ElementStateStore = Depends(get_element_state),
    audit_store: AuditStore = Depends(get_audit_store),
):
    """Analyst pulls an In-Review submission back → rests in Draft (spontaneous)."""
    catalog = _load_source_catalog(paths["sources"], source)
    result = _resolve_table_column(catalog, table, column, schema)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Column '{column}' not found in '{source}.{table}'")
    _, resolved_schema, _ = result

    payload = body or WithdrawRequest()
    element_state.withdraw(source, resolved_schema, table, column,
                           actor=payload.actor, actor_role=payload.actor_role)

    audit_store.log_business(
        event_type=audit_events.ELEMENT_WITHDRAWN,
        subject_type="element",
        subject_id=f"{source}:{resolved_schema}.{table}.{column}",
        payload={
            "source": source, "schema": resolved_schema, "table": table, "column": column,
            "actor": payload.actor, "actor_role": payload.actor_role,
        },
    )

    return {
        "source": source,
        "schema": resolved_schema,
        "table": table,
        "column": column,
        "lifecycle_state": element_state.get(source, resolved_schema, table, column),
        "submission": element_state.get_submission_status(source, resolved_schema, table, column),
        "last_status": element_state.get_last_status(source, resolved_schema, table, column),
    }


@router.post("/{source}/{table}/{column}/revoke")
async def revoke_interpretation(
    source: str,
    table: str,
    column: str,
    body: WithdrawRequest | None = None,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    element_state: ElementStateStore = Depends(get_element_state),
    audit_store: AuditStore = Depends(get_audit_store),
):
    """Analyst pulls a prior approval back → rests in Draft (re-open for editing)."""
    catalog = _load_source_catalog(paths["sources"], source)
    result = _resolve_table_column(catalog, table, column, schema)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Column '{column}' not found in '{source}.{table}'")
    _, resolved_schema, _ = result

    payload = body or WithdrawRequest()
    element_state.revoke(source, resolved_schema, table, column,
                         actor=payload.actor, actor_role=payload.actor_role)

    audit_store.log_business(
        event_type=audit_events.ELEMENT_REVOKED,
        subject_type="element",
        subject_id=f"{source}:{resolved_schema}.{table}.{column}",
        payload={
            "source": source, "schema": resolved_schema, "table": table, "column": column,
            "actor": payload.actor, "actor_role": payload.actor_role,
        },
    )

    return {
        "source": source,
        "schema": resolved_schema,
        "table": table,
        "column": column,
        "lifecycle_state": element_state.get(source, resolved_schema, table, column),
        "submission": element_state.get_submission_status(source, resolved_schema, table, column),
        "last_status": element_state.get_last_status(source, resolved_schema, table, column),
    }


@router.post("/{source}/{table}/{column}/return")
async def return_interpretation(
    source: str,
    table: str,
    column: str,
    body: RejectDefinitionRequest | None = None,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    element_state: ElementStateStore = Depends(get_element_state),
    audit_store: AuditStore = Depends(get_audit_store),
):
    """Steward returns a submission for rework → canonical 'returned' (fix-and-resubmit)."""
    catalog = _load_source_catalog(paths["sources"], source)
    result = _resolve_table_column(catalog, table, column, schema)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Column '{column}' not found in '{source}.{table}'")
    _, resolved_schema, _ = result

    payload = body or RejectDefinitionRequest()
    element_state.reject(source, resolved_schema, table, column,
                         decided_by=payload.decided_by, decided_by_role=payload.decided_by_role,
                         reason=payload.reason)

    audit_store.log_business(
        event_type=audit_events.ELEMENT_RETURNED,
        subject_type="element",
        subject_id=f"{source}:{resolved_schema}.{table}.{column}",
        payload={
            "source": source, "schema": resolved_schema, "table": table, "column": column,
            "decided_by": payload.decided_by, "decided_by_role": payload.decided_by_role,
            "reason": payload.reason,
        },
    )

    return {
        "source": source,
        "schema": resolved_schema,
        "table": table,
        "column": column,
        "lifecycle_state": element_state.get(source, resolved_schema, table, column),
        "submission": element_state.get_submission_status(source, resolved_schema, table, column),
        "last_status": element_state.get_last_status(source, resolved_schema, table, column),
    }


@router.post("/{source}/{table}/{column}/decline")
async def decline_interpretation(
    source: str,
    table: str,
    column: str,
    body: RejectDefinitionRequest | None = None,
    schema: Optional[str] = Query(default=None),
    paths: dict = Depends(get_paths),
    element_state: ElementStateStore = Depends(get_element_state),
    audit_store: AuditStore = Depends(get_audit_store),
):
    """Steward outright-rejects a submission → canonical 'rejected' (distinct from Return)."""
    catalog = _load_source_catalog(paths["sources"], source)
    result = _resolve_table_column(catalog, table, column, schema)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Column '{column}' not found in '{source}.{table}'")
    _, resolved_schema, _ = result

    payload = body or RejectDefinitionRequest()
    element_state.decline(source, resolved_schema, table, column,
                          decided_by=payload.decided_by, decided_by_role=payload.decided_by_role,
                          reason=payload.reason)

    audit_store.log_business(
        event_type=audit_events.ELEMENT_REJECTED,
        subject_type="element",
        subject_id=f"{source}:{resolved_schema}.{table}.{column}",
        payload={
            "source": source, "schema": resolved_schema, "table": table, "column": column,
            "decided_by": payload.decided_by, "decided_by_role": payload.decided_by_role,
            "reason": payload.reason,
        },
    )

    return {
        "source": source,
        "schema": resolved_schema,
        "table": table,
        "column": column,
        "lifecycle_state": element_state.get(source, resolved_schema, table, column),
        "submission": element_state.get_submission_status(source, resolved_schema, table, column),
        "last_status": element_state.get_last_status(source, resolved_schema, table, column),
    }


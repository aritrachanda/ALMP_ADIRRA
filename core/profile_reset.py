"""Profile-reset orchestrator (openspec/changes/add-profile-reset).

Returns a dataset/table, or an entire source, to the same pre-profiling shape a freshly
onboarded (never profiled) table already has: catalog stats nulled back to schema-only,
semantic types/DQ scores/Interpretation lifecycle+content/Reference Data soft-reset (SCD2
history windows closed, current rows blanked — D9), and reference-set bindings/binding-review/
annotations hard-deleted (they have no history table of their own).

Deliberately FastAPI-free (D1) — ``core/`` never imports FastAPI anywhere in this codebase.
Every store's clear call takes the SAME caller-managed SQLAlchemy session (D3): a table-level
reset opens one transaction for that table; a source-level reset opens ONE transaction spanning
every table in the source (user decision — a source-level reset is all-or-nothing for the whole
source, not per table). Nothing commits until the very end of the call, so a failure anywhere
rolls back everything that call touched — no bespoke undo logic, because nothing was ever
committed in the first place.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from core.annotation_repo import AnnotationRepo
from core.catalog_db import load_catalog
from core.catalog_db.repository import clear_table_stats
from core.dq_score_repo import DQScoreRepo
from core.element_content_repo import ElementContentRepo
from core.element_lifecycle_repo import ElementLifecycleRepo
from core.glossary_db.db import session_scope
from core.reference_binding_review_repo import ReferenceBindingReviewRepo
from core.reference_code_repo import ReferenceCodeRepo
from core.reference_set_repo import ReferenceSetRepo
from core.semantic_type_repo import SemanticTypeRepo

logger = logging.getLogger(__name__)

#: Called after each store's clear step with (step_name, detail_dict) — purely observational
#: (D6): nothing commits until the whole reset_table/reset_source call finishes, so this is not
#: a sequence of small committed steps, just progress reporting for the SSE layer (Section 4).
ProgressCallback = Callable[[str, dict[str, Any]], None]

#: Child-before-parent clear order (D2): every non-catalog store first, catalog stats last — the
#: catalog is both the column list this whole pass enumerates from and the sole "is this
#: profiled at all" signal (D11), so it is the last thing to change.
STEPS: tuple[str, ...] = (
    "dq_score", "semantic_type", "reference_code", "reference_set_binding",
    "reference_binding_review", "interpretation_lifecycle", "interpretation_content",
    "annotations", "catalog",
)


def _table_columns(catalog: dict, schema: str | None, table: str) -> list[str]:
    """Column names for one table, read from an already-loaded catalog dict.

    D2: columns are enumerated from the catalog BEFORE any store — including the catalog
    itself — is cleared, since the catalog is the only place that still has the column list
    once its own stats are nulled.
    """
    for sch in catalog.get("schemas", []) or []:
        if (sch.get("name") or "") != (schema or ""):
            continue
        for tbl in sch.get("tables", []) or []:
            if (tbl.get("table_name") or tbl.get("name")) == table:
                return [c["name"] for c in (tbl.get("columns") or []) if c.get("name")]
    return []


def _clear_table_in_session(
    session, source: str, schema: str | None, table: str, catalog: dict, *,
    actor: str | None = None, on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Run every store's clear for ONE table using *session* — never commits (D3).

    The caller (:func:`reset_table` or :func:`reset_source`) owns the transaction boundary, so
    this function can be called once per table inside either a single-table transaction or one
    shared, whole-source transaction.
    """
    def _emit(step: str, detail: Any) -> None:
        if on_progress is not None:
            on_progress(step, {"source": source, "schema": schema, "table": table, "detail": detail})

    result: dict[str, Any] = {
        "source": source, "schema": schema, "table": table,
        "columns": len(_table_columns(catalog, schema, table)),
    }

    n = DQScoreRepo().clear_for_table(session, source, schema, table)
    result["dq_score"] = n
    _emit("dq_score", n)

    n = SemanticTypeRepo().clear_for_table(session, source, schema, table)
    result["semantic_type"] = n
    _emit("semantic_type", n)

    n = ReferenceCodeRepo().clear_for_table(session, source, schema, table)
    result["reference_code"] = n
    _emit("reference_code", n)

    n = ReferenceSetRepo().clear_for_table(session, source, schema, table)
    result["reference_set_binding"] = n
    _emit("reference_set_binding", n)

    n = ReferenceBindingReviewRepo().clear_for_table(session, source, schema, table)
    result["reference_binding_review"] = n
    _emit("reference_binding_review", n)

    n = ElementLifecycleRepo().clear_for_table(session, source, schema, table, actor=actor)
    result["interpretation_lifecycle"] = n
    _emit("interpretation_lifecycle", n)

    content_result = ElementContentRepo().clear_for_table(session, source, schema, table)
    result["interpretation_content"] = content_result
    _emit("interpretation_content", content_result)

    anno_result = AnnotationRepo().clear_for_table(session, source, schema, table)
    result["annotations"] = anno_result
    _emit("annotations", anno_result)

    # Catalog is cleared LAST (D2): every other store's clear above has already read whatever it
    # needed (the column list came from *catalog*, loaded before this function ran), so the
    # catalog — the sole "is this profiled" signal (D11) — only changes once everything that
    # depended on the old profile has already been cleared.
    catalog_result = clear_table_stats(session, source, schema or "", table, triggered_by=actor)
    result["catalog"] = catalog_result
    _emit("catalog", catalog_result)

    return result


def _log_reset_audit(
    *, scope: str, source: str, schema: str | None, table: str | None,
    actor: str | None, result: dict[str, Any],
) -> None:
    """Log one audit event per reset call. Append-only (user decision): this only ADDS an
    event describing the reset; it never touches — let alone deletes — any prior audit event.
    """
    try:
        from core.audit import get_current_store
        store = get_current_store()
        if store is None:
            return
        subject_id = source if table is None else f"{source}|{schema or ''}|{table}"
        store.log_business(
            "profile_reset", "dataset" if table else "source", subject_id,
            {"scope": scope, "source": source, "schema": schema, "table": table, "result": result},
            actor_user_id=actor,
        )
    except Exception:
        logger.exception("Failed to log profile-reset audit event (scope=%r, source=%r)", scope, source)


def reset_table(
    source: str, schema: str | None, table: str, *, catalog: dict | None = None,
    actor: str | None = None, on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Reset one dataset/table back to a pre-profiling baseline.

    Opens ONE transaction (D3): every store's clear for this table runs inside it, and it
    commits only once, at the very end. Any failure rolls back everything for this table — no
    partial reset is possible. Idempotent: calling this again on already-blank data is a
    no-op success (every underlying ``clear_for_table`` already guarantees that).
    """
    if catalog is None:
        catalog = load_catalog(source, kind="source")
    with session_scope() as s:
        result = _clear_table_in_session(
            s, source, schema, table, catalog, actor=actor, on_progress=on_progress,
        )
    _log_reset_audit(scope="table", source=source, schema=schema, table=table,
                     actor=actor, result=result)
    return result


def reset_source(
    source: str, *, actor: str | None = None, on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Reset every table in *source* back to a pre-profiling baseline.

    Opens ONE transaction spanning EVERY table (D3, user decision) — a source-level reset is
    all-or-nothing for the whole source, not per table: a single failing table rolls back every
    table's work, not just its own.
    """
    catalog = load_catalog(source, kind="source")
    tables: list[tuple[str | None, str]] = []
    for sch in catalog.get("schemas", []) or []:
        schema_name = sch.get("name") or None
        for tbl in sch.get("tables", []) or []:
            table_name = tbl.get("table_name") or tbl.get("name")
            if table_name:
                tables.append((schema_name, table_name))

    per_table: list[dict[str, Any]] = []
    with session_scope() as s:
        for schema, table in tables:
            per_table.append(
                _clear_table_in_session(
                    s, source, schema, table, catalog, actor=actor, on_progress=on_progress,
                )
            )

    result = {"source": source, "table_count": len(tables), "tables": per_table}
    _log_reset_audit(scope="source", source=source, schema=None, table=None,
                     actor=actor, result=result)
    return result

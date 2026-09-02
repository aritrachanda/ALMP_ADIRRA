"""DQ scoring service — gather, score, persist, and re-score on events.

Ties the pure scorer (``core.dq_scorer``) to the live governance stores and
the score store (``core.dq_score_store``). Kept in ``core`` and dependency-
injected so it imports no ``api`` module: the column-data loader and the
optional glossary/reference-data providers are passed in by ``api.main`` at
wire-up.

Score-on-write (DQ §16.2): scoring happens on an explicit event — here, a
semantic type accept — never on a read path. The event subscription is
exception-isolated so a DQ failure can never break a semantic disposition.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Literal

from core import governance_events
from core.audit import events as audit_events
from core.dq_config import DQScoringConfig
from core.dq_dataset_scorer import DATASET_BREAKDOWN_VERSION, score_dataset
from core.dq_score_store import DQScoreStore
from core.dq_scorer import BREAKDOWN_VERSION, score_column
from core.element_state import ElementStateStore
from core.semantic_type_store import SemanticTypeStore

logger = logging.getLogger(__name__)

# (col_dict, tbl_dict) or None if the column can't be located in the catalog.
ColumnLoader = Callable[[str, str | None, str, str], "tuple[dict, dict | None] | None"]
# tbl_dict or None if the table can't be located in the catalog.
DatasetLoader = Callable[[str, str | None, str], "dict | None"]
GovProvider = Callable[[str, str | None, str, str], "dict | None"]

# Governance events the DQ store subscribes to (U0 event names). No more REJECTED
# subscription (2026-08-20, tech-debt #13/#36/#45) -- semantic-type rejection was
# confirmed dead code with zero UI callers, so this event could never actually fire.
_ACCEPTED = audit_events.SEMANTIC_TYPE_ACCEPTED
_SCOPE_CHANGED = audit_events.ASSESSMENT_SCOPE_CHANGED

# Per-column DQ progress status (honest — DQ has no data-fingerprint recheck, only
# never-scored vs a scorer/rules-version bump vs an unchanged cache hit; see the
# fingerprint-vs-DQ asymmetry noted in docs/tech-debt.md).
DQProgressStatus = Literal["recheck", "first_time", "cache_hit"]


class DQScoringService:
    def __init__(
        self,
        *,
        dq_store: DQScoreStore,
        element_state: ElementStateStore,
        semantic_store: SemanticTypeStore,
        config: DQScoringConfig,
        column_loader: ColumnLoader,
        dataset_loader: DatasetLoader | None = None,
        glossary_provider: GovProvider | None = None,
        refdata_provider: GovProvider | None = None,
        findings_provider: GovProvider | None = None,
    ) -> None:
        self._dq = dq_store
        self._state = element_state
        self._semantic = semantic_store
        self._config = config
        self._load_column = column_loader
        self._load_dataset = dataset_loader
        self._glossary_provider = glossary_provider
        self._refdata_provider = refdata_provider
        self._findings_provider = findings_provider

    def batch(self):
        """Coalesce all score writes within the block into one atomic file write.

        Passthrough to the store's ``batch()`` so callers that score many
        columns/tables (e.g. a source overview roll-up) write the file once
        instead of once per record.
        """
        return self._dq.batch()

    # ── gather ───────────────────────────────────────────────────────────────

    def _gather(self, source: str, schema: str | None, table: str, column: str,
                col_dict: dict) -> dict[str, Any]:
        state = self._state
        description = state.get_description(source, schema, table, column) or col_dict.get("description")
        metadata = state.get_metadata(source, schema, table, column) or {}
        lifecycle = state.get(source, schema, table, column)
        definition = {
            "present": bool(description and str(description).strip()),
            "is_ai": bool(metadata.get("is_ai_generated")),
            "lifecycle": lifecycle,
        }

        business_value = state.get_business_name(source, schema, table, column)
        if business_value:
            bn_source = "ai_or_auto" if metadata.get("business_name_is_ai") else "human"
        else:
            bn_source = "none"
        business_name = {"value": business_value, "source": bn_source}

        intent = {
            "nullability": metadata.get("nullability"),
            "date_role": metadata.get("date_role"),
            "criticality": metadata.get("criticality"),
            "placeholder_exceptions": metadata.get("placeholder_exceptions"),
        }

        semantic_record = self._semantic.get(source, schema, table, column)
        glossary = self._glossary_provider(source, schema, table, column) if self._glossary_provider else None
        reference_data = self._refdata_provider(source, schema, table, column) if self._refdata_provider else None

        findings: list[dict] = []
        if self._findings_provider:
            findings = list(self._findings_provider(source, schema, table, column) or [])
        # F4 — a semantic type/value conflict routes into Validity as a rule finding.
        if semantic_record and semantic_record.get("type_value_conflict"):
            findings.append({
                "severity": "attention", "category": "validity", "provenance": "rule",
                "rationale": "semantic type/value conflict",
            })

        return {
            "definition": definition,
            "business_name": business_name,
            "intent": intent,
            "semantic_record": semantic_record,
            "glossary": glossary,
            "reference_data": reference_data,
            "findings": findings,
            "assessment_scope": state.get_assessment_scope(source, schema, table, column),
        }

    @staticmethod
    def _signal_snapshot(col_dict: dict, gathered: dict, breakdown: dict) -> dict[str, Any]:
        """Canonical snapshot of every scored input (DQ §16.3) — drives the fingerprint."""
        semantic = gathered.get("semantic_record") or {}
        profiler_fields = (
            "row_count", "null_count", "distinct_count", "uniqueness_pct", "duplicate_count",
            "empty_string_count", "placeholder_count", "inferred_pattern", "pattern_confidence",
            "invalid_format_count", "type_mismatch_count", "future_date_count", "suspicious_date_count",
            "numeric_stddev", "numeric_avg", "numeric_median", "numeric_outlier_count",
            "code_values", "top_values", "validator_pass_rates", "constant_run_warning", "data_type",
        )
        return {
            "profiler": {f: col_dict.get(f) for f in profiler_fields},
            "definition": gathered.get("definition"),
            "business_name": gathered.get("business_name"),
            "glossary": gathered.get("glossary"),
            "reference_data": gathered.get("reference_data"),
            "intent": gathered.get("intent"),
            "assessment_scope": gathered.get("assessment_scope"),
            "semantic_type": {"state": semantic.get("state"), "type_id": semantic.get("type_id")},
            "archetype": breakdown.get("archetype"),
        }

    # ── score + persist ──────────────────────────────────────────────────────

    def score_and_persist(self, source: str, schema: str | None, table: str,
                          column: str) -> dict[str, Any] | None:
        loaded = self._load_column(source, schema, table, column)
        if not loaded:
            return None
        col_dict, tbl_dict = loaded
        gathered = self._gather(source, schema, table, column, col_dict)

        breakdown = score_column(
            col_dict=col_dict,
            tbl_dict=tbl_dict,
            semantic_record=gathered["semantic_record"],
            definition=gathered["definition"],
            business_name=gathered["business_name"],
            glossary=gathered["glossary"],
            reference_data=gathered["reference_data"],
            intent=gathered["intent"],
            findings=gathered["findings"],
            assessment_scope=gathered["assessment_scope"],
            config=self._config,
        )
        snapshot = self._signal_snapshot(col_dict, gathered, breakdown)
        key = self._dq.key(source, schema, table, column)
        return self._dq.record(key, breakdown, signal_snapshot=snapshot, config=self._config)

    def get_or_score(self, source: str, schema: str | None, table: str,
                     column: str) -> dict[str, Any] | None:
        """Return the latest persisted DQ record, scoring on first view (U2b).

        Read-path safe: serves the stored record when one exists and only
        computes-and-persists the first time a column is viewed with no prior
        score. A stored record written by an older scorer shape (stale
        ``breakdown_version`` — e.g. before U2d's per-line-item
        ``evidence_note``) is re-scored ONCE to heal it, then served from the
        store thereafter. Still write-on-event/first-view — never recomputes on
        every read.
        """
        key = self._dq.key(source, schema, table, column)
        latest = self._dq.latest(key)
        if latest is not None and latest.get("breakdown_version") == BREAKDOWN_VERSION:
            return latest
        return self.score_and_persist(source, schema, table, column)

    def get_or_score_many(
        self, source: str, items: list[tuple[str | None, str, str]],
    ) -> dict[tuple[str | None, str, str], dict[str, Any] | None]:
        """Bulk equivalent of calling ``get_or_score()`` once per ``(schema, table, column)``.

        One bulk read for the whole batch (e.g. every column of a table, or a whole
        source's worth of columns) instead of one Postgres round-trip per column — the
        N+1 cost ``list_tables`` paid calling ``get_or_score`` per column, mirroring A1's
        write-side ``batch()`` on the read side. Falls back to the normal per-column
        ``score_and_persist()`` only for columns genuinely missing a fresh record (first
        view, or a stale ``breakdown_version``) — after first view, that's normally zero
        columns. Returned dict is keyed by the same ``(schema, table, column)`` tuples
        passed in, not the internal store key — callers never need to rebuild that format.
        """
        keys = [self._dq.key(source, schema, table, column) for schema, table, column in items]
        existing = self._dq.latest_many(keys)
        results: dict[tuple[str | None, str, str], dict[str, Any] | None] = {}
        for item, key in zip(items, keys):
            schema, table, column = item
            record = existing.get(key)
            if record is not None and record.get("breakdown_version") == BREAKDOWN_VERSION:
                results[item] = record
            else:
                results[item] = self.score_and_persist(source, schema, table, column)
        return results

    # ── dataset roll-up (§15) ────────────────────────────────────────────────

    def _dataset_members(self, source: str, schema: str | None, table: str,
                         tbl_dict: dict,
                         progress_cb: Callable[[int, int, str, DQProgressStatus], None] | None = None,
                         ) -> tuple[list[dict], dict[str, str]]:
        """Build the per-column roll-up inputs + the in-scope column fingerprints.

        Reads each column's PERSISTED score (scoring on first view — §16.4, the
        store is the cache), never re-profiling. Only in-scope columns
        contribute a fingerprint, so descoping/rescoping a column re-rolls the
        dataset (its fingerprint enters/leaves the dataset signal snapshot).

        ``progress_cb(index, total, column_name, status)`` — when given, reports
        each column's real DQ-scoring status BEFORE the (identical) get_or_score
        call happens, honest and read-only: "first_time" (never scored before),
        "recheck" (scored before, but the scorer's breakdown_version has since
        moved on — a real rules/scorer update, never a fabricated "data changed"
        claim since DQ has no such fingerprint check), or "cache_hit" (scored
        before, unchanged).
        """
        columns: list[dict] = []
        col_fingerprints: dict[str, str] = {}
        all_columns = tbl_dict.get("columns", []) or []
        total_columns = len(all_columns)
        for index, col in enumerate(all_columns):
            name = col.get("name")
            if not name:
                continue
            if progress_cb is not None:
                try:
                    key = self._dq.key(source, schema, table, name)
                    prior = self._dq.latest(key)
                    if prior is None:
                        status: DQProgressStatus = "first_time"
                    elif prior.get("breakdown_version") != BREAKDOWN_VERSION:
                        status = "recheck"
                    else:
                        status = "cache_hit"
                    progress_cb(index + 1, total_columns, name, status)
                except Exception:
                    pass
            record = self.get_or_score(source, schema, table, name) or {}
            scope = self._state.get_assessment_scope(source, schema, table, name)
            in_scope = scope != "out_of_scope"
            meta = self._state.get_metadata(source, schema, table, name) or {}
            columns.append({
                "column": name,
                "state": record.get("state", "unscored"),
                "dq_score": record.get("dq_score"),
                "archetype": record.get("archetype"),
                "criticality": meta.get("criticality") or "standard",
                "in_scope": in_scope,
                # Surfaced on the dataset roll-up's "columns dragging the score
                # down" rows (Polish Batch follow-up) so the lingo there
                # matches the element-level card: grade label/colour + a count
                # of the outstanding improvement actions for that column.
                "grade_label": record.get("grade_label"),
                "grade_color_intent": record.get("grade_color_intent"),
                "action_count": len(record.get("actions") or []),
            })
            if in_scope and record.get("signal_fingerprint"):
                col_fingerprints[name] = record["signal_fingerprint"]
        return columns, col_fingerprints

    @staticmethod
    def _table_signals(tbl_dict: dict) -> dict[str, Any]:
        return {
            "row_count": tbl_dict.get("row_count") or 0,
            "duplicate_count": tbl_dict.get("duplicate_count"),
            "orphan_fk_count": tbl_dict.get("orphan_fk_count"),
            "primary_key": tbl_dict.get("primary_key") or [],
            "has_fk": bool((tbl_dict.get("relations") or [])
                           or (tbl_dict.get("inferred_relations") or [])),
        }

    def score_and_persist_dataset(self, source: str, schema: str | None,
                                  table: str,
                                  progress_cb: Callable[[int, int, str, DQProgressStatus], None] | None = None,
                                  ) -> dict[str, Any] | None:
        """Roll up a table's column scores into one dataset record (§15).

        The dataset ``signal_fingerprint`` is derived from the constituent
        in-scope column fingerprints plus the table-level signals, so any
        member column's score change (or a scope change) bubbles up as a new
        dataset record (§15.4). Reuses the store's append-on-change mechanics.
        """
        if self._load_dataset is None:
            return None
        tbl_dict = self._load_dataset(source, schema, table)
        if not tbl_dict:
            return None
        # One atomic write for the whole table: every member column scored inside
        # _dataset_members plus the dataset record itself flush together on exit.
        with self._dq.batch():
            columns, col_fingerprints = self._dataset_members(source, schema, table, tbl_dict, progress_cb)
            table_signals = self._table_signals(tbl_dict)
            breakdown = score_dataset(columns=columns, table_signals=table_signals, config=self._config)
            snapshot = {
                "column_fingerprints": dict(sorted(col_fingerprints.items())),
                "table_signals": table_signals,
            }
            key = self._dq.dataset_key(source, schema, table)
            return self._dq.record(key, breakdown, signal_snapshot=snapshot, config=self._config)

    def get_or_score_dataset(self, source: str, schema: str | None,
                             table: str,
                             progress_cb: Callable[[int, int, str, DQProgressStatus], None] | None = None,
                             ) -> dict[str, Any] | None:
        """Return the latest persisted dataset record, rolling up on first view.

        Read-path safe: serves the stored record when one exists (and its shape
        is current), rolling up only on first view or after a heal-worthy
        ``breakdown_version`` bump. Member-column changes re-roll via the event
        path, not on every read. ``progress_cb`` (see ``_dataset_members``) only
        fires when a real roll-up happens — a fully cached dataset record is
        served with zero column reads, so honestly reports zero progress events.
        """
        key = self._dq.dataset_key(source, schema, table)
        latest = self._dq.latest(key)
        if latest is not None and latest.get("breakdown_version") == DATASET_BREAKDOWN_VERSION:
            return latest
        return self.score_and_persist_dataset(source, schema, table, progress_cb)

    def dataset_history(self, source: str, schema: str | None,
                        table: str) -> list[dict[str, Any]]:
        """Chronological (oldest→newest) score history for the dataset trend."""
        key = self._dq.dataset_key(source, schema, table)
        return list(reversed(self._dq.history(key)))

    # ── event handling ───────────────────────────────────────────────────────

    def _on_rescore_event(self, payload: dict[str, Any]) -> None:
        """Re-score a single column in response to a governance event.

        Shared by semantic accept (U2) and assessment-scope changes
        (U2c) — a descope makes the column's record ``unscored``; a re-scope
        scores it again. Exception-isolated so a DQ failure can never break the
        disposition that triggered it.
        """
        try:
            self.score_and_persist(
                payload.get("source"), payload.get("schema"),
                payload.get("table"), payload.get("column"),
            )
        except Exception:
            logger.exception("DQ re-score failed for event payload=%r", payload)
        # A member column changed → re-roll its dataset (§15 — a column-level
        # change bubbles up). Isolated so a roll-up failure never breaks the
        # column disposition either.
        try:
            self.score_and_persist_dataset(
                payload.get("source"), payload.get("schema"), payload.get("table"),
            )
        except Exception:
            logger.exception("DQ dataset re-roll failed for event payload=%r", payload)

    def register_subscribers(self) -> None:
        """Subscribe to semantic accept and scope changes so a
        disposition re-scores the affected column."""
        install(self)


# ── module-level idempotent subscription ─────────────────────────────────────
# A single dispatcher is registered per process and forwards to the active
# service. register_once keeps it idempotent across app lifespans, and it
# re-registers cleanly after a governance_events.clear() (test isolation).

_active_service: "DQScoringService | None" = None


def _dispatch(payload: dict[str, Any]) -> None:
    service = _active_service
    if service is not None:
        service._on_rescore_event(payload)


def install(service: "DQScoringService") -> None:
    """Make *service* the active DQ scorer and register the event dispatcher."""
    global _active_service
    _active_service = service
    governance_events.register_once(_ACCEPTED, _dispatch)
    governance_events.register_once(_SCOPE_CHANGED, _dispatch)

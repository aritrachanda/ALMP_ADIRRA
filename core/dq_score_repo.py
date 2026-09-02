"""Postgres-backed repository for DQ column/dataset scores (govern-pg-a1-dq-scores-build).

Mirrors ``core.dq_score_store.DQScoreStore``'s public contract exactly (``key()``,
``dataset_key()``, ``record()``, ``latest()``, ``history()``, ``batch()``). Adds one new,
Postgres-only method, ``as_of()``, for point-in-time lookups.

Real SCD2 (docs/governance-postgres-migration.md §4.4, the standing rule established while
building this slice): ``dq_score`` holds the current record per key with its own ``valid_from``;
``dq_score_history`` holds every superseded record with a real, non-sentinel ``valid_from``/
``valid_to`` window. A window opens/closes on every genuine change to ``dq_score``/``state``/
``signal_fingerprint`` — including a column's ``scored -> unscored`` transition (out of scope or
an emptied table), which plays the same gap-creating role ``reference_code``'s revoke does (see
``core/reference_code_repo.py``, the pattern this module ports).

Synchronous psycopg 3 (route handlers run in FastAPI's threadpool; never call inside an
``async def``).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func, or_, select

from core.dq_config import DQScoringConfig
from core.dq_score_store import DQScoreStore
from core.glossary_db.db import session_scope
from core.shared.models import DqScore, DqScoreHistory

_DEFAULT_MAX_RECORDS = 50


class DQScoreRepo:
    """Data-access for DQ column/dataset scores on Postgres."""

    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = dsn

    # ── keys (pure, stateless — identical shape to DQScoreStore's) ─────────────

    @staticmethod
    def key(source: str, schema: str | None, table: str, column: str) -> str:
        return f"{source}|{schema or ''}|{table}|{column}"

    @staticmethod
    def dataset_key(source: str, schema: str | None, table: str) -> str:
        return f"{source}|{schema or ''}|{table}"

    @staticmethod
    def _key_kind(key: str) -> str:
        return "column" if key.count("|") == 3 else "dataset"

    # ── record shape ─────────────────────────────────────────────────────────

    @staticmethod
    def _to_record(row: DqScore | DqScoreHistory) -> dict[str, Any]:
        """Reconstruct the YAML-shaped record dict: the raw breakdown, plus the promoted
        scored_at/fingerprint columns merged back in — same shape ``DQScoreStore.record()``/
        ``latest()``/``history()`` return in YAML mode (proves task 3.12's parity claim).
        """
        record = dict(row.breakdown)
        record["scored_at"] = row.scored_at.isoformat()
        record["signal_fingerprint"] = row.signal_fingerprint
        record["config_fingerprint"] = row.config_fingerprint
        return record

    # ── writes ───────────────────────────────────────────────────────────────

    def record(
        self,
        key: str,
        breakdown: dict[str, Any],
        *,
        signal_snapshot: dict[str, Any],
        config: DQScoringConfig,
        max_records: int = _DEFAULT_MAX_RECORDS,
    ) -> dict[str, Any]:
        """Persist a score for *key*, appending history only when it genuinely changed (§16.2).

        Opens/closes a real SCD2 window on every change (D4) — including a ``scored -> unscored``
        transition, DQ's own gap-creating event (no manual approve/revoke workflow exists here,
        unlike ``reference_code``). Returns the stored record (existing current when nothing
        changed).
        """
        signal_fp = DQScoreStore.signal_fingerprint(config.model_version, signal_snapshot)
        config_fp = DQScoreStore.config_fingerprint(config)
        state = breakdown.get("state") or "unscored"
        dq_score_value = breakdown.get("dq_score")
        breakdown_version = breakdown.get("breakdown_version")
        now = datetime.now(timezone.utc)

        with session_scope(self._dsn) as s:
            existing = s.execute(
                select(DqScore).where(DqScore.key == key).with_for_update()
            ).scalar_one_or_none()

            if existing is None:
                # First-ever record for this key: valid_from is its own scored_at — a brand-new
                # key has no earlier "true" origination to approximate (unlike reference_code's
                # backfill sentinel, which exists to cover pre-existing data of unknown origin).
                row = DqScore(
                    key=key, key_kind=self._key_kind(key), state=state, dq_score=dq_score_value,
                    grade_label=breakdown.get("grade_label"), breakdown_version=breakdown_version,
                    signal_fingerprint=signal_fp, config_fingerprint=config_fp, breakdown=breakdown,
                    valid_from=now, scored_at=now,
                )
                s.add(row)
                s.flush()
                return self._to_record(row)

            same_signal = existing.signal_fingerprint == signal_fp
            same_score = existing.dq_score == dq_score_value
            same_state = existing.state == state
            if same_signal and same_score and same_state:
                if existing.breakdown_version == breakdown_version:
                    # Genuine no-op: nothing changed, not even the display shape.
                    return self._to_record(existing)
                # Shape-only refresh (e.g. a new evidence_note field the fingerprint can't see):
                # heal the stored breakdown in place, but keep the original scored_at/valid_from
                # — no real-world change happened, so no new window opens.
                existing.breakdown_version = breakdown_version
                existing.breakdown = breakdown
                existing.updated_at = func.now()
                return self._to_record(existing)

            # A genuine change (including scored <-> unscored, DQ's own gap-creating transition):
            # close the outgoing version into history, then open a new current window.
            self._close_current_into_history(s, existing, valid_to=now)
            existing.state = state
            existing.dq_score = dq_score_value
            existing.grade_label = breakdown.get("grade_label")
            existing.breakdown_version = breakdown_version
            existing.signal_fingerprint = signal_fp
            existing.config_fingerprint = config_fp
            existing.breakdown = breakdown
            existing.valid_from = now
            existing.scored_at = now
            existing.updated_at = func.now()
            self._prune_history(s, existing.id, max_records)
            return self._to_record(existing)

    @staticmethod
    def _close_current_into_history(session, row: DqScore, *, valid_to) -> None:
        """Snapshot *row*'s CURRENT fields into ``dq_score_history``, closing that version with a
        real ``valid_to``. Must be called BEFORE the caller mutates *row*.
        """
        session.add(DqScoreHistory(
            dq_score_id=row.id, key=row.key, key_kind=row.key_kind, state=row.state,
            dq_score=row.dq_score, grade_label=row.grade_label,
            breakdown_version=row.breakdown_version, signal_fingerprint=row.signal_fingerprint,
            config_fingerprint=row.config_fingerprint, breakdown=row.breakdown,
            valid_from=row.valid_from, valid_to=valid_to, scored_at=row.scored_at,
        ))

    @staticmethod
    def _prune_history(session, dq_score_id: int, max_records: int) -> None:
        """Keep the oldest (baseline) + latest ``max_records - 1`` history rows for one key,
        delete the middle — reuses ``core.catalog_db.repository._prune_snapshots()``'s exact
        retention rule (D5), adapted to this table's FK/window columns.
        """
        ids = session.execute(
            select(DqScoreHistory.id).where(DqScoreHistory.dq_score_id == dq_score_id)
            .order_by(DqScoreHistory.valid_to.desc())
        ).scalars().all()
        if len(ids) <= max_records:
            return
        baseline = ids[-1]
        keep = set(ids[: max_records - 1])
        keep.add(baseline)
        to_delete = [i for i in ids if i not in keep]
        if to_delete:
            session.execute(delete(DqScoreHistory).where(DqScoreHistory.id.in_(to_delete)))

    # ── reads ────────────────────────────────────────────────────────────────

    def latest(self, key: str) -> dict[str, Any] | None:
        with session_scope(self._dsn) as s:
            row = s.execute(select(DqScore).where(DqScore.key == key)).scalar_one_or_none()
            return self._to_record(row) if row is not None else None

    def latest_many(self, keys: list[str]) -> dict[str, dict[str, Any]]:
        """Bulk equivalent of calling ``latest()`` once per key — one query, not N.

        Built for callers scoring/reading every column of a table (or source) at once
        (e.g. ``list_tables``'s DQ badges): the single-key ``latest()`` loop this replaces
        opened one Postgres round-trip per column, exactly the cost the YAML store's
        whole-file-in-memory read never had. Missing keys are simply absent from the
        returned dict (never a ``None`` placeholder), same "not found" contract as
        ``latest()`` returning ``None``.
        """
        if not keys:
            return {}
        with session_scope(self._dsn) as s:
            rows = s.execute(select(DqScore).where(DqScore.key.in_(keys))).scalars().all()
            return {row.key: self._to_record(row) for row in rows}

    def history(self, key: str) -> list[dict[str, Any]]:
        """Chronological history, newest first — current record, then every superseded version
        in descending order, exactly matching ``DQScoreStore``'s single-list YAML shape.
        """
        with session_scope(self._dsn) as s:
            current = s.execute(select(DqScore).where(DqScore.key == key)).scalar_one_or_none()
            records = [self._to_record(current)] if current is not None else []
            hist_rows = s.execute(
                select(DqScoreHistory).where(DqScoreHistory.key == key)
                .order_by(DqScoreHistory.valid_to.desc())
            ).scalars().all()
            records.extend(self._to_record(h) for h in hist_rows)
            return records

    def as_of(self, key: str, as_of_date) -> dict[str, Any] | None:
        """Return the score/grade applicable at *as_of_date* (a point-in-time lookup).

        Checks the current row first: only when its ``state`` is ``"scored"`` AND
        ``as_of_date >= valid_from`` — a column currently sitting ``unscored`` (out-of-scope/
        empty-table gap) must never leak a stale ``valid_from`` as a false-positive answer for a
        date inside that gap (D4, mirrors ``reference_code_repo.as_of()``'s ``status ==
        "approved"`` guard). Otherwise searches ``dq_score_history`` for a window covering the
        date. Returns ``None`` ("not found") if neither matches.
        """
        with session_scope(self._dsn) as s:
            row = s.execute(select(DqScore).where(DqScore.key == key)).scalar_one_or_none()
            if row is None:
                return None
            if row.state == "scored" and as_of_date >= row.valid_from:
                record = self._to_record(row)
                record["valid_from"] = row.valid_from
                record["valid_to"] = None
                return record
            hist = s.execute(
                select(DqScoreHistory).where(
                    DqScoreHistory.key == key,
                    DqScoreHistory.valid_from <= as_of_date,
                    DqScoreHistory.valid_to > as_of_date,
                )
            ).scalar_one_or_none()
            if hist is None:
                return None
            record = self._to_record(hist)
            record["valid_from"] = hist.valid_from
            record["valid_to"] = hist.valid_to
            return record

    # ── add-profile-reset: soft-reset (D9) — never opens its own transaction ────

    def clear_for_table(self, session, source: str, schema: str | None, table: str) -> int:
        """Soft-reset every DQ score for this table (column-level rows AND its own
        dataset-level rollup row): writes ``state='unscored'`` — the same gap-creating
        transition ``record()`` already produces for an out-of-scope/emptied column — after
        closing the outgoing version into ``dq_score_history`` first. Nothing is hard-deleted.

        Takes a caller-managed *session* (D3) — unlike ``record()``, never opens its own
        ``session_scope()``, so the reset orchestrator can wrap it in one shared transaction
        with every other store's clear. Returns the number of rows actually cleared
        (already-unscored rows are skipped, keeping repeated calls idempotent).
        """
        dataset_key = self.dataset_key(source, schema, table)
        column_prefix = f"{dataset_key}|"
        now = datetime.now(timezone.utc)
        rows = session.execute(
            select(DqScore)
            .where(or_(DqScore.key == dataset_key, DqScore.key.like(f"{column_prefix}%")))
            .with_for_update()
        ).scalars().all()

        cleared = 0
        for row in rows:
            if row.state == "unscored":
                continue
            self._close_current_into_history(session, row, valid_to=now)
            row.state = "unscored"
            row.dq_score = None
            row.grade_label = None
            row.breakdown_version = None
            row.breakdown = {"state": "unscored", "reason": "profile_reset"}
            row.signal_fingerprint = None
            row.config_fingerprint = None
            row.valid_from = now
            row.scored_at = now
            row.updated_at = now
            cleared += 1
        return cleared

    def clear_for_source(self, session, source: str) -> int:
        """Soft-reset every DQ score for *source* — see :meth:`clear_for_table`."""
        prefix = f"{source}|"
        keys = session.execute(
            select(DqScore.key).where(DqScore.key.like(f"{prefix}%"))
        ).scalars().all()
        tables = {
            (parts[1] or None, parts[2])
            for parts in (k.split("|") for k in keys)
            if len(parts) >= 3
        }
        return sum(self.clear_for_table(session, source, schema, table) for schema, table in tables)

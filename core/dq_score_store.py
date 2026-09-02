"""Postgres-backed store for DQ scores (Postgres-only since Slice F of the governance
YAML->Postgres migration).

Each key maps to a history list (latest first) — a new record is appended only
when the score or the signal fingerprint actually changed (DQ §16.2–16.3), so
config-hash churn or a no-op re-profile never bloats history. History is bounded
by ``history_retention`` (default: last 50, always keep the first/baseline).

Keys: ``source|schema|table|column`` for columns (``key``) and
``source|schema|table`` for dataset roll-ups (``dataset_key``).

The legacy ``governance/dq_scores.yaml`` file (and the flaky Windows ``os.replace`` retry it
needed) was retired once ``dq_backend`` had been live on Postgres and stable; the file is
archived, not deleted (see ``docs/governance-postgres-migration.md``).
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

from core.dq_config import DQScoringConfig


class _NULL_BATCH:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class DQScoreStore:
    def __init__(self, path: Path | None = None) -> None:
        """*path* is accepted (and ignored) for call-site compatibility with the pre-Postgres
        signature — every caller still passes it."""
        self._repo_instance = None

    def _repo(self):
        if self._repo_instance is None:
            from core.dq_score_repo import DQScoreRepo
            self._repo_instance = DQScoreRepo()
        return self._repo_instance

    def batch(self):
        """No-op context manager — each ``record()`` call is already a small, isolated
        upsert, so there is no whole-file cost to coalesce. Kept so callers written for the
        old YAML-batching behaviour need no changes."""
        return _NULL_BATCH()

    @staticmethod
    def key(source: str, schema: str | None, table: str, column: str) -> str:
        return f"{source}|{schema or ''}|{table}|{column}"

    @staticmethod
    def dataset_key(source: str, schema: str | None, table: str) -> str:
        return f"{source}|{schema or ''}|{table}"

    # ── fingerprints (§16.3) ─────────────────────────────────────────────────

    @staticmethod
    def config_fingerprint(config: DQScoringConfig) -> str:
        canonical = json.dumps(config.raw or {}, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def signal_fingerprint(model_version: str, signal_snapshot: dict[str, Any]) -> str:
        canonical = json.dumps(signal_snapshot, sort_keys=True, default=str)
        return hashlib.sha256(f"{model_version}\n{canonical}".encode("utf-8")).hexdigest()

    # ── reads ────────────────────────────────────────────────────────────────

    def history(self, key: str) -> list[dict[str, Any]]:
        return self._repo().history(key)

    def latest(self, key: str) -> dict[str, Any] | None:
        return self._repo().latest(key)

    def latest_many(self, keys: list[str]) -> dict[str, dict[str, Any]]:
        """Bulk equivalent of ``latest()`` — one Postgres query instead of one per key."""
        return self._repo().latest_many(keys)

    def as_of(self, key: str, as_of_date: date) -> dict[str, Any] | None:
        """Point-in-time lookup."""
        return self._repo().as_of(key, as_of_date)

    # ── writes ───────────────────────────────────────────────────────────────

    def record(
        self,
        key: str,
        breakdown: dict[str, Any],
        *,
        signal_snapshot: dict[str, Any],
        config: DQScoringConfig,
        max_records: int = 50,
    ) -> dict[str, Any]:
        """Persist a score for *key*, appending only when it changed (§16.2).

        Returns the stored record (existing latest when nothing changed).
        """
        return self._repo().record(
            key, breakdown, signal_snapshot=signal_snapshot, config=config, max_records=max_records)


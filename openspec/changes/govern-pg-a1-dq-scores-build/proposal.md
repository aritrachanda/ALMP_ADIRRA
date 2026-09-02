## Why

DQ scores today live in `governance/dq_scores.yaml`, a single append-only file rewritten in full
(atomic temp-file swap) on every scored column or dataset. It is already the biggest governance
YAML file and is parsed in full on every backend startup (~29 seconds on the real `adm` dataset) —
the single largest fixed cost in this migration programme (see `docs/governance-postgres-migration.md`
§2, slice **A1**). This is slice A1 of the eleven-slice plan: build the Postgres-backed store as a
dormant, flag-gated alternative behind `DQScoreStore` — no data moves, no flag flips, no behaviour
change. Slice A2 (a separate, later change) does the migration/parity/flip.

**Decision (2026-08-11, user):** DQ scores get full SCD2 (real `valid_from`/`valid_to` windows and
a point-in-time `as_of(date)` lookup), not just a plain current+history split. Rationale: in a
banking-regulatory context we cannot assume every future corner a historical query might come
from, and must not be caught unable to answer "what was this column's DQ score/grade on date X"
if ever asked. This is now the STANDARD approach for every future governance history table in
this programme (recorded in `docs/governance-postgres-migration.md` §4 as a ground rule), not a
case-by-case call — DQ scores are the first slice built this way, after `reference_code`.

## What Changes

- Add Alembic migration for two new tables: `dq_score` (current record per key, gains a
  `valid_from`) and `dq_score_history` (retired versions, each with a real, non-sentinel
  `valid_from`/`valid_to` window — same shape as `reference_code`/`reference_code_history`), plus
  the same keep-first-plus-latest-N retention rule as the existing YAML pruning, with full
  data-dictionary `COMMENT ON` coverage per the S0 standing rule.
- Add ORM models (`DqScore`, `DqScoreHistory`) to `core/shared/models/governance.py`.
- Add a new `DQScoreRepo` (Postgres-backed), mirroring `DQScoreStore`'s existing public contract
  exactly: `key()`, `dataset_key()`, `record()`, `latest()`, `history()`, `batch()` — plus a new
  `as_of(key, as_of_date)` point-in-time lookup (not on today's YAML store; Postgres-only surface).
- Make `DQScoreStore` itself backend-aware: each public method branches to the new repo when
  `dq_backend() == "postgres"`, else keeps today's YAML logic untouched — same shape as
  `ElementStateStore`'s existing `_use_pg()`/`_repo()` pattern for the lifecycle slice. Callers
  (`core/dq_service.py`, `api/main.py`) are unchanged; the flag defaults to `yaml`.
- Add Postgres-gated tests mirroring `tests/test_dq_score_store.py`'s coverage (fingerprint
  no-op/append policy, retention pruning, dataset vs. column keys) plus new SCD2-specific tests
  (window-closing on change, gap semantics when a column goes out of scope, `as_of()` lookups).

## Capabilities

### New Capabilities
- `dq-score-persistence`: Postgres-backed storage, SCD2 history (real `valid_from`/`valid_to`
  windows), and point-in-time (`as_of`) lookup for DQ column/dataset scores, selectable via a
  `dq_backend` flag (default `yaml`), with byte-identical behaviour to the existing YAML store
  while the flag stays at its default.

### Modified Capabilities
(none — this slice is purely additive; no existing spec-level behavior changes)

## Impact

- New: `db/migrations/versions/0011_add_dq_score.py` (or next available number after S0/
  historize-reference-codes land), `core/dq_score_repo.py`, ORM additions to
  `core/shared/models/governance.py` + re-exports from `core/shared/models/__init__.py`.
- Modified: `core/dq_score_store.py` (backend branch added to every public method, matching the
  `ElementStateStore` pattern — no signature changes).
- Untouched: `core/dq_service.py`, `api/main.py`, `governance/dq_scores.yaml` (remains the live
  source of truth; this slice never migrates data or flips the flag).
- Tests: new `tests/test_dq_score_repo.py` (Postgres-gated, skips if `adm_test` unreachable).

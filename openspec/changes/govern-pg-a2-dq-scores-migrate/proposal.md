## Why

Slice A1 (committed) built the Postgres-backed `dq_score`/`dq_score_history` tables and
`DQScoreRepo`, fully dormant behind `dq_backend` (default `yaml`). This is slice A2: migrate the
real `governance/dq_scores.yaml` data into those tables, prove parity against the live YAML store,
and hand the flip decision to the user. `dq_scores.yaml` is the single largest governance YAML
file today (2,382 keys, 2,460 records, ~18 MB) and is parsed in full on every backend startup
(~29 seconds on the real `adm` dataset) — the biggest fixed cost this whole migration programme
set out to remove (`docs/governance-postgres-migration.md` §2/§5).

## What Changes

- Add `core/dq_score_migrate.py`: reads `governance/dq_scores.yaml`, and for every key writes the
  newest record as the `dq_score` current row and every older record as a `dq_score_history` row,
  with REAL SCD2 windows derived directly from each record's own `scored_at` (no sentinel needed —
  unlike `reference_code`'s backfill, every YAML record already carries a concrete, known
  timestamp of when it was computed, so there is no "true origin predates tracking" ambiguity to
  approximate).
- Add a parity check: every key's current `dq_score`/`state`/`grade_label`/`breakdown_version` and
  `dq_score_history` row count must match what `DQScoreStore.latest()`/`.history()` already return
  from the YAML file — "0 delta" evidence, same standard used for prior slices' migrations.
- Pin `ADM_DQ_BACKEND=yaml` in `tests/conftest.py` — the exact isolation trap that already bit
  glossary and audit (a live `dq_backend: postgres` flag would make backend-unaware tests hit the
  real `adm` database instead of a fixture).
- Run the migration against the real `adm` database and review the parity report (agent-run,
  reviewed by the user — no code changes needed for this step beyond running the script).
- **The user** flips `dq_backend: postgres` in `project.yaml` and restarts — the agent never flips
  this flag (standing rule, `docs/governance-postgres-migration.md` §4.1).

## Capabilities

### New Capabilities
- `dq-score-migration`: a one-time, re-runnable migration of `governance/dq_scores.yaml` into the
  `dq_score`/`dq_score_history` tables A1 built, with a parity check proving every key's current
  score and history depth match exactly before the user flips the backend flag.

### Modified Capabilities
(none — `openspec/specs/dq-score-persistence/` does not exist yet since slice A1's change hasn't
been archived; this proposal does not depend on that step happening first)

## Impact

- New: `core/dq_score_migrate.py` (migration + parity script, CLI entry point mirroring
  `core/reference_code_migrate.py`'s shape), `tests/test_dq_score_migrate.py`.
- Modified: `tests/conftest.py` (pin `ADM_DQ_BACKEND=yaml`).
- Not touched by this slice: `core/dq_service.py`, `api/main.py`, `core/dq_score_store.py`,
  `core/dq_score_repo.py` (all already built in A1) — this slice is data-migration only, no new
  application code paths.
- User-owned, out of this change's automated scope: reviewing the parity report, flipping the
  flag, restarting the backend, and measuring the startup-time improvement.

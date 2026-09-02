## Why

Slice B1 (committed `0f1f1e2`) built the Postgres-backed `semantic_type_assignment` /
`semantic_type_assignment_history` tables and `SemanticTypeRepo`, fully dormant behind
`semantic_backend` (default `yaml`). This is slice B2: migrate the real
`governance/semantic_type_assignments.yaml` data into those tables, prove parity against the live
YAML store, and hand the flip decision to the user.

`semantic_type_assignments.yaml` is the largest remaining governance YAML file now that A1/A2
took DQ scores off YAML. Measured directly against the live file on 2026-08-14:

| Fact | Value |
| --- | --- |
| Records (one per column, 4 sources) | 2,290 |
| File size | 3.05 MB |
| `SemanticTypeStore` construction cost | ~6.5s at every backend startup |
| State distribution | proposed 1,233 · unresolved 586 · suggested 401 · confirmed 70 |
| Records carrying a nested `latest_proposal` | 67 |

That ~6.5-second parse is the dominant remaining fixed backend-startup cost this migration
programme set out to remove, and the same full-file-rewrite-per-column behaviour is the
documented cause of the ~80-second first-visit table stalls (`docs/tech-debt.md`).

## What Changes

- Add `core/semantic_type_migrate.py`: reads `governance/semantic_type_assignments.yaml` and
  writes one `semantic_type_assignment` current row per key, mirroring
  `core/dq_score_migrate.py`'s shape (CLI entry point, `--force`, idempotent by default).
- Add a parity check: every key's migrated row must match what `SemanticTypeStore.get()` already
  returns from the YAML file — "0 delta" evidence, the same standard every prior slice's
  migration was held to.
- Pin `ADM_SEMANTIC_BACKEND=yaml` in `tests/conftest.py` — **already done in B1**, listed here
  only so the isolation guarantee is explicit in this slice's scope (it is the exact trap that
  already bit glossary, audit, and DQ).
- Run the migration against the real `adm` database and present the parity report for review.
- **The user** flips `semantic_backend: postgres` in `project.yaml` and restarts — the agent never
  flips this flag (standing rule, `docs/governance-postgres-migration.md` §4.1).

## Two structural differences from A2 (do not assume A2's shape carries over)

**1. There is no history to migrate.** `dq_scores.yaml` stored a *list* of records per key, so A2
migrated newest→current and older→history. `semantic_type_assignments.yaml` stores exactly **one**
record per key — there is no historical depth in the file at all. And `semantic_type_assignment_history`
only ever opens a row on an Interpretation Set *submission*, a concept that did not exist before
B1. Therefore B2 migrates **current rows only**, and the history table correctly starts **empty**,
filling only from real submissions after the flip. Confirmed by measurement: 0 of 2,290 records
carry a `submitted_at` value.

**2. Four fields in the real data have no column in B1's table.** Enumerated across all 2,290
records (2026-08-14) — this is a genuine coverage gap that must be decided before any data moves,
not silently dropped:

| Field | Records carrying it | In B1's table? |
| --- | --- | --- |
| `score_breakdown` | 2,290 present / **1,703 non-null** | ❌ no column |
| `resolution_reason` | 443 | ❌ no column |
| `nearest_candidates` | 23 | ❌ no column |
| `data_fingerprint` | 49 (legacy, superseded 2026-08-12) | ❌ no column |

Deciding what happens to these four is **the headline open question of this slice** (design.md
D1) and is explicitly *not* pre-decided here.

## Capabilities

### New Capabilities
- `semantic-type-migration`: a one-time, re-runnable migration of
  `governance/semantic_type_assignments.yaml` into the `semantic_type_assignment` table B1 built,
  with a parity check proving every key's migrated record matches the YAML store's output exactly
  before the user flips the backend flag.

### Modified Capabilities
(none — `openspec/specs/semantic-type-persistence/` does not exist yet since slice B1's change
has not been archived; this proposal does not depend on that happening first)

## Impact

- New: `core/semantic_type_migrate.py` (migration + parity script, CLI entry point mirroring
  `core/dq_score_migrate.py`), `tests/test_semantic_type_migrate.py`.
- Possibly modified, pending D1: `db/migrations/versions/` (a new migration adding columns for
  the four uncovered fields), `core/shared/models/governance.py`, `core/semantic_type_repo.py`.
- Not touched: `core/semantic_type_store.py`, `core/semantic_resolver.py`, `api/routes/element.py`
  (all already built//wired in B1) — beyond D1's outcome, this slice is data-migration only.
- User-owned, out of this change's automated scope: reviewing the parity report, flipping the
  flag, restarting the backend, and confirming the startup-time improvement.

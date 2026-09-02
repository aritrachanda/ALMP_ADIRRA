## 1. Schema

- [x] 1.1 Write the next-numbered Alembic migration (after `0010_add_reference_code_history`):
      `CREATE TABLE dq_score` (current record per key) with columns: `id BIGINT PK`, `key TEXT
      NOT NULL UNIQUE`, `key_kind TEXT NOT NULL CHECK (key_kind IN ('column','dataset'))`,
      `state TEXT NOT NULL`, `dq_score INTEGER`, `grade_label TEXT`, `breakdown_version INTEGER`,
      `signal_fingerprint TEXT`, `config_fingerprint TEXT`, `breakdown JSONB NOT NULL`,
      `valid_from TIMESTAMPTZ NOT NULL` (SCD2 — real business-effective date the current record
      took effect; the first-ever record for a key uses its own `scored_at`, since a brand-new
      key has no earlier "true" origination to approximate — see design.md's Non-Goals note on
      why this differs from `reference_code`'s backfill sentinel), `scored_at TIMESTAMPTZ NOT
      NULL`, `created_at`/`updated_at TIMESTAMPTZ`. Landed as `0011_add_dq_score.py`.
- [x] 1.2 In the same migration, `CREATE TABLE dq_score_history` mirroring `dq_score`'s columns
      (same set minus the uniqueness constraint on `key`) plus `dq_score_id BIGINT REFERENCES
      dq_score(id) ON DELETE CASCADE`, `valid_to TIMESTAMPTZ NOT NULL` (real closing timestamp —
      never a placeholder, set the instant a record is superseded), and a
      `CHECK (valid_to > valid_from)` window-integrity constraint (same shape as
      `reference_code_history`). Add indexes: `dq_score(key)`, `dq_score_history(key,
      valid_from)`, `dq_score_history(dq_score_id)`.
- [x] 1.3 Add full `COMMENT ON TABLE`/`COMMENT ON COLUMN` data-dictionary text for both tables,
      per the S0 standing rule.
- [x] 1.4 Add ORM models `DqScore`/`DqScoreHistory` to `core/shared/models/governance.py`,
      re-exported from `core/shared/models/__init__.py`.

## 2. Repository

- [x] 2.1 Create `core/dq_score_repo.py` with a `DQScoreRepo` class: `record(key, breakdown, *,
      signal_snapshot, config, max_records=50)`, `latest(key)`, `history(key)`, `key()`,
      `dataset_key()` — same signatures/return shapes as `DQScoreStore`'s existing methods, plus a
      new `as_of(key, as_of_date)`. `record()` derives `key_kind` from whether the key contains 3
      or 4 `|`-separated segments (matching `key()`/`dataset_key()`'s existing shapes), computes
      fingerprints the same way as `DQScoreStore` (reuse its `signal_fingerprint`/
      `config_fingerprint` static methods rather than duplicating the hashing logic), and applies
      the same no-op/refresh-in-place rules as `DQScoreStore.record()` (§16.2-16.3). On a genuine
      change, closes the outgoing record into `dq_score_history` with `valid_to` = the new
      record's `scored_at`, and sets the new current row's `valid_from` to that same timestamp
      (D4) — including when the change is `scored -> unscored` (out-of-scope/empty-table gap) or
      `unscored -> scored` (re-scope).
- [x] 2.2 Add a `dq_backend()` helper (env `ADM_DQ_BACKEND` first, else cached
      `project.yaml` `database.dq_backend`, default `yaml`) — same shape as
      `core.element_lifecycle_repo.element_backend()`.
- [x] 2.3 Add retention pruning as a SQL delete over `dq_score_history`, reusing
      `core/catalog_db/repository.py::_prune_snapshots()`'s exact "keep baseline + latest N-1"
      pattern (ordered by `valid_to DESC` instead of `captured_at DESC`).
- [x] 2.4 Add `DQScoreRepo.as_of(key, as_of_date)`: check the current `dq_score` row first
      (return it only if `state == "scored"` AND `as_of_date >= valid_from` — the `state` guard
      is required, not optional, per D4/the reference_code D7 precedent, so a mid-gap `unscored`
      row never leaks a false-positive answer); otherwise search `dq_score_history` for a window
      covering `as_of_date`; return "not found" if neither matches.
- [x] 2.5 Wire the backend branch into `DQScoreStore`: add `_use_pg()`/`_repo()` (lazy
      construction) mirroring `ElementStateStore`'s pattern; branch `record()`, `latest()`,
      `history()`, `batch()` to the repo when `dq_backend() == "postgres"`, else keep today's
      YAML logic unchanged. `key()`/`dataset_key()` stay pure static helpers (no branch needed —
      they don't touch storage). `as_of()` is exposed only when the repo is active (no YAML-mode
      equivalent — see design.md D6).
- [x] 2.6 `batch()` in pg mode is a no-op context manager (D7) — yields immediately, no deferred
      writes.

## 3. Tests

- [x] 3.1 First-ever score for a key creates a `dq_score` row (its `valid_from` = its own
      `scored_at`) and zero `dq_score_history` rows. Landed as
      `test_first_ever_score_uses_its_own_scored_at_no_history`.
- [x] 3.2 A changed re-score (different `dq_score`/`state`/`signal_fingerprint`) closes the prior
      record into `dq_score_history` with a real `valid_to`, and updates the current row's
      `valid_from` to that same timestamp. Landed as
      `test_changed_rescore_closes_history_with_real_valid_to`.
- [x] 3.3 An identical re-score (same `dq_score`/`state`/`signal_fingerprint`) creates no history
      row and does not advance `scored_at`/`valid_from`. Landed as
      `test_identical_rescore_creates_no_history_and_does_not_advance`.
- [x] 3.4 An identical re-score with a newer `breakdown_version` refreshes the current row's
      breakdown in place without creating a history row (mirrors `DQScoreStore.record()`'s
      existing "shape-only" refresh case). Landed as
      `test_identical_score_newer_breakdown_version_refreshes_in_place`.
- [x] 3.5 Retention pruning: seeding more than the retention bound worth of history rows for one
      key results in exactly baseline + latest N-1 remaining after a prune. Landed as
      `test_retention_keeps_baseline_and_latest_n_minus_1`.
- [x] 3.6 Column keys (from `key()`) store `key_kind='column'`; dataset keys (from
      `dataset_key()`) store `key_kind='dataset'`. Landed as
      `test_column_and_dataset_keys_store_correct_key_kind`.
- [x] 3.7 A column going out of scope (`scored -> unscored`) closes the outgoing `scored` record
      into `dq_score_history` with a real `valid_to`; a later re-scope (`unscored -> scored`)
      opens a new current window with a real `valid_from`. Landed as
      `test_scored_to_unscored_closes_history_then_rescope_opens_new_window`.
- [x] 3.8 `as_of()` returns the current row for a date on/after its `valid_from` when `state ==
      "scored"`. Landed as `test_as_of_returns_current_row_for_recent_date`.
- [x] 3.9 `as_of()` returns the correct historical row for a date covered by a
      `dq_score_history` window. Landed as `test_as_of_returns_historical_row_for_older_date`
      (also asserts "now" resolves to the current, updated value in the same scenario).
- [x] 3.10 `as_of()` returns "not found" for a date inside an unscored gap, even though the
      current row's `valid_from` predates the requested date (proves the `state == "scored"`
      guard, not just the date comparison). Landed as
      `test_as_of_returns_not_found_inside_unscored_gap`.
- [x] 3.11 `as_of()` returns "not found" for a date before the key's first-ever score. Landed as
      `test_as_of_returns_not_found_before_first_score`.
- [x] 3.12 `DQScoreStore` with `ADM_DQ_BACKEND=postgres` produces identical `record()`/`latest()`/
      `history()` results (same shape, same values) as the same sequence of calls against a fresh
      YAML-backed `DQScoreStore` — a parity check between the two backends' behavior, not their
      storage (proves the "signatures unchanged" claim, not just repo-level unit tests). Landed
      as `test_store_postgres_backend_parity_with_yaml` (sequenced YAML-then-postgres since
      `_use_pg()` reads a process-global env var, not a per-instance flag).
- [x] 3.13 Every existing `tests/test_dq_score_store.py` test still passes unmodified (default
      `yaml` backend, zero regressions). Verified: 13/13 pass unmodified alongside the 12 new
      `tests/test_dq_score_repo.py` tests (25 total).

## 4. Gates and documentation

- [x] 4.1 Run the full backend test suite (server stopped) — expect no regressions. First run:
      582 passed, 1 failed (`test_semantic_type_agent_gating.py::test_include_ai_true_failure_is_
      non_fatal`) — confirmed via isolated re-run (4/4 pass) to be the SAME pre-existing,
      order-dependent flake already documented during `govern-pg-s0-foundations`'s gate, not
      caused by this slice (dq_score code touches nothing semantic-type-related). Logged the
      recurrence in `docs/tech-debt.md`/`/memories/repo/tech-debt.md`. Migration `0011_add_dq_
      score` also applied and verified live against the real `adm` database (schema/comments
      correct, both tables empty — fully dormant, matching the design).
- [x] 4.2 Update `/memories/repo/postgres-migration.md` (or a dedicated repo-memory note) and this
      change's status once shipped.
- [x] 4.3 STOP for user review — do not commit. This slice ships fully dormant (`dq_backend`
      stays `yaml`), so there is no live-database flip decision here, but the user still reviews
      before it lands, matching the established per-slice pattern.

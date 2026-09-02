## 1. Migration script

- [x] 1.1 Create `core/dq_score_migrate.py` mirroring `core/reference_code_migrate.py`'s shape:
      `_load(yaml_path)`, `migrate_dq_scores(*, yaml_path=..., dsn=None, force=False) -> dict`
      (stats: `keys`, `current_written`, `history_written`, `skipped_existing`), a CLI entry point.
- [x] 1.2 For each key (sorted, deterministic order): load its YAML record list (newest first).
      Reuse `DQScoreRepo._key_kind(key)` for the `key_kind` column (D4) — do not re-derive the
      rule. Skip the key entirely if a `dq_score` row already exists for it and `force=False`
      (D5).
- [x] 1.3 Write the newest record (index 0) as the `dq_score` current row: `valid_from` = that
      record's own `scored_at` (parsed from its ISO string), all other fields copied directly
      (`state`, `dq_score`, `grade_label`, `breakdown_version`, `signal_fingerprint`,
      `config_fingerprint`, and the full record dict as `breakdown`).
- [x] 1.4 Write every older record (index > 0) as a `dq_score_history` row: `valid_from` = that
      record's own `scored_at`; `valid_to` = the NEXT-NEWER record's `scored_at` (index `i-1`'s
      `scored_at`) — per D1, never a placeholder, always derived from real YAML timestamps.
- [x] 1.5 `--force`: truncate `dq_score` (cascades to `dq_score_history` via the FK) for the keys
      being migrated before writing, mirroring `reference_code_migrate.py`'s truncate-then-reload
      pattern.
- [x] 1.6 Add `parity_rows(*, yaml_path=...) -> list[dict]`: for every key, compare the freshly-
      migrated Postgres data (queried directly, not through `DQScoreStore`) against
      `DQScoreStore.latest(key)`/`.history(key)` called in YAML mode — report `key`, `match`
      (bool), and which field(s) differ if not matching (D3).

## 2. Tests

- [x] 2.1 Postgres-gated test file `tests/test_dq_score_migrate.py` (skip if unreachable, same
      `adm_test` pattern as `tests/test_dq_score_repo.py`) using a synthetic YAML fixture (not the
      real 2,382-key file) covering: a single-record key, a multi-record key (proves window
      derivation), a dataset key, and re-running with/without `--force`.
- [x] 2.2 Parity check test: seed a YAML fixture, migrate, assert `parity_rows()` reports 100%
      match for every key.
- [x] 2.3 Idempotency test: run the migration twice without `--force`; assert no duplicate rows
      and stats show the second run's `skipped_existing` count matches the key count.
- [x] 2.4 `--force` test: migrate, mutate the YAML fixture, re-run with `--force`; assert the
      Postgres data now reflects the mutated fixture, not the original.

## 3. Real-database migration + parity review

- [x] 3.1 Run `python -m core.dq_score_migrate` against the real `adm` database (no `--force` —
      this is a first run). Result: 2,382 keys, 2,382 current rows written, 78 history rows
      written, 0 skipped.
- [x] 3.2 Run `parity_rows()` against the real `adm` database and the real
      `governance/dq_scores.yaml`; review the report. Expect 100% match (2,382 keys) given no
      application code changed since A1. Result: **2,382/2,382 keys match, 0 mismatches.**
- [x] 3.3 Present the parity report to the user for review.

## 4. Gates and documentation

- [x] 4.1 Pin `ADM_DQ_BACKEND=yaml` in `tests/conftest.py` (the isolation trap that already bit
      glossary and audit — `project.yaml`'s `dq_backend` staying `yaml` today makes this currently
      a no-op safety net, but protects the suite the moment the user flips the flag).
- [x] 4.2 Run the full backend test suite (server stopped) — expect no regressions. Result: 589
      passed, 0 failed (the previously-documented order-dependent flake in
      `test_semantic_type_agent_gating.py` happened to pass this run too — consistent with it
      being order-dependent, not a regression from this change).
- [x] 4.3 Update `/memories/repo/postgres-migration.md` and this change's status once shipped.
- [x] 4.4 STOP for user review — do not commit, and do not flip `dq_backend`. The user decides
      whether/when to flip the flag and restart; this change's automated scope ends at the parity
      report (task 3.3).

>> `dq_backend` (and `element_backend`/`refdata_backend`/`audit_backend`) have since been flipped
   to `postgres` in `project.yaml` — a deliberate decision made by the user after deliberation, as
   the final step of migrating these modules off YAML (confirmed 2026-08-13). The flip surfaced a
   real, separate N+1 performance bug in `list_tables()`'s per-column DQ-score reads (fixed the same
   day — see `/memories/repo/tech-debt.md`'s DQ-bulk-read entry); the flip itself was correct.

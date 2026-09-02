## 1. Schema

- [x] 1.1 Write the next-numbered Alembic migration (after `0009_add_data_dictionary_comments`,
      assuming S0 lands first — otherwise the next available number after `0008`):
      `ALTER TABLE reference_code ADD COLUMN valid_from TIMESTAMPTZ`. Landed as
      `0010_add_reference_code_history.py`.
- [x] 1.2 In the same migration, `CREATE TABLE reference_code_history` mirroring
      `reference_code`'s business columns (`element_key`, `code`, `value`, `meaning`, `origin`,
      `status`, `submitted_at`, `submitted_by`, `approved_at`, `approved_by`) plus
      `valid_from`/`valid_to` (both `TIMESTAMPTZ NOT NULL`, never a sentinel) plus
      `reference_code_id BIGINT REFERENCES reference_code(id)`. Add supporting indexes
      (`(element_key, code, valid_from)`, `(reference_code_id)`). Also added a
      `CHECK (valid_to > valid_from)` window-integrity constraint (natural extension of the
      "always two real, ordered dates" invariant already agreed).
- [x] 1.3 In the same migration, backfill every existing `reference_code` row's `valid_from` to
      the sentinel (`1800-01-01 00:00:00+00`) — zero `reference_code_history` rows created by
      this step. VERIFIED live: 16/16 rows backfilled, 0 history rows created.
- [x] 1.4 Add full `COMMENT ON TABLE`/`COMMENT ON COLUMN` data-dictionary text for
      `reference_code.valid_from` and every column of `reference_code_history`, per the standing
      rule established in `govern-pg-s0-foundations`. Verified live.
- [x] 1.5 Add the corresponding ORM model (`ReferenceCodeHistory`) — following whatever models
      package layout `govern-pg-s0-foundations` (slice S0) lands (`core/shared/models/governance.py`
      if S0 is already done, otherwise `core/glossary_db/models.py` for now). S0 was already done
      and committed — added to `core/shared/models/governance.py` + re-exported from
      `core/shared/models/__init__.py`. Verified importable, columns match.

## 2. Repository logic

- [x] 2.1 Add a private helper on `ReferenceCodeRepo` that closes a `reference_code` row's current
      version into `reference_code_history` given an explicit `valid_to` timestamp (used by both
      hooks below). Landed as `_close_current_into_history()` (static helper).
- [x] 2.2 Wire the close-into-history helper into `revoke_codes()`: when a code's status moves
      `approved → draft` via revoke, close its outgoing version with `valid_to` = the revoke's
      real timestamp, inside the same transaction as the existing status/timestamp updates.
- [x] 2.3 Wire the open-new-window logic into `approve_codes()`: when a code's status moves
      `in_review → approved`, if `reference_code_history` already has at least one row for this
      code, set the current row's `valid_from` to this approval's real timestamp; otherwise (first-
      ever approval) set it to the D2 sentinel.
- [x] 2.4 Add `ReferenceCodeRepo.as_of(element_key, code, as_of_date)`: check the current row's
      `valid_from` first (return it if `as_of_date >= valid_from`); otherwise query
      `reference_code_history` for the row whose window covers `as_of_date`; return "not found"
      if neither matches. REFINED during implementation (see design.md D7 addendum): the
      current-row check ALSO requires `row.status == "approved"` — a draft/in-review row can be
      mid-edit, and its stale `valid_from` must never be mistaken for a stable historical answer.

## 3. Tests

- [x] 3.1 Revoking an approved code creates a `reference_code_history` row with a real `valid_to`
      matching the revoke timestamp. Landed as `test_revoke_closes_history_with_real_valid_to`.
- [x] 3.2 A code's first-ever approval sets `valid_from` to the sentinel, not `now()`. Landed as
      `test_first_approval_uses_sentinel_not_now`.
- [x] 3.3 A second approval (after a revoke) sets `valid_from` to the real approval date — verify
      this happens even when the re-approved value/meaning are byte-identical to the pre-revoke
      version (no "no-op" short-circuit). Landed as
      `test_second_approval_after_revoke_uses_real_date_even_if_unchanged`.
- [x] 3.4 `as_of()` returns the current row for a date on/after its `valid_from`. Landed as
      `test_as_of_returns_current_row_for_recent_date`.
- [x] 3.5 `as_of()` returns the correct historical row for a date covered by a
      `reference_code_history` window. Landed as `test_as_of_returns_historical_row_for_older_date`
      (also asserts "now" resolves to the current, updated value in the same scenario).
- [x] 3.6 `as_of()` returns "not found" for a date inside a revoked gap (between a close and the
      next open). Landed as `test_as_of_returns_not_found_inside_revoked_gap` (plus
      `test_as_of_unknown_code_returns_not_found` for an unrelated code).
- [x] 3.7 Every existing `ReferenceCodeRepo` test (summaries, submit, approve, revoke, remove)
      still passes unmodified — proves existing reads are unaffected. Verified: original 15
      tests in this file + 9 in `test_reference_code_logic.py` (24 total) all pass unmodified.
- [x] 3.8 Backfill migration test: existing rows get the sentinel `valid_from`;
      `reference_code_history` is empty immediately after backfill. The literal migration-time
      backfill was already verified live against the real `adm` database (16/16 rows backfilled,
      0 history rows — see task 1.3). Re-simulating an `ALTER TABLE ... ADD COLUMN ... DEFAULT`
      backfill in a throwaway pytest schema would just be re-testing Postgres's own guaranteed
      DEFAULT semantics, not custom app logic — so instead landed
      `test_new_code_defaults_to_sentinel_with_no_history`, which tests the same underlying
      mechanism (the column's DB-level default) that both the real backfill and every new insert
      path (including the `pg_insert` upsert in `save_codes()`) depend on.

## 4. Gates and documentation

- [x] 4.1 Run the full backend test suite (server stopped) — expect no regressions. First run
      surfaced 1 failure: `test_full_column_comment_coverage_for_pre_s0_tables` hardcoded
      "281 columns across the 18 pre-S0 tables," which this change's `valid_from` column bumps
      to 282 — a direct, expected consequence of this migration (not a regression). Updated the
      hardcoded count/comment to 282 and re-ran the full suite: **571 passed**, 0 failed.
- [x] 4.2 Update `/memories/repo/reference-code-historization.md` and this change's status once
      shipped. Done — appended an "IMPLEMENTATION STATUS" section.
- [x] 4.3 STOP for user review — do not commit. Await explicit go-ahead before applying the
      migration against the real `adm` database. User reviewed and gave explicit go-ahead to
      commit.

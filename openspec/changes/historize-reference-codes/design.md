## Context

`reference_code` (Phase 5b.2, `db/migrations/versions/0005_add_reference_code.py`) is already live
on Postgres: one row per `(element_key, code)`, columns `id, element_key, code, value, meaning,
origin, status, submitted_at, submitted_by, approved_at, approved_by, created_at, updated_at`.
Its own migration docstring flagged temporal audit of value/meaning edits as a deliberately
deferred "later slice" — this change is that slice.

Grounded in the real write paths (`core/reference_code_repo.py`):
- `EDITABLE_STATUSES = {'empty', 'draft'}` — an `approved` row is locked; it cannot be edited
  directly.
- `revoke_codes()` is the **only** path out of `approved` (→ `draft`); it clears
  `approved_at`/`approved_by`/`submitted_at`/`submitted_by` and writes a `lifecycle_transition`
  row (`from_status='approved', to_status='revoked'`).
- `approve_codes()` is the only path into `approved` (from `in_review`); it stamps
  `approved_at`/`approved_by` and writes a `lifecycle_transition` row
  (`from_status='in_review', to_status='approved'`).
- Therefore every second-or-later approval was **necessarily** preceded by a revoke — there is no
  code path today where an approved code's content changes without first leaving `approved`.

## Goals / Non-Goals

**Goals:**
- Every code's value/meaning change becomes auditable and exactly reproducible as of any past
  date, including correctly representing gaps where no approved value existed.
- Zero change to any existing read path — `ReferenceCodeRepo`'s ~10 existing methods (including
  `_build_summaries()`'s unfiltered `select(ReferenceCode)`) continue to see exactly one row per
  code, unchanged.
- No backend flag — this is additive capability on an already-live table, not a system swap.

**Non-Goals:**
- Historizing `status` transitions — already fully covered by the existing `lifecycle_transition`
  table (see Decision D6 below); nothing new is built for that dimension.
- A UI for browsing a code's history — not requested, not scoped here.
- Any change to `reference_set`/`reference_set_entry` (slice D of the separate governance YAML
  migration) — noted there as a future design update, not addressed by this change.
- Aligning this pattern with the Catalog's own snapshot-based historization
  (`catalog_dataset_snapshot`/`catalog_element_snapshot`) — explicitly deferred by the user to a
  separate, later discussion.

## Decisions

### D1 — Not the Catalog snapshot pattern
Catalog's snapshots are periodic photographs; "as of date X" means guessing the nearest photo
before X. Regulatory reproduction needs an exact match, not an approximation — true SCD2 with
explicit `valid_from`/`valid_to` windows is required instead.

### D2 — Business-effective dates, not system timestamps
A code's first-ever approved version (whether freshly created or backfilled from data that already
existed before this change) gets `valid_from` defaulted to a far-past sentinel
(`1800-01-01 00:00:00+00`) — onboarding a codeset into ADM is not the same event as the code coming
into existence in the real world, so we don't claim to know its true origin date. Real, dated
versions only start appearing from the first genuine post-onboarding approved change onward.

### D3 — Current + history table split (not a single SCD2 table)
Considered and rejected: a single table with every version as a row (current and historical alike),
with or without a convenience view. Chosen instead: `reference_code` keeps today's one-row-per-code
shape (gains only `valid_from`), and a new sibling `reference_code_history` holds retired versions.
Rationale, in order of weight:
1. **Existing unfiltered reads stay correct without modification.** `ReferenceCodeRepo` has ~10
   read methods, including `_build_summaries()`'s bare `select(ReferenceCode)` feeding the DQ
   scoring hot path and the Reference Dataspace overview. A single-table design would require
   adding a current-row filter to every one of them, correctly, forever — an easy, invisible-in-
   review class of mistake (the same failure shape already logged elsewhere in this codebase: a
   query that looks complete but silently starts counting stale data). The split needs none of
   that; those methods are untouched.
2. **No sentinel needed on either side.** The current table needs no `valid_to`/`is_current` —
   every row is current by construction. The history table's `valid_from`/`valid_to` are *always*
   two real, concrete dates — a row only lands there the instant it's superseded, so there is never
   a placeholder "still open" value to encode.
3. **Write cost is identical either way** (a 2-statement close-old/open-new transaction), so this
   was not a deciding factor.
4. **Matches existing precedent** — `dq_score`/`dq_score_history` (governance migration slice A)
   uses the same current+history shape for the same reason.
User's own deciding reason: "less change area to handle."

### D4 — Catalog's historization approach is out of scope
Explicitly deferred by the user to a separate discussion; not touched, not aligned, not
reconsidered here.

### D5 — Full column mirror on `reference_code_history`
`reference_code_history` mirrors every business field of `reference_code` (`value`, `meaning`,
`origin`, `status`, `submitted_at`/`submitted_by`, `approved_at`/`approved_by`) plus
`valid_from`/`valid_to` plus a `reference_code_id` foreign key back to the current row — full
reproducibility of what the row looked like, not a narrowed subset. It does **not** duplicate
who/why a value changed — that's already captured by the existing `lifecycle_transition` audit
trail (`subject_type='reference_code'`), avoiding redundant audit data across two tables.

### D6 — Two write-path hooks, not one (superseded an earlier "skip no-op re-approvals" idea)
Because `approved` rows are always revoked before they can be edited again (see Context), the real
trigger for historization isn't "did the content change" — it's "did the code leave approved status
at all."
- **`revoke_codes()`** closes the outgoing version into `reference_code_history`, with
  `valid_to` = the real revoke timestamp. This is what creates the gap: no row, current or
  historical, covers a revoked period.
- **`approve_codes()`** opens a new dated window on every approval after the first
  (`valid_from` = that approval's real date), regardless of whether the re-approved content
  matches what was there before the revoke — a period with no approved value is itself a
  meaningful fact worth preserving, not a no-op to be collapsed away. Only the very first-ever
  approval (no prior `reference_code_history` rows for this code) uses the D2 sentinel instead of
  a real date.

### D7 — The "as of date X" lookup returns value/meaning only, not status
A code's `status` on any past date is already fully answerable today via the existing
`lifecycle_transition` table (its `to_status`, at the latest transition with `occurred_at <= X`) —
`revoked` is recorded there as the transition's `to_status` even though the row's own resting
`status` column is just `'draft'` afterward. No new schema is needed for that dimension. This
change's "as of" lookup is scoped to value/meaning only: it checks the current row's `valid_from`
first (cheap, common case — most lookups are for "now" or a recent date), then falls back to
`reference_code_history` for older dates. A date inside a revoked gap simply matches nothing in
either table — "not found" is the correct answer by construction, with no need to separately state
why (that reason remains available via `lifecycle_transition` if ever needed, but is out of scope
for this lookup).

**REFINEMENT found during implementation:** checking only `valid_from` is not sufficient on its
own. `reference_code` rows in `draft`/`in_review` status (i.e. after a revoke, before the next
approval) are editable — a steward can be actively changing `value`/`meaning` while the code sits
in that state. If the current row's stale `valid_from` (left over from before the revoke) were
trusted blindly, `as_of()` could return whatever is *currently mid-edit* as if it were a stable,
approved historical answer for a date inside the gap — exactly the wrong outcome D7 already rules
out. Fixed by also requiring `row.status == "approved"` before trusting the current row: only an
actually-approved row's `valid_from` is a valid open window. This is not a new decision, it's a
correctness detail required to faithfully implement D7 as already agreed (an unapproved row can
never be a valid answer to "what was officially approved").

### D8 — No backend flag
Every other slice of the governance/catalog migration program added a `yaml`↔`postgres` flag
because it was replacing an existing system with a choice between two. There is no second system
here — `reference_code` is already the one live store, and this only adds capability on top of it.
The new column and table are additive and safe to ship directly; the two write-path hooks are
built and covered by tests first, then wired into the live `approve_codes()`/`revoke_codes()` calls
once reviewed — the same "build, verify, then switch on" discipline as every other slice, just
without an environment-variable toggle, because there's nothing to toggle back to.

## Risks / Trade-offs

- **[Risk] The two-statement close/open transaction (in `revoke_codes()` and `approve_codes()`
  respectively) must be atomic with the existing status/timestamp updates in those same methods,
  or a crash mid-transaction could leave a code with no current window matching reality.**
  → Mitigation: both hooks execute inside the same `session_scope()` transaction the methods
  already use for their existing writes — no new transaction boundary introduced.
- **[Risk] A future edit to `reference_code`'s columns (e.g. slice E's annotation work, or any
  other change) could be made without the corresponding `reference_code_history` column being
  added, silently narrowing history's reproducibility.**
  → Mitigation: `reference_code_history`'s full-mirror design (D5) is a deliberate, named
  convention — any future column addition to `reference_code` should be reviewed for whether
  `reference_code_history` needs the same column.
- **[Trade-off] `reference_code_history` cannot answer "what was the status on date X"** — by
  design (D7); this is answered by a separate table already. Anyone building a combined
  status+value view later needs to know to query both.

## Migration Plan

1. Write the Alembic migration: `ALTER TABLE reference_code ADD COLUMN valid_from TIMESTAMPTZ`;
   `CREATE TABLE reference_code_history (...)`; backfill every existing `reference_code` row's
   `valid_from` to the D2 sentinel in the same migration (no `reference_code_history` rows created
   for the backfill — there is no prior version to close). Full `COMMENT ON` data dictionary per
   the standing rule from `govern-pg-s0-foundations`.
2. Add `ReferenceCodeRepo` methods: an internal helper to close the current row into history, wired
   into `revoke_codes()`; the open-new-window logic wired into `approve_codes()`; the new
   `as_of(element_key, code, as_of_date)` read method.
3. Tests: revoke closes with a real `valid_to`; first-ever approval uses the sentinel; a subsequent
   approval (post-revoke) opens a new real-dated window regardless of content match; `as_of()`
   returns the current row for recent dates, a historical row for older dates, and "not found" for
   a date inside a gap; backfill produces zero history rows and the correct sentinel.
4. Full backend test suite green.
5. Apply the migration against the real `adm` database.

**Rollback:** the new column and table are purely additive; `alembic downgrade` drops
`reference_code_history` and the `valid_from` column with no data loss to `reference_code`'s
existing fields. Until the hooks are wired into `revoke_codes()`/`approve_codes()` (a deliberate,
separate, reviewed step), nothing about existing behavior changes at all.

## Open Questions

None outstanding — D1 through D8 were all confirmed with the user across this session before this
design was written.

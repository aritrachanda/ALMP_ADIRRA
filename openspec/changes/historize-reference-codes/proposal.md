## Why

Some regulations require reproducing exactly what a reference code (e.g. a currency, product, or
status code) officially meant on a given past date. Today, `reference_code` (already live on
Postgres, Phase 5b.2) holds exactly one row per `(element_key, code)` — every edit `UPDATE`s that
row in place. A code's `value`/`meaning` can already change silently today with zero trace of what
it used to say or when the change took effect. This gap was explicitly flagged at the time
`reference_code` was first built (its migration docstring: *"NO hard delete (governance object);
temporal audit of value/meaning edits is a later slice"*) — this proposal is that slice.

## What Changes

- Add a `valid_from` column to the existing, already-live `reference_code` table: the
  business-effective date the code's *current* value/meaning took effect. Pre-existing rows are
  backfilled with a far-past sentinel date (their true origin predates ADM tracking them) — real,
  dated values only start appearing from the first *approved* change onward. No `valid_to`, no
  `is_current` flag needed on this table — every row here is current by construction.
- Add a new table, `reference_code_history`, mirroring `reference_code`'s business fields plus a
  `valid_from`/`valid_to` pair that is **always** two real, concrete dates — never a placeholder —
  because a row only lands here at the exact moment its value stopped being the officially
  approved answer.
- Wire two write-path hooks, both already-existing methods on `ReferenceCodeRepo`:
  - `revoke_codes()` — closes the outgoing approved version into `reference_code_history` with
    `valid_to` = the real revoke timestamp. This is what creates a genuine gap (a period with no
    officially approved value) rather than silently extending the old value's validity through a
    period it wasn't actually approved.
  - `approve_codes()` — every approval after the code's first-ever approval opens a new dated
    window (`valid_from` = that approval's real date), regardless of whether the re-approved
    content matches what was there before — a gap is itself meaningful, not a no-op.
- Add a repository method to look up a code's officially approved value/meaning **as of a given
  date**, checking the current row first (cheap, common case), falling back to
  `reference_code_history` for older dates, and correctly returning "not found" for any date that
  falls inside a revoked gap — no approved value existed then, and that lookup does not need to
  separately explain *why* (the code's status trail is already fully recoverable from the existing
  `lifecycle_transition` table if that's ever needed).
- **No backend flag.** Every other Postgres slice added a `yaml`↔`postgres` flag because it was
  *replacing* an existing system. This isn't replacing anything — `reference_code` is already the
  live store; this only adds new capability on top of it. The new column and table are purely
  additive; the write-path hooks are built and tested, then wired into the live `approve_codes()`/
  `revoke_codes()` calls once reviewed.

## Capabilities

### New Capabilities
- `reference-code-history`: point-in-time historization of reference code value/meaning changes,
  covering every approved version a code has ever had, gap-aware (a revoked period correctly has
  no approved value), queryable "as of" any date.

### Modified Capabilities
(none — no existing spec documents `reference_code`'s historization behavior; the original 5b.2
work predates the OpenSpec workflow being adopted for this codebase)

## Impact

- **New**: one Alembic migration (`0010_add_reference_code_history.py` or next available number)
  adding `reference_code.valid_from` + creating `reference_code_history`, with full data-dictionary
  comments per the standing rule established in `govern-pg-s0-foundations`.
- **Changed**: `core/reference_code_repo.py` — `revoke_codes()` gains the close-into-history step;
  `approve_codes()` gains the open-new-window step; a new `as_of(element_key, code, date)` method.
- **No changes** to any existing read method (`_build_summaries()` and the ~9 others) — they
  continue reading only the current row, exactly as today.
- **No frontend changes** required for this proposal; a future UI for browsing a code's history is
  explicitly out of scope here.
- **Tests**: new tests covering the revoke→history-close, approve→history-open (first-ever vs.
  subsequent), gap-returns-not-found, and backfill-gets-sentinel behaviors.

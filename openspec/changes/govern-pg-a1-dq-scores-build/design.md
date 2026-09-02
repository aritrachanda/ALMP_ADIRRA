## Context

`DQScoreStore` (`core/dq_score_store.py`) is a thread-safe YAML store keyed by
`source|schema|table|column` (column scores) or `source|schema|table` (dataset roll-ups). Each key
maps to a history list, newest first, appended to only when the score/state/signal fingerprint
actually changes (§16.2) — a no-op re-score never grows the file. History is pruned to
"oldest (baseline) + latest N-1" (default N=50). The whole file is rewritten atomically
(`os.replace` with Windows-retry) on every write; a Windows-only flaky test around that retry
already exists as a known tech-debt item this slice's later fold-in (A2) plans to retire.

The stored record shape (`core/dq_scorer.py`) is a deeply nested, versioned dict: top-level
`state` (`"scored"`/`"unscored"`), `dq_score` (int, scored only), `grade_label`,
`grade_color_intent`, `breakdown_version` (currently 7, has changed 7 times as the scoring model
evolved), plus a `components` list of nested line-item breakdowns, plus remediation actions. This
shape changes often and is not a stable, enumerable column set — the same problem already solved
elsewhere in this codebase for `term_version.attributes`/`ai_provenance` (JSONB) and
`catalog_element_snapshot` (JSONB stats blob).

The call surface is intentionally tiny (confirmed via grep — only 2 files touch the store):
`core/dq_service.py` calls `.batch()`, `.key()`, `.dataset_key()`, `.record()`, `.latest()`,
`.history()`; `api/main.py` only constructs it. This is why the plan doc calls DQ "the easier
surface" to prove the history-table shape on before doing the same for semantic types (B slices).

**Standing decision (2026-08-11, user, applies to this and every future governance history
table):** real SCD2 — genuine `valid_from`/`valid_to` windows and a point-in-time `as_of(date)`
lookup, not just a plain current+history split — is now the STANDARD approach across this whole
migration programme, not a per-table judgement call. Rationale (user's own words): in a
banking-regulatory context we cannot assume every corner a historical query might come from, and
must not be caught unable to answer "what was true on date X" if ever asked. This reverses the
earlier draft of this design (which had proposed skipping SCD2 for DQ scores specifically since
they are auto-computed, not steward-approved) — recorded here for the historical record, but
superseded. See `docs/governance-postgres-migration.md` §4 for the ground-rule text.

DQ scores DO have a real, discrete transition that plays the same role as `reference_code`'s
revoke: a column's `state` can flip from `"scored"` to `"unscored"` (out-of-scope or an emptied
table — see `core/dq_scorer.py`'s early returns) and back again on a later re-scope. This is the
DQ-domain equivalent of a "gap" — while a column sits `unscored`, there is no current, valid score
to answer a point-in-time question with, exactly like a revoked reference code sitting in draft.

## Goals / Non-Goals

**Goals:**
- Build a Postgres-backed `DQScoreRepo` with the exact same read/write semantics as the existing
  YAML store (same no-op-detection rule, same retention rule, same key shapes).
- Give every DQ score key real SCD2 history: `dq_score` (current row) carries a `valid_from`;
  `dq_score_history` rows carry both `valid_from` and `valid_to`, both real, non-sentinel dates —
  and a new `as_of(key, as_of_date)` lookup answers "what was this key's score/grade on date X"
  from either table, or reports "not found" for a date inside an unscored gap or before the first
  score.
- Make `DQScoreStore` backend-aware without changing its public method signatures, so
  `core/dq_service.py` and `api/main.py` need zero changes. `as_of()` is new Postgres-only surface
  (no YAML equivalent exists or is being added).
- Ship this fully dormant: `dq_backend` defaults to `yaml`; nothing reads or writes Postgres until
  the flag is flipped (which is slice A2, not this one).

**Non-Goals:**
- No migration of real data (that is A2's `migrate_from_yaml.py` + parity script) — including the
  question of what `valid_from` to assign the oldest migrated row per key when YAML's own history
  retention (also N=50, keep-first) has already pruned away any earlier evidence; that is an A2
  migration-time decision, not an A1 schema decision (the schema itself places no constraint
  requiring `valid_from` to be "real" vs. a placeholder — either is a valid `TIMESTAMPTZ`).
- No flag flip, no wiring into `api/main.py`'s construction beyond passing a DSN.
- No changes to the scoring engine (`core/dq_scorer.py`, `core/dq_dataset_scorer.py`) — the
  breakdown shape is persisted as-is, whatever version it currently is.
- No fix for the `_replace_with_retry` Windows flakiness or the 29-second startup parse — those
  only go away once A2 flips the flag; this slice cannot claim that win yet.

## Decisions

**D1 — Current + history table split, now with real SCD2 windows (reuses the
S0/historize-reference-codes precedent, extended per the standing decision above).** `dq_score`
holds one row per key (the current record, with its own `valid_from`); `dq_score_history` holds
retired records, each with a real, non-sentinel `valid_from`/`valid_to` window. This mirrors
`reference_code`/`reference_code_history` exactly (not the lighter no-window variant this design
originally proposed) — a second full SCD2 instance in the codebase, following the same standard.
Alternative considered: single table with an `is_current` flag or `valid_to` sentinel — rejected
for the same reason as the reference-code decision (D3 there): every existing unfiltered read
would need a new filter forever, a class of bug already seen twice in this codebase (dq-scores/
semantic-type fingerprint issues logged in `docs/tech-debt.md`).

**D2 — The breakdown itself is stored as JSONB, not exploded into columns.** Only a handful of
fields are promoted to real columns for indexing/filtering: `key` (or `dataset_key`), `state`,
`dq_score`, `grade_label`, `breakdown_version`, `signal_fingerprint`, `config_fingerprint`,
`scored_at`. Everything else (`components`, remediation `actions`, `archetype*`, etc.) goes into a
single `breakdown JSONB` column, written verbatim from the scorer's dict. Alternative considered:
model `components`/line-items as real rows/tables — rejected because `BREAKDOWN_VERSION` has
already changed 7 times and the shape is display-oriented, not queried structurally by anything
today; JSONB matches the precedent already set for `term_version.attributes`/`ai_provenance` and
`catalog_element_snapshot`'s stats payload.

**D3 — One row type per key, columns and datasets share the same tables.** `dq_score`/
`dq_score_history` do not split column-scores from dataset-roll-ups into separate tables; both use
the same `key` column (`source|schema|table|column` or `source|schema|table`, exactly as today) and
a `key_kind` discriminator column (`'column'`/`'dataset'`) for clarity/indexing. Alternative
considered: separate `dq_score`/`dq_dataset_score` tables — rejected as unnecessary duplication;
the store's own `key()`/`dataset_key()` static methods already produce a single opaque string keyed
the same way today in one YAML file, so one pair of tables mirrors that faithfully.

**D4 — Real SCD2 windowing, with `state == "scored"` gating `as_of()`'s current-row check
(supersedes the earlier no-SCD2 draft of this decision).** `dq_score_history` rows carry real
`valid_from`/`valid_to`; `dq_score.valid_from` is set the same way `reference_code.valid_from` is:
the very first record ever written for a key needs no fabricated precision (nothing to compare
against — see the Non-Goals note on migration-time ambiguity), while every SUBSEQUENT change
(a real `dq_score`/`state`/`signal_fingerprint` difference — §16.2's existing no-op rule decides
what counts as "changed") closes the outgoing row into history with `valid_to` = the new record's
`scored_at`, and opens the new current row with `valid_from` = that same timestamp. `as_of()`
mirrors `reference_code_repo.as_of()`'s D7 refinement exactly: the current row only answers a
lookup when its `state == "scored"` AND `as_of_date >= valid_from` — a column currently sitting
`unscored` (out-of-scope/empty-table gap) must never leak a stale `valid_from` as a false-positive
answer for a date inside that gap, mirroring why `reference_code`'s check requires
`status == "approved"`. Otherwise `dq_score_history` is searched for a window covering the date;
no match means "not found" (correct for a genuine gap or a date before the key's first score).

**D5 — Retention is a SQL delete, reusing the exact pattern already built for catalog
snapshots.** `core/catalog_db/repository.py::_prune_snapshots()` already implements "keep the
oldest (baseline) + latest N-1, delete the middle" as a SQL delete over a `captured_at DESC`
ordered id list — this is the exact rule `DQScoreStore._prune_locked()` implements in Python over a
list today. `DQScoreRepo` reuses the same shape (adapted to `dq_score_history`'s own FK/timestamp
columns) rather than inventing a third variant of the same retention rule.

**D6 — Backend switch lives inside `DQScoreStore`, not a new dispatcher module.** Every public
method (`record`, `latest`, `history`, `batch`) gains a `if self._use_pg(): return
self._repo().<method>(...)` branch, mirroring `ElementStateStore`'s existing `_use_pg()`/`_repo()`
pattern exactly (lazy repo construction, `ADM_DQ_BACKEND` env override checked live, else
`project.yaml`'s `database.dq_backend` cached after first read). `as_of()` has no YAML-mode
equivalent — it is exposed only on the repo/pg path (calling it while `dq_backend()` resolves to
`yaml` raises, same shape as any other pg-only capability in this codebase would). Alternative
considered: a `core.catalog`-style dispatch function wrapping the whole store — rejected because
the store is already the single call surface (unlike catalog's 5 route files), so there is no
analogous choke-point problem to solve; the existing `ElementStateStore` shape is the closer
precedent here.

**D7 — `batch()` becomes a no-op context manager in Postgres mode.** The YAML store's `batch()`
exists purely to coalesce N whole-file rewrites into 1; Postgres has no equivalent cost (each
`record()` call is already a small, isolated upsert). In pg mode, `batch()` yields immediately with
no deferred-write bookkeeping — callers (`core/dq_service.py`'s bulk roll-up path) need no changes
since the context-manager contract is identical either way.

**D8 — This decision (real SCD2) is now the standard for every future governance history table,
not re-litigated per slice.** Recorded as a ground rule in `docs/governance-postgres-migration.md`
§4 so slices B (semantic types), C (element content), D (reference sets/learned patterns), and E
(annotations) inherit it directly rather than each re-deciding whether their data "needs" SCD2.
Where a table's domain has no natural discrete transition equivalent to "revoke"/"unscored" (e.g.
a value that is always simply overwritten with no gap concept), the future slice's design.md still
must show real `valid_from`/`valid_to` windows opened/closed on every change — it does not get to
skip windowing, only decide what event marks a window boundary in that domain.

## Risks / Trade-offs

[Risk] JSONB `breakdown` column drifts silently if `BREAKDOWN_VERSION` changes again after this
lands, since nothing validates its shape at the DB layer.
→ Mitigation: this is the same trade-off the YAML store already accepts today (no schema
validation on the dict either) — not a regression, and consistent with D2's reasoning that the
shape is display-oriented, not queried structurally.

[Risk] Building this fully dormant means slice A2 (migrate/parity/flip) is where the real
correctness risk concentrates — a subtle repo bug here would only surface once real data flows
through it in A2.
→ Mitigation: Postgres-gated tests in this slice mirror `tests/test_dq_score_store.py` line-for-
line (same fingerprint/no-op/retention assertions against the new repo) so behavioral parity is
proven before A2 ever touches real data.

[Risk] `key_kind` discriminator (D3) is new surface not present in the YAML store (which infers
column-vs-dataset only by string shape/caller intent, never stores it explicitly).
→ Mitigation: purely additive metadata for future indexing/filtering; existing `key()`/
`dataset_key()` call sites don't need to know about it — `record()` derives it internally.

[Risk] Real SCD2 windowing adds meaningful complexity (window-closing logic, gap-aware `as_of()`,
two new date columns) to data that, unlike `reference_code`, has no manual steward workflow —
every window boundary is decided purely by the automated scorer's own no-op-detection rule.
→ Mitigation: this is the accepted cost of the standing decision (D8) — the regulatory
reproducibility requirement outweighs the added mechanical complexity, and the mechanics
themselves are a direct, already-proven port of `reference_code_repo`'s `_close_current_into_
history()`/`as_of()` shape, not a new design to validate from scratch.

[Risk] `valid_from` on the very first record for a key has no natural "real" business date (see
the Non-Goals note) — using `scored_at` itself is accurate for anything scored live from now on,
but A2's migration of pre-existing YAML history may need a placeholder for older, retention-pruned
records whose true first-effective date is unknowable.
→ Mitigation: left as an explicit A2 decision, not resolved here — the schema imposes no
constraint that would block A2 from choosing a sentinel later if needed.

## Migration Plan

1. Alembic migration adds `dq_score`/`dq_score_history` (+ comments), additive only, no existing
   table touched.
2. `DQScoreRepo` + ORM models land, imported nowhere yet outside their own tests.
3. `DQScoreStore` gains the backend branch; `dq_backend` defaults to `yaml` in `project.yaml`, so
   the running app is byte-identical until a later slice (A2) flips it.
4. Rollback: none needed — nothing is wired into the live path in this slice; deleting the new
   files/migration (`alembic downgrade`) fully reverts with zero data-loss risk since no real data
   is ever written to the new tables here.

## Open Questions

None outstanding — D1-D8 above resolve every design question raised by the proposal.

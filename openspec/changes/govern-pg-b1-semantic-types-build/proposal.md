## Why

`governance/semantic_type_assignments.yaml` is the second-largest governance YAML file (2,290
records — one per catalog column across all 4 sources, 3 MB) and, like `dq_scores.yaml` before
slice A1/A2, is parsed in full at every backend startup (~6.5 seconds measured directly against
the real file) and rewritten in full on every steward disposition or re-resolution. This is slice
B1 of the eleven-slice plan: build the Postgres-backed store as a dormant, flag-gated alternative
behind `SemanticTypeStore` — no data moves, no flag flips, no behaviour change to the live app.
Slice B2 (a separate, later change) does the migration/parity/flip, and is expected to be the
larger win of the two (the plan's ~80-second per-table stall).

**A second, equally important problem folds into this same slice**, found during investigation
(2026-08-11, user-directed): `core/semantic_resolver.py`'s `column_fingerprint()` deliberately
bakes in 2 governance signals (`_glossary_domain`, `_definition_state`) alongside profiling stats
— but only ONE of the two call sites that build a column dict actually adds those signals before
fingerprinting. Element Detail (`api/routes/element.py` ~L1453) enriches the column dict with
both signals before resolving; Table Overview (`resolve_table` → `resolve_column`, same file
~L293) never does. For any column with a confirmed glossary link or an approved definition,
visiting Element Detail computes and persists one fingerprint; visiting Table Overview for the
SAME column computes a genuinely different fingerprint (missing those 2 fields) — a real
cache-miss that forces actual re-resolution, purely from which screen the column happened to be
viewed from, not from any real profile or governance change. This directly matches the user's
concern: "after a server restart or a new user session or simply UI navigation... new semantic
deduction — that's something we must avoid." A prior fix (2026-08-10, see `docs/tech-debt.md`)
patched only the misleading progress-status *wording* for this case and explicitly deferred the
real fix (unifying the two enrichment paths) to a later slice (B3 in the original plan) — this
proposal pulls that fix forward into B1, at the user's explicit direction, since it is the same
"do not trigger spurious re-deduction" problem this whole slice exists to get right.

>> RESOLVED 2026-08-12, COMMITTED (f8876ae), ahead of the rest of this slice's build-out. Landed
   as part of a separate, broader fingerprint-churn fix (the actual root cause of the mass churn
   the user had observed was non-deterministic `sample_values` ordering, not this asymmetry —
   see `/memories/repo/semantic-fingerprint-fix-plan.md`). The fix taken was NOT "unify the two
   enrichment paths" as this proposal originally planned — it was simpler: remove the 2
   governance signals from `column_fingerprint()` AND from `_score_column()`'s confidence nudges
   entirely, after measuring 0/54 real impact from the nudge. This makes the asymmetry
   structurally impossible rather than merely reconciled. See design.md's D2 for full reasoning.
   The `fingerprint`/`data_fingerprint` parallel-field duplication (previously earmarked for a
   later B3 fold-in) was also merged back into one field as part of the same commit — nothing
   remains open for either item in this slice.

**Verified NOT a problem** (2026-08-11 investigation): the catalog-stats side of the fingerprint
is stable. Reading the full catalog twice (fresh, independent Postgres queries, no caching) across
all 4 sources / 2,290 columns produced **zero fingerprint mismatches** — a server restart or new
session does not, by itself, cause spurious re-fingerprinting from the catalog data. The governance-
signal enrichment asymmetry above is the one real, confirmed cause.

## What Changes

- Add Alembic migration for `semantic_type_assignment` (current record per key) and
  `semantic_type_prior` (learned-pattern priors, additive to the existing YAML-only mechanism),
  with full data-dictionary `COMMENT ON` coverage per the S0 standing rule, and real SCD2 history
  (`semantic_type_assignment_history`) per the standing rule established in slice A1
  (`docs/governance-postgres-migration.md` §4.4). **D1 RESOLVED 2026-08-13**: a history row is
  written only when the Interpretation Set is submitted (not on every confirm/reject/re-resolve),
  and each row carries two named columns — `system_deduced_type` (the machine's own opinion) and
  `accepted_type` (what a human actually confirmed) — replacing today's nested `latest_proposal`
  trick. See design.md D1 for the full resolution.
- **NEW (2026-08-13, user-directed) Backend-enforce the Interpretation Set submit gate.**
  `submit_definition_for_review` (`api/routes/element.py`) has zero server-side validation today —
  the "description + business name + accepted semantic type" gate is frontend-only
  (`submitGateMet`). Add the equivalent 409 check server-side, mirroring the existing
  `submit_reference_codes` precedent (same file) whose own docstring already claims to match "the
  interpretation-set submit gate" — this slice actually builds that for real. Needed so the
  history-row write can safely assume `accepted_type` exists at submission time.
- **NEW (2026-08-13, user-directed) Fix `confirm()`/`reject()`'s data-loss bug.** Today, when a
  steward picks a different type than the machine suggested ("Replace"), `type_id` is overwritten
  in place and the machine's original suggestion is lost from the live record. Must capture it into
  an explicit `system_deduced_type`-shaped field at the moment of the first override instead.
- Add a new `SemanticTypeRepo` (Postgres-backed), mirroring `SemanticTypeStore`'s existing public
  contract: `get()`, `get_or_default()`, `get_by_key()`, `set_record()` (preserving the
  `preserve_disposed=True` sticky-disposition rule exactly), `set_proposed()`, `confirm()`,
  `reject()`, priors read/write.
- Make `SemanticTypeStore` itself backend-aware: each public method branches to the new repo when
  `semantic_backend() == "postgres"` (env `ADM_SEMANTIC_BACKEND`, default `yaml`), same shape as
  `ElementStateStore`'s existing `_use_pg()`/`_repo()` pattern. Callers are unchanged; the flag
  defaults to `yaml`.
- **Fix the governance-signal enrichment asymmetry** — **ALREADY DONE, 2026-08-12 (f8876ae)**, see
  the "Why" section above. No remaining work for this bullet; kept here only so the slice's scope
  history is legible without cross-referencing commits.
- Add Postgres-gated tests mirroring the existing `SemanticTypeStore`/resolver test coverage, plus
  new tests specifically proving fingerprint stability across the two previously-asymmetric call
  paths, and across repeated/independent catalog reads (regression-proofing the investigation's
  empirical finding).

## Capabilities

### New Capabilities
- `semantic-type-persistence`: Postgres-backed storage, SCD2 history, and priors for semantic-type
  assignments, selectable via a `semantic_backend` flag (default `yaml`), with byte-identical
  behaviour to the existing YAML store while the flag stays at its default.
- `semantic-type-fingerprint-consistency`: a single, shared governance-signal enrichment path used
  by every caller that fingerprints a column for semantic-type resolution, eliminating the
  code-path-dependent fingerprint mismatch found in this investigation. **Already delivered
  2026-08-12 (f8876ae)** — achieved by removing the signals rather than unifying the enrichment
  path; see design.md D2. The spec for this capability is kept (updated to describe the actual
  mechanism) so the requirement remains documented and regression-tested going forward.

## Impact

- New: `db/migrations/versions/00XX_add_semantic_type_assignment.py` (next available number),
  `core/semantic_type_repo.py`, ORM additions to `core/shared/models/governance.py` + re-exports.
- Modified (already shipped 2026-08-12, f8876ae): `core/semantic_resolver.py` — governance-signal
  removal (D2). Still to modify: `core/semantic_type_store.py` (backend branch, matching
  `ElementStateStore`'s pattern).
- Not in this slice: no migration of real data (B2), no flag flip (B2).
- Tests: new `tests/test_semantic_type_repo.py` (Postgres-gated). The fingerprint-consistency
  regression tests (originally planned for this slice) are covered by the tests added alongside
  the 2026-08-12 commit in `tests/test_semantic_resolver.py`.

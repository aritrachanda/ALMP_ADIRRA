## 1. Resolve open design questions (before writing any DDL)

- [x] 1.1 Resolve D1: decide the SCD2 window-boundary shape for
      `semantic_type_assignment_history`. **RESOLVED 2026-08-13** — window boundary is Interpretation
      Set submission (not disposition, not machine re-resolve); row shape is two named columns
      (`system_deduced_type` / `accepted_type`), not the original 3 candidates. See design.md D1 for
      the full resolution, the `confirm()`/`reject()` fix needed, and the new backend-enforcement
      scope (tasks 1.4/1.5 below).
- [x] 1.2 Confirm D4: whether `semantic_type_prior` needs any windowing at all, or is a plain
      current-only upsert table (no revoke/re-approve workflow exists for priors today).
      **RESOLVED 2026-08-13 — no table at all.** The learned-patterns/priors subsystem was
      deleted from the codebase (commit `a74802b`, same day) before this task was picked back up;
      confirmed with the user that B1 should drop `semantic_type_prior` entirely rather than build
      a table for a deleted subsystem. See design.md D4.
- [x] 1.3 ~~Verify D2's implementation note...~~ **MOOT 2026-08-12** — D2 was resolved by removing
      the governance signals from the fingerprint entirely (see task group 4 below), not by adding
      a bulk per-table lookup. Nothing to verify.
- [x] 1.4 **NEW (2026-08-13, user-directed)** Fix `SemanticTypeStore.confirm()`/`reject()`: capture
      the machine's pre-override type_id/confidence into an explicit `system_deduced_type`-shaped
      field at the moment of the FIRST override, instead of silently overwriting `type_id` in place
      (today's behavior loses the machine's original suggestion the moment a steward "Replace"s it).
      See design.md D1 for the full reasoning. **DONE** — also added `domain_role` to the captured
      snapshot (user-approved 2026-08-13, anticipating future RBAC needs).
- [x] 1.5 **NEW (2026-08-13, user-directed)** Add backend enforcement to `submit_definition_for_review`
      (`api/routes/element.py`): a 409 gate requiring description + business name + confirmed
      semantic type, mirroring `submitGateMet` (frontend) and the existing `submit_reference_codes`
      409 precedent (same file, ~L2779 — its own docstring already says "matching the
      interpretation-set submit gate," confirming this was the original intent, just never built for
      this route). Needed so the history-row write can safely assume `accepted_type` exists at
      submission. Also wire a `SemanticTypeStore`/`SemanticTypeRepo` dependency into this route (it
      currently has none) so it can both run this gate and read the record to write history.
      **DONE, and explicitly confirmed 2026-08-13**: Definition + Business Name + Accepted Semantic
      Type required together; Business Glossary Linkage and Reference Codesets remain optional.

## 2. Schema

- [x] 2.1 Write the next-numbered Alembic migration: `semantic_type_assignment` (current record
      per key, now including `system_deduced_type`/`accepted_type` per D1) and
      `semantic_type_assignment_history` (real SCD2 windows, one row per Interpretation Set
      submission per D1). No `semantic_type_prior` table (D4 RESOLVED 2026-08-13 — dropped, the
      priors subsystem it would have served no longer exists). Full `COMMENT ON TABLE`/
      `COMMENT ON COLUMN` coverage, per the S0 standing rule.
- [x] 2.2 Add ORM models to `core/shared/models/governance.py`, re-exported from
      `core/shared/models/__init__.py`. **DONE** — includes 2026-08-13 rework: the history table
      carries the FULL accepted snapshot as real, named columns (not two JSONB blobs, per user
      correction) plus a small `deduced_*` column group; `semantic_type_assignment` carries NO
      `submitted_at`/`submitted_by` of its own (a semantic type is submitted only as part of the
      whole Interpretation Set, not on its own).

## 3. Repository

- [x] 3.1 Create `core/semantic_type_repo.py` with a `SemanticTypeRepo` class mirroring
      `SemanticTypeStore`'s public contract exactly: `get()`, `get_or_default()`, `get_by_key()`,
      `set_record()` (preserving `preserve_disposed=True`'s sticky-disposition rule and the
      `latest_proposal` nesting exactly), `set_proposed()`, `confirm()`, `reject()`. No priors
      read/write (D4 — subsystem deleted, dropped from scope). Also adds `record_submission()`
      (new, D1) — copies the full accepted snapshot straight from the current row, caller only
      supplies the machine's own `deduced_*` opinion.
- [x] 3.2 Add a `semantic_backend()` helper (env `ADM_SEMANTIC_BACKEND` first, else cached
      `project.yaml` `database.semantic_backend`, default `yaml`) — same shape as
      `core.dq_score_repo.dq_backend()`/`core.element_lifecycle_repo.element_backend()`.
- [x] 3.3 Wire the backend branch into `SemanticTypeStore`: add `_use_pg()`/`_repo()` (lazy
      construction, mirroring `ElementStateStore`'s and `DQScoreStore`'s pattern) — **including
      the `__init__`-time eager `_load()` guard** (A1's own hard-learned lesson: branch
      construction-time file parsing too, not just the public read/write methods — see
      `docs/tech-debt.md`'s `DQScoreStore.__init__` bugfix entry, 2026-08-11, for exactly what
      goes wrong if this is skipped).

## 4. Fix the governance-signal enrichment asymmetry (D2)

>> DONE 2026-08-12, COMMITTED (f8876ae) — via a different mechanism than 4.2/4.3 originally
   planned. Kept below for history/traceability.

- [x] 4.1 Measure the current blast radius empirically before changing anything: count how many
      of the 2,290 records currently have a confirmed glossary link and/or an approved
      definition (the population actually affected by the asymmetry), same evidence-based
      approach as the 2026-08-10 fingerprint bug fix (62/2,290 measured then). **Result: 0 of 54
      recently re-deduced columns were governance-linked** — different measurement than 4.1
      originally envisioned (it measured recent-churn overlap, not static glossary/definition
      linkage count), but it's the number that actually drove the decision below.
- [x] 4.2 ~~Extract the governance-signal enrichment logic... into one shared function.~~ NOT
      done as originally written — superseded by removal (4.2-alt below).
- [x] 4.2-alt (actual fix) Removed `_glossary_domain`/`_definition_state` from
      `_FINGERPRINT_COL_FIELDS` and deleted the two `+0.05` confidence-nudge blocks from
      `_score_column()` in `core/semantic_resolver.py`, rather than enriching Table Overview to
      match Element Detail.
- [x] 4.3 ~~Call that shared function from the Table Overview path...~~ **MOOT** — no enrichment
      call site exists anymore for either path to call.
- [x] 4.4 Re-measure after the fix: confirmed no governance signal remains in
      `column_fingerprint()` for either call path — the two paths are now structurally identical
      by construction, not just empirically equal.

## 5. Tests

- [x] 5.1 Postgres-gated `tests/test_semantic_type_repo.py` mirroring `SemanticTypeStore`'s
      existing test coverage (sticky disposition, `latest_proposal` nesting, state transitions,
      the D1 override-capture fix) against the new repo, plus `tests/test_semantic_type_submit_gate.py`
      for the new backend 409 gate. No priors coverage (D4 — subsystem deleted).
- [x] 5.2 SCD2 tests for the self-contained history table: window open/close correctness
      (`test_record_submission_opens_a_window`, `test_second_submission_closes_the_first_window`),
      and the "no prior assignment" guard.
- [x] 5.3 New regression test proving Element-Detail-then-Table-Overview (and the reverse) produce
      identical fingerprints — **DONE 2026-08-13** via `tests/test_semantic_resolver_fingerprint_consistency.py`,
      kept permanently (user-approved) with a loud module-level warning against reactive fixes if
      it ever fails — see `/memories/repo/semantic-fingerprint-fix-plan.md`'s standing rule.
- [x] 5.4 New regression test proving fingerprint stability across two independent, uncached
      catalog reads — **DONE 2026-08-13**, same file/commit as 5.3 above.
- [x] 5.5 Every existing semantic-type/resolver test (`test_semantic_resolver.py`,
      `test_semantic_type_api.py`, `test_pattern_review.py`, `test_pattern_drafting.py`,
      `test_semantic_type_agent_gating.py`, etc.) still passes unmodified. Also fixed 3 tests in
      `test_review_queue_phase1.py` that modeled the OLD, weaker submit gate (description-only) —
      updated their setup to also set a business name and confirm a semantic type, per the newly
      confirmed gate rule (task 1.5).

## 6. Gates and documentation

- [x] 6.1 Run the full backend test suite (server stopped) — **566/566 passed, 0 failures**
      (2026-08-13, after the schema rework below). No occurrence of the previously-documented
      order-dependent flake this run.
- [x] 6.2 Update `/memories/repo/postgres-migration.md` and this change's status once shipped.
      **DONE 2026-08-14** — full suite re-confirmed green (568/568, including the 2 new
      fingerprint-consistency tests) after the schema rework; memory status updated.
- [x] 6.3 STOP for user review — do not commit. The storage side ships fully dormant
      (`semantic_backend` stays `yaml`); the D2 enrichment fix is a live behavior change and its
      measured before/after impact (task 4.1/4.4) must be presented to the user explicitly before
      any commit, same as every prior slice's review gate. **DONE 2026-08-14** — D2's before/after
      (0/54 columns affected) was already presented and discussed with the user during design;
      re-confirmed here. Nothing committed. Awaiting the user's explicit go-ahead to commit.

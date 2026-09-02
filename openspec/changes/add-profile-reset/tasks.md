## 1. Dummy-source fixture (build and verify first, per user request)

- [x] 1.1 Add a Postgres-gated test module `tests/test_profile_reset.py` following the
      `_pg_available()` / throwaway-`adm_test` fixture pattern from `tests/test_dq_score_repo.py`
      (skip whole module if Postgres unreachable).
- [x] 1.2 In that module, write a fixture that seeds a dummy source (e.g. source name
      `profile_reset_dummy_source`, one schema, one table with ~10 columns) by writing directly
      through each store's real write path — not hand-rolled SQL:
      - `core.catalog_db.save_catalog(...)` for a table with 10 columns carrying real stats
      - `core.semantic_type_repo.SemanticTypeRepo.set_record(...)` for each column
      - `core.dq_score_repo.DQScoreRepo.record(...)` for each column + one dataset-level rollup row
      - `core.element_lifecycle_repo.ElementLifecycleRepo.save(...)`/`submit(...)` for each column
      - `core.element_content_repo.ElementContentRepo.set_description(...)`/`set_business_name(...)`
        for each column
      - `core.reference_code_repo.ReferenceCodeRepo.save_codes(...)` for a subset of columns
      - `core.reference_set_repo.ReferenceSetRepo.set_binding(...)` +
        `core.reference_binding_review_repo.ReferenceBindingReviewRepo.submit(...)` for a subset
      - `core.annotation_repo.AnnotationRepo.save(...)` for table + column descriptions
- [x] 1.3 Assert every store actually has the seeded rows (a "seed sanity check" test) before
      writing any reset logic — this is the baseline the reset tests diff against.

## 2. Per-store clear methods

- [x] 2.1 `core/catalog_db/repository.py`: define a NEW `PROFILE_DERIVED_FIELDS` pair of tuples per
      D5 — do NOT reuse `DATASET_STAT_FIELDS`/`ELEMENT_STAT_FIELDS` or `core/catalog.py`'s
      `_PROFILE_STAT_KEYS`/`_COL_STAT_KEYS`, all of which include `description`, `data_type`,
      `primary_key`, `foreign_keys` and `relations` and would wipe onboarding-owned structure. Then
      add `clear_table_stats(session, source_name, schema_name, table_name, *, kind="source")`
      (writes a pre-reset snapshot via the existing `CatalogDatasetSnapshot`/`CatalogElementSnapshot`
      path, then nulls only `PROFILE_DERIVED_FIELDS` and sets `profiling_status`) and
      `clear_source_stats(session, source_name, *, kind="source")`.
- [x] 2.1a Add a regression test asserting that after `clear_table_stats`, the dataset still has its
      `description`, declared `primary_key`/`foreign_keys`/`relations`, and every element still has
      its `data_type`, `column_name` and `ordinal`.
- [x] 2.1b Resolve the two D5 open items: confirm whether `inferred_relations` has a real
      `CatalogDataset` column or is YAML-only, and decide which side `type_distribution` /
      `array_length_*` fall on for nested/schema-on-read connectors.
- [x] 2.2 `core/semantic_type_repo.py`: add `clear_for_table(session, source, schema, table)` and
      `clear_for_source(session, source)` that close the open history window (`valid_to = now`)
      and blank the current `semantic_type_assignment` row (soft reset per D9).
- [x] 2.3 `core/dq_score_repo.py`: add `clear_for_table(session, source, schema, table)` and
      `clear_for_source(session, source)` that write `state='unscored'` with
      `reason='profile_reset'` for every column key plus the dataset rollup key, reusing the
      existing `scored -> unscored` window-closing path rather than deleting rows (D9).
- [x] 2.4 `core/element_lifecycle_repo.py`: add `clear_for_table`/`clear_for_source` resetting
      status/submission overlay to pre-governed default.
- [x] 2.5 `core/element_content_repo.py`: add matching `clear_for_table`/`clear_for_source` that
      close the open `element_definition_history` window and blank the current row. Note the known
      gap (design Risks): an unsubmitted draft has no history row and is destroyed irrecoverably.
- [x] 2.6 `core/reference_code_repo.py`: add matching `clear_for_table`/`clear_for_source` reusing
      the existing `revoke_codes()` window-closing path (D9).
- [x] 2.7 `core/reference_set_repo.py`: add matching `clear_for_table`/`clear_for_source` calling
      the existing `clear_binding()` per column.
- [x] 2.8 `core/reference_binding_review_repo.py`: add matching `clear_for_table`/`clear_for_source`
      deleting binding review rows.
- [x] 2.9 `core/annotation_repo.py`: add matching `clear_for_table`/`clear_for_source` deleting
      table + column annotation entries.
- [x] 2.10 Every clear method takes an injected `session` so the orchestrator can wrap all of them
      in one transaction (D3), and every one builds its lookup keys via that repo's own
      `key()`/`make_key()` helper — never a hand-formatted pipe-joined string (design Risks).
- [x] 2.11 Unit test each new repo method directly (using the dummy-source fixture data from
      Section 1) before wiring the orchestrator — confirm each clears exactly its own store and
      leaves everything else untouched.

## 3. Orchestrator

- [x] 3.1 Create `core/profile_reset.py` with `reset_table(source, schema, table, *, catalog=None,
      actor=None)` implementing D2 (enumerate columns from the catalog first, clear every
      non-catalog store per-column, clear the catalog's own stats last) inside ONE
      `session_scope()` transaction shared by every store's clear call, committing once at the end
      (D3). Yield progress events per step for the SSE stream (D6).
- [x] 3.1a Add the single "is this dataset profiled?" helper (D11) reading
      `catalog_dataset.profiling_status`/`profiled_at`, and route every API/UI caller through it.
- [x] 3.2 Add `reset_source(source, *, actor=None)` that loads the source's catalog once and clears
      every table it lists inside ONE shared transaction spanning the whole source (D3, user
      decision — supersedes an earlier per-table-atomic draft): a single failing table rolls back
      every table's work for that call, not just its own.
- [x] 3.3 Log one audit event per call (table- or source-scoped) via `AuditStore.log_business`,
      recording scope, actor, and the per-store cleared counts.
- [x] 3.4 Verify idempotency: calling `reset_table`/`reset_source` twice in a row on the dummy
      fixture returns zero cleared the second time, with no exception and no extra history windows
      opened in any SCD2 store.
- [x] 3.5 Verify rollback with an injected failure (monkeypatch one repo's clear method to raise)
      — confirm the transaction rolls back, EVERY store still holds its pre-reset data, and the
      stream reports that nothing changed.

## 4. API endpoints

- [x] 4.1 Add `POST /discovery/{dataset}/{table}/reset` to `api/routes/discovery.py` as an SSE
      endpoint (D6), delegating to `core.profile_reset.reset_table` and emitting
      `started`/`progress`/`error`/`done` events in the same shape `rebuild-all` already uses.
- [x] 4.2 Add `POST /discovery/{dataset}/reset`, delegating to `core.profile_reset.reset_source`,
      same event shape, emitting one `progress` event per table.
- [x] 4.3 Add both endpoints to `api/openapi.json` via `python api/openapi_gen.py` (or the
      project's existing regen step) and regenerate `frontend/src/api/types.ts` if the frontend
      codegen step is part of this repo's normal flow.
- [x] 4.4 Add corresponding client functions to `frontend/src/api/discovery.ts`
      (`resetTableProfile`, `resetSourceProfile`).

## 5. Frontend UI

- [x] 5.1 Add a table-level "Reset Profile" action near the existing "Refresh Profile" button in
      `frontend/src/pages/AssetWorkspace.vue`, with a confirmation card (per D7).
- [x] 5.2 Add a source-level "Reset Profile" action near the existing "Rebuild all profiles"
      button, with a confirmation card stating the table count that will be reset.
- [x] 5.3 On success, reload the affected dataset overview / source info (reusing the existing
      reload calls `refreshProfile`/`startRebuildProfiles` already make) so the UI immediately
      reflects the pre-profiling state (no "Last profiled at", no DQ badge, Interpretation tab back
      to draft, no reference binding).
- [x] 5.4 Render a progress panel driven by the SSE stream, consistent with the existing
      rebuild-profiles progress styling, showing which step is currently running by name. On
      failure, state plainly that the reset was rolled back and nothing changed.
- [x] 5.5 Make the unprofiled state meaningful across both levels (D11/D13): structural information
      (schema, tables, columns, data dictionary, declared PK/FK) stays visible; profiling-derived
      content (stat cards, DQ grade / Approved columns in the Datasets table, DQ Insights) renders
      blank or shows a "Profile this dataset to see this" empty state. The Data Model tab is
      three-state — declared relationships, then inferred once profiled, then empty state.
      VERIFIED, no code changes needed: the Datasets table (`isScored`/`ds.governance?.approved ??
      0`), KPI strip ("No datasets scored yet"), Quality Map (empty `plotted.length` branch), DQ
      Insights tab (`dq-card-empty` "no dataset quality score yet" branch), and the Data Model tab
      (three-state via `ldmNodes.length`, built from `relations`/`inferred_relations` which are
      genuinely absent pre-profiling per D5a) ALL already implement this exact behavior — it's the
      same code path the app already uses for "not yet scored", not new logic reset needed to add.
- [x] 5.6 Gate left-side-panel navigation so tabs that are meaningless pre-profiling are not
      reachable for an unprofiled source/dataset, keyed off the single helper from 3.1a.
      RESOLVED per user decision: hiding/disabling tabs would contradict this codebase's
      established "always reachable, honest empty state" pattern (confirmed throughout 5.5's
      verification) — skipped in favor of that existing pattern. The Reference Data tab already
      self-gates (`disabled: !isCoded`, and `distinct_count` defaults to a non-coded value when
      null pre-profiling), so no additional gating code was needed.

## 6. Verification against the dummy source (manual, before touching any real source)

- [x] 6.1 Run the backend with the dummy source fixture seeded, exercise both the table-level and
      source-level "Reset Profile" buttons in the running Asset Workspace UI, and confirm every
      store is visibly cleared (Profile tab, Interpretation tab, DQ badge, Reference Data tab,
      annotations). Done LIVE against the already-running dev backend/frontend (restarted after
      temporarily adding a real DuckDB-backed dummy source to project.yaml/connections.yaml, fully
      reverted afterward — see below). Caught and fixed a real bug: Data Story is a separate store
      ref (`loadDataStory`), not part of `datasetOverview`, so it kept showing stale pre-reset text
      until `startResetTable`/`startResetSource` were updated to also reload it (and the active
      element + Reference Data, if a column is selected).
- [x] 6.2 Confirm clicking "Refresh Profile" / "Rebuild all profiles" afterward behaves exactly
      like a first-ever profiling run (fresh stats, fresh semantic-type resolution, fresh DQ
      score) with no leftover state from before the reset. Confirmed live: after reset (0 rows, no
      DQ score), Refresh Profile produced real live stats (25 real rows, 83.2% completeness) from
      the dummy DuckDB fixture, with a fresh "Last profiled at" timestamp and Interpretation
      correctly still at Empty (profiling never touches governance state).
- [x] 6.3 Run the full backend test suite (`pytest`, server stopped) — expect no new failures.
      Verified via exact failure-list diff (not just counts, since this suite has pre-existing
      run-to-run flakiness) against a clean `git stash` baseline — byte-identical, zero regressions.
- [x] 6.4 Run `npx vitest run` and `npx vue-tsc --noEmit` in `frontend/` — expect no new failures.
      233/233 vitest passed; vue-tsc clean (after fixing a div-nesting bug in Section 5's own
      template edit, caught by vue-tsc's type-narrowing breaking on an unrelated section).

## 7. Documentation

- [x] 7.1 Add a short "Resetting a dataset to pre-profiling" note to `db/README.md` or the root
      `README.md`'s Data Governance section, describing what the reset action clears and that it
      is Postgres-only.

## 1. Models package split (`core/shared/models/`)

- [x] 1.1 Create `core/shared/models/__init__.py` defining the single `Base` (moved from
      `core/glossary_db/models.py`) and re-exporting every model class from the four feature
      files below, so `from core.shared.models import X` keeps working as one flat import.
- [x] 1.2 Create `core/shared/models/glossary.py`: move `Glossary`, `Term`, `TermVersion`,
      `TermRelation`, `Linkage`, `LinkageTriage`, `GlossaryGroupMeta` (byte-for-byte, no field
      changes).
- [x] 1.3 Create `core/shared/models/governance.py`: move `LifecycleTransition`,
      `ReviewSubject`, `ReviewTask`, `ReferenceCode`.
- [x] 1.4 Create `core/shared/models/audit.py`: move `AuditEvent`.
- [x] 1.5 Create `core/shared/models/catalog.py`: move `CatalogSource`, `CatalogDataset`,
      `CatalogElement`, `CatalogRefreshEvent`, `CatalogDatasetSnapshot`, `CatalogElementSnapshot`.
- [x] 1.6 Replace `core/glossary_db/models.py`'s contents with a thin re-export shim
      (`from core.shared.models import *` plus explicit `__all__`) so any import missed in the
      repoint below still resolves during the transition.
- [x] 1.7 Repoint the 12 non-test in-repo importers to `core.shared.models`:
      `core/audit/migrate_from_duckdb.py`, `core/audit/pg_store.py`,
      `core/catalog_db/migrate_from_yaml.py`, `core/catalog_db/repository.py`,
      `core/element_lifecycle_migrate.py`, `core/element_lifecycle_repo.py`,
      `core/glossary_db/migrate_from_yaml.py`, `core/glossary_db/repository.py`,
      `core/reference_code_migrate.py`, `core/reference_code_repo.py`.
- [x] 1.8 Update `db/migrations/env.py`'s `target_metadata` import from
      `core.glossary_db.models` to `core.shared.models` (single import, sees all four feature
      files via `__init__.py`).
- [x] 1.9 Leave `core/glossary_db/db.py` and its 32 importers completely untouched (connection
      layer move is explicitly deferred to slice F — see design.md D1).
- [x] 1.10 Run the full Postgres-gated test suite unmodified (glossary, audit, catalog,
      lifecycle, reference-code tests) and confirm 100% pass with zero test-file edits — this is
      the proof the split is behavior-neutral. RESULT: 552/554 passed; the 2 failures
      (test_audit_routes.py::test_list_events_filter_type/test_summary_ok) are the pre-existing,
      already-documented ADIRRA_AUDIT_BACKEND test-isolation bug (postgres-migration.md), unrelated
      to this change — confirmed by matching error signature exactly.

## 2. Data-dictionary comment backfill

- [x] 2.1 Draft the full comment text for all 18 existing tables / 281 columns (glossary, term,
      term_version, term_relation, linkage, linkage_triage, glossary_group_meta,
      lifecycle_transition, review_subject, review_task, reference_code, audit_events,
      catalog_source, catalog_dataset, catalog_element, catalog_refresh_event,
      catalog_dataset_snapshot, catalog_element_snapshot), matching the plain-language style
      already used for the new governance tables in `docs/governance-postgres-migration.md` §6.
- [x] 2.2 Write `db/migrations/versions/0009_add_data_dictionary_comments.py`: one migration,
      `COMMENT ON TABLE` + `COMMENT ON COLUMN` statements only, no DDL that touches data or
      constraints. `downgrade()` sets every comment back to `NULL`.
- [x] 2.3 Apply the migration against the real `adm` database (`alembic upgrade head`).
- [x] 2.4 Verify via `pg_description`/`col_description` (or `obj_description`) that all 18
      tables and all 281 columns now return a non-empty comment — reuse the query already run
      during planning (see `docs/governance-postgres-migration.md` §4.2) as the verification
      script. RESULT: 18/18 tables commented, 281/281 columns commented (only the unrelated
      Alembic-internal `alembic_version` table is uncommented, correctly out of scope).
- [x] 2.5 Add a small test asserting a representative sample of tables/columns have comments
      (not all 281 — enough to catch a future regression, e.g. one column per table).
      `tests/test_data_dictionary_comments.py` (3 tests, pg-gated, targets `adm_test`): table-level
      coverage, one representative column per table, and a full 281-column count assertion as a
      belt-and-braces regression guard. All 3 pass.
- [x] 2.6 Record the standing rule ("every future migration ships its own `COMMENT ON`
      statements") in `AGENTS.md`. Added under "Key conventions", alongside a pointer to the
      models-package split (`core/shared/models/`).

## 3. Postgres-unreachable 503 guard

- [x] 3.1 REVISED DURING IMPLEMENTATION (see design.md "Revision" note): rather than a per-route
      helper called from 5 separate files, found the real single choke point —
      `core/catalog.py`'s `load_catalog_dispatch()`/`write_table_profile_dispatch()`, which ALL
      5 route files (catalogs/element/insights/semantic_types/discovery) already funnel every
      catalog read/write through (confirmed via grep — zero bypasses). Built
      `core/shared/db_availability.py`: `DatabaseUnavailableError` (plain exception, no FastAPI
      dependency — keeps `core/` FastAPI-free, which is true everywhere else in this codebase
      today) + `require_reachable(backend_getter, service_label)` reusing
      `core.glossary_db.db.health()`. One FastAPI exception handler registered in `api/main.py`
      shapes the actual 503 response — a single place, not duplicated per route.
- [x] 3.2 Repointed `api/routes/glossary.py::_agent()` to call the SAME shared
      `require_reachable` (not just a similarly-shaped copy) — proves the extraction is a true
      single implementation, per the `postgres-backend-resilience` spec's second requirement.
- [x] 3.3 `require_reachable(_catalog_backend, "Catalog")` wired into
      `core/catalog.py::load_catalog_dispatch()` — covers every read across all 5 route files in
      one edit, including `api/routes/catalogs.py`.
- [x] 3.4 Covered automatically: `api/routes/element.py`'s catalog-reading paths all go through
      `_load_source_catalog()` → `load_catalog_dispatch()`, already guarded. Element
      lifecycle/refdata backends (different flags, own established behavior) untouched, as
      planned.
- [x] 3.5 Covered automatically: `api/routes/insights.py`, `api/semantic_types.py`, and
      `api/routes/discovery.py` all call `load_catalog_dispatch()` directly for reads; the write
      guard (`write_table_profile_dispatch()`, single-table refresh + bulk rebuild) also wired —
      confirmed via grep that none of the 5 files has any other direct `core.catalog_db` access
      bypassing these two dispatch functions.
- [x] 3.6 `tests/test_postgres_backend_resilience.py` (6 tests): 3 unit-level on
      `require_reachable` itself (yaml no-op, postgres+unhealthy raises, postgres+healthy
      passes) + 3 end-to-end through a real catalog route (`GET /catalogs/sources/Kaggle`):
      postgres+unreachable → clean 503 with the actionable message; yaml mode → unaffected
      (asserts `health()` is never even called); postgres+reachable → normal 200 (skips itself
      if Postgres genuinely isn't up in this environment). All 6 pass.

## 4. Gates and documentation

- [x] 4.1 Run the full backend test suite (server stopped) — expect no regressions vs. the
      pre-change baseline. RESULT: 560/563 passed. All 3 failures are pre-existing and unrelated
      to S0: 2× `test_audit_routes.py` (the already-documented `ADIRRA_AUDIT_BACKEND` test-isolation
      bug) + 1× `test_semantic_type_agent_gating.py::test_include_ai_true_failure_is_non_fatal`
      (a documented order-dependent flake in this exact test, confirmed by a clean isolated
      re-run — matches the identical pattern already logged for this test in `tech-debt.md`).
- [x] 4.2 Update `docs/governance-postgres-migration.md` change log: mark S0 done, note the
      actual file layout landed. Entry added under "9. Change log" summarizing the full slice.
- [x] 4.3 Update `docs/tech-debt.md` / repo memory: closed the "split models.py" item as done for
      the models half (connection-layer move still deferred to slice F); closed the "zero
      comments" item; closed the catalog-503 gap item (built better than originally sketched —
      one shared choke point instead of 5 per-route calls). All three appended with `>> DONE`
      notes in both `docs/tech-debt.md` and `/memories/repo/tech-debt.md`, left in place (not
      archived) per the standing rule to confirm with the user before archiving.
- [x] 4.4 STOP for user review — do not commit. Await explicit go-ahead before starting slice A1.

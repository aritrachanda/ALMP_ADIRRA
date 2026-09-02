## 1. Pre-implementation sign-off
*Confirm the open design calls before any schema gets built.*

- [x] 1.1 Confirm D2 (PK/FK/relations + sample/top values as JSONB, not normalized) — CONFIRMED
      2026-08-05: proceed with JSONB for now; revisit normalization post-cutover if a real need
      to query these individually shows up
- [x] 1.2 Confirm D8 (append-only snapshot history vs classic SCD2) — CONFIRMED 2026-08-05:
      proceed with the snapshot-table approach for now; revisit post-cutover if needed
- [x] 1.3 Confirm capability name/scope (`source-catalog-postgres-storage`) and that
      `.annotations.yaml` migration stays explicitly out of scope for this change — covered by
      your full artifact review + "good to go" (2026-08-05)

## 2. Schema (Alembic)
*Create the actual Postgres tables — nothing reads or writes them yet.*

- [x] 2.1 Add migration for `catalog_source` (source_id, source_name, kind, connector_type,
      connection_ref, version, schema_hash, generated_at)
- [x] 2.2 Add migration for `catalog_dataset` (dataset_id, source_id FK, schema_name, table_name,
      description, row_count, row_count_error, primary_key/inferred_primary_key/foreign_keys/
      relations JSONB, duplicate_count, duplicate_pct, orphan_fk_count, completeness_summary,
      pct_columns_described, profiled_at, origin_uri, ingested_at, profiling_status,
      content_hash, source_modified_at, size_bytes, file_count, format_hint JSONB) — field
      list mirrors `core/extractors/profiler.py`'s full table-level profile output exactly
- [x] 2.3 Add migration for `catalog_element` (element_id, dataset_id FK, parent_element_id
      self-FK, qualified_column_name, column_name, column_kind, nesting_level, ordinal, data_type, description,
      type_distribution JSONB, array_length_min/max/avg, row_count, null_count, null_pct,
      distinct_count, duplicate_count, uniqueness_pct, empty_string_count, placeholder_count,
      min_value, max_value, length_min, length_max, length_avg, inferred_pattern,
      pattern_confidence, invalid_format_count, code_values JSONB, value_distribution JSONB,
      numeric_avg, numeric_median, numeric_stddev, numeric_outlier_count, outlier_detection,
      decimal_scale_distribution JSONB, future_date_count, suspicious_date_count,
      type_mismatch_count, validator_pass_rates JSONB, constant_run_warning JSONB, stats_error,
      sample_values JSONB, top_values JSONB) — field list mirrors
      `core/extractors/profiler.py`'s full `ColumnProfile` output exactly
- [x] 2.4 Add migration for `catalog_refresh_event` (id, dataset_id FK, refreshed_at,
      triggered_by, changed BOOLEAN) — one row per refresh attempt, always, whether or not
      anything changed
- [x] 2.5 Add migration for `catalog_dataset_snapshot` and `catalog_element_snapshot` (frozen
      copies + captured_at + fingerprint)
- [x] 2.6 Add unique constraints/indexes: `(source_id, schema_name, table_name)`,
      `(dataset_id, qualified_column_name)` (renamed from `path`, refined from `column_name` —
      qualified_column_name is unique per dataset even once nesting exists, D7;
      `(dataset_id, column_name)` kept as a plain non-unique index for leaf-name lookup
      instead), index on `parent_element_id`. ADDED (2026-08-06, post-Phase-8 discussion):
      `UNIQUE(dataset_id, captured_at)` on `catalog_dataset_snapshot` and
      `UNIQUE(element_id, captured_at)` on `catalog_element_snapshot` — both already had a
      surrogate `id` PK but no enforced natural-key uniqueness; now matches the surrogate-PK-
      plus-natural-unique pattern used by every other table in this schema. Applied to the
      migration file, ORM models, and directly to both the live `adm` and `adm_test` databases
      (already-applied migration, so the file edit alone wouldn't retroactively reach them).
- [x] 2.7 Add `legal_entity` column to `catalog_source`
- [x] 2.8 Round-trip upgrade/downgrade verified against adm-postgres (Docker) —
      `db/migrations/versions/0008_add_source_catalog.py`, upgrade → downgrade → upgrade all
      clean; confirmed all 6 tables + 46 `catalog_element` columns present

## 3. Repository layer
*Build the code that reads and writes the new tables, matching today's read shape exactly.*

- [x] 3.1 Create `core/catalog_db/` package (models, db session helpers) mirroring
      `core/glossary_db/` — NOTE (flagged, not a silent deviation): reuses the SHARED
      `core.glossary_db.db`/`core.glossary_db.models` connection layer + ORM Base rather than
      duplicating a separate engine/session setup, matching the established precedent of
      `core/audit/pg_store.py` (a different, unrelated subsystem doing the same). `catalog_db/`
      holds `db.py` (catalog_backend flag) + `repository.py` (all read/write logic); the 6 ORM
      models live in `core/glossary_db/models.py` alongside Glossary/Term/AuditEvent.
- [x] 3.2 Implement read methods returning the same shape as
      `core/catalog.py::load_catalog_with_annotations` (source/schema/table/column dicts)
- [x] 3.3 Implement write methods: whole-source save (initial build) and single-table upsert
      (profile refresh — updates only that table's row + its columns)
- [x] 3.4 Implement annotation merge-on-read against the existing `.annotations.yaml` contract
      (unchanged file location/format)
- [x] 3.5 Implement snapshot capture on profile refresh: fingerprint current stats, skip insert if
      unchanged from the latest snapshot, otherwise append; enforce bounded retention (keep
      first/baseline + latest N, prune the middle)
- [x] 3.6 Implement `catalog_refresh_event` logging: write one row on every refresh attempt
      (regardless of whether stats changed), so "N events ago" can be resolved precisely

**Phase 3 verification (2026-08-05)**: smoke-tested end-to-end against real `adm-postgres` —
whole-source save + load + annotation merge, single-table refresh updating only that dataset,
snapshot dedupe (identical refresh -> no new snapshot), schema drift (new column mid-stream
gets its own row + snapshot), and refresh-event logging on every attempt (including no-op) all
verified correct. Full backend suite: 542 passed, 2 pre-existing failures in
`tests/test_audit_routes.py` traced and confirmed UNRELATED to this work (a pre-existing,
already-documented ADIRRA_AUDIT_BACKEND test-isolation gap materializing now that audit_backend is
live `postgres` — see `/memories/repo/postgres-migration.md`). Nothing reads/writes these
tables from the live app yet — `catalog_backend` flag not wired into any route (Phase 4).

## 4. Flag wiring
*Add the on/off switch — default stays YAML, so nothing changes yet.*

- [x] 4.1 Add `catalog_backend: yaml | postgres` to `project.yaml` (default `yaml`)
- [x] 4.2 Add a factory/dispatch point selecting YAML vs Postgres catalog access based on the flag
      — `core/catalog.py::load_catalog_dispatch` / `save_catalog_dispatch` /
      `write_table_profile_dispatch`. The single-table-refresh dispatch's YAML branch
      intentionally raises `NotImplementedError` rather than silently no-op-ing — that path
      still belongs to `discovery.py`'s existing `_writeback_table_profile` until Phase 6
      repoints it (avoids duplicating that logic here ahead of time).
- [x] 4.3 Verify default (`yaml`) behavior is byte-identical to pre-change behavior — smoke-
      tested both branches directly (yaml writes/reads a real file; postgres round-trips via
      the Phase-3 repository) via `ADIRRA_CATALOG_BACKEND` env override; full backend suite
      543 passed, only the same pre-existing unrelated `test_audit_routes.py` flakiness seen

## 5. Migration + parity script
*Copy real YAML data into Postgres and prove it reads back identically.*

- [x] 5.1 Write a script to load every existing `sources/generated/*.yaml` into
      `catalog_source`/`catalog_dataset`/`catalog_element` — `core/catalog_db/migrate_from_yaml.py`
- [x] 5.2 Write a script to load `mappings/target_catalogs/*.yaml` (bird/crdm) the same way
      (`kind='target'`) — same script, driven by `project.yaml`'s `targets` list
- [x] 5.3 Write a parity check comparing Postgres read-back against the original YAML for every
      migrated source/target — `check_parity()` in the same script; compares by
      (schema,table)/column KEY rather than list position (order can legitimately differ), with
      normalization for JSONB's representation limits (dates -> ISO strings, Decimal -> float,
      relative numeric tolerance for float64 precision at large magnitudes)
- [x] 5.4 Run migration + parity against real repo data (ALM Bank, Faker, Kaggle, banking, bird,
      crdm); fix any discrepancies found — **all 6 PARITY PASS**. Three real bugs found + fixed
      along the way (not data problems — all in the storage/comparison layer):
      1. Postgres's default JSON serializer can't handle raw Python `date`/`datetime` objects
         (real profiled `top_values`/`code_values` entries aren't pre-stringified, unlike
         `sample_values`/`min_value`/`max_value`) — fixed by giving the shared engine
         (`core/glossary_db/db.py`) a `json_serializer` with a proper `default` handler
         (date/datetime -> ISO 8601, everything else -> `str()`) — protects every JSONB write
         across glossary/audit/catalog, not just this one path.
      2. Parity check's date/datetime comparison needed to normalize the YAML side to the same
         ISO 8601 representation Postgres actually stores, rather than raw Python objects.
      3. Large numeric averages (e.g. a big-integer-like ID column) showed as "different" under
         an absolute tolerance — float64 only carries ~15-17 significant digits at that
         magnitude, so an absolute `1e-6` tolerance was meaningless; switched to a relative
         tolerance instead.

## 6. Repoint readers/writers (behind the flag, contract unchanged)
*Make the real app code use the flag — still safe, since the flag defaults to YAML.*

- [x] 6.1 `core/catalog_builder.py` — `save_catalog()` now calls `save_catalog_dispatch`
      (kind threaded through `ensure_catalogs()`/`main()` as `source`/`target` per entry)
- [x] 6.2 `core/catalog.py` — `write_table_profile_dispatch`'s YAML branch is now fully
      implemented (moved from `api/routes/discovery.py._writeback_table_profile`, D2/6.3
      below), not just the postgres branch from Phase 4
- [x] 6.3 `api/routes/discovery.py` — both call sites (`refresh_table_profile`,
      `rebuild_source_profiles`) now call `write_table_profile_dispatch`; the local
      `_writeback_table_profile`/`_PROFILE_STAT_KEYS`/`_COL_STAT_KEYS` were removed (moved
      into `core/catalog.py`, single implementation). Both files' read calls repointed to
      `load_catalog_dispatch`. NOTE: the single-table refresh's write gate was widened from
      `if catalog_path.exists()` to `if catalog_path.exists() or backend()=='postgres'` since
      a postgres-backed source doesn't require a YAML file to exist — flagged to user.
- [x] 6.4 `api/routes/catalogs.py` — repointed to `load_catalog_dispatch`, threading
      `kind='source'|'target'` from the route's existing `type` path param
- [x] 6.5 `api/routes/element.py` — repointed to `load_catalog_dispatch`
- [x] 6.6 `api/semantic_types.py` — repointed to `load_catalog_dispatch` (its own bespoke
      mtime cache wrapper kept as-is, still beneficial since dispatch's postgres branch has
      no caching of its own)
- [x] 6.7 `api/routes/insights.py` — repointed to `load_catalog_dispatch`
- [x] BONUS (not in the original list, found while repointing): `api/main.py`'s
      `_prewarm_catalogs` also called the YAML-only loader directly — repointed too, with
      `kind` correctly threaded per source/target so prewarming respects the flag for both.

**Phase 6 verification (2026-08-06)**: full backend suite 542 passed / 2 pre-existing unrelated
`test_audit_routes.py` failures (documented, same root cause as before — live `audit_backend`
without a test-pinned override); a smoke test (temp script, deleted after) confirmed
`load_catalog_dispatch`/`write_table_profile_dispatch` work end-to-end in postgres mode using
the exact call shape `discovery.py` now uses (read a real migrated table, write+verify+revert
a row_count change) against real data (`banking`).

## 7. Tests
*Prove nothing broke, in both modes.*

- [x] 7.1 Repository-level tests (Postgres-gated, skip if DB down) — `tests/test_catalog_db_repository.py`:
      read shape, missing-source empty dict, annotation merge, single-table upsert isolation
      (sibling table untouched), snapshot dedupe + refresh-event-always-logged (including the
      no-op-refresh-still-logs-an-event case), and retention pruning (keeps baseline + latest N)
- [x] 7.2 Migration/parity script tests against fixture YAML catalogs — `tests/test_catalog_migration.py`:
      migrate + parity pass (including a real date-in-`top_values` fixture, replicating the
      exact shape that exposed the Phase-5 JSONB serialization bug), the `--force`
      skip/re-run guard, parity correctly detecting a real injected mismatch, and the
      missing-YAML-file case
- [x] 7.3 Full existing backend + frontend suites still pass with `catalog_backend` left at
      default (`yaml`) — backend 552 passed (542 + 10 new), same 2 pre-existing unrelated
      `test_audit_routes.py` failures; frontend 251 passed (18 files), untouched by this work

**Phase 7 verification (2026-08-06)**: found and fixed one test-infra gap while writing these —
the throwaway `adm_test` database (used by all Postgres-gated tests) had been created by an
earlier test run BEFORE the `path`→`qualified_column_name` rename and was already at Alembic
head, so re-running `upgrade head` was a no-op and left it on the old column name; fixed with a
one-time downgrade+upgrade of `adm_test` (safe — disposable test DB, no real data). Also found
2 authoring mistakes in my own fixtures during the first test run (not app bugs): an
annotations-file fixture using the wrong top-level YAML key, and a `top_values` fixture shaped
as `{date: count}` instead of the real profiler's `[{"value":..., "count":...}]` list shape —
both fixed to match the real formats.

## 8. User validation and cutover
*The only phase where the live flag actually changes — fully your call.*

- [x] 8.1 Manual UI validation with `catalog_backend: postgres` set locally (via
      `ADIRRA_CATALOG_BACKEND` env override, `project.yaml` left untouched) — scope corrected by
      user mid-validation to **Asset Workspace + Data Standards** (Reference Dataspace/Business
      Glossary), NOT Discovery/Data Catalog/other Data Governance-group pages as originally
      literally worded here. Asset Workspace verified across banking, ALM Bank, Faker, Kaggle:
      source/dataset/element browsing, governance stats, semantic-type mix, data stories.
      Two real bugs found + fixed during this pass (not pre-existing, both introduced/exposed by
      this migration):
      1. A self-inflicted data wipe from my OWN Phase 6 smoke test (passed an empty `columns: []`
         profile, which `upsert_table_profile`'s correct-by-design schema-drift logic read as
         "delete all columns") — fixed by re-running `migrate_from_yaml --force` for all 6
         sources/targets from the untouched original YAML files; re-confirmed ALL PARITY PASS.
      2. A real, load-bearing bug: Postgres returns `NUMERIC` columns as Python `Decimal`, which
         crashed `element.py`'s overview endpoint (`1.0 - Decimal(...)` TypeError) — fixed at the
         single read boundary (`core/catalog_db/repository.py`'s `_snapshot_values` + the
         dataset-level dict construction now convert Decimal → float), so every consumer gets
         the same plain-float shape YAML always gave them.
- [x] 8.2 Performance measured against the YAML baseline — **headline result: ALM Bank's full
      "Rebuild all profiles" (65 datasets, 1,910 columns, 133,007 rows) went from ~2 hours in
      YAML mode (full-catalog-file read+patch+rewrite after EVERY single table, cost growing
      with each table processed) to ~90 seconds in Postgres mode (each table's write is an
      isolated single-table upsert, cost stays flat regardless of table count)** — roughly an
      80x improvement on the exact scenario this migration was meant to fix. Smaller reads
      (dataset/element lists, single-table refresh) also measured in the tens-of-milliseconds
      range once a client-side `localhost`-resolution artifact was ruled out (see repo memory).
- [x] 8.3 User reviews and explicitly approves flipping the live flag — approved 2026-08-07,
      after a multi-round Q&A drilling into caching behavior, PII/DQ findings, rollback
      rehearsal, and Postgres-unreachable handling (all recorded in repo memory); one bug found
      during this discussion (single-table "Refresh Profile" freezing the whole backend) was
      fixed on the spot before approval, not deferred.
- [x] 8.4 Flip `catalog_backend: postgres`, restart backend, re-verify — `project.yaml` edited
      2026-08-07/08 (comment updated to record the flip date + rollback instructions inline);
      backend restarted WITHOUT the `ADIRRA_CATALOG_BACKEND` env override (so the persisted
      `project.yaml` default is what's actually being exercised, not a leftover env var);
      re-verified independently: `/health` 200, `catalogs/sources/banking` 200 in 29ms,
      `element/ALM Bank/tables` 200. User separately confirmed the UI itself looks correct on
      first look.
- [x] 8.5 Document rollback step (flip back to `yaml`) in repo memory; keep YAML files as the
      safety net, no deletion in this change — rollback documented inline in `project.yaml`'s
      own comment (flip `catalog_backend` back to `yaml`, restart) and in repo memory
      (`postgres-migration.md`); rollback was actually REHEARSED once already during Phase 8
      validation (env-var-based, not the persisted flag) and confirmed clean — no data loss,
      `banking` catalog read back correctly in yaml mode afterward. YAML files were never
      touched by any of this work and remain fully intact as the safety net.

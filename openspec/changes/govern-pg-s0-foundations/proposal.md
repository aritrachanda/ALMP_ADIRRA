## Why

We are about to migrate the remaining Data Governance YAML stores (semantic types, DQ scores,
element content, reference sets, learned patterns, catalog annotations) into Postgres, in slices,
following `docs/governance-postgres-migration.md`. Before roughly ten more tables land on top of
the 18 already there, three foundational gaps need closing — otherwise every later slice inherits
them and they get more expensive to fix the longer they wait:

- All 18 existing tables live in one file, `core/glossary_db/models.py`, regardless of which
  feature owns them (glossary, audit, catalog, reference codes, review lifecycle). Adding ~10 more
  tables to that file makes an already-misnamed dumping ground worse. This is a standing tech-debt
  item, parked specifically "revisit after cutover" — that time is now, before it gets harder.
- None of the 18 existing tables or their 281 columns carry a single database comment. A steward
  or reviewer opening the database directly (e.g. in DBeaver) has no way to know what a table or
  column means without reading Python source. The user reviews the data model personally, and the
  product's own thesis is self-describing, governed data — an undescribed database contradicts
  that.
- Only the Business Glossary and BIRD routes currently give a clean, friendly error when Postgres
  is unreachable (`503` with a helpful message). Every other Postgres-backed route path
  (catalog, and every governance slice about to be added) still lets a raw connection exception
  surface as an unhandled stack trace.

None of this moves data or flips a backend flag. It is pure groundwork so the next eight slices
(A1 through F) build on a clean, documented, resilient foundation instead of compounding the same
three gaps ten more times.

## What Changes

- Split the single `core/glossary_db/models.py` into `core/shared/models/` — one file per feature
  (`glossary.py`, `catalog.py`, `audit.py`, `governance.py`), sharing one `Base` and one metadata
  object, with `db/migrations/env.py` updated to import all of them for autogenerate. The shared
  Postgres connection layer (`core/glossary_db/db.py` — engine, session, health check) is **not**
  moved in this change; it keeps working exactly as-is via its current import path and every
  existing caller is unaffected. Moving it is deferred to the final retirement slice (F), tracked
  as a follow-up, alongside a compatibility note in `docs/tech-debt.md`.
- Add a `COMMENT ON TABLE` / `COMMENT ON COLUMN` for **every** table and **every** column already
  in the database — all 18 tables, all 281 columns — in one new, comments-only Alembic migration.
  Zero risk: no data, no constraints, no behavior change, trivially reversible.
- Establish a standing rule (recorded in `AGENTS.md` and `docs/governance-postgres-migration.md`)
  that every future migration ships its `COMMENT ON` statements in the same migration that creates
  the table/column — never as a follow-up.
- Extend the existing "Postgres unreachable → clean `503`" pattern (already used by Glossary and
  BIRD: a startup health-check log line plus a per-request guard) to **every** Postgres-backed
  route family: catalog routes today, and every governance route added by the slices that follow
  this one. One shared guard, reused everywhere, instead of each slice inventing its own.

## Capabilities

### New Capabilities
- `database-schema-documentation`: every Postgres table and column created in this codebase must
  carry a plain-language `COMMENT ON` describing its meaning/purpose, enforced going forward and
  backfilled for everything that already exists.
- `postgres-backend-resilience`: every route backed by a Postgres-selectable backend flag must
  degrade to a clean `503` with an actionable message when the database is unreachable, rather
  than surfacing a raw exception.

### Modified Capabilities
(none — no existing spec documents model file layout or covers DB-down handling for
non-glossary/BIRD routes)

## Impact

- **New**: `core/shared/models/` package (`__init__.py` re-exporting `Base` + all models,
  `glossary.py`, `catalog.py`, `audit.py`, `governance.py`); one new Alembic migration
  (`0009_add_data_dictionary_comments.py`, comments-only); a small shared guard helper (e.g.
  `core/shared/db_guard.py` or reusing `core.glossary_db.db.health()` directly) used by every
  Postgres-backed route module.
- **Changed imports only, no behavior change**: every file importing from
  `core.glossary_db.models` (12 non-test files: `core/audit/migrate_from_duckdb.py`,
  `core/audit/pg_store.py`, `core/catalog_db/migrate_from_yaml.py`,
  `core/catalog_db/repository.py`, `core/element_lifecycle_migrate.py`,
  `core/element_lifecycle_repo.py`, `core/glossary_db/migrate_from_yaml.py`,
  `core/glossary_db/repository.py`, `core/reference_code_migrate.py`,
  `core/reference_code_repo.py`, `db/migrations/env.py`, plus ~12 test files) repoints to
  `core.shared.models`. `core/glossary_db/db.py` and every one of its 32 importers are
  **untouched** in this change.
- **Changed**: `api/routes/catalogs.py`, `api/routes/element.py`, `api/routes/insights.py`,
  `api/routes/semantic_types.py`, `api/routes/discovery.py` gain the same DB-unreachable guard
  `api/routes/glossary.py` already has.
- **Tests**: existing glossary/audit/catalog/lifecycle/reference-code Postgres-gated tests must
  keep passing unchanged after the import repoint (proves the split is behavior-neutral); new
  tests for the comment backfill (spot-check via `obj_description`/`col_description`) and for the
  503 guard on the newly-covered routes.
- **No frontend changes.**

# ADIRRA governance database (PostgreSQL 16)

**Status: LIVE — the default backend for governance/user state.** What started as a
"Business Glossary v2" scaffold is now the default persistence layer for most governance
data, migrated in phased slices (see `openspec/changes/` for the individual migration
proposals). Two different levels of "default" apply:

- **Postgres-only (no YAML/DuckDB fallback left)**: semantic-type assignments
  (`core/semantic_type_store.py`) and DQ scores (`core/dq_score_store.py`) — the legacy
  YAML files were retired once each cutover proved stable; they're archived, not deleted,
  but the code path to read them no longer exists.
- **Postgres by default, YAML/DuckDB kept as a live rollback switch**: Business Glossary,
  the per-element Interpretation lifecycle (draft/submit/approve/...), Reference Data
  (per-code review), the Audit log, and the source/target Catalog (schema + profiling
  stats). Each has its own `project.yaml` → `database:` flag (`glossary_backend`,
  `element_backend`, `refdata_backend`, `audit_backend`, `catalog_backend`), all currently
  set to `postgres`, each overridable per-process via its own `ADM_*_BACKEND` env var
  (e.g. `ADIRRA_CATALOG_BACKEND=yaml`) without editing `project.yaml`.

Source/target catalog data (schema + profiling stats, `catalog_source`/`catalog_dataset`/
`catalog_element`) and DQ/semantic-type/reference-code data all now live in this same
database, alongside the glossary — it's no longer a glossary-only database. Migration `0019`
also added a separate `bird` schema holding the full ECB BIRD Knowledge Base export (all nine
frameworks, read-only, `core/bird_kb.py`) — unrelated to the governance tables above but colocated
in the same Postgres instance rather than its old standalone DuckDB file; see the "BIRD Knowledge
Base" section of the root [README.md](../README.md) for detail.

## Configuration

- Connection details live in `project.yaml` under `database:` (host/port/name/user/schema).
- The password comes from the `ADM_DB_PASSWORD` environment variable (put it in `.env` for
  local dev). If unset, a local-only default `adm_local_dev` is used so a fresh clone boots.
- No DSN or secret is stored in `alembic.ini` — `db/migrations/env.py` assembles it.

## Start / stop (manual dev step, like `uvicorn`)

```bash
docker compose -f db/docker-compose.yml up -d      # start Postgres 16
docker compose -f db/docker-compose.yml ps         # check health
docker compose -f db/docker-compose.yml down       # stop, KEEP data
```

Apply migrations (needs the container running):

```bash
alembic -c db/alembic.ini upgrade head
```

## Seeding a fresh database from the existing YAML/DuckDB data

After `alembic upgrade head` on an empty database, each migrated area has its own one-time
CLI migrator that reads the legacy YAML/DuckDB files and populates Postgres (safe to re-run
with `--force` to overwrite):

```bash
python -m core.glossary_db.migrate_from_yaml            # Business Glossary
python -m core.catalog_db.migrate_from_yaml              # Source + target catalogs (all sources/targets)
python -m core.catalog_db.migrate_from_yaml --name "ALM Bank"   # ...or just one
```

Each migrator also supports a parity/diff check against the source YAML — see the module's
own `--help` and the relevant `openspec/changes/` proposal for the exact flags. Reference
data, DQ scores, semantic types, and audit events have their own equivalent one-time
migrators under `core/` (see each store's module docstring for the exact command).

## Operational story

### RESET — clean database before a demo
```bash
docker compose -f db/docker-compose.yml down -v     # destroy the volume (all data gone)
docker compose -f db/docker-compose.yml up -d       # fresh empty Postgres
alembic -c db/alembic.ini upgrade head              # recreate schema
# Re-run the migrate_from_yaml commands above to repopulate from the legacy YAML files,
# or re-onboard sources fresh — there is no single combined reset+reseed script yet.
```

### PERSISTENCE — where data lives between restarts
- Data is stored in the named Docker volume **`adm_pgdata`** (not a bind mount), so it
  survives `down`, container removal, and machine reboots.
- `docker compose ... down -v` **destroys** `adm_pgdata` and everything in it (glossary
  terms, catalog/profiling data, DQ scores, semantic types, reference data, audit log).
  There is no undo. Only use `-v` for an intentional reset.

### DB DOWN — what the app does when Postgres is unreachable
- Postgres is a manual dev dependency (`docker compose up -d`), not auto-started.
- Built: a health check (`_guard()` in `api/routes/glossary_v2.py`, same pattern used by
  other Postgres-backed routes) returns a clear `503` ("Glossary database is not running.
  Start it with: docker compose -f db/docker-compose.yml up -d") instead of a raw stack
  trace when the database is unreachable.


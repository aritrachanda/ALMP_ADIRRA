## Context

`core/glossary_db/models.py` currently holds all 18 tables in the database, spanning four
unrelated features (Glossary, Audit, Catalog, and review/reference-code governance), and is
imported by 24 files. `core/glossary_db/db.py` holds the shared engine/session/health-check layer
and is imported by 32 files across every Postgres-backed feature. Both filenames now lie about
their scope. This is a known, already-logged tech-debt item (`docs/tech-debt.md`, "PARKED
post-cutover: split core/glossary_db/models.py per-feature"), explicitly deferred until after the
catalog cutover — which is now done.

Separately: zero of the 18 existing tables or 281 columns carry a database comment (verified
directly against the live `adm` database, see `docs/governance-postgres-migration.md` §4.2), and
only two route families (`glossary`, BIRD) handle a down Postgres cleanly.

This is slice **S0** of the eleven-slice governance migration plan
(`docs/governance-postgres-migration.md` §5) — pure groundwork, no data migration, no backend
flag, no behavior change.

## Goals / Non-Goals

**Goals:**
- Give the ~10 new governance tables (slices A–E) a clean home from day one, instead of adding to
  the existing dumping ground.
- Make every table/column in the database self-describing via `COMMENT ON`, both retroactively
  (18 tables today) and as a standing rule for every migration from now on.
- Give every Postgres-backed route a clean `503` instead of a raw stack trace when the database is
  down, using the one pattern that already works (Glossary/BIRD) instead of each future slice
  inventing its own.

**Non-Goals:**
- Moving the shared connection layer (`core/glossary_db/db.py`) — deferred to slice F (retirement
  & cleanup), when backend flags are being removed anyway. A compatibility note goes into
  `docs/tech-debt.md` so this isn't forgotten.
- Any new governance table (semantic types, DQ scores, element content, reference sets, learned
  patterns, annotations) — those are slices A through E.
- Any behavior change to glossary, audit, catalog, or reference-code features — this change must
  be a pure refactor + additive comments + additive error handling for previously-unhandled paths.

## Decisions

### D1 — Models layout: `core/shared/models/` package, split by feature (not per-feature-folder)

Three layouts were considered:

- **A — fully per-feature** (`core/catalog_db/models.py`, `core/audit/models.py`, etc.): puts each
  model file next to its owning feature's code, but leaves nowhere neutral for the shared `Base`,
  and forces `db/migrations/env.py` to import every model module individually for autogenerate to
  see all tables — miss one and autogenerate silently stops seeing those tables. Rejected.
- **B — one package, split by feature inside it** (`core/shared/models/{glossary,catalog,audit,
  governance}.py`, one shared `Base` in `__init__.py`): keeps the same physical separation as A
  without the `Base`-ownership problem, and gives `env.py` one single import that always sees
  every table. **Chosen** (user decision 2026-08-10).
- **C — B, plus move the connection layer too**: the correct long-term end state, but touches all
  32 importers of `core/glossary_db/db.py` in the same change as the model split. Deferred to
  slice F (user decision) — a re-export shim is left in place so nothing importing
  `core.glossary_db.db` needs to change today.

`core/shared/` was chosen over a brand-new top-level package because it already exists as the
agreed neutral home for cross-feature code (`core/shared/json_utils.py` precedent, with a standing
tech-debt reminder to keep sweeping utilities into it).

**Mechanics:**
- `core/shared/models/__init__.py` defines `Base` and re-exports every model class, so
  `from core.shared.models import Term, CatalogSource, AuditEvent, ReviewSubject, ...` keeps working
  as one flat import for existing callers that need multiple models at once.
- `core/shared/models/glossary.py`: `Glossary`, `Term`, `TermVersion`, `TermRelation`, `Linkage`,
  `LinkageTriage`, `GlossaryGroupMeta`.
- `core/shared/models/governance.py`: `LifecycleTransition`, `ReviewSubject`, `ReviewTask`,
  `ReferenceCode` (today's cross-feature review/reference-lifecycle tables; this is also where
  slices A–E's new tables land, matching the file's name).
- `core/shared/models/audit.py`: `AuditEvent`.
- `core/shared/models/catalog.py`: `CatalogSource`, `CatalogDataset`, `CatalogElement`,
  `CatalogRefreshEvent`, `CatalogDatasetSnapshot`, `CatalogElementSnapshot`.
- `core/glossary_db/models.py` becomes a thin re-export shim (`from core.shared.models import *`)
  for one release cycle so any import missed during the mechanical repoint still works; every
  in-repo caller is repointed directly in this same change (no caller should rely on the shim).
- `db/migrations/env.py`'s `target_metadata` import changes from
  `from core.glossary_db.models import Base` to `from core.shared.models import Base` — since all
  four feature files import into the same `__init__.py`, one import still sees every table.

### D2 — Data dictionary comments: backfill depth = every table + every column

User chose the complete option over "non-obvious columns only" — ~299 sentences across 18 tables /
281 columns, written once, in a single comments-only migration
(`0009_add_data_dictionary_comments.py`). Wording style matches the dictionary already drafted for
the new governance tables in `docs/governance-postgres-migration.md` §6: plain language, states
purpose/meaning, not a restatement of the SQL type. This migration touches zero data, zero
constraints — `COMMENT ON TABLE x IS '...'` / `COMMENT ON COLUMN x.y IS '...'` are metadata-only
statements with no lock contention risk and no rollback risk beyond re-running with `IS NULL`.

Going forward (the standing rule, not part of this migration but decided alongside it): every
future migration ships its `COMMENT ON` statements in the same migration that creates the
table/column. Recorded in `AGENTS.md` and `docs/governance-postgres-migration.md` §4.2, enforced
by convention/review rather than tooling for now.

### D3 — 503 guard: extend to all Postgres-backed routes, one shared implementation

User chose "all Postgres-backed routes" over "catalog only". The existing pattern
(`api/routes/glossary.py`'s per-request `backend()=="postgres" and not health()` check, paired
with the startup health-check log line in `api/main.py`) is proven and already shipped — this
change extracts it into one small shared helper (reusing `core.glossary_db.db.health()`, which is
already backend-agnostic despite its glossary-flavored home) so `catalogs.py`, `element.py`,
`insights.py`, `semantic_types.py`, and `discovery.py` all call the same guard instead of each
writing its own copy — and so every governance route added in slices A–E inherits the same
guard for free by following the same one-line convention.

**REVISION during implementation (2026-08-11):** the plan above assumed 5 separate call sites, one
per route file. Implementation found a better single choke point instead — every one of those 5
files already funnels every catalog read through `core/catalog.py::load_catalog_dispatch()` and
every write through `write_table_profile_dispatch()` (confirmed via grep: zero bypasses). Wiring
the guard into those two functions covers all 5 route files, both reads and both write paths
(single-table refresh + bulk rebuild), automatically — including any future route added later,
with no risk of a route forgetting the one-line convention. Since `core/` imports zero FastAPI
anywhere in this codebase (a clean, worth-preserving boundary), the guard couldn't raise
`HTTPException` directly from `core/catalog.py`. Landed as:
- `core/shared/db_availability.py` — a plain `DatabaseUnavailableError` exception (carries which
  feature/service is down) + `require_reachable(backend_getter, service_label)`, FastAPI-free,
  reusing `core.glossary_db.db.health()`. Lives in `core/shared/` (not baked into `catalog.py`
  specifically) so every later governance slice (A–E) can reuse the exact same helper too — the
  user's own suggestion, since the whole point of this capability is reuse beyond catalog.
- `api/main.py` registers **one** `@app.exception_handler(DatabaseUnavailableError)` that shapes
  the actual 503 response (message unchanged from the original glossary wording, service label
  substituted in).
- `api/routes/glossary.py::_agent()` now also calls the same `require_reachable` (not a
  similarly-shaped copy) — this is what makes the spec's "one shared implementation reused across
  route families" requirement literally true, not just true in spirit.

## Risks / Trade-offs

- **[Risk] A missed import during the mechanical models-split repoint silently breaks a migration
  script or repository at runtime instead of at import time.**
  → Mitigation: the temporary re-export shim in `core/glossary_db/models.py` means even a missed
  caller keeps working during the transition; the full Postgres-gated test suite (which exercises
  every one of the 12 non-test importers) is the actual verification gate before this is called
  done, not a grep count.
- **[Risk] 281 hand-written column comments will contain some inconsistency or a copy-paste
  mistake.**
  → Mitigation: low stakes (metadata-only, trivially fixed in a follow-up `COMMENT ON`), and this
  is a one-time backfill, not a repeated cost.
- **[Trade-off] The connection-layer rename is deferred, so `core/glossary_db/db.py` remains a
  misnamed but functioning shared module until slice F.**
  → Accepted per user decision; a `docs/tech-debt.md` entry keeps this from being forgotten.

## Migration Plan

1. Create `core/shared/models/` with the four feature files + `__init__.py`, byte-for-byte moving
   each class (no field/type changes).
2. Turn `core/glossary_db/models.py` into a re-export shim.
3. Repoint the 12 non-test in-repo importers (+ `db/migrations/env.py`) to `core.shared.models`
   directly.
4. Run the full Postgres-gated test suite unchanged — this is the proof the split is behavior
   neutral (existing tests for glossary/audit/catalog/lifecycle/reference-code must all still
   pass without modification, since nothing about the tables themselves changed).
5. Write and apply `0009_add_data_dictionary_comments.py` (comments-only) against the real `adm`
   database.
6. Extract the shared 503 guard helper; wire it into the 5 catalog-family route modules; add a
   focused test per route confirming the clean-503 behavior when the DB is down (mirroring however
   the existing glossary test simulates this).
7. Full backend gate (pytest) green; no frontend changes, so no frontend gate needed.

**Rollback:** every step here is either a pure import-path change (revert the commit) or an
additive, comments-only migration (`alembic downgrade` drops the comments; no data or constraint
impact either way).

## Open Questions

None outstanding — all three decisions (D1/D2/D3) were confirmed with the user before this design
was written.

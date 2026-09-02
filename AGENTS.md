# ADIRRA (Agentic Data Intelligence for Regulatory Readiness Acceleration) — Agent Instructions

## What this project is

ADIRRA is a **working prototype** (demo phase complete) — a full-lifecycle data intelligence platform
for regulatory and risk analytics in financial institutions. It connects to source databases,
extracts/profiles schemas, and uses an LLM to map columns to target regulatory data models (BIRD,
CRDM today). It also has a multi-agent chat interface for CRR3/DPM Q&A and an AI-enriched business
glossary.

The platform vision: datasets flow **onboarded → governed → profiled → defined → measured →
protected → modelled → mapped → transformed → visualised**. Only the **Data Governance** layer is
built today; the rest is roadmap. Engineer to working-prototype standards (proper error handling,
tested critical paths) — do not add production-scale concerns (HA, horizontal scaling, hardened
auth) unless explicitly asked.

## Tech stack

- **Backend**: Python 3.11+, FastAPI (`api/`, SSE streaming for mapping progress), DuckDB
  (local/embedded) via `core/connectors.py`. LLM calls go through a
  provider-dispatched layer (`agents/mapping_agent.py` `_PROVIDERS`) supporting `azure` (Azure
  Foundry — current default), `openai`, and `gemini`; the Azure/OpenAI SDK client is built by the
  single factory `foundry_client.py` (`create_foundry_client`).
- **Governance database**: PostgreSQL 16 (`db/`, Docker Compose + Alembic migrations) is the
  default persistence layer for governance/user state (Business Glossary, element Interpretation
  lifecycle, Reference Data, Audit log, source/target Catalog, semantic types, DQ scores) —
  semantic types and DQ scores are Postgres-only (no YAML fallback left); the rest can still be
  switched back to their legacy `yaml`/`duckdb` backend per-process via `project.yaml`'s
  `database:` block or its per-store `ADM_*_BACKEND` env var override. See `db/README.md`.
- **Frontend**: Vue 3 + Quasar 2 + TypeScript + Vite in `frontend/` (dev server port 9000), Pinia
  stores. The only UI — a legacy Streamlit app (`ui/`) was retired 2026-08-28.
- **Data formats**: YAML for config (`project.yaml`, `connections.yaml`) and a few remaining
  YAML-backed governance stores (see above); Excel for target data model source files.

## Dev commands

```bash
# Backend — run from repo root, one instance at a time (see gotcha below)
uvicorn api.main:app --port 8000          # add --reload only if you understand the risk below
pytest                                     # full backend test suite

# Frontend — run from frontend/
npm run dev                                # Vite dev server, port 9000
npm run test                               # vitest run
npx vue-tsc --noEmit                       # type-check
npm run lint                               # eslint . --ext .ts,.vue
npm run build                              # lint + vue-tsc + vite build (this is the full CI gate)
```

Frontend-specific conventions (Quasar/Pinia patterns, test layout) are in
[.github/instructions/frontend.instructions.md](.github/instructions/frontend.instructions.md).

## Critical gotchas

- **DuckDB is single-writer.** Only ONE `uvicorn api.main:app` process may run at a time — a second
  instance fails with `IOException: ... used by another process` and can interleave writes to any
  DuckDB-backed file still in use (source connection files under `sources/duckdb/`, or a governance
  store you've overridden back to its legacy `yaml`/`duckdb` backend — most governance data is
  PostgreSQL-backed by default today, see `db/README.md`). Check for an existing backend before
  starting a new one.
- **`--reload` orphans a child process.** Uvicorn's `--reload` runs a reloader parent + a worker
  child; the child (not the parent) holds the DuckDB lock. Killing only the parent orphans the
  child and leaves the lock held. Prefer running without `--reload`, or tree-kill by port:
  `Get-NetTCPConnection -LocalPort 8000 -State Listen | ForEach-Object { taskkill /PID $_.OwningProcess /T /F }`
- **Always `yaml.safe_dump()`, never `yaml.dump()`** when writing catalog/governance YAML.
- **DuckDB SQL has no `POSITION(needle IN haystack)`** — use `STRPOS(haystack, needle)` instead
  (1-indexed, returns 0 if not found).
- Backend tests redirect audit/state/DQ-score paths via env vars
  (`AI_TIMO_AUDIT_DB`/`AI_TIMO_ELEMENT_STATE`/`AI_TIMO_DQ_SCORES`, set in `tests/conftest.py`) so
  `pytest` never touches real `audit/`/`governance/` data — legacy `AI_TIMO_*` naming is intentional
  and does not need to be renamed to match the app.

## LLM portability — hard constraint

The app must be **completely LLM-agnostic**. Provider selection, API keys, and endpoints come
exclusively from `.env` + `project.yaml` (`agent.provider` / `agent.model` / `agent.api_key_env`)
— never hardcode a provider name, key, or endpoint anywhere in the codebase. Build the client via
`foundry_client.create_foundry_client(...)` (the single client factory) rather than instantiating
SDK clients directly.

## Making changes

- Implement exactly what's asked — do not add conditional visibility, runtime gating, or "smart"
  fallback behavior the user didn't request (e.g. hiding a schema dropdown just because a source
  has only one schema). Render what was asked for.
- **When in doubt, ask.** If you're genuinely unsure about scope, intent, or whether to add a
  conditional / edge-case behavior, ask the user first rather than guessing.

## Key conventions

- Config: `project.yaml`, `connections.yaml` at repo root.
- Source catalogs: `sources/generated/*.yaml` (auto-generated, don't hand-edit).
- Target catalogs: `mappings/target_catalogs/*.yaml` (BIRD/CRDM currently frozen).
- Mapping results: `mappings/results/`.
- Agent code: `agents/` (one file per LLM agent — mapping, bird_mapping, chat, crr, dpm, glossary,
  semantic_type, catalog, assessment).
- Core library: `core/` (connectors, catalog builder, extractors, DQ scoring, semantic types).
- **Chat assistant/persona name is user-customizable** via `persona.yaml` (and the persona settings
  UI) — never hardcode a display name (e.g. `Aylin`) in code, prompts, or reset defaults
  (`api/routes/settings.py`). Read it from persona config/state instead.
- Secrets: `.env` only — never hardcoded, never committed.
- `docs/` and `.github/prompts/` are **entirely gitignored** (local-only working notes/prompts) —
  don't expect them to exist on a fresh clone, and don't treat their absence as broken.
- **Tech-debt tracking lives in two places that must be kept in sync**: agent memory
  `/memories/repo/tech-debt.md` (open items) + `/memories/repo/tech-debt-archive.md` (resolved and
  committed items), mirrored 1:1 at `docs/tech-debt.md`/`docs/tech-debt-archive.md` (gitignored,
  directly browsable in the repo). Whenever you add, resolve, or archive a tech-debt entry, update
  BOTH the memory copy and its `docs/` mirror in the same turn — don't let them drift. When an item
  becomes fully resolved AND committed, move it out of the live file into the archive file (both
  copies), correcting any "NOT YET COMMITTED" language to reference the real commit hash.
- **Every Postgres migration ships its own `COMMENT ON TABLE`/`COMMENT ON COLUMN` statements** for
  every table/column it creates, in the same migration — in plain, non-jargon language describing
  what the thing means/its purpose, not a restatement of its SQL type (see
  `db/migrations/versions/0009_add_data_dictionary_comments.py` for the wording style, and
  `docs/governance-postgres-migration.md` §4.2/§6 for the full rationale). ORM models live in
  `core/shared/models/` (split by feature: `glossary.py`/`governance.py`/`audit.py`/`catalog.py`,
  one shared `Base`) — `core/glossary_db/models.py` is now a backwards-compatible re-export shim,
  new code should import from `core.shared.models` directly.

## OpenSpec CLI

Run OpenSpec commands with `npx` (e.g. `npx openspec list`, `npx openspec propose`) — bare
`openspec` may not resolve. See the `openspec-propose`/`openspec-apply-change`/
`openspec-archive-change`/`openspec-explore` skills for the full change workflow.

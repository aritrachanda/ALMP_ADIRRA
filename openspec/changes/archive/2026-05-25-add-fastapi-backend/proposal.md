# Add a FastAPI backend exposing core/ and agents/ over HTTP

## Why

The production UI is migrating from Streamlit to Vue/Quasar (see `build-vue-frontend`). A SPA cannot import Python modules directly — we need a thin HTTP API layer over the existing `core/` services and `agents/` so the Vue frontend has a stable, typed contract. The agents and core logic are already well-separated from the Streamlit UI, so wrapping them in REST endpoints is straightforward.

## What Changes

### FastAPI app in existing `api/` directory
- The `api/` directory already has empty scaffolding (`routers/`, `routes/`, `schemas/`). Build the FastAPI app here — no repo restructure, no moving `core/` or `agents/`.
- Thin routers under `api/routes/`:
  - `health.py` — liveness/readiness
  - `catalogs.py` — list sources/targets, get catalog with tables/columns
  - `mappings.py` — list/get/save mappings, accept/discard candidates, run mapping (sync + SSE stream)
  - `glossary.py` — get glossary, CRUD terms, AI-assisted term generation, uncovered concepts
  - `chat.py` — list/get/create conversations, append messages
  - `discovery.py` — table stats, DuckDB query execution, column profiling
  - `annotations.py` — get/set table and column annotation overlays
- All endpoints return JSON. Pydantic v2 schemas in `api/schemas/` drive validation and OpenAPI generation.
- Mapping agent streaming via SSE (`POST /mappings/{source}/{target}/run-stream`) using the existing `mapping_sse.py` adapter. Sync endpoint for small datasets / tests.

### No repo restructure
- `core/` and `agents/` stay at repo root. The API imports from them directly (same as Streamlit does today).
- No shims, no `git mv`, no broken imports. Streamlit continues to work unchanged during the migration window.

### Configuration
- `api/main.py` reads existing `project.yaml`, `connections.yaml`, and `.env` from repo root.
- CORS origins configurable via env (`AI_TIMO_CORS_ORIGINS`). Default for dev: `http://localhost:9000`.

### Out of scope
- Authentication / authorization (single-user demo)
- Database for state (everything stays file-based: YAML / JSON)
- WebSocket transport (SSE is sufficient)
- Production deployment (Docker, CI)
- Frontend (handled by `build-vue-frontend`)

## Capabilities

### New Capabilities
- `http-api`: FastAPI application exposing catalogs, mappings, glossary, chat, discovery, and annotation endpoints with Pydantic v2 schemas and auto-generated OpenAPI docs.
- `streaming-mapping-agent`: SSE endpoint for streaming live mapping agent progress using the existing MappingEvent/mapping_sse infrastructure.

### Modified Capabilities
_(none — this is a new layer wrapping existing logic)_

## Impact

- **New dependencies**: `fastapi`, `uvicorn[standard]`, `pydantic>=2`, `sse-starlette`. All MIT/BSD.
- **Affected code**: populates the existing empty `api/` directory. No changes to `core/`, `agents/`, `ui/`, or data files.
- **Sequencing**: This change ships first. `build-vue-frontend` depends on it.

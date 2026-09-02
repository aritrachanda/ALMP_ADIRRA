# Design — add-fastapi-backend

## Context

The Vue/Quasar frontend needs a stable HTTP contract against the existing Python business logic. Today, Streamlit pages import `core/` and `agents/` directly — in-process, no API boundary. The agents and core modules are well-separated from the UI already, so wrapping them in FastAPI routes is thin plumbing, not a rewrite.

The `api/` directory already exists with empty scaffolding (`routers/`, `routes/`, `schemas/`). The SSE adapter for the mapping agent (`agents/agent_utils/mapping_sse.py`) is already built.

## Goals / Non-Goals

**Goals:**
- A FastAPI app in `api/` that exposes every operation the Streamlit pages currently perform.
- OpenAPI schema auto-generated for frontend type generation.
- Streamlit keeps working unchanged — no repo restructure.
- Async endpoints for I/O-bound operations (LLM calls, DB queries); sync for trivial reads.

**Non-Goals:**
- Auth, multi-user.
- Persistence beyond current file-based storage (YAML/JSON).
- WebSocket transport (SSE suffices).
- Containerization, CI, deployment.
- Frontend code (handled by `build-vue-frontend`).

## Decisions

### D1. No repo restructure — API at `api/`

Keep `core/` and `agents/` at repo root. The FastAPI app lives in `api/` and imports directly:

```
ai-timo/
├── api/
│   ├── main.py
│   ├── deps.py          (DI: project config, connections, stores)
│   ├── routes/
│   │   ├── health.py
│   │   ├── catalogs.py
│   │   ├── mappings.py
│   │   ├── glossary.py
│   │   ├── chat.py
│   │   ├── discovery.py
│   │   └── annotations.py
│   └── schemas/
│       ├── catalog.py
│       ├── mapping.py
│       ├── glossary.py
│       ├── chat.py
│       ├── discovery.py
│       └── annotation.py
├── agents/              (unchanged)
├── core/                (unchanged)
├── ui/                  (unchanged — Streamlit fallback)
├── frontend/            (added by build-vue-frontend)
├── connections.yaml
├── project.yaml
└── ...
```

**Why not move to `backend/`?** Adds complexity (shims, broken imports, path manipulation) for no benefit in a demo app. The current flat layout works fine — `api/` imports from `core/` and `agents/` the same way `ui/` does.

### D2. Dependency injection via `api/deps.py`

Shared resources loaded once at startup via FastAPI lifespan:
- `get_project()` — parsed `project.yaml`
- `get_connections()` — parsed `connections.yaml`
- `get_glossary_agent()` — `GlossaryAgent` instance
- `get_chat_store()` — `ChatHistory` manager

Route functions declare these as `Depends(...)` parameters.

### D3. SSE for the mapping agent

The mapping agent generators (`map_source_to_target_stream`, `map_source_to_bird_stream`) yield `MappingEvent` TypedDicts. The SSE adapter in `mapping_sse.py` already formats these for HTTP streaming.

**Endpoint**: `POST /mappings/{source}/{target}/run-stream` returns `text/event-stream`.

**SSE event types** (from `mapping_sse.py`):
- `analyzing`, `candidates`, `scoring`, `validating` → `event: status`
- `columns`, `table_done` → `event: candidate`
- `error` → `event: error`
- `done` → `event: done`

**Sync fallback**: `POST /mappings/{source}/{target}/run` for small datasets and tests.

### D4. Pydantic v2 schemas

Every request/response is a Pydantic model. The same models drive OpenAPI generation. We commit `api/openapi.json` so the frontend can generate types deterministically.

### D5. Endpoint inventory

| Group | Method | Path | Description |
|-------|--------|------|-------------|
| Health | GET | `/health` | Liveness check |
| Health | GET | `/readiness` | Catalog-load status |
| Project | GET | `/project` | Project config (name, agent settings) |
| Catalogs | GET | `/catalogs/{type}` | List sources or targets |
| Catalogs | GET | `/catalogs/{type}/{name}` | Get catalog with tables |
| Catalogs | GET | `/catalogs/{type}/{name}/{table}` | Get table with columns |
| Mappings | GET | `/mappings` | List all mapping files |
| Mappings | GET | `/mappings/{source}/{target}` | Get mapping result |
| Mappings | POST | `/mappings/{source}/{target}/run` | Run mapping (sync) |
| Mappings | POST | `/mappings/{source}/{target}/run-stream` | Run mapping (SSE) |
| Mappings | PATCH | `/mappings/{source}/{target}/candidates` | Accept/discard candidates |
| Mappings | PUT | `/mappings/{source}/{target}` | Save mapping result |
| Glossary | GET | `/glossary` | Full glossary with terms |
| Glossary | GET | `/glossary/terms/{id}` | Single term |
| Glossary | PUT | `/glossary/terms` | Create/update term |
| Glossary | DELETE | `/glossary/terms/{id}` | Delete term |
| Glossary | POST | `/glossary/terms/{id}/ai-suggest` | AI-assisted field generation |
| Glossary | GET | `/glossary/uncovered` | Uncovered source concepts |
| Chat | GET | `/chat/conversations` | List conversations |
| Chat | POST | `/chat/conversations` | Create conversation |
| Chat | GET | `/chat/conversations/{id}` | Get conversation |
| Chat | POST | `/chat/conversations/{id}/messages` | Send message, get reply |
| Chat | DELETE | `/chat/conversations/{id}` | Delete conversation |
| Discovery | GET | `/discovery/{dataset}/{table}/stats` | Table/column stats |
| Discovery | POST | `/discovery/{dataset}/{table}/query` | Execute DuckDB query |
| Annotations | GET | `/annotations/{dataset}` | Get annotation overlay |
| Annotations | PUT | `/annotations/{dataset}/{table}` | Set table/column annotations |

### D6. CORS

Allowed origins via `AI_TIMO_CORS_ORIGINS` env var (comma-separated). Default: `http://localhost:9000`.

### D7. Dev workflow

```bash
# Start backend
uvicorn api.main:app --reload --port 8000

# Regenerate OpenAPI schema
python -m api.openapi_gen   # writes api/openapi.json
```

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| API design ossifies wrong abstractions | Tag as `v0`; don't promise stability until Vue port is live. |
| Chat endpoint needs to call LLM (slow) | Make it async; stream response if needed later. For now, sync is fine for demo. |
| Discovery query endpoint exposes SQL execution | Read-only queries only; same safety as the existing chat agent's `query_data` tool. |
| Pydantic v2 vs existing dict-based code | Schemas wrap, don't replace, internal dicts. Core code unchanged. |

## Open Questions

- Should mapping results be cached server-side, or does the frontend always re-fetch from the YAML file? Default: re-fetch from file (simple, matches current behavior).
- Do we need an upload endpoint for new source databases? Default: defer until needed.

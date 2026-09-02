# Tasks — add-fastapi-backend

## 1. Setup & scaffolding

- [x] 1.1 Update `requirements.txt` to add `fastapi`, `uvicorn[standard]`, `pydantic>=2`, `sse-starlette`. Pin major versions.
- [x] 1.2 Create `api/main.py`: FastAPI app, CORS middleware reading `AI_TIMO_CORS_ORIGINS` env var, lifespan that loads `project.yaml` and `connections.yaml` once.
- [x] 1.3 Create `api/deps.py` with DI helpers: `get_project()`, `get_connections()`, `get_glossary_agent()`, `get_chat_store()`.
- [x] 1.4 Create `api/routes/__init__.py` and `api/schemas/__init__.py` (ensure package structure).
- [x] 1.5 Create `api/routes/health.py` with `GET /health` returning `{"status":"ok"}` and `GET /readiness` returning project config status.
- [x] 1.6 Add a `pytest` smoke test that boots the app via `httpx.AsyncClient` and hits `/health`.
- [x] 1.7 Confirm `streamlit run ui/app.py` still works (no imports broken by adding api/).

## 2. Catalogs API

- [x] 2.1 Define Pydantic schemas in `api/schemas/catalog.py`: `CatalogList`, `Catalog`, `Table`, `Column` mirroring the YAML catalog shape.
- [x] 2.2 `GET /catalogs/{type}` — list source or target catalog names (type = sources | targets).
- [x] 2.3 `GET /catalogs/{type}/{name}` — return the parsed catalog with tables.
- [x] 2.4 `GET /catalogs/{type}/{name}/{table}` — return one table with column metadata.
- [x] 2.5 Tests: load each fixture catalog via the API and assert table/column counts match YAML.

## 3. Mappings API

- [x] 3.1 Define schemas in `api/schemas/mapping.py`: `MappingResult`, `MappingTable`, `MappingCandidate`, `ColumnMapping`, `MappingRunRequest`.
- [x] 3.2 `GET /mappings` — list `(source, target)` pairs that have a YAML in `mappings/`.
- [x] 3.3 `GET /mappings/{source}/{target}` — return the parsed mapping YAML.
- [x] 3.4 `POST /mappings/{source}/{target}/run` — sync mapping run; body has `dataset_context`, `agent_choice`, `selected_tables`.
- [x] 3.5 `POST /mappings/{source}/{target}/run-stream` — SSE-streamed run using existing `mapping_sse.py` adapter; emits `status`, `candidate`, `done`, `error` SSE events.
- [x] 3.6 `PATCH /mappings/{source}/{target}/candidates` — batch accept/discard candidates; persist to YAML.
- [x] 3.7 `PUT /mappings/{source}/{target}` — save full mapping result.
- [x] 3.8 Tests: round-trip accept→re-fetch; SSE endpoint returns 200 and yields events.

## 4. Glossary API

- [x] 4.1 Define schemas in `api/schemas/glossary.py`: `Glossary`, `GlossaryTerm`, `TermUpdate`, `UncoveredConcept`.
- [x] 4.2 `GET /glossary` — full glossary with terms and metadata.
- [x] 4.3 `GET /glossary/terms/{id}` — single term by ID.
- [x] 4.4 `PUT /glossary/terms` — create/update term; writes to `glossary/glossary.yaml`.
- [x] 4.5 `DELETE /glossary/terms/{id}` — remove term.
- [x] 4.6 `POST /glossary/terms/{id}/ai-suggest` — AI-assisted term field generation using `glossary_agent.suggest_term_update()`.
- [x] 4.7 `GET /glossary/uncovered` — uncovered source concepts via `glossary_intake.find_uncovered_source_concepts()`.
- [x] 4.8 Tests: CRUD round-trip; uncovered endpoint returns expected shape.

## 5. Chat API

- [x] 5.1 Define schemas in `api/schemas/chat.py`: `ConversationSummary`, `Conversation`, `Message`, `SendMessageRequest`.
- [x] 5.2 `GET /chat/conversations` — list conversation summaries (id, title, updated_at).
- [x] 5.3 `POST /chat/conversations` — create new conversation.
- [x] 5.4 `GET /chat/conversations/{id}` — full conversation with messages.
- [x] 5.5 `POST /chat/conversations/{id}/messages` — send user message, get assistant reply (calls `chat_agent.chat()`).
- [x] 5.6 `DELETE /chat/conversations/{id}` — delete conversation file.
- [x] 5.7 Tests: create→send→fetch round trip.

## 6. Discovery API

- [x] 6.1 Define schemas in `api/schemas/discovery.py`: `TableStats`, `ColumnStats`, `QueryRequest`, `QueryResult`.
- [x] 6.2 `GET /discovery/{dataset}/{table}/stats` — table and column statistics (row count, null %, distinct, samples).
- [x] 6.3 `POST /discovery/{dataset}/{table}/query` — execute read-only DuckDB/Snowflake query; return results as JSON rows.
- [x] 6.4 Tests: stats endpoint returns expected column metadata; query endpoint executes simple SELECT.

## 7. Annotations API

- [x] 7.1 Define schemas in `api/schemas/annotation.py`: `AnnotationOverlay`, `TableAnnotation`, `ColumnAnnotation`.
- [x] 7.2 `GET /annotations/{dataset}` — get annotation overlay for a dataset.
- [x] 7.3 `PUT /annotations/{dataset}/{table}` — set table-level and column-level annotations; writes to `.annotations.yaml`.
- [x] 7.4 Tests: write annotation then read back; verify it doesn't modify the source catalog.

## 8. OpenAPI generation & docs

- [x] 8.1 Create `api/openapi_gen.py` script that writes `api/openapi.json` from the live app schema.
- [x] 8.2 Commit `api/openapi.json`.
- [x] 8.3 Update repo root `README.md` with backend quickstart: `uvicorn api.main:app --reload --port 8000`.

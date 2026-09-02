# Spec delta — http-api (ADDED)

## ADDED Requirements

### Requirement: The system SHALL expose a versioned HTTP API over `core/` services

A FastAPI application SHALL expose catalog browsing, mapping runs and edits, glossary CRUD, and chat conversations. Endpoints SHALL accept and return JSON validated by Pydantic v2 schemas. The OpenAPI schema SHALL be generated and committed to the repository as `api/openapi.json`.

#### Scenario: Health endpoint reports liveness

- **WHEN** a client requests `GET /health`
- **THEN** the API responds with HTTP 200 and body `{"status":"ok"}`

#### Scenario: Catalogs list returns project sources and targets

- **WHEN** a client requests `GET /catalogs`
- **THEN** the API responds with HTTP 200
- **AND** the body contains the names of every source and target listed in `project.yaml`

#### Scenario: Mapping accept persists to YAML

- **WHEN** a client issues `PATCH /mappings/{source}/{target}/candidates/{t}/{c}` with body `{"status":"accepted"}`
- **THEN** the API responds with HTTP 200
- **AND** the corresponding `mappings/<source>_to_<target>.yaml` file on disk has the candidate's `status` set to `accepted`

#### Scenario: Glossary upsert creates a new term

- **WHEN** a client issues `PUT /glossary/terms` with a term not yet present in the glossary
- **THEN** the API responds with HTTP 200
- **AND** subsequent `GET /glossary` includes the new term under the requested `(category, subcategory)`

#### Scenario: Chat append returns user and assistant turns

- **WHEN** a client issues `POST /chat/conversations/{id}/messages` with `{"content":"hi"}`
- **THEN** the API responds with HTTP 200
- **AND** the response contains both the appended user turn and a stubbed assistant turn
- **AND** the conversation's JSON file on disk contains both turns

#### Scenario: OpenAPI is committed and matches runtime

- **GIVEN** `api/openapi.json` is committed to the repository
- **WHEN** the test `test_openapi_matches_runtime` runs
- **THEN** the on-disk file equals the schema served by the live application

### Requirement: CORS SHALL be configurable per environment

The API SHALL enable CORS for origins listed in the environment variable `AI_TIMO_CORS_ORIGINS` (comma-separated). When unset, the API defaults to `http://localhost:9000` (the Vue dev server URL).

#### Scenario: Default CORS origins allow Quasar dev server

- **WHEN** `AI_TIMO_CORS_ORIGINS` is unset and a browser request comes from `http://localhost:9000` (Vue dev server)
- **THEN** the response includes the appropriate `Access-Control-Allow-Origin` header

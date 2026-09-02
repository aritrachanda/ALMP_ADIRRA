# Build Vue/Quasar frontend replacing Streamlit UI

## Why

Streamlit has reached its ceiling for this product. The current UI fights the framework at every step — no real layout control, no reusable components, brittle CSS hacks for basic patterns like collapsible navigation, inline editing, and cross-page state. The `polish-ui-to-figma` change proved this: after 58/63 tasks, visual fidelity was still well below what we need for demos.

The team standard frontend is Vue 3 + Quasar + TypeScript + Pinia — proven in the aldares project. Combined with the FastAPI backend (`add-fastapi-backend`), we get a clean separation between presentation and business logic, proper component architecture, and a UI that can match the DPMM Figma mockups.

This is a full migration — all pages, not a partial port. The Streamlit `ui/` directory is retired when complete.

## What Changes

### New `frontend/` directory
- Vue 3 SPA with Quasar 2.x, TypeScript, Pinia, Vue Router, Vite.
- Direct communication with FastAPI backend at `:8000` — no Express BFF layer.
- DPMM design tokens wired into Quasar brand config and SCSS variables.
- Typed API service layer using types generated from the backend's `api/openapi.json`.

### All pages migrated (not demo-scoped)

**Phase 1 — Shell:**
- App shell: `QLayout` + `QHeader` (brand, notifications, user) + `QDrawer` (grouped navigation matching current Streamlit IA).
- Vue Router mirroring the Streamlit page structure.

**Phase 2 — Independent pages (no cross-page deps):**
- **Chat**: Two-pane layout (conversation list + chat area), hero greeting with suggestion chips, streaming assistant responses, conversation CRUD.
- **Mapping**: Source/target selector, agent choice, three-tab result view (Visualization with vis-network graph, Table with flat dataframe, Raw with accept/discard editor), SSE streaming progress, SQL preview.

**Phase 3 — Coupled cluster (migrated as one unit):**
- **Catalog**: Dataset/table browser, column stats, inline annotation editing, AI description generation, glossary cross-references.
- **Glossary**: Domain/category tree with search, term detail with per-section editing, AI-assisted generation, uncovered concepts discovery, export/sync.
- **Discovery**: Table/column stats browser, inline chat panel scoped to selected table, DuckDB query execution, Plotly chart rendering.
- Cross-page navigation via Vue Router (`router.push`) + Pinia stores replacing Streamlit's `session_state` jumps.

**Phase 4 — Stubs and polish:**
- Dashboard, Input Data, Data Model, Corrections, Active Reports, Reporting History, Settings, Audit Log, About — styled placeholder pages.

**Phase 5 — Retire Streamlit:**
- Remove `ui/` directory.
- Remove `streamlit` and `streamlit-agraph` from `requirements.txt`.
- Update `README.md`.

### Patterns adopted from aldares
- MainLayout with QLayout/QHeader/QDrawer (from aldares `MainLayout.vue`)
- Pinia stores per domain (from aldares store pattern)
- vis-network graph component (from aldares `LineageGraph.vue`)
- QTable with column visibility toggle (from aldares `ActiveReportsTable.vue`)
- Typed central `types/index.ts` (from aldares pattern)

### Cross-page state approach
Streamlit's `session_state` global bag is replaced by:
- **Pinia stores** for shared domain data (catalogs, glossary terms, mappings)
- **Vue Router query params** for deep-linking (e.g., `?term=risk-weight` in glossary)
- **`router.push()`** for cross-page navigation with context (replaces `st.switch_page()` + `catalog_jump`/`discovery_jump`)

### Out of scope
- Authentication / SSO
- Internationalization
- Mobile / responsive below 1024px
- Production deployment (Docker, CI)
- Express BFF — going direct Vue → FastAPI

## Capabilities

### New Capabilities
- `vue-app-shell`: QLayout-based app shell with branded header, collapsible drawer with grouped navigation, Vue Router with all page routes.
- `vue-chat-page`: Two-pane chat with conversation list, hero greeting, suggestion chips, streaming assistant responses via the FastAPI chat endpoint.
- `vue-mapping-page`: Source/target selector, three-tab result view (vis-network Visualization, Table, Raw editor), SSE streaming progress from the mapping API.
- `vue-catalog-page`: Dataset/table browser with column stats, inline annotation editing, AI description generation, glossary cross-reference navigation.
- `vue-glossary-page`: Domain/category tree browser with search, term detail with per-section inline editing, AI-assisted generation, uncovered concepts grid.
- `vue-discovery-page`: Table/column stats browser with inline chat panel, DuckDB query execution, chart rendering.

### Modified Capabilities
_(none — new frontend layer; existing backend/agent code unchanged)_

## Impact

- **New folder**: `frontend/` with its own `package.json`. Independent from Python code.
- **New dev dependencies**: Vue 3, Quasar 2, Pinia, Vue Router, Vite, TypeScript, vis-network, Chart.js/Plotly.
- **Removed**: `ui/` directory (Streamlit) and `streamlit`/`streamlit-agraph` from `requirements.txt` — after full migration.
- **Prerequisite**: `add-fastapi-backend` must be complete (provides the API contract).
- **Dev workflow**: `cd frontend && npm run dev` (`:9000`) + `uvicorn api.main:app --reload` (`:8000`). CORS configured by the backend.

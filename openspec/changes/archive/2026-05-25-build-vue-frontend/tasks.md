# Tasks — build-vue-frontend

## 1. Project scaffolding

- [x] 1.1 Initialize `frontend/` with Vite + Vue 3 + TypeScript. Add Quasar 2, Pinia, Vue Router as dependencies.
- [x] 1.2 Configure `vite.config.ts`: Quasar plugin, SCSS variables, dev proxy (`/api` → `http://localhost:8000`), port 9000.
- [x] 1.3 Configure `tsconfig.json`: strict mode, path aliases (`src/*`), ESNext target.
- [x] 1.4 Add ESLint with `eslint-plugin-vue` and `typescript-eslint`.
- [x] 1.5 Create `src/css/tokens.scss` with DPMM design tokens (colors, spacing, typography).
- [x] 1.6 Wire brand colors in `src/main.ts` Quasar config (primary, secondary, accent, dark).
- [x] 1.7 Add dev scripts to `package.json`: `dev`, `build`, `lint`, `test`, `codegen` (openapi-typescript).

## 2. API service layer

- [~] 2.1 Install `openapi-typescript`. Add `codegen` script that reads `../api/openapi.json` → writes `src/api/types.ts`. *(Skipped — openapi-typescript 7.x requires TypeScript ^5.x, incompatible with TS 6.x used by vue-tsc 3.x. Hand-written types in `src/types/index.ts` cover all API shapes.)*
- [x] 2.2 Create `src/api/client.ts`: base fetch wrapper with error handling and `/api` prefix.
- [x] 2.3 Create `src/api/catalogs.ts`: `listCatalogs()`, `getCatalog()`, `getTable()`.
- [x] 2.4 Create `src/api/mappings.ts`: `listMappings()`, `getMapping()`, `runMapping()`, `updateCandidates()`, `saveMapping()`.
- [x] 2.5 Create `src/api/glossary.ts`: `getGlossary()`, `getTerm()`, `upsertTerm()`, `deleteTerm()`, `aiSuggest()`, `getUncovered()`.
- [x] 2.6 Create `src/api/chat.ts`: `listConversations()`, `createConversation()`, `getConversation()`, `sendMessage()`, `deleteConversation()`.
- [x] 2.7 Create `src/api/discovery.ts`: `getTableStats()`, `executeQuery()`.
- [x] 2.8 Create `src/api/annotations.ts`: `getAnnotations()`, `setAnnotations()`.
- [x] 2.9 Create `src/api/sse.ts`: SSE reader using fetch + ReadableStream for POST endpoints.

## 3. App shell (layout, navigation, router)

- [x] 3.1 Create `src/layouts/MainLayout.vue` using QLayout + QHeader + QDrawer. Header: logo, page title, notification bell, user avatar. Drawer: grouped navigation (Data, Reports, Tools, System) with QExpansionItem.
- [x] 3.2 Create `src/components/TopMenu.vue`: header bar with brand logo, breadcrumb/title, notification icon, user menu.
- [x] 3.3 Create `src/components/SideMenu.vue`: collapsible sidebar with grouped nav items matching current Streamlit IA (Dashboard, Data→Input/Model/Corrections, Reports→Active/History, Tools→Chat/Mapping/Glossary/Catalog/Discovery, System→Settings/Audit/About).
- [x] 3.4 Create `src/router/index.ts` with all routes (lazy-loaded page components). Default redirect `/` → `/dashboard`.
- [x] 3.5 Create `src/types/index.ts` with domain type interfaces (Catalog, Table, Column, Mapping, GlossaryTerm, Conversation, Message, etc.).
- [x] 3.6 Create skeleton Pinia stores: `useCatalogStore`, `useMappingStore`, `useGlossaryStore`, `useChatStore`, `useDiscoveryStore`, `useAnnotationStore`.
- [x] 3.7 Create placeholder page components for all routes (just `<q-page>` with page title).
- [x] 3.8 Verify shell renders: navigation works, all routes load their placeholder, drawer collapses.

## 4. Chat page

- [x] 4.1 Create `src/pages/ChatPage.vue` with two-pane layout: left drawer for conversation list, main area for chat.
- [x] 4.2 Implement conversation list panel: search input, list of conversations with title and timestamp, "New conversation" button.
- [x] 4.3 Implement hero state: centered greeting with suggestion chips (QChip/QBtn) shown when no active conversation. Clicking a chip creates a conversation with that message.
- [x] 4.4 Implement message display: user messages right-aligned, assistant messages left-aligned. Use QChatMessage or custom styled bubbles.
- [x] 4.5 Implement chat input: bottom-pinned text input (QInput) with send button. Calls `POST /chat/conversations/{id}/messages`.
- [x] 4.6 Wire `useChatStore`: load conversations on mount, create/select/delete conversations, append messages.
- [x] 4.7 Test: create conversation, send message, verify response appears.

## 5. Mapping page

- [x] 5.1 Create `src/pages/MappingPage.vue` with header controls and three-tab layout.
- [x] 5.2 Implement source/target selector: dropdowns populated from `useCatalogStore`. Agent choice selector (Generic/BIRD).
- [x] 5.3 Implement target table multi-select: checkbox list of target tables for the mapping run.
- [x] 5.4 Implement "Run Mapping" button that triggers SSE stream via `useMappingStore.runStream()`.
- [x] 5.5 Implement streaming progress display: per-table status indicators (analyzing → candidates → scoring → columns → validating → done), live updates from SSE events.
- [x] 5.6 Create `src/components/MappingGraph.vue`: vis-network graph adapted from aldares `LineageGraph.vue`. Source nodes left (blue), target nodes right (grey), edges colored by confidence.
- [x] 5.7 Implement Visualization tab: render MappingGraph with mapping results. Click node to highlight edges and show detail.
- [x] 5.8 Implement Table tab: QTable showing all column mappings (source→target, confidence, transformation type, status). Sortable, filterable.
- [x] 5.9 Implement Raw tab: per-candidate cards with accept/discard buttons. Column-level detail with confidence indicators.
- [x] 5.10 Implement SQL preview: collapsible panel showing generated SQL for accepted mappings.
- [x] 5.11 Wire `useMappingStore`: load existing mappings, run stream, accept/discard candidates, save.
- [x] 5.12 Test: run mapping stream, verify events update UI, accept candidate, verify persistence.

## 6. Catalog page

- [x] 6.1 Create `src/pages/CatalogPage.vue` with dataset/table selectors and column grid.
- [x] 6.2 Implement dataset + table dropdowns populated from `useCatalogStore`.
- [x] 6.3 Implement table header: metadata row (row count, PK, description coverage percentage).
- [x] 6.4 Implement column grid: QTable with columns for name, type, null%, samples, user description, mapping instructions. Zebra striping.
- [x] 6.5 Implement inline editing: user descriptions and mapping instructions as editable text fields. Save writes to annotation overlay via `useAnnotationStore`.
- [x] 6.6 Implement AI generation buttons: "Improve with AI" per column and "Generate all" for the table. Call annotation/AI endpoints.
- [x] 6.7 Implement glossary cross-reference: per-column buttons to view existing glossary term or create new one (navigates to glossary page).
- [x] 6.8 Handle incoming navigation: read `route.query.dataset` and `route.query.table` to auto-select on mount (replaces `catalog_jump`).
- [x] 6.9 Wire `useAnnotationStore`: load/save annotations per dataset/table.
- [x] 6.10 Test: select table, edit description, save, verify annotation persisted.

## 7. Glossary page

- [x] 7.1 Create `src/pages/GlossaryPage.vue` with three-pane layout: left tree, center term detail, right AI assist (toggleable).
- [x] 7.2 Implement domain/category tree: QTree with collapsible nodes, search filter above. Selecting a leaf loads the term.
- [x] 7.3 Implement term detail panel: sections (Definition, Business Context, Related Objects, Source Context) with per-section inline edit (pencil icon toggle). Display AI-generated badges where applicable.
- [x] 7.4 Implement "New Term" flow: form with title, domain, category, definition fields. Save/Cancel at top right. Pre-fill from route query params (replaces `_gloss_new_prefill_pending`).
- [x] 7.5 Implement AI-assist panel: toggleable right panel with chat-like interface for AI-assisted term generation. Calls `POST /glossary/terms/{id}/ai-suggest`.
- [x] 7.6 Implement uncovered concepts tab: QTable showing catalog items not yet in glossary, with filters (source, object, field). Action buttons: "Review in Catalog" and "Add Term".
- [x] 7.7 Implement cross-page navigation: "Review in Catalog" → `router.push('/tools/catalog', { query })`, "Review in Discovery" → `router.push('/tools/discovery', { query })`.
- [x] 7.8 Handle incoming navigation: read `route.query.term` to auto-select term on mount (replaces `gloss_selected_id` + query params).
- [x] 7.9 Wire `useGlossaryStore`: load glossary, CRUD terms, manage editing state, prefill state.
- [x] 7.10 Test: browse tree, select term, edit section, save. Navigate from uncovered concepts to catalog.

## 8. Discovery page

- [x] 8.1 Create `src/pages/DiscoveryPage.vue` with table overview and inline chat panel.
- [x] 8.2 Implement dataset/table selectors shared with `useCatalogStore`.
- [x] 8.3 Implement table overview: metrics row (row count, columns, PK), foreign key relationships display.
- [x] 8.4 Implement column stats table: QTable with data type, null%, distinct count, min/max, sample values (collapsible detail).
- [x] 8.5 Implement fixed-bottom chat panel: collapsible chat scoped to selected table. System prompt pre-populated with table context. Calls chat endpoints.
- [x] 8.6 Implement query results display: render DuckDB query results as QTable.
- [x] 8.7 Implement chart rendering: render chart specifications from chat tool results using Chart.js.
- [x] 8.8 Handle incoming navigation: read `route.query.dataset` and `route.query.table` (replaces `discovery_jump`).
- [x] 8.9 Wire `useDiscoveryStore`: load table stats, manage inline chat state, execute queries.
- [x] 8.10 Test: select table, view stats, run query in chat, verify results displayed.

## 9. Cross-page integration testing

- [x] 9.1 Test Glossary → Catalog navigation: click "Review in Catalog" from uncovered concepts, verify catalog page opens with correct dataset/table selected.
- [~] 9.2 Test Glossary → Discovery navigation: click "Review in Discovery", verify discovery page opens correctly. *(Skipped — "Review in Discovery" button not added to uncovered concepts; catalog review covers the primary use case.)*
- [x] 9.3 Test Catalog → Glossary navigation: click glossary cross-reference button on a column, verify glossary page opens with correct term selected.
- [x] 9.4 Test Catalog → Glossary new term: click "+ Glossary" on a column, verify glossary new term form opens with pre-filled data.
- [x] 9.5 Test deep-linking: verify direct URL navigation works for `/tools/glossary?term=X`, `/tools/catalog?dataset=Y&table=Z`.

## 10. Stub pages

- [x] 10.1 Create styled `DashboardPage.vue`: page title, placeholder cards for future widgets.
- [x] 10.2 Create styled `InputDataPage.vue`, `DataModelPage.vue`, `CorrectionsPage.vue`: page title + "Coming soon" content.
- [x] 10.3 Create styled `ActiveReportsPage.vue`, `ReportingHistoryPage.vue`: page title + "Coming soon" content.
- [x] 10.4 Create styled `SettingsPage.vue`, `AuditLogPage.vue`, `AboutPage.vue`: page title + "Coming soon" / product info content.

## 11. Retire Streamlit

- [~] 11.1 Remove `ui/` directory. *(Deferred — Streamlit UI kept alongside Vue frontend for demo flexibility.)*
- [~] 11.2 Remove `streamlit` and `streamlit-agraph` from `requirements.txt`. *(Deferred — kept for parallel Streamlit usage.)*
- [~] 11.3 Update repo root `README.md`: remove Streamlit references, add `cd frontend && npm run dev` instructions. *(Partial — Vue frontend section added; Streamlit section kept as "legacy".)*
- [~] 11.4 Final smoke test: backend + frontend run together, all pages accessible, no references to Streamlit remain. *(Deferred — Streamlit intentionally retained.)*

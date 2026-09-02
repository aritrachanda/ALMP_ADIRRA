# Design — build-vue-frontend

## Context

The Streamlit UI has 6 functional pages (Chat, Mapping, Glossary, Catalog, Discovery) plus stubs. Cross-page state flows through Streamlit's `session_state` — particularly between Glossary, Catalog, and Discovery which share navigation jumps and pre-fill data. The agents (business logic) are already cleanly separated from the UI; the FastAPI backend (`add-fastapi-backend`) wraps them in REST/SSE endpoints.

The aldares project provides a proven Vue/Quasar frontend to copy patterns from: layout, stores, vis-network graph, table components, and project structure. No Express BFF — the Vue app communicates directly with FastAPI.

## Goals / Non-Goals

**Goals:**
- Complete Vue/Quasar frontend covering all pages currently in Streamlit.
- Direct communication with FastAPI backend (no intermediate BFF).
- Reuse proven patterns from the aldares frontend.
- Cross-page state cleanly managed via Pinia stores + Vue Router.
- Streamlit retired after migration is complete.

**Non-Goals:**
- Pixel-perfect Figma parity (target ~85% visual fidelity; polish is iterative).
- Auth, i18n, mobile, deployment.
- Building a component library — use Quasar components directly; extract shared patterns only when duplication appears.
- SSR — SPA is sufficient.

## Decisions

### D1. Project setup

```
frontend/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
├── src/
│   ├── App.vue
│   ├── main.ts
│   ├── api/                  # API service layer
│   │   ├── client.ts         # Base fetch wrapper
│   │   ├── types.ts          # Generated from openapi.json
│   │   ├── catalogs.ts
│   │   ├── mappings.ts
│   │   ├── glossary.ts
│   │   ├── chat.ts
│   │   ├── discovery.ts
│   │   ├── annotations.ts
│   │   └── sse.ts            # SSE reader helper
│   ├── components/
│   ├── css/
│   │   └── tokens.scss       # DPMM design tokens
│   ├── layouts/
│   │   └── MainLayout.vue
│   ├── pages/
│   ├── router/
│   │   └── index.ts
│   ├── stores/
│   └── types/
│       └── index.ts          # Domain types
└── tests/
```

**Stack**: Vue 3.5+, Quasar 2.x, Pinia 2.x, Vue Router 4.x, TypeScript 5.x, Vite 6.x, vis-network, Chart.js + vue-chartjs.

### D2. Direct to FastAPI (no BFF)

The Vue app calls `http://localhost:8000` directly in dev. Vite proxies `/api` → `http://localhost:8000` to avoid CORS during development:

```ts
// vite.config.ts
server: {
  port: 9000,
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true,
      rewrite: (path) => path.replace(/^\/api/, '')
    }
  }
}
```

All API calls in `src/api/*.ts` use `/api/` prefix. In production, a reverse proxy (nginx) handles the routing.

### D3. Typed API client — lightweight approach

Use `openapi-typescript` to generate types from `api/openapi.json` → `src/api/types.ts`. Hand-write thin fetch wrappers per endpoint group (one file per domain: `catalogs.ts`, `mappings.ts`, etc.) that use these types. No full codegen client — keeps deps small for ~30 endpoints.

```ts
// Example: src/api/catalogs.ts
export async function listCatalogs(type: 'sources' | 'targets'): Promise<CatalogList> {
  const res = await fetch(`/api/catalogs/${type}`)
  if (!res.ok) throw new ApiError(res)
  return res.json()
}
```

### D4. Routing mirrors Streamlit IA

```ts
// src/router/index.ts
const routes = [
  { path: '/',                       redirect: '/dashboard' },
  { path: '/dashboard',              component: () => import('../pages/DashboardPage.vue') },
  { path: '/data/input',             component: () => import('../pages/InputDataPage.vue') },
  { path: '/data/model',             component: () => import('../pages/DataModelPage.vue') },
  { path: '/data/corrections',       component: () => import('../pages/CorrectionsPage.vue') },
  { path: '/reports/active',         component: () => import('../pages/ActiveReportsPage.vue') },
  { path: '/reports/history',        component: () => import('../pages/ReportingHistoryPage.vue') },
  { path: '/tools/chat',             component: () => import('../pages/ChatPage.vue') },
  { path: '/tools/mapping',          component: () => import('../pages/MappingPage.vue') },
  { path: '/tools/glossary',         component: () => import('../pages/GlossaryPage.vue') },
  { path: '/tools/catalog',          component: () => import('../pages/CatalogPage.vue') },
  { path: '/tools/discovery',        component: () => import('../pages/DiscoveryPage.vue') },
  { path: '/system/settings',        component: () => import('../pages/SettingsPage.vue') },
  { path: '/system/audit-log',       component: () => import('../pages/AuditLogPage.vue') },
  { path: '/system/about',           component: () => import('../pages/AboutPage.vue') },
]
```

### D5. Pinia stores — one per domain

| Store | Key State | Shared By |
|-------|-----------|-----------|
| `useCatalogStore` | sources, targets, selectedDataset, selectedTable | Catalog, Mapping, Discovery |
| `useMappingStore` | mappings, activeMapping, streamStatus | Mapping |
| `useGlossaryStore` | terms, categories, selectedTerm, uncoveredConcepts | Glossary, Catalog |
| `useChatStore` | conversations, activeConversation, messages | Chat |
| `useDiscoveryStore` | tableStats, queryResults, chatMessages | Discovery |
| `useAnnotationStore` | annotations per dataset/table | Catalog |

**Cross-page state migration:**
- `catalog_jump` → `router.push({ path: '/tools/catalog', query: { dataset, table } })`
- `discovery_jump` → `router.push({ path: '/tools/discovery', query: { dataset, table } })`
- `gloss_selected_id` → `router.push({ path: '/tools/glossary', query: { term: id } })`
- `_gloss_new_prefill_pending` → `useGlossaryStore().setPrefill({ title, tags, related_objects })`

### D6. SSE for mapping streaming

Since `EventSource` only supports GET, use `fetch()` with `ReadableStream` to read SSE from the POST endpoint:

```ts
// src/api/sse.ts
export async function* readSSE(url: string, body: object): AsyncGenerator<SSEEvent> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  // Parse SSE frames from the stream...
}
```

`useMappingStore.runStream()` consumes this generator and updates reactive state as events arrive.

### D7. vis-network graph (reuse from aldares)

The Mapping page's Visualization tab and the Discovery page both need interactive graphs. Adapt aldares' `LineageGraph.vue`:
- Source tables on left (blue), target tables on right (grey)
- Edges colored by confidence (green/yellow/red)
- Click-to-select with detail panel
- Export to PNG

### D8. Migration order — dependency-driven

```
Phase 1: Shell          — layout, navigation, router, stores skeleton, API layer
                          (everything else builds on this)

Phase 2: Chat           — standalone page, no cross-page deps
         Mapping        — standalone page, tests SSE streaming

Phase 3: Catalog  ─┐
         Glossary  ├── migrated together (shared stores, cross-navigation)
         Discovery─┘

Phase 4: Stub pages     — Dashboard, Input Data, Data Model, Corrections,
                          Active Reports, History, Settings, Audit Log, About

Phase 5: Retire         — remove ui/, streamlit deps, update README
```

Phase 2 pages can be built in parallel. Phase 3 pages share `useCatalogStore` and `useGlossaryStore` and must be developed together to ensure cross-page navigation works.

### D9. DPMM design tokens

Quasar brand colors in `main.ts`:
```ts
brand: {
  primary: '#0d4da1',
  secondary: '#0e2a47',
  accent: '#e9f3ff',
  dark: '#0d2e4d',
  positive: '#21BA45',
  negative: '#C10015',
  warning: '#F2C037',
}
```

Additional tokens (spacing, typography) in `src/css/tokens.scss`.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| Large scope — all pages at once | Phased approach; shell + 2 pages is a useful checkpoint. Stubs provide nav completeness early. |
| Backend API not ready when frontend starts | Phase 1 (shell + API layer) can stub responses. Backend should ship first per the plan. |
| vis-network bundle size | Tree-shake; only import Network, not the full vis.js suite. Same approach as aldares. |
| Cross-page state bugs in Glossary/Catalog/Discovery cluster | Migrate the cluster as one unit; test cross-navigation explicitly. |
| No Streamlit fallback during migration | Streamlit keeps working until Phase 5. Both can run simultaneously — different ports. |

## Open Questions

- Chart library for Discovery page: stick with Chart.js (same as aldares) or use Plotly (same as current Streamlit)? Default: Chart.js for consistency with aldares; re-evaluate if the discovery charts need Plotly-specific features.
- Component library: bare Quasar or extract shared DPMM components? Default: bare Quasar; promote to shared only after duplication appears.

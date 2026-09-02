## Context

The Streamlit UI (`ui/`) was updated in PRs #26–#27 (`chore/BusinessGlossary4`) to introduce a Home landing page, reorganize the sidebar, and replace four stub pages with real content. The Vue/Quasar frontend (`frontend/`) was built in parallel and currently mirrors the old Streamlit navigation structure, which is now out of date.

Six stub page files exist in `frontend/src/pages/` for routes that have been removed from the Streamlit nav entirely: `ActiveReportsPage.vue`, `AuditLogPage.vue`, `CorrectionsPage.vue`, `DataModelPage.vue`, `InputDataPage.vue`, `ReportingHistoryPage.vue`. These will be deleted.

The Dashboard page needs a backend summary endpoint since the Vue frontend cannot read YAML files directly.

## Goals / Non-Goals

**Goals:**
- Match the Streamlit navigation IA exactly (groups, order, default route)
- Create a `HomePage.vue` with hero banner and feature cards
- Replace the four stub pages with meaningful content
- Add `GET /dashboard/summary` endpoint for coverage metrics
- Remove all stub-only page files and their routes

**Non-Goals:**
- Full Settings functionality (import/export/sync pipelines) — cards only, no wiring
- Parity with all Streamlit styling details — use existing Vue DPMM design tokens
- Altair-style chart animations — Chart.js (already wired) is sufficient

## Decisions

### Navigation structure

The new sidebar has two groups instead of four. All "Data Governance" tools are flattened into a single group. There is no longer a top-level "Dashboard" item — it moves inside the group.

```
Home (top-level, default)
Data Governance ▸
  Chat
  Discovery
  Data Catalog
  Business Glossary
  Mapping
  Dashboard
System ▸
  Settings
  About
```

The existing `q-expansion-item` pattern in `SideMenu.vue` is preserved. The mini-mode template blocks are kept in sync (current pattern duplicates items for mini/full modes — this is retained as-is).

### Default route

`/` currently redirects to `/dashboard`. It will redirect to `/home` instead. The `/dashboard` route remains accessible but is no longer the entry point.

### Home page approach

The Streamlit `home.py` is a CSS-heavy hero page. In Vue, the same visual intent is achieved with scoped `<style>` SCSS using existing DPMM design tokens (primary `#0d4da1`, secondary `#0e2a47`). No new dependencies. The gradient hero and feature card grid are implemented with plain CSS grid/flexbox.

### Dashboard data source

The Streamlit dashboard reads YAML files on disk directly. The Vue frontend cannot do this. A new `GET /api/dashboard/summary` endpoint in `api/routes/dashboard.py` will read the same YAML files and return structured JSON:

```json
{
  "sources": { "datasets": 2, "tables": 14, "columns": 187 },
  "targets": { "datasets": 1, "tables": 28, "columns": 312 },
  "mappings": { "total": 28, "with_results": 6, "mapped_columns": 84 },
  "glossary": { "terms": 42, "uncovered": 31 }
}
```

The Vue `DashboardPage.vue` calls this endpoint and renders metric cards + a Bar chart (already wired via Chart.js).

### Settings page

Settings becomes a static card layout: ZIP export card, PDF card, Sync card — each with a status badge ("Live", "Coming soon"). No `q-form` or wired actions. This matches the Streamlit intent without requiring backend endpoints that don't exist yet.

### About page

Pure static content: product identity card, capability cards (Chat, Catalog, Glossary, Mapping, Discovery), stack badges. No API calls.

### Stub page deletion

Files are deleted outright. Routes are removed from `router/index.ts`. No redirect aliases needed — these routes were never deep-linked from other pages.

## Risks / Trade-offs

- **Dashboard YAML coupling** → The summary endpoint reads project paths from `project.yaml` (already done for other endpoints). If path config changes, the endpoint must be updated — same risk as the existing catalog endpoints.
- **Stub deletion is irreversible** → Acceptable: the pages contained only `"Coming soon"` content and are not referenced anywhere in the codebase.
- **Settings cards without wiring** → Risk of appearing incomplete in demos. Mitigation: use "Coming soon" / "Planned" badges clearly on non-functional cards.

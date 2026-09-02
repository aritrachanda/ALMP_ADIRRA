## Why

The Streamlit UI received significant navigation and page updates in `chore/BusinessGlossary4` (PRs #26–#27). The Vue/Quasar frontend must reflect the same information architecture so both UIs remain coherent and the Vue frontend is demo-ready as the primary interface.

## What Changes

- **Add `HomePage.vue`**: New rich landing page (hero banner, feature cards, phase roadmap). Becomes the default route `/`.
- **Restructure `SideMenu.vue`**: Remove the Data and Reports groups; rename the Tools group to "Data Governance"; reorder items; add Home at the top.
- **Update default route**: Router default redirect changes from `/dashboard` to `/home`.
- **Update `DashboardPage.vue`**: Replace "Coming soon" stub with real coverage metrics (source/target table counts, column coverage, mapping progress, glossary coverage) backed by a new backend summary endpoint.
- **Update `AboutPage.vue`**: Replace "Coming soon" stub with styled product information cards.
- **Update `SettingsPage.vue`**: Replace "Coming soon" stub with import/export cards (ZIP package, PDF generation, glossary/mapping sync). Full functionality deferred; cards with status badges only.
- **Remove stub page files**: Delete `ActiveReportsPage.vue`, `AuditLogPage.vue`, `CorrectionsPage.vue`, `DataModelPage.vue`, `InputDataPage.vue`, `ReportingHistoryPage.vue` and their routes — these pages are no longer in the navigation.

## Capabilities

### New Capabilities

- `vue-home-page`: Styled hero landing page with feature cards and roadmap section. Static content, no API dependency.
- `vue-dashboard-page`: Coverage metrics dashboard reading from backend summary data (source/target/mapping/glossary stats).

### Modified Capabilities

- `vue-app-shell`: Navigation structure changes — groups renamed and reordered, default route updated, stub route entries removed.
- `vue-catalog-page`: No spec change — kept as-is.
- `vue-chat-page`: No spec change — kept as-is.
- `vue-glossary-page`: No spec change — kept as-is.
- `vue-discovery-page`: No spec change — kept as-is.
- `vue-mapping-page`: No spec change — kept as-is.

## Impact

- `frontend/src/components/SideMenu.vue` — navigation restructure
- `frontend/src/router/index.ts` — default route + stub routes removed
- `frontend/src/pages/HomePage.vue` — new file
- `frontend/src/pages/DashboardPage.vue` — rewritten from stub
- `frontend/src/pages/AboutPage.vue` — rewritten from stub
- `frontend/src/pages/SettingsPage.vue` — rewritten from stub
- `frontend/src/pages/{ActiveReports,AuditLog,Corrections,DataModel,InputData,ReportingHistory}Page.vue` — deleted
- `api/routes/dashboard.py` — new backend route for summary stats
- `api/main.py` — register dashboard router

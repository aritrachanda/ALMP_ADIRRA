# Tasks — sync-streamlit-nav-to-vue

## 1. Remove stub pages

- [x] 1.1 Delete `frontend/src/pages/ActiveReportsPage.vue`
- [x] 1.2 Delete `frontend/src/pages/AuditLogPage.vue`
- [x] 1.3 Delete `frontend/src/pages/CorrectionsPage.vue`
- [x] 1.4 Delete `frontend/src/pages/DataModelPage.vue`
- [x] 1.5 Delete `frontend/src/pages/InputDataPage.vue`
- [x] 1.6 Delete `frontend/src/pages/ReportingHistoryPage.vue`
- [x] 1.7 Remove the corresponding route entries from `frontend/src/router/index.ts`

## 2. Home page

- [x] 2.1 Create `frontend/src/pages/HomePage.vue` with hero banner (dark gradient, kicker badge, headline, subtitle).
- [x] 2.2 Add capability card grid (Chat, Discovery, Catalog, Glossary, Mapping) with icon, name, description, and router-link.
- [x] 2.3 Add phase/roadmap section below the cards.
- [x] 2.4 Add `/home` route to `frontend/src/router/index.ts` (lazy-loaded `HomePage`). *(Done in 1.7)*
- [x] 2.5 Change default redirect in router from `/dashboard` to `/home`.

## 3. Navigation restructure

- [x] 3.1 Rewrite `frontend/src/components/SideMenu.vue`: replace Data and Reports groups with a single "Data Governance" group containing Chat, Discovery, Data Catalog, Business Glossary, Mapping, Dashboard.
- [x] 3.2 Add "Home" as a top-level item above the Data Governance group.
- [x] 3.3 Remove Audit Log from the System group; keep Settings and About.
- [x] 3.4 Update mini-mode template blocks to match the new structure.
- [x] 3.5 Verify active-route highlighting works for the new Home route.

## 4. Dashboard page — real content

- [x] 4.1 Create `api/routes/dashboard.py` with `GET /dashboard/summary` endpoint. Read sources, targets, mappings, glossary from `project.yaml` paths. Return JSON with `sources`, `targets`, `mappings`, `glossary` keys.
- [x] 4.2 Register the dashboard router in `api/main.py`.
- [x] 4.3 Rewrite `frontend/src/pages/DashboardPage.vue`: metric cards for sources, targets, mappings, glossary; loading and error states.
- [x] 4.4 Add a Bar chart (Chart.js) showing mapped vs. unmapped columns when mapping data is present.
- [x] 4.5 Add `src/api/dashboard.ts` API function `getDashboardSummary()`.

## 5. About page — real content

- [x] 5.1 Rewrite `frontend/src/pages/AboutPage.vue`: product identity card, capability cards, tech stack badges. No API calls.

## 6. Settings page — card layout

- [x] 6.1 Rewrite `frontend/src/pages/SettingsPage.vue`: hero card + three feature cards (ZIP export, PDF export, Sync). Each card has a status badge ("Live" or "Coming soon"). No wired actions.

## 7. Verification

- [x] 7.1 Verify no TypeScript errors: `npm run build` in `frontend/`.
- [x] 7.2 Verify sidebar renders correctly in both expanded and mini modes.
- [x] 7.3 Verify `/` redirects to Home, `/tools/dashboard` shows metrics, `/system/about` shows product cards.
- [x] 7.4 Verify deleted page routes return a "not found" view (no 404 in console).

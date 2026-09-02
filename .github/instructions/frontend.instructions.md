---
applyTo: "frontend/**"
description: "Vue 3 + Quasar frontend conventions for ADIRRA — component/store patterns, styling tokens, and test layout."
---

# Frontend (Vue 3 + Quasar) Conventions

## Structure

- `src/pages/` — routed page components (e.g. `AssetWorkspace.vue`, the most-used page).
- `src/components/` — shared components (`TopMenu.vue`, `SideMenu.vue`, `BusinessContextPanel.vue`, …).
- `src/stores/` — Pinia stores, one per domain (`elementStore.ts`, `glossaryStore.ts`, …).
- `src/api/` — typed API client functions, one module per backend route group.
- `src/router/index.ts` — all routes live under a single `MainLayout.vue` parent; every route has
  `meta.title` and `meta.group` (the latter must match a `SideMenu.vue` expansion-group label —
  it drives the header breadcrumb in `TopMenu.vue`).
- `src/styles/tokens.scss` — CSS custom properties (design tokens). Don't use
  `src/css/tokens.scss` if you ever see it referenced — that path was a dead duplicate.

## Cross-component state (breadcrumbs, page-owned drill-down)

Pages with in-page drill-down state (e.g. `AssetWorkspace.vue`'s source → dataset → column
selection) that needs to be reflected in a component outside their own tree (e.g. `TopMenu.vue`'s
breadcrumb) should publish that state to a Pinia store action (see `elementStore.breadcrumbTrail` /
`setBreadcrumbTrail` / `clearBreadcrumbTrail`) via a `watch(...)`, and clear it in
`onBeforeUnmount`. Don't reach into another page's local `ref`s directly — there's no mechanism for
that across routed pages.

## Styling gotchas

- **`overflow: hidden` on a card clips absolutely-positioned popovers inside it**, even ones meant
  to overflow the card's visual bounds (e.g. a dropdown menu in a card header). If a popover must
  escape the card, `<teleport to="body">` it and position it via `getBoundingClientRect()` on the
  anchor, rather than removing the card's `overflow: hidden` (which is usually there to clip the
  header bar into the card's rounded corners).
- **`color-mix()` blended with `transparent` over a light card background desaturates toward
  gray**, especially for already-muted token colours (e.g. `--info-col`). For a clearly-tinted
  gradient, use a solid hex + alpha-suffix pair (e.g. `#1d4e8955, #1d4e891f`) instead of
  `color-mix(in srgb, var(--token) X%, transparent)`.
- Quasar teleports `.q-menu`/`.q-dialog` to `<body>` — global CSS meant for those must be written
  as `.q-menu ...` / `.q-dialog ...`, not bare element/class selectors, or it will leak onto
  unrelated components (e.g. the sidebar) that share the same class names.
- A component that renders a nav item at the "wrong" indentation is usually a component reuse
  issue, not a CSS bug — check whether it's using an item component meant for *nested* items
  (e.g. `NavItem.vue`, which adds child-level padding) versus a plain top-level `q-item`.
- **A page that must scroll but gets its content clipped is almost always a flex `min-height`
  bug**, not a missing `overflow`. Flex children default to `min-height: auto`, so a flex column
  won't shrink to let an inner area scroll unless you set `min-height: 0` on the scroll container
  *and* its flex ancestors. Also don't copy the app-shell pattern (`height: 100%; overflow:
  hidden`) onto a *scrollable* page — that pattern is for fixed full-height layouts like
  `AssetWorkspace.vue`, not pages whose content grows and needs to scroll. (This bug took ~4
  attempts on `ReferenceDataspace.vue` before the real cause — `min-height: 0` — was found.)

## Testing

- Vitest + jsdom, test files in `frontend/tests/**/*.test.ts` (not colocated with source).
- Run a single file: `npx vitest run tests/<name>.test.ts`.
- Full gate before considering frontend work done: `npx vitest run` (all tests) then
  `npx vue-tsc --noEmit` (type-check) — `npm run build` runs both plus lint.

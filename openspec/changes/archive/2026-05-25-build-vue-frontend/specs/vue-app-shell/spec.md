# Spec — vue-app-shell (ADDED)

## ADDED Requirements

### Requirement: QLayout-based app shell with branded header and collapsible navigation

The app SHALL render a QLayout with QHeader (top bar) and QDrawer (left sidebar). The header SHALL display the product logo, current page title, a notification bell icon, and a user avatar. The drawer SHALL contain grouped navigation matching the current Streamlit IA.

#### Scenario: Navigation groups match Streamlit IA

- **GIVEN** the app shell is rendered
- **THEN** the sidebar SHALL contain these groups with their child items:
  - Dashboard (top-level, no group)
  - Data → Input Data, Data Model (CRDM), Corrections
  - Reports → Active Reports, Reporting History
  - Tools → Chat, Mapping, Business Glossary, Data Catalog, Discovery
  - System → Settings, Audit Log, About

#### Scenario: Sidebar collapses to mini mode

- **WHEN** the user clicks the collapse toggle
- **THEN** the sidebar SHALL collapse to icon-only (mini) mode
- **AND** hovering over an icon SHALL show a tooltip with the page name

#### Scenario: Active route is highlighted

- **WHEN** the user navigates to a page
- **THEN** the corresponding sidebar item SHALL be visually highlighted
- **AND** the page title in the header SHALL update to match

### Requirement: Vue Router with lazy-loaded pages

All page components SHALL be lazy-loaded via dynamic imports. The router SHALL redirect `/` to `/dashboard`. Unknown routes SHALL display a "Page not found" view.

#### Scenario: Direct URL navigation works

- **WHEN** a user enters `/tools/glossary?term=risk-weight` in the browser
- **THEN** the glossary page SHALL load with the specified term selected

### Requirement: DPMM design tokens

Brand colors SHALL be configured via Quasar's brand system. Additional tokens (spacing scale, typography) SHALL be defined in a SCSS variables file and available to all components.

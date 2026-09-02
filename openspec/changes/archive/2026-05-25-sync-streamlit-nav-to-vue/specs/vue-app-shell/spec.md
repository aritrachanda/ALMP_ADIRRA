# Spec — vue-app-shell (MODIFIED)

## MODIFIED Requirements

### Requirement: QLayout-based app shell with branded header and collapsible navigation

The app SHALL render a QLayout with QHeader (top bar) and QDrawer (left sidebar). The header SHALL display the product logo, current page title, a notification bell icon, and a user avatar. The drawer SHALL contain grouped navigation matching the current IA.

#### Scenario: Navigation groups match current IA

- **GIVEN** the app shell is rendered
- **THEN** the sidebar SHALL contain:
  - Home (top-level, default route)
  - Data Governance → Chat, Discovery, Data Catalog, Business Glossary, Mapping, Dashboard
  - System → Settings, About

#### Scenario: Sidebar collapses to mini mode

- **WHEN** the user clicks the collapse toggle
- **THEN** the sidebar SHALL collapse to icon-only (mini) mode
- **AND** hovering over an icon SHALL show a tooltip with the page name

#### Scenario: Active route is highlighted

- **WHEN** the user navigates to a page
- **THEN** the corresponding sidebar item SHALL be visually highlighted
- **AND** the page title in the header SHALL update to match

### Requirement: Vue Router with lazy-loaded pages

All page components SHALL be lazy-loaded via dynamic imports. The router SHALL redirect `/` to `/home`. Unknown routes SHALL display a "Page not found" view. Routes for stub-only pages (Input Data, Data Model, Corrections, Active Reports, Reporting History, Audit Log) SHALL be removed.

#### Scenario: Default route is Home

- **WHEN** a user navigates to `/`
- **THEN** the router SHALL redirect to `/home`

#### Scenario: Direct URL navigation works

- **WHEN** a user enters `/tools/glossary?term=risk-weight` in the browser
- **THEN** the glossary page SHALL load with the specified term selected

## REMOVED Requirements

### Requirement: Stub page routes (Input Data, Data Model, Corrections, Active Reports, Reporting History, Audit Log)

**Reason**: These pages were placeholder stubs with no content and are no longer part of the navigation IA.
**Migration**: No links to these routes exist in the application. Files can be deleted without redirect.

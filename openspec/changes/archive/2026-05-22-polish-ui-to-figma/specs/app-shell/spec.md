# Spec delta — app-shell (ADDED)

## ADDED Requirements

### Requirement: The app SHALL hide Streamlit's default chrome and render a custom navy top bar

The default Streamlit header (`[data-testid="stHeader"]`) and the default page-padding above the main content SHALL be hidden via CSS. In its place, every page SHALL render a single shared **top app bar** containing, from left to right: the ALMPARTNERS logo, a breadcrumb / page title, a bell icon, and an avatar+name badge. The bar uses the DPMM navy palette (`--dpmm-navy` background, `--dpmm-navy-text` text). The bell and avatar are visual only in this version (no click handlers wired).

#### Scenario: Default Streamlit header is hidden

- **WHEN** any page in the app is loaded
- **THEN** the default Streamlit header element is not visible
- **AND** the main content begins flush with the custom top bar

#### Scenario: Top bar shows the page title

- **WHEN** the user navigates to a page (e.g. "Business glossary")
- **THEN** the top bar displays the page title (or breadcrumb) in the center-left position
- **AND** the logo is on the far left and the bell + avatar are on the far right

### Requirement: The sidebar SHALL render the DPMM navigation IA in navy

The sidebar SHALL be styled with the DPMM navy palette and SHALL group navigation items into the IA used in the Figma frames: **Dashboard**, **Data** (with Input data, Data model (CRDM), Corrections grouped under it), **Active reports**, **Reporting history**, **Chat**, **Mapping**, **Business glossary**, **Data Catalog**, **Discovery**, **Settings**, with **Audit log** and **About the product** pinned to the bottom. Group headings ("Data", "Reports", "Chat", "Settings") SHALL render as static caption labels. Animated expand/collapse of group children is NOT required (Streamlit's `st.navigation` does not support it natively).

#### Scenario: Sidebar uses the navy palette

- **WHEN** any page is loaded
- **THEN** the sidebar background is the DPMM navy color
- **AND** the active page item is highlighted with the active navy color

#### Scenario: Group headings appear above their children

- **WHEN** the sidebar renders
- **THEN** each group heading ("Data", "Reports", "Chat", "Settings") appears as a small uppercase caption above its child links
- **AND** child links appear immediately below their heading

#### Scenario: About the product is pinned to the bottom

- **WHEN** the sidebar renders
- **THEN** "Audit log" and "About the product" appear at the bottom of the sidebar, separated visually from the rest of the navigation

### Requirement: Glossary and Mapping pages SHALL use a three-pane layout

Pages that include a list/tree alongside a detail surface (Business glossary and Mapping / Data model (CRDM)) SHALL render that surface in a three-pane layout: the global sidebar (left), a **secondary panel** (center-left, e.g. term tree or dataset list), and a **main detail panel** (right). The split between the secondary panel and the main panel SHALL be implemented with `st.columns` using a roughly 1:3 ratio.

#### Scenario: Glossary page uses three panes

- **WHEN** the user opens the Business glossary page
- **THEN** the navy sidebar is on the far left
- **AND** a secondary panel listing terms (with search and Add new) is to its right
- **AND** the term detail / New term form occupies the remaining width

#### Scenario: Mapping page uses three panes

- **WHEN** the user opens the Mapping page
- **THEN** the navy sidebar is on the far left
- **AND** a secondary panel listing datasets is to its right
- **AND** the mapping result tabs (Visualization / Table / Raw) occupy the remaining width

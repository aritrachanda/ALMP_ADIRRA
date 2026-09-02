# Spec delta — ui-navigation (ADDED)

## ADDED Requirements

### Requirement: The application SHALL present a grouped left-sidebar navigation

The Streamlit app's sidebar SHALL render the following sections and items, in order:

1. Dashboard
2. Data
   - Input data
   - Data model (CRDM)
   - Corrections
3. Active reports
4. Reporting history
5. Chat
   - Chat (the chat shell page itself, acting as the section's landing page)
   - Mapping
   - Business glossary
   - Data Catalog
   - Discovery
6. Settings

#### Scenario: Sections render as visual groupings

- **WHEN** the user opens the app
- **THEN** each top-level section is rendered as a visual group label
- **AND** each sub-item is a navigable page

#### Scenario: Existing pages remain reachable

- **WHEN** the user clicks `Chat → Mapping`, `Chat → Data Catalog`, or `Chat → Discovery`
- **THEN** the existing `pages/mapping.py`, `pages/catalog.py`, and `pages/discovery.py` are loaded unchanged

#### Scenario: Stub pages exist for not-yet-built sections

- **WHEN** the user clicks Dashboard, any Data sub-item, Active reports, Reporting history, or Settings
- **THEN** a placeholder page renders with a title and a "Coming soon" message

### Requirement: The sidebar SHALL apply ALM Partners visual theming

The Streamlit application SHALL apply ALM Partners visual styling on startup, combining a `.streamlit/config.toml` theme (primary colors, background, text) with a small CSS file (`ui/assets/styles.css`) injected once at app start to polish the sidebar appearance. The visual fidelity target is approximately 90% of the supplied mockups; pixel-perfect parity is explicitly out of scope.

#### Scenario: Theme is loaded on startup

- **WHEN** the app starts
- **THEN** `.streamlit/config.toml` is honored for primary colors, background, and text
- **AND** `ui/assets/styles.css` is injected once for sidebar polish (deep-navy background, item spacing, icon alignment)

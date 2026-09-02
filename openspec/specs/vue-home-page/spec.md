# Spec — vue-home-page (ADDED)

## ADDED Requirements

### Requirement: Hero landing page

The Home page SHALL render a full-width hero banner with a gradient dark background, a kicker badge ("AGENTIC DATA MANAGEMENT"), a headline, and a subtitle describing the product's purpose. The page SHALL be the default landing page at `/home`.

#### Scenario: Hero section renders with brand identity

- **WHEN** a user navigates to `/home`
- **THEN** the page SHALL display a hero banner with headline and subtitle
- **AND** the page background SHALL use the DPMM primary dark color scheme

### Requirement: Feature capability cards

Below the hero, the page SHALL display a grid of cards — one per core capability (Chat, Discovery, Data Catalog, Business Glossary, Mapping). Each card SHALL include an icon, capability name, a one-sentence description, and a navigation link to the capability page.

#### Scenario: Clicking a capability card navigates to that page

- **WHEN** the user clicks a capability card
- **THEN** the router SHALL navigate to the corresponding tool route

### Requirement: Phase / roadmap section

The page SHALL include a section summarizing the current product phase and what is available in this release, so users in a demo context understand what is live vs. planned.

#### Scenario: Phase section is visible below feature cards

- **WHEN** the user scrolls down on the Home page
- **THEN** a phase/roadmap section SHALL be visible with at least one current-phase description

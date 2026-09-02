# Spec delta — business-glossary (ADDED)

## ADDED Requirements

### Requirement: The Business Glossary SHALL be backed by a YAML file

The glossary's source of truth SHALL be a single YAML file at `glossary/glossary.yaml` that supports a 2- or 3-level hierarchy (categories, optional subcategories, terms). All read and write access SHALL go through `core/glossary.py`, which MUST NOT import Streamlit so the same module can be reused by future non-Streamlit frontends.

#### Scenario: Glossary loads from `glossary/glossary.yaml`

- **WHEN** the Business Glossary page opens
- **THEN** terms are loaded from `glossary/glossary.yaml`
- **AND** the file supports 2 or 3 levels: categories → optional subcategories → terms

#### Scenario: A term has the documented fields

- **GIVEN** a term in the glossary
- **THEN** it has a required `title`
- **AND** optional `business_description`, `detailed_description`
- **AND** an optional `related_objects` list of strings

#### Scenario: Persistence module is Streamlit-free

- **WHEN** `core/glossary.py` is imported
- **THEN** it does NOT import `streamlit`
- **AND** it exposes load, save, and term-level mutation functions usable from any Python context

### Requirement: The Glossary page SHALL render a 3-pane layout

The Business Glossary page SHALL present a left navigation panel (search, "Add new +", and an expandable category/subcategory/term tree) alongside a right detail panel that shows the selected term. The detail panel SHALL render the `Title`, `Business description`, `Detailed description`, and `Related objects` sections in a fixed order.

#### Scenario: Tree, list, and detail are visible

- **WHEN** the user opens the Business Glossary page
- **THEN** the left panel shows a search box, "Add new +" button, and an expandable tree of categories → subcategories → terms
- **AND** the right panel shows the selected term's `Title`, `Business description`, `Detailed description`, and `Related objects` sections
- **AND** if no term is selected, the right panel shows a placeholder

#### Scenario: Search filters the tree

- **WHEN** the user types in the search box
- **THEN** the tree shows only terms whose title matches (case-insensitive substring)
- **AND** parent categories/subcategories collapse to show only matching terms

### Requirement: The Glossary page SHALL support per-section editing

Each section in the right detail panel SHALL be independently editable via a pencil icon. Entering edit mode for one section MUST NOT affect the read/edit state of the other sections. Save SHALL persist the change to `glossary/glossary.yaml` immediately; Cancel SHALL discard the in-progress edit without writing to disk.

#### Scenario: Pencil icon enters section edit mode

- **WHEN** the user clicks a pencil icon next to a section
- **THEN** that section renders as an inline editor with Save and Cancel buttons
- **AND** other sections remain in read mode

#### Scenario: Save persists the change

- **WHEN** the user clicks Save in a section's editor
- **THEN** the term is updated via `core/glossary.upsert_term(...)`
- **AND** the entire glossary is written back to `glossary/glossary.yaml`
- **AND** the section returns to read mode showing the new value

#### Scenario: Cancel discards the change

- **WHEN** the user clicks Cancel in a section's editor
- **THEN** no file write occurs
- **AND** the section returns to read mode showing the prior value

### Requirement: The Glossary page SHALL support adding new terms

Users SHALL be able to create a new glossary term via the "Add new +" control. The new-term form SHALL allow choosing the target category and (optional) subcategory and SHALL persist the term to `glossary/glossary.yaml` on Save.

#### Scenario: Add new opens an empty form

- **WHEN** the user clicks "Add new +"
- **THEN** the right panel shows an empty term form with category/subcategory pickers and the term fields
- **AND** Save creates the term in the chosen location and persists the glossary
- **AND** Cancel discards the draft

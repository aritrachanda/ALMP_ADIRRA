# Spec — vue-catalog-page (ADDED)

## ADDED Requirements

### Requirement: Dataset and table browser

The Catalog page SHALL provide dataset and table dropdowns populated from the catalogs API. Selecting a table SHALL display its metadata and columns.

#### Scenario: Table header with metadata

- **GIVEN** a table is selected
- **THEN** a metadata row SHALL display: row count, primary key columns, description coverage percentage

#### Scenario: Column grid with stats

- **GIVEN** a table is selected
- **THEN** a QTable SHALL display columns with: name, data type, null %, sample values (collapsible), user description, mapping instructions
- **AND** the table SHALL use zebra striping for readability

### Requirement: Inline annotation editing

User descriptions and mapping instructions SHALL be editable inline. Changes SHALL be saved to the annotation overlay via `PUT /annotations/{dataset}/{table}` — the source catalog SHALL NOT be modified.

#### Scenario: Edit and save a column description

- **WHEN** the user edits a column's user description and clicks Save
- **THEN** the annotation SHALL be persisted via the annotations API
- **AND** a confirmation toast SHALL appear

### Requirement: AI description generation

"Improve with AI" buttons SHALL be available per column and per table (batch). Clicking SHALL call the backend AI generation endpoint and pre-fill the description fields with the result.

### Requirement: Glossary cross-references

Each column SHALL show whether a matching glossary term exists. A button SHALL navigate to the glossary page to view or create the term.

#### Scenario: Navigate to glossary from column

- **WHEN** the user clicks the glossary button on a column that has a matching term
- **THEN** the app SHALL navigate to `/tools/glossary?term={id}`

#### Scenario: Create glossary term from column

- **WHEN** the user clicks "+ Glossary" on a column without a matching term
- **THEN** the app SHALL navigate to `/tools/glossary?new=true&title={column_name}&source={dataset}&table={table}`

### Requirement: Incoming navigation

- **WHEN** the page loads with `route.query.dataset` and `route.query.table` set
- **THEN** the corresponding dataset and table SHALL be auto-selected (replaces Streamlit's `catalog_jump`)

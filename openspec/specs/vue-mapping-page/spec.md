# Spec — vue-mapping-page (ADDED)

## ADDED Requirements

### Requirement: Source/target selection and mapping execution

The Mapping page SHALL provide dropdowns to select a source and target catalog (populated from the API). A target table multi-select SHALL allow choosing which tables to map. An agent choice selector (Generic / BIRD) SHALL be available. A "Run Mapping" button SHALL trigger the mapping process.

#### Scenario: SSE streaming progress

- **WHEN** the user clicks "Run Mapping"
- **THEN** the page SHALL open an SSE connection to `POST /mappings/{source}/{target}/run-stream`
- **AND** display per-table progress indicators that update in real-time as events arrive
- **AND** show step status (analyzing → candidates → scoring → columns → validating → done) per table
- **AND** display a final summary when the `done` event arrives

### Requirement: Three-tab result view

Results SHALL be displayed in three tabs: Visualization, Table, and Raw.

#### Scenario: Visualization tab — network graph

- **GIVEN** a completed mapping result
- **THEN** the Visualization tab SHALL render a vis-network graph
- **AND** source tables SHALL appear as blue nodes on the left
- **AND** target tables SHALL appear as grey nodes on the right
- **AND** edges SHALL be colored by confidence: green (≥0.7), yellow (0.4–0.69), red (<0.4)
- **AND** clicking a node SHALL highlight its connected edges

#### Scenario: Table tab — flat mapping view

- **GIVEN** a completed mapping result
- **THEN** the Table tab SHALL display a QTable with columns: source table, source column, target table, target column, confidence (with color indicator), transformation type, status
- **AND** the table SHALL be sortable and filterable

#### Scenario: Raw tab — accept/discard editor

- **GIVEN** a completed mapping result
- **THEN** the Raw tab SHALL show per-candidate cards with column-level detail
- **AND** each candidate SHALL have Accept and Discard buttons
- **AND** accepting/discarding SHALL call `PATCH /mappings/{source}/{target}/candidates` and persist

### Requirement: SQL preview

Below the result tabs, a collapsible panel SHALL show the SQL preview generated from accepted mappings.

### Requirement: Load existing mappings

- **WHEN** the page loads and a mapping already exists for the selected source/target pair
- **THEN** the existing mapping SHALL be loaded and displayed in the three tabs

# Spec delta — mapping-visualization (ADDED)

## ADDED Requirements

### Requirement: The Mapping page SHALL render mapping results in three views

The Mapping page SHALL present generated mapping results in three tabbed views: a **Visualization** view (graph), a **Table** view (flat dataframe), and a **Raw** view (the existing per-candidate accept/discard editor). The Visualization tab SHALL be the default. Switching tabs MUST NOT lose any unsaved edits made in the Raw view.

#### Scenario: Three tabs are available after a mapping run

- **WHEN** a mapping has been generated for the selected source/target pair
- **THEN** the page shows tabs labeled "Visualization", "Table", and "Raw"
- **AND** "Visualization" is selected by default

#### Scenario: Tabs preserve in-progress edits

- **WHEN** the user edits a candidate in the Raw tab and switches to another tab and back
- **THEN** the in-progress edits are still present in the Raw editor

### Requirement: The Visualization tab SHALL render a card-graph of source→target mappings

The Visualization tab SHALL render an interactive card-graph using `streamlit-agraph`. Each node SHALL be styled as a **card** showing the table name, a "X cols, Y rows" caption, and a confidence pill (high/medium/low colored using the DPMM confidence palette: green `#22c55e`, yellow `#eab308`, red `#ef4444`). Source-table cards appear on one side, target-table cards on the other. Edges represent column-level mappings between those tables and SHALL be colored using the same confidence buckets. Selecting a card SHALL highlight its incident edges.

#### Scenario: Tables are rendered as confidence-pill cards

- **WHEN** the Visualization tab opens with a generated mapping
- **THEN** each unique source table appears as a card on the left labeled with the table name, a "X cols, Y rows" caption, and a confidence pill summarising the table's overall mapping confidence
- **AND** each unique target table appears as a card on the right with the same elements

#### Scenario: Confidence is encoded as edge color

- **WHEN** an edge is drawn for a column mapping with confidence ≥ 0.7
- **THEN** the edge is rendered green
- **AND** edges with confidence in [0.4, 0.7) are rendered yellow
- **AND** edges with confidence < 0.4 are rendered red

#### Scenario: Selecting a card highlights its edges

- **WHEN** the user clicks a card in the Visualization tab
- **THEN** the edges incident to that card are highlighted (e.g. blue) while non-incident edges remain dimmed
- **AND** clicking the background restores the default rendering

#### Scenario: Discarded mappings are excluded from the graph

- **WHEN** a candidate or column mapping has status "discarded"
- **THEN** its edges are not drawn

### Requirement: The Table tab SHALL render a flat, sortable mapping table

The Table tab SHALL render a single `st.dataframe` with one row per column-level mapping (across all non-discarded candidates), with columns: source schema, source table, source column, target schema, target table, target column, confidence (numeric + emoji bucket 🟢/🟡/🔴), status, and rationale. The table SHALL be sortable by the user.

#### Scenario: One row per column mapping

- **WHEN** the Table tab opens with a generated mapping
- **THEN** each non-discarded source-column → target-column mapping appears as a single row
- **AND** the row shows source/target schema, table, column, confidence, status, and rationale

#### Scenario: Confidence shows both number and emoji bucket

- **GIVEN** a mapping row
- **THEN** the confidence column displays both the numeric value and the bucket emoji (🟢, 🟡, or 🔴) consistent with the Visualization tab's color thresholds

### Requirement: The Table tab SHALL include an SQL preview

Below the mapping table, the Table tab SHALL render a read-only SQL preview as `st.code(..., language="sql")` inside a `st.expander("SQL query")` (collapsed by default), showing a generated `SELECT` statement that aliases each accepted source column to its target column name. The SQL is preview-only and is NOT executed.

#### Scenario: SQL preview reflects accepted mappings

- **WHEN** at least one column mapping has status "accepted"
- **AND** the user expands the "SQL query" expander
- **THEN** the SQL preview renders a `SELECT` listing each accepted source column aliased `AS <target_column>` from the corresponding source table

#### Scenario: SQL preview is empty when no mappings are accepted

- **WHEN** no column mappings have status "accepted"
- **AND** the user expands the "SQL query" expander
- **THEN** the SQL preview shows a placeholder comment (e.g. `-- Accept mappings to generate SQL`)

### Requirement: The Table tab SHALL include a toolbar above the dataframe

Above the mapping dataframe, the Table tab SHALL render a toolbar containing: a **View columns** multiselect (controls which columns are shown), a **Filter by pipeline** selectbox (filters rows by source table / pipeline), and a **Search** input (case-insensitive substring filter across all visible string columns).

#### Scenario: View columns hides and shows columns

- **WHEN** the user deselects a column in the View columns multiselect
- **THEN** that column is no longer rendered in the dataframe
- **AND** re-selecting it restores the column

#### Scenario: Filter by pipeline narrows the rows

- **WHEN** the user picks a pipeline value in the Filter by pipeline selectbox
- **THEN** only rows whose source table matches the selected pipeline are shown
- **AND** picking the "All" / blank option restores all rows

#### Scenario: Search filters the dataframe

- **WHEN** the user types into the Search input
- **THEN** only rows containing the search text in any visible string column (case-insensitive) are shown
- **AND** clearing the input restores all rows

### Requirement: The Mapping page SHALL include a left dataset panel

The Mapping page SHALL render a left **dataset panel** (between the navy sidebar and the main detail) listing the available datasets that can be mapped. For the demo, the panel MAY contain a single hard-coded entry pointing at the active mapping; the panel MUST be present in the layout so future datasets can be added without restructuring the page.

#### Scenario: Dataset panel renders even with one entry

- **WHEN** the user opens the Mapping page
- **THEN** a dataset panel is visible to the left of the mapping result tabs
- **AND** the panel lists at least one dataset entry that, when selected, shows its mapping in the main detail panel

### Requirement: The Raw tab SHALL preserve the existing accept/discard editor

The Raw tab SHALL render the pre-existing per-candidate accept/discard editor unchanged (expanders per candidate, `st.data_editor` per candidate's columns, accept/discard/reset buttons). Edits made in this tab SHALL persist via the existing save path to `mappings/<source>_to_<target>.yaml`.

#### Scenario: Raw tab matches today's behavior

- **WHEN** the user opens the Raw tab
- **THEN** the per-candidate expander/data-editor UI is rendered exactly as it was before this change
- **AND** accept/discard/reset and inline column edits write back to the mapping YAML on save

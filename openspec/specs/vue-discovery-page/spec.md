# Spec — vue-discovery-page (ADDED)

## ADDED Requirements

### Requirement: Table stats browser

The Discovery page SHALL provide dataset and table selectors. Selecting a table SHALL display its overview and column statistics.

#### Scenario: Table overview

- **GIVEN** a table is selected
- **THEN** the page SHALL display: row count, column count, primary key, and foreign key relationships

#### Scenario: Column stats table

- **GIVEN** a table is selected
- **THEN** a QTable SHALL display columns with: name, data type, null %, distinct count, min, max, sample values
- **AND** sample values SHALL be collapsible (click to expand/collapse)

### Requirement: Inline chat panel scoped to table

A fixed-bottom collapsible chat panel SHALL allow querying the selected table. The system prompt SHALL be pre-populated with the table's schema and connection information.

#### Scenario: Execute DuckDB query via chat

- **WHEN** the user asks a data question in the chat panel
- **THEN** the chat SHALL call `POST /discovery/{dataset}/{table}/query`
- **AND** display the query results as a QTable below the response

#### Scenario: Chart rendering

- **WHEN** the chat response includes a chart specification
- **THEN** the chart SHALL be rendered using Chart.js (bar, line, pie, etc.)

### Requirement: Incoming navigation

- **WHEN** the page loads with `route.query.dataset` and `route.query.table` set
- **THEN** the corresponding dataset and table SHALL be auto-selected

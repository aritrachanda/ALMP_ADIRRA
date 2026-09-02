## ADDED Requirements

### Requirement: Resolve a deep-link query into workspace selection

On load, the Asset Workspace SHALL read `source`, `schema`, `table`, `column`, and `tab` from the
route query and, when a `source` is present, set `selectedSource`, `selectedTableSchema`,
`selectedTable`, `selectedColumn`, and `activeTab` accordingly, loading the data for the deepest
provided level.

#### Scenario: Full field deep link opens the field on the requested tab
- **WHEN** the workspace loads with `?source=banking&schema=src&table=accounts&column=currency&tab=refdata`
- **THEN** `selectedSource` is `banking`, `selectedTable` is `accounts`, `selectedTableSchema` is
  `src`, `selectedColumn` is `currency`, and `activeTab` is `refdata`

#### Scenario: Source-only deep link opens the source
- **WHEN** the workspace loads with `?source=banking` and no table/column
- **THEN** `selectedSource` is `banking` and no table or column is selected

#### Scenario: Legacy tab value is healed
- **WHEN** the query contains `tab=definition`
- **THEN** `activeTab` is set to `interpretation`

### Requirement: Query precedence over stored selection

When the route query includes a `source`, it SHALL take precedence over the `localStorage`
`workspace_selection`. When the query has no `source`, the existing `localStorage` restore SHALL be
used unchanged.

#### Scenario: Query wins over localStorage
- **WHEN** `localStorage` holds a selection for `payments.amount` and the workspace loads with
  `?source=banking&schema=src&table=accounts&column=currency`
- **THEN** the workspace selects `banking / src / accounts / currency`, not the stored `payments`
  selection

#### Scenario: No query falls back to localStorage
- **WHEN** the workspace loads with no query params and `localStorage` holds a valid selection
- **THEN** the stored selection is restored exactly as before this change

### Requirement: Validate deep-link levels and fall back gracefully

Each query level SHALL be validated against loaded data — `source` against the source list, `table`
against the loaded tables (matching `schema` when provided), and `column` against that table's
columns. On an invalid level, the workspace SHALL select the deepest valid level instead of a
non-existent one.

#### Scenario: Unknown source falls back to stored restore
- **WHEN** the workspace loads with `?source=ghost` that is not in the source list
- **THEN** no query-driven selection is applied and the normal `localStorage` restore runs

#### Scenario: Unknown column stops at the dataset
- **WHEN** the query names a valid `source` and `table` but a `column` that does not exist on that
  table
- **THEN** the workspace selects the table (dataset view) and does not select a column

## ADDED Requirements

### Requirement: Table header with metadata
The catalog page SHALL display a table header showing the table name, row count, primary key columns, and a description coverage metric (e.g., "5 of 12 columns described").

#### Scenario: Table with PK and stats
- **WHEN** a user views a table that has a primary key and row count in the catalog
- **THEN** the header SHALL display the PK columns and row count

#### Scenario: Coverage metric
- **WHEN** a user views a table where 5 of 12 columns have at least one non-empty description (source or user)
- **THEN** the header SHALL display "5 / 12 columns described"

### Requirement: Source description displayed as read-only
The catalog page SHALL display the source `description` field from the catalog YAML as read-only text. This field SHALL NOT be editable on the page.

#### Scenario: Column with source description
- **WHEN** a column has a non-empty `description` in the catalog YAML
- **THEN** the page SHALL display it as read-only text labeled as the source description

#### Scenario: Column without source description
- **WHEN** a column has a null or empty `description` in the catalog YAML
- **THEN** no source description SHALL be shown (no placeholder, no "N/A")

### Requirement: User annotation fields are editable
The catalog page SHALL display editable fields for `user_description` and `mapping_instructions` for each table and each column, loaded from the annotation overlay file.

#### Scenario: Editing a column's user description
- **WHEN** a user types into the `user_description` field for a column and clicks Save
- **THEN** the value SHALL be persisted to the annotation overlay file

#### Scenario: Editing mapping instructions
- **WHEN** a user types into the `mapping_instructions` field for a column and clicks Save
- **THEN** the value SHALL be persisted to the annotation overlay file

### Requirement: Inline column stats
The catalog page SHALL display curated column statistics inline: distinct count and null percentage. Min/max values MAY be shown if available.

#### Scenario: Column with stats
- **WHEN** a column has `distinct_count` and `null_pct` in the catalog
- **THEN** the page SHALL display them inline in the column row (e.g., "403 unique · 0% null")

#### Scenario: Column without stats (schema-only dataset)
- **WHEN** a column has null stats (e.g., target datasets from Excel)
- **THEN** the stats area SHALL be empty (no error, no "N/A")

### Requirement: PK and FK indicators on columns
The catalog page SHALL display a primary key indicator (🔑) on columns that are part of the table's primary key and a foreign key indicator (→) on columns that are foreign keys.

#### Scenario: PK column
- **WHEN** a column is listed in the table's `primary_key` array
- **THEN** the column name SHALL be prefixed with a 🔑 indicator

#### Scenario: FK column
- **WHEN** a column is listed in the table's `foreign_keys` array
- **THEN** the column name SHALL be prefixed with a → indicator

### Requirement: Sample values toggle
The catalog page SHALL provide a toggle/expander to show sample values for columns. Sample values SHALL be hidden by default.

#### Scenario: User expands sample values
- **WHEN** a user clicks the sample values toggle for the table
- **THEN** sample values for each column SHALL become visible

#### Scenario: Column with no sample values
- **WHEN** a column has an empty `sample_values` array
- **THEN** no sample values SHALL be shown for that column

### Requirement: Save writes to annotation overlay only
The Save button SHALL write only to the annotation overlay file. It SHALL NOT modify the catalog YAML.

#### Scenario: Save descriptions
- **WHEN** a user edits annotations and clicks Save
- **THEN** only `<dataset>.annotations.yaml` SHALL be modified; the catalog YAML SHALL remain unchanged

## ADDED Requirements

### Requirement: Target-driven iteration
The mapping agent SHALL iterate over each target table and find matching source data, rather than iterating source tables.

#### Scenario: All target tables visited
- **WHEN** the mapping agent runs against a source and target catalog
- **THEN** every target table in the catalog SHALL have an entry in the output, either with mapped source columns or explicitly marked as unmapped

#### Scenario: Target table with no matching source
- **WHEN** a target table has no relevant source data in any source table
- **THEN** the output SHALL include that target table with all columns marked `transformation_type: unmapped` and `confidence: 0.0`

### Requirement: Multi-source column mapping
Each target column mapping SHALL reference the specific source schema, source table, and source column it draws from, allowing a single target table to pull data from multiple source tables.

#### Scenario: Target table populated from two source tables
- **WHEN** a target table's columns map to columns from different source tables (e.g., `src.accounts` and `src.counterparties`)
- **THEN** each column mapping SHALL include `source_schema`, `source_table`, and `source_column` identifying the specific source

### Requirement: SQL query generation per target table
The mapping agent SHALL produce a draft SQL query for each target table that expresses the column mappings as a SELECT statement.

#### Scenario: Single-source SQL
- **WHEN** all mapped columns in a target table come from one source table
- **THEN** the `sql_query` field SHALL contain a SELECT with column aliases matching target column names

#### Scenario: Multi-source SQL with JOINs
- **WHEN** mapped columns come from multiple source tables
- **THEN** the `sql_query` field SHALL contain JOINs between the source tables

#### Scenario: Unmapped target table SQL
- **WHEN** a target table has no mapped source columns
- **THEN** the `sql_query` field SHALL be null

### Requirement: Source pre-filtering for prompt construction
The mapping agent SHALL pre-filter source tables for each target table, selecting the top-N most relevant source tables by token overlap scoring before constructing the LLM prompt.

#### Scenario: Large source catalog filtered
- **WHEN** the source catalog contains more tables than `max_source_tables` configuration
- **THEN** only the top-N scoring source tables' columns SHALL be included in the prompt for that target table

### Requirement: Target-centric output schema (version 2)
The mapping output YAML SHALL use `version: 2` and structure `tables[]` with one entry per target table, each containing a `columns[]` array where each column references its source location and a `sql_query` field.

#### Scenario: Output structure
- **WHEN** the mapping agent completes
- **THEN** the output SHALL have `version: 2` and each entry in `tables[]` SHALL contain `target_schema`, `target_table`, `sql_query`, `status`, and `columns[]`

#### Scenario: Column entry structure
- **WHEN** a target column is mapped
- **THEN** the column entry SHALL contain `target_column`, `source_schema`, `source_table`, `source_column`, `confidence`, `rationale`, `transformation_type`, `notes`, and `status`

### Requirement: Backward-compatible UI parsing
The mapping UI SHALL detect the `version` field and parse both version 1 (source-centric) and version 2 (target-centric) mapping files.

#### Scenario: Version 2 file loaded
- **WHEN** the UI loads a mapping file with `version: 2`
- **THEN** it SHALL parse the target-centric structure for display, graph, and SQL preview

#### Scenario: Version 1 file loaded
- **WHEN** the UI loads a mapping file with `version: 1` or no version field
- **THEN** it SHALL parse the existing source-centric structure (backward compatible)

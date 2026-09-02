## ADDED Requirements

### Requirement: DuckDB comment extraction
The DuckDB connector SHALL extract table and column comments from `duckdb_tables()` and `duckdb_columns()` system functions and populate `description` fields in the schema structure.

#### Scenario: Table with column comments in DuckDB
- **WHEN** a DuckDB table has `COMMENT ON COLUMN` metadata set
- **THEN** the extracted schema SHALL include those comments as `description` values on the corresponding column dicts

#### Scenario: Table with table-level comment in DuckDB
- **WHEN** a DuckDB table has `COMMENT ON TABLE` metadata set
- **THEN** the extracted schema SHALL include that comment as the table's `description` value

#### Scenario: No comments set in DuckDB
- **WHEN** a DuckDB table has no comments set
- **THEN** the `description` fields SHALL be `null` (no error, no change from current behavior)

#### Scenario: DuckDB version without comment support
- **WHEN** the DuckDB version does not support the `comment` column in system functions
- **THEN** the connector SHALL fall back gracefully and leave `description` as `null`

### Requirement: Snowflake comment extraction
The Snowflake connector SHALL extract table and column comments from `information_schema` and populate `description` fields in the schema structure.

#### Scenario: Table with column comments in Snowflake
- **WHEN** a Snowflake table has `COMMENT` metadata on columns
- **THEN** the extracted schema SHALL include those comments as `description` values on the corresponding column dicts

#### Scenario: Table with table-level comment in Snowflake
- **WHEN** a Snowflake table has a `COMMENT` on the table itself
- **THEN** the extracted schema SHALL include that comment as the table's `description` value

#### Scenario: No comments set in Snowflake
- **WHEN** a Snowflake table has no comments
- **THEN** the `description` fields SHALL be `null`

### Requirement: Comment extraction is connector-agnostic
The `BaseConnector` class SHALL define a `fetch_comments()` method with a default implementation returning an empty dict. Connectors that support comments SHALL override it.

#### Scenario: Connector without comment support
- **WHEN** a connector does not override `fetch_comments()`
- **THEN** `extract_schema_from_db()` SHALL proceed without error and leave descriptions as `null`

### Requirement: Comments merged into catalog during build
The `extract_schema_from_db()` function SHALL call `fetch_comments()` on the connector and merge the returned comments into the schema structure's `description` fields.

#### Scenario: Schema extraction with comments available
- **WHEN** `extract_schema_from_db()` runs against a connector that returns comments
- **THEN** the resulting schema dict SHALL have `description` populated on tables and columns where comments exist

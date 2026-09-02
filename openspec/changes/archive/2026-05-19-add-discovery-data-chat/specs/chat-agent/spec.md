## ADDED Requirements

### Requirement: Chat agent SHALL support a query_data tool for executing read-only SQL
The chat agent SHALL expose a `query_data` tool that accepts a SQL query string and a connection name, executes the query against the corresponding DuckDB database in read-only mode, and returns the result as a JSON array of row objects.

#### Scenario: Successful SQL query
- **WHEN** the LLM calls `query_data` with arguments `sql` and `connection_name`
- **THEN** the tool SHALL open the DuckDB file for that connection in read-only mode
- **AND** execute the SQL query
- **AND** return the result as a JSON array of row objects (max 1000 rows)
- **AND** include the column names and row count in the response

#### Scenario: SQL query exceeds row limit
- **WHEN** the query returns more than 1000 rows
- **THEN** the tool SHALL return only the first 1000 rows
- **AND** append a message indicating the result was truncated

#### Scenario: SQL query fails
- **WHEN** the SQL query is invalid or references a non-existent table/column
- **THEN** the tool SHALL return the DuckDB error message as the tool result
- **AND** the LLM SHALL be able to retry with a corrected query

#### Scenario: Connection not found or not a DuckDB connection
- **WHEN** the connection name does not exist or is not a DuckDB connection
- **THEN** the tool SHALL return an error message listing available DuckDB connections

### Requirement: Chat agent SHALL support a render_chart tool for structured chart specifications
The chat agent SHALL expose a `render_chart` tool that returns a structured JSON chart specification. The tool itself does not render anything — it returns the spec for the UI layer to render.

#### Scenario: LLM requests a chart
- **WHEN** the LLM calls `render_chart` with arguments `type`, `title`, `x`, `y`, `data_sql`, `connection_name`, and optional `color`
- **THEN** the tool SHALL validate that `type` is one of: `bar`, `line`, `scatter`, `pie`, `histogram`
- **AND** return the chart specification as a JSON object for the UI to render

#### Scenario: Invalid chart type
- **WHEN** the LLM calls `render_chart` with an unsupported chart `type`
- **THEN** the tool SHALL return an error message listing supported chart types

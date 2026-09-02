# Spec — chat-agent

## Requirements

### Requirement: Chat agent SHALL process messages using LLM with multi-turn history
The chat agent SHALL send the full conversation history (all previous messages) to the LLM on each turn, enabling context-aware multi-turn conversations. The system prompt SHALL provide a project overview and describe available tools.

#### Scenario: First message in a conversation
- **WHEN** the user sends their first message in a new conversation
- **THEN** the chat agent SHALL send the system prompt plus the user message to the LLM
- **AND** return the LLM's text response as the assistant reply

#### Scenario: Subsequent messages include history
- **WHEN** the user sends a follow-up message in an existing conversation
- **THEN** the chat agent SHALL send the system prompt plus all prior messages (user and assistant) plus the new user message to the LLM
- **AND** return the LLM's text response

### Requirement: Chat agent SHALL support LLM-native tool calling
The chat agent SHALL define tools as function definitions passed to the Azure Responses API. When the LLM requests a tool call, the agent SHALL execute the corresponding function, return the result to the LLM, and let the LLM generate a final text response.

#### Scenario: LLM requests a tool call
- **WHEN** the LLM response contains a tool call request (e.g. `get_glossary`)
- **THEN** the chat agent SHALL execute the requested function with the provided arguments
- **AND** append the tool result to the message array
- **AND** send the updated messages back to the LLM for a final response

#### Scenario: Tool calling loop is bounded
- **WHEN** the LLM makes repeated tool call requests
- **THEN** the chat agent SHALL execute up to 10 iterations of tool calls
- **AND** if the limit is reached, return whatever response is available

### Requirement: Chat agent SHALL provide context-fetching tools
The chat agent SHALL expose tools for fetching project context. Large catalogs SHALL return summary views by default; drill-down tools allow fetching single-table or single-column detail.

Summary tools:
- `list_sources` — list available source dataset names
- `list_targets` — list available target data model names
- `list_mappings` — list available mapping files
- `get_glossary` — return glossary term IDs grouped by category
- `get_source_catalog` — return a summary of a source (table list with column counts)
- `get_target_catalog` — return a summary of a target (table list with descriptions and column counts)
- `get_mapping` — return a mapping summary (per-source-table mapped/unmapped counts)

Drill-down tools:
- `get_glossary_term` — return full details for a specific glossary term
- `get_source_table` — return full column details for a single source table
- `get_target_table` — return full column details for a single target table
- `get_mapping_table` — return column-level mapping details for a specific source table

Search tools:
- `search_column` — find columns by name (substring) across source/target catalogs
- `get_column` — return full metadata for a single column

#### Scenario: Get glossary
- **WHEN** the LLM calls `get_glossary`
- **THEN** the tool SHALL return all glossary term IDs grouped by category from `glossary/glossary.yaml`

#### Scenario: Get source catalog
- **WHEN** the LLM calls `get_source_catalog` with argument `source_name`
- **THEN** the tool SHALL return a table-level summary for that source (not the full column dump)

#### Scenario: Get target catalog
- **WHEN** the LLM calls `get_target_catalog` with argument `target_name`
- **THEN** the tool SHALL return a table-level summary for that target

#### Scenario: Get mapping
- **WHEN** the LLM calls `get_mapping` with arguments `source_name` and `target_name`
- **THEN** the tool SHALL return a per-source-table summary of mapped/unmapped column counts
- **AND** if the mapping file does not exist, return a message indicating no mapping exists

#### Scenario: Search column
- **WHEN** the LLM calls `search_column` with a `column_name` substring
- **THEN** the tool SHALL return all matching columns across the specified catalog(s) with table name, data type, and description

#### Scenario: Get column
- **WHEN** the LLM calls `get_column` with catalog type, catalog name, table name, and column name
- **THEN** the tool SHALL return full metadata for that single column

#### Scenario: Tool output safety cap
- **WHEN** any tool returns output exceeding 30 000 characters
- **THEN** the output SHALL be truncated and a hint appended directing the LLM to use a more specific drill-down tool

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

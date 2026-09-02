## ADDED Requirements

### Requirement: Discovery page SHALL provide an inline chat scoped to the selected table
The Discovery page SHALL include a collapsible chat panel at the bottom of the page. The chat SHALL be pre-loaded with the currently selected table's schema, column statistics, and database connection context so the agent can answer questions and write SQL without requiring the user to describe the table.

#### Scenario: Chat panel is available on Discovery page
- **WHEN** the user navigates to the Discovery page and selects a table
- **THEN** a collapsible chat panel ("Ask about this table") SHALL be visible below the column statistics
- **AND** the panel SHALL be collapsed by default

#### Scenario: Chat is scoped to the selected table
- **WHEN** the user opens the chat panel and sends a message
- **THEN** the chat agent SHALL receive a system prompt containing the selected table's full schema (column names, data types, descriptions, statistics, sample values) and the database connection identifier
- **AND** the agent SHALL be able to answer questions about the table without additional tool calls for schema information

#### Scenario: Changing the selected table resets the chat
- **WHEN** the user selects a different table in the sidebar
- **THEN** the chat history for the previous table SHALL be cleared
- **AND** the system prompt SHALL be updated with the new table's context

### Requirement: Discovery chat SHALL render query results as interactive dataframes
When the chat agent calls the `query_data` tool, the Discovery page SHALL render the returned data as a Streamlit dataframe inline within the chat conversation.

#### Scenario: SQL query result displayed as dataframe
- **WHEN** the chat agent calls `query_data` and the query succeeds
- **THEN** the result SHALL be rendered as `st.dataframe()` within the assistant's response
- **AND** the text response from the agent SHALL be rendered above or below the dataframe

#### Scenario: SQL query error displayed as message
- **WHEN** the chat agent calls `query_data` and the query fails (syntax error, missing table, etc.)
- **THEN** the error message SHALL be returned to the agent as a tool result
- **AND** the agent SHALL be able to self-correct and retry with a fixed query

### Requirement: Discovery chat SHALL render chart specifications as interactive Plotly charts
When the chat agent calls the `render_chart` tool, the Discovery page SHALL execute the chart's data query, build a Plotly figure from the structured spec, and render it inline.

#### Scenario: Valid chart spec rendered as Plotly chart
- **WHEN** the chat agent calls `render_chart` with a valid spec (type, title, x, y, data_sql)
- **THEN** the UI SHALL execute `data_sql` against the database
- **AND** render the result as an interactive Plotly chart using `st.plotly_chart()`

#### Scenario: Chart spec with invalid columns falls back to dataframe
- **WHEN** the chart spec references x or y columns that do not exist in the query result
- **THEN** the UI SHALL fall back to rendering the query result as `st.dataframe()`
- **AND** display an info message explaining the fallback

#### Scenario: Supported chart types
- **WHEN** the chart spec `type` is one of: `bar`, `line`, `scatter`, `pie`, `histogram`
- **THEN** the UI SHALL render the corresponding Plotly Express chart
- **WHEN** the chart spec `type` is not in the supported list
- **THEN** the UI SHALL fall back to `st.dataframe()` with an info message

### Requirement: Discovery chat history SHALL NOT be persisted
Discovery chat conversations are ephemeral and table-scoped. They SHALL be stored only in Streamlit session state and SHALL NOT be written to `chat_history/`.

#### Scenario: Chat state lives in session only
- **WHEN** the user navigates away from the Discovery page and returns
- **THEN** the chat history SHALL be cleared
- **AND** no files SHALL be created in the `chat_history/` directory

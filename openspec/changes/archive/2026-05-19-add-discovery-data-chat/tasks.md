## 1. Chat Agent — New Tools

- [x] 1.1 Add `query_data(sql, connection_name)` tool to `agents/chat_agent.py`: open DuckDB in read-only mode, execute SQL, return JSON rows (max 1000), return error message on failure
- [x] 1.2 Add `render_chart(type, title, x, y, data_sql, connection_name, color?)` tool to `agents/chat_agent.py`: validate chart type against allowed list (bar, line, scatter, pie, histogram), return structured JSON spec
- [x] 1.3 Add helper to resolve `connection_name` → DuckDB file path using `connections.yaml`
- [x] 1.4 Register both tools in the chat agent's tool definitions array and update the system prompt to describe when to use them

## 2. Discovery Page — Inline Chat UI

- [x] 2.1 Add a collapsible chat panel (`st.expander`) at the bottom of `ui/pages/discovery.py`
- [x] 2.2 Build the table-scoped system prompt: inject current table's schema, column stats, sample values, and connection name
- [x] 2.3 Wire chat input to `chat_agent.chat()` with the custom system prompt and session-state message history
- [x] 2.4 Reset chat history in session state when the selected table changes

## 3. Discovery Page — Rich Result Rendering

- [x] 3.1 Detect `query_data` tool results in the assistant response and render them as `st.dataframe()`
- [x] 3.2 Detect `render_chart` tool results: execute `data_sql`, build Plotly Express figure from the spec, render with `st.plotly_chart()`
- [x] 3.3 Add fallback: if chart x/y columns are missing from query result or chart type is unsupported, render as `st.dataframe()` with info message
- [x] 3.4 Render plain text responses as `st.markdown()` alongside any tool result visuals

## 4. Dependencies & Cleanup

- [x] 4.1 Add `plotly` to `requirements.txt` if not already present
- [x] 4.2 Verify end-to-end flow: select table → ask a data question → see dataframe result → ask for chart → see Plotly chart

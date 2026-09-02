## Why

The Discovery page is the entry point for exploring source and target data, but it is entirely passive — a static YAML browser with no AI involvement. Every other core page (Mapping, Chat, Glossary) showcases agentic capabilities, making Discovery the weakest link in the demo narrative. Adding an inline data chat to Discovery lets the AI assist from the very first moment a user looks at their data: answering questions, querying actual data, and rendering ad-hoc visualizations — all scoped to the table being inspected.

## What Changes

- Add an inline chat panel to the Discovery page, scoped to the currently selected table
- Extend the chat agent with two new tools:
  - `query_data` — execute read-only SQL against the source/target DuckDB database and return tabular results
  - `render_chart` — return a structured chart specification (type, axes, SQL) that the UI renders as an interactive Plotly chart
- The Discovery page renders tool results inline: `query_data` results as `st.dataframe()`, `render_chart` results as `st.plotly_chart()`
- The inline chat pre-loads the current table's schema and column statistics into the system prompt so the agent can write accurate SQL and answer questions without extra tool calls

## Capabilities

### New Capabilities
- `discovery-data-chat`: Inline chat on the Discovery page with table-scoped context, SQL query execution, and dynamic chart rendering

### Modified Capabilities
- `chat-agent`: Add `query_data` and `render_chart` tools to the existing chat agent tool set

## Impact

- **Files modified**: `agents/chat_agent.py` (new tools), `ui/pages/discovery.py` (inline chat UI + chart renderer)
- **Files created**: None expected beyond the above modifications
- **Dependencies**: `plotly` added to `requirements.txt` (Streamlit already bundles it but explicit is better)
- **APIs**: No external API changes; new tools are internal to the chat agent
- **Security**: `query_data` must enforce read-only access (DuckDB read-only connection mode) and cap result size to prevent memory issues

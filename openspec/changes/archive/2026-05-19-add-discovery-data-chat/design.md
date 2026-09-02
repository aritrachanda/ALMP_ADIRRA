## Context

The Discovery page (`ui/pages/discovery.py`) currently loads source/target catalogs from YAML files and presents a static table browser: dataset selector → table selector → column statistics grid → column detail drill-down. It has zero AI involvement.

The chat agent (`agents/chat_agent.py`) already supports multi-turn conversation with tool calling via the Azure Responses API. It has 11+ tools for catalog browsing, mapping queries, glossary lookups, and CRR3 regulatory search. The Chat page (`ui/pages/chat.py`) renders these conversations.

Source and target databases are DuckDB files on disk. Connection details are in `connections.yaml`, loaded via `core/connectors.py`.

## Goals / Non-Goals

**Goals:**
- Add an inline chat to the Discovery page that is pre-scoped to the currently selected table
- Enable the chat agent to execute read-only SQL queries against source/target DuckDB databases
- Enable the chat agent to produce structured chart specifications that the UI renders as interactive Plotly charts
- Show query results as dataframes and charts inline within the chat conversation

**Non-Goals:**
- Full code generation / `exec()` of arbitrary Python — too risky, not needed for the demo use case
- Snowflake query support — only DuckDB for now (Snowflake connections use `schema_only: true`)
- Persisting discovery chat conversations to `chat_history/` — these are ephemeral, table-scoped interactions
- Replacing or duplicating the main Chat page — Discovery chat is lightweight and contextual

## Decisions

### 1. LLM generates SQL, not Python code

The `query_data` tool accepts a SQL string. The backend executes it against a read-only DuckDB connection and returns the result as a JSON table.

**Why not exec()?** SQL is inherently scoped — read-only DuckDB connections reject DDL/DML. Python exec() requires sandboxing, import allowlists, and timeout guards, all for marginal benefit in a demo app. SQL covers the queries users will ask (aggregations, filters, joins across tables in the same database).

**Alternative considered:** Structured query builder (column, aggregation, filter params). Rejected because it can't express joins, window functions, or complex filters that make the demo impressive.

### 2. Chart rendering via structured JSON spec, not raw plotting code

The `render_chart` tool returns a JSON object: `{ type, title, x, y, color, data_sql }`. The UI maps `type` to a Plotly Express function (bar, line, scatter, pie, histogram), runs `data_sql`, and renders the chart.

**Why not raw Plotly code?** Structured specs are safe (validated against a fixed schema), render consistently with the app's styling, and fail gracefully (fall back to table view if spec is invalid).

**Supported chart types:** `bar`, `line`, `scatter`, `pie`, `histogram`. Covers ~90% of demo asks. New types can be added by extending the renderer map.

### 3. Read-only DuckDB connection with result size cap

`query_data` opens the DuckDB file in read-only mode (`duckdb.connect(path, read_only=True)`) and caps results at 1000 rows. The connection is opened per-query and closed immediately — no persistent connection.

**Why per-query?** DuckDB file locks. The catalog builder or other processes may write to the same file. Read-only + open/close avoids contention.

### 4. Discovery chat uses a separate system prompt, not the main chat agent's

The Discovery chat injects the current table's full schema (column names, types, stats, sample values) and the database connection name into the system prompt. This is different from the main Chat page which has a broader project-wide prompt.

The same `chat_agent.chat()` function is reused, but called with a custom system prompt and a fresh (non-persisted) message history.

### 5. Inline chat renders in an expander at the bottom of Discovery

The chat panel lives in a `st.expander("💬 Ask about this table", expanded=False)` at the bottom of the Discovery page. This keeps the existing table browser as the primary view and lets users opt into the chat when they want it.

## Risks / Trade-offs

- **[Large table schemas in prompt]** → Cap the system prompt context to the selected table only (not the entire catalog). Column-level stats are summarized, not dumped raw.
- **[SQL errors from LLM]** → The tool returns the DuckDB error message to the LLM, which can self-correct and retry. The existing tool-call loop (max 10 iterations) handles this naturally.
- **[Chart spec doesn't match data]** → Validate that x/y columns exist in the query result before rendering. Fall back to `st.dataframe()` with an info message if validation fails.
- **[DuckDB file not found]** → Some datasets may not have a local DuckDB file (e.g., Snowflake-only sources). The tool returns a clear error message; the chat still works for schema/metadata questions using existing catalog tools.

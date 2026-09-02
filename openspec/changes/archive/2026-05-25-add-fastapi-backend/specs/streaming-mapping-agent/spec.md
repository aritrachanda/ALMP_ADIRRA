# Spec delta — streaming-mapping-agent (ADDED)

## ADDED Requirements

### Requirement: Generator-based chain-of-thought streaming

The mapping agent SHALL expose a generator function (`map_source_to_target_stream` / `map_source_to_bird_stream`) that yields structured `MappingEvent` dicts during execution. Each event carries progress information for real-time UI rendering.

#### Scenario: Event flow per target table follows 5-step sequence

- **WHEN** the mapping agent processes a single target table
- **THEN** the generator SHALL yield events in this order:
  1. `analyzing` — source schema analysis starting (includes `data.target_columns` count)
  2. `candidates` — candidate source tables found (includes `data.candidates` list of names, `data.source_tables` count, `data.source_columns` count)
  3. `scoring` — table-level scoring in progress
  4. `columns` — per-column mapping results (includes `data.columns[]` with `target_column`, `source_column`, `confidence`, `transformation_type`, `notes`; and `data.table_confidence`)
  5. `validating` — transformation validation pass
- **AND** a `table_done` event with summary (`data.mapped`, `data.unmapped`, `data.high_confidence`, `data.table_confidence`)

#### Scenario: Final event on success

- **WHEN** all target tables have been processed successfully
- **THEN** the generator SHALL yield a `done` event with `data.mapping` containing the full mapping result

#### Scenario: Error event on failure

- **WHEN** the agent raises an exception processing a table
- **THEN** the generator SHALL yield an `error` event with a descriptive message
- **AND** continue processing remaining tables

### Requirement: MappingEvent structure

Each event SHALL be a `TypedDict` with fields: `type` (EventType literal), `target_table` (str), `index` (int, 1-based), `total` (int), `message` (str), `data` (optional dict), `timestamp` (ISO 8601 string).

#### Scenario: EventType literals

- **GIVEN** the `EventType` type alias
- **THEN** it SHALL be `Literal["analyzing", "candidates", "scoring", "columns", "validating", "table_done", "error", "done"]`

### Requirement: SSE adapter for FastAPI backend

The `mapping_sse.py` module SHALL provide `format_sse_events()` that consumes a `MappingEvent` generator and yields SSE text frames suitable for `text/event-stream` responses. Internal event types map to SSE event names:

| MappingEvent.type | SSE event name |
|-------------------|---------------|
| analyzing         | status        |
| candidates        | status        |
| scoring           | status        |
| columns           | candidate     |
| validating        | status        |
| table_done        | candidate     |
| error             | error         |
| done              | done          |

#### Scenario: SSE stream emits events in order

- **WHEN** a client opens `POST /mappings/{source}/{target}/run-stream`
- **THEN** the response is HTTP 200 with `Content-Type: text/event-stream`
- **AND** the stream emits `status` events before `candidate` events for each table
- **AND** the stream emits a final `done` event

#### Scenario: SSE stream emits an error event on failure

- **WHEN** the agent raises an exception during the run
- **THEN** the stream emits an `error` event with the exception message
- **AND** the stream is closed cleanly

### Requirement: Streamlit UI tree-style progress rendering

The Streamlit mapping page SHALL render streaming events as a tree-style progress log with step numbers and status icons.

#### Scenario: Per-table progress rendering

- **WHEN** a mapping run is streaming in the Streamlit UI
- **THEN** each table's progress SHALL be rendered with:
  - `⚙️ Step 1–5` labels for each phase
  - `→ Found N candidates: X, Y, Z` showing discovered candidates
  - Per-column lines with confidence icons: `✓` (≥0.8, direct), `⚠️` (derived or 0.5–0.79), `❌` (<0.5 or unmapped)
  - `✅ Complete — M/N mapped with H at >0.8 confidence` summary

### Requirement: A synchronous mapping run endpoint SHALL remain available

For dry runs, tests, and small datasets where streaming has no value, the API SHALL also expose a synchronous `POST /mappings/{source}/{target}/run` that blocks until the mapping is saved and returns the full mapping in the response body.

#### Scenario: Synchronous run returns the persisted mapping

- **WHEN** a client posts `POST /mappings/{source}/{target}/run` with `{"dry_run": true}`
- **THEN** the API responds with HTTP 200
- **AND** the response body is the same mapping object served by `GET /mappings/{source}/{target}`

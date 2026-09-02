## Context

The mapping agents (`mapping_agent.py`, `bird_mapping_agent.py`) currently iterate over source tables, find candidate target tables for each, and produce column-level mappings. The UI (`ui/pages/mapping.py`) flattens `tables[].candidates[].columns[]` for display, graph building, and SQL preview. The chat agent also reads mapping YAML in `_tool_get_mapping()`.

The desired orientation is **target-driven**: iterate target tables, find relevant source data for each, and produce a SQL query that populates the target table. This better serves regulatory reporting where every target table must be explicitly addressed.

## Goals / Non-Goals

**Goals:**
- Reverse the mapping loop: iterate target tables, find source data for each
- Produce a draft SQL query per target table as first-class output
- Ensure every target table is visited (populated or explicitly marked as a gap)
- Support multi-source mappings (a target table pulling from multiple source tables via JOINs)
- Update the mapping YAML output schema to be target-centric
- Update all consumers (UI, chat agent) to parse the new structure

**Non-Goals:**
- Generating executable/validated SQL — the SQL is a draft hint, not a runnable query
- Changing LLM providers or model configuration
- Modifying the catalog format (sources/targets YAML stays the same)
- Adding new UI pages — existing mapping page adapts to new structure
- Production-grade SQL optimization or dialect support

## Decisions

### 1. New output schema: target-table as primary axis

**Decision**: Restructure mapping YAML so `tables[]` contains one entry per target table.

```yaml
version: 2
source: banking
target: bird
provider: azure
model: gpt-5.4-mini
generated_at: "2026-05-19T..."
status: draft
tables:
  - target_schema: E_INPUT
    target_table: INSTRMNT_RL
    target_framework: FINREP          # BIRD-specific, null for generic
    table_confidence: 0.93
    table_rationale: "..."
    status: pending
    sql_query: |
      SELECT s.account_id AS INSTRMNT_ID, ...
      FROM src.accounts s
      LEFT JOIN src.counterparties c ON ...
    columns:
      - target_column: INSTRMNT_ID
        source_schema: src
        source_table: accounts
        source_column: account_id
        confidence: 0.98
        rationale: "..."
        transformation_type: direct
        notes: null
        status: pending
      - target_column: CNTRPRTY_ID
        source_schema: src
        source_table: counterparties
        source_column: counterparty_id
        confidence: 0.90
        rationale: "..."
        transformation_type: derived
        notes: "Join via accounts.counterparty_id"
        status: pending
      - target_column: SOME_COL
        source_schema: null
        source_table: null
        source_column: null
        confidence: 0.0
        rationale: "No suitable source data found"
        transformation_type: unmapped
        notes: null
        status: pending
```

**Rationale**: Target-centric nesting naturally answers "how do I fill this table?" Each column mapping can reference different source tables, enabling multi-source JOINs. Unmapped target columns are explicit. The `sql_query` field sits at the target-table level where it belongs.

**Alternative considered**: Keep source-centric structure, add SQL as a post-processing step. Rejected because it fights the natural data flow and makes multi-source JOINs awkward.

### 2. Reverse the pre-filtering direction

**Decision**: For each target table, score all source tables by token overlap and select the top-N most relevant sources to include in the prompt.

**Rationale**: Same scoring heuristic (token overlap on names + descriptions) works in either direction. The BIRD agent adds framework/role bonus scoring, which still applies — just scoring source tables against target context instead of vice versa.

### 3. Restructured LLM prompt

**Decision**: Present one target table with all its columns, plus a filtered set of source columns. Ask the LLM to map each target column to the best source column (from any source table), classify the transformation, and produce a SQL query.

Prompt structure:
```
TARGET TABLE: E_INPUT.INSTRMNT_RL
Target columns:
  - INSTRMNT_ID [VARCHAR] — Unique instrument identifier
  - CRRNCY [VARCHAR] — Currency code
  ...

SOURCE COLUMNS (all available):
  - src.accounts.account_id [VARCHAR] — ...
  - src.accounts.currency [VARCHAR] — ...
  - src.counterparties.counterparty_id [VARCHAR] — ...
  ...

Map each target column to the best source column. Produce a SQL query.
```

**Rationale**: This naturally asks the right question. The LLM sees the full target table schema and all candidate source columns, enabling cross-table JOINs.

### 4. Version bump in output schema

**Decision**: Set `version: 2` in the new output format. Keep the old `_flatten_mapping` logic in the UI behind a version check so both formats can coexist during transition.

**Rationale**: Existing mapping YAML files in `mappings/` won't break the UI immediately. Simple version dispatch.

### 5. SQL query as LLM-generated draft

**Decision**: Include `sql_query` in the LLM response schema. The LLM generates a best-effort SELECT statement based on the column mappings it produced.

**Rationale**: The LLM already understands the mappings — generating SQL in the same call avoids a second round-trip. The existing `_build_sql_preview` in the UI can be replaced by displaying the LLM-generated SQL directly (with option to regenerate).

## Risks / Trade-offs

- **Prompt size increase**: Presenting all source columns for each target table may exceed context limits for large catalogs → Mitigated by pre-filtering source tables (top-N) before prompt construction, same as current approach but reversed direction.

- **More LLM calls if many target tables**: Target catalogs (BIRD, CRDM) may have more tables than source catalogs → Accept this; regulatory completeness is more valuable than fewer API calls. Can batch small target tables.

- **SQL quality**: LLM-generated SQL may have syntax issues or incorrect JOINs → Acceptable for a demo/PoC. The SQL is a draft starting point, not executable output.

- **Breaking change to mapping YAML**: Existing files and consumers break → Mitigated by version field and dual-format support in UI during transition. Old files can be regenerated.

- **Chat agent mapping reader**: `_tool_get_mapping()` in chat_agent.py uses a different structure expectation → Must update to handle version 2 format.

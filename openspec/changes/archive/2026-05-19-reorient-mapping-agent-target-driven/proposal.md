## Why

The mapping agent currently iterates over **source tables** and asks "where can this data go?" — but the real business question is the reverse: "which source data can populate this target regulatory table?" This distinction matters because the desired output is a SQL query per target table, and target-driven iteration guarantees every regulatory table is explicitly addressed (populated or flagged as a gap). The source-driven approach leaves target tables that don't closely resemble any source table silently unmapped.

## What Changes

- **Reverse the main loop axis** in both `mapping_agent.py` and `bird_mapping_agent.py`: iterate over target tables instead of source tables.
- **Reverse pre-filtering**: for each target table, score and select the most relevant source tables (currently the opposite direction).
- **Restructure the LLM prompt** to present one target table and ask "which source columns populate each target column?" — enabling multi-source joins and derived columns.
- **Add SQL query generation** as a first-class output: each target table mapping includes a draft `SELECT … FROM … JOIN …` query that populates it.
- **Restructure the mapping output schema** so the primary axis is target tables, each containing source mappings and a SQL query, rather than source tables with candidate targets.
- **BREAKING**: The mapping YAML output structure changes (target-table-centric instead of source-table-centric). Existing mapping files and any UI code that reads them will need updating.

## Capabilities

### New Capabilities
- `target-driven-mapping`: Core mapping logic reoriented to iterate target tables, find source data for each, and produce per-target-table SQL queries.

### Modified Capabilities
<!-- No existing spec-level capabilities are affected — the mapping agent has no spec yet. -->

## Impact

- `agents/mapping_agent.py` — main loop, prompt building, pre-filtering, output structure all change.
- `agents/bird_mapping_agent.py` — same changes, BIRD-specific prompt and filtering adapted.
- `mappings/*.yaml` — output format changes; existing files become incompatible.
- `ui/pages/mapping.py` — must read the new target-centric YAML structure.
- Any downstream code that parses mapping YAML (e.g. audit log, reporting) needs updating.

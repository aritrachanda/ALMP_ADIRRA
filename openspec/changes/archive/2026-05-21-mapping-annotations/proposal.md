## Why

The mapping agent currently sees only column names, types, and raw catalog descriptions when building LLM prompts. The recently added annotation overlay system (`user_description`, `mapping_instructions`, sample values, profiling stats) sits unused by the mapping pipeline. Feeding this enriched metadata into the prompt would improve column-matching accuracy, transformation logic, and SQL quality — especially for ambiguous or domain-specific columns.

We also need a reproducible, single-table test case to validate mapping quality before and after this change.

## What Changes

- Load annotation overlays alongside source/target catalogs in the mapping agent and merge `user_description`, `mapping_instructions`, and `sample_values` into the per-column prompt line
- Apply the same enrichment in the BIRD mapping agent (shared code path)
- Create a Guarantee test script that runs `map_source_to_target` scoped to `CRDM.input.Guarantee` and saves the result for manual review / before-after comparison

## Capabilities

### New Capabilities
- `mapping-context-enrichment`: Wiring annotation overlays and profiling data into the mapping agent's LLM prompt
- `mapping-test-case`: Reproducible single-table mapping run for quality validation

### Modified Capabilities

## Impact

- `agents/mapping_agent.py` — prompt construction changes (user prompt per column gains extra lines)
- `agents/bird_mapping_agent.py` — inherits enrichment via shared helpers
- `core/annotations.py` — used by the agent (read-only, no changes needed)
- New file: `tests/test_guarantee_mapping.py` — manual-run test script
- Token usage per LLM call increases (~2-3× for source column section); existing `max_source_tables` pre-filter mitigates this

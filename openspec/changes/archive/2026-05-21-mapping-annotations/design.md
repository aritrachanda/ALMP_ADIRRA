## Context

The mapping agent (`mapping_agent.py`) builds a per-target-table LLM prompt listing all candidate source columns as:

```
- src.loans.principal_amount [DOUBLE] — None
```

Annotation overlays (`<dataset>.annotations.yaml`) now contain `user_description` and `mapping_instructions` per column, and the catalog YAML has profiler stats (`sample_values`, `distinct_count`, `null_pct`). None of this reaches the mapping prompt today.

The BIRD agent (`bird_mapping_agent.py`) shares helpers with the generic agent and will inherit any enrichment automatically.

## Goals / Non-Goals

**Goals:**
- Merge annotation overlay data into source column prompt lines so the LLM sees business descriptions, mapping guidance, and sample values
- Keep prompt size manageable — only add metadata that exists (skip empty fields)
- Create a `tests/test_guarantee_mapping.py` script that runs `banking → CRDM.input.Guarantee` as a standalone quality check

**Non-Goals:**
- Enriching target columns (target catalogs come from regulatory models and don't have annotations yet)
- Automated quality scoring or golden-file regression testing
- Changing the LLM response schema or SQL generation logic

## Decisions

### 1. Merge annotations at prompt-build time, not at catalog load time

Load annotations in `_build_user_prompt()` (or its helper) and append to each column's prompt line. The catalog YAML stays unchanged — annotations are read-only overlay.

**Why:** Keeps the catalog as the single source of truth for schema. The mapping agent is the consumer, not the owner, of annotation data.

### 2. Column prompt format

Enrich only when data exists. The prompt line grows conditionally:

```
- src.guarantees.guarantee_amount [DOUBLE]
  Description: Total guaranteed amount in the contract currency.
  Mapping: Map to monetary amount fields. Cast DOUBLE to DECIMAL for precision.
  Samples: 15000.0, 250000.0, 1000000.0
```

Fields omitted when empty. This avoids bloating prompts for unannotated columns.

**Alternative considered:** A structured block per column (JSON-like). Rejected — the LLM parses natural-language lines just as well and it uses fewer tokens.

### 3. Pass annotations dict into `map_source_to_target` / `map_source_to_target_stream`

Add an optional `source_annotations: dict | None = None` parameter. The caller (UI or test script) loads annotations and passes them in. The agent doesn't need to know about file paths or overlay loading.

**Why:** Keeps the agent function pure — it receives data, not file paths. The UI already has access to the catalog directory.

### 4. Test script as a standalone Python file, not pytest

`tests/test_guarantee_mapping.py` is a runnable script (`python tests/test_guarantee_mapping.py`) that:
1. Loads banking source + CRDM target catalogs and banking annotations
2. Calls `map_source_to_target()` with `target_tables={"CRDM.input.Guarantee"}`
3. Saves the result to `tests/golden/banking_to_crdm_guarantee.yaml`
4. Prints a summary: mapped/derived/unmapped column counts, confidence scores

No assertion framework. The output is reviewed manually or diffed against a previous run.

## Risks / Trade-offs

- **Token budget increase** — Adding 1–3 extra lines per source column could 2–3× the source section size. Mitigated by: only emitting non-empty fields; existing `max_source_tables` pre-filter already caps context; Guarantee test has only ~10 source tables.
- **LLM prompt sensitivity** — Extra context could occasionally confuse the model (e.g., `mapping_instructions` written for a different target model). Low risk since instructions are human-authored and reviewed.
- **Non-deterministic test output** — Same prompt can produce different mappings across runs. The test script is for manual comparison, not CI pass/fail.

## 1. Enrich mapping prompt with annotations

- [x] 1.1 Add `source_annotations: dict | None = None` parameter to `map_source_to_target()` and `map_source_to_target_stream()` in `mapping_agent.py`
- [x] 1.2 Create helper `_enrich_column_line()` that appends `user_description`, `mapping_instructions`, and `sample_values` as indented sub-lines when present
- [x] 1.3 Wire `_enrich_column_line()` into the source column section of `_build_user_prompt()` (or equivalent prompt construction)
- [x] 1.4 Pass annotations through from UI caller in `ui/pages/mapping.py` (load annotations for the selected source dataset)

## 2. BIRD agent enrichment

- [x] 2.1 Add `source_annotations` parameter to `map_source_to_bird()` and `map_source_to_bird_stream()` in `bird_mapping_agent.py`
- [x] 2.2 Forward annotations to the shared prompt construction path

## 3. Guarantee test script

- [x] 3.1 Create `tests/test_guarantee_mapping.py` that loads banking source + CRDM target catalogs and annotations, runs `map_source_to_target` with `target_tables={"CRDM.input.Guarantee"}`, and saves result to `tests/golden/`
- [x] 3.2 Add `--no-annotations` flag to run a baseline comparison without annotations
- [x] 3.3 Print summary: mapped/derived/unmapped counts, average confidence, column list
- [x] 3.4 Run the test script and review the output

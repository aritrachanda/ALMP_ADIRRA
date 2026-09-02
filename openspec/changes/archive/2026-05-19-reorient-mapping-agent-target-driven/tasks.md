## 1. Core Mapping Agent — Reverse Loop & Prompt

- [x] 1.1 Refactor `mapping_agent.py`: reverse main loop to iterate target tables, pre-filter source tables per target
- [x] 1.2 Rewrite `build_system_prompt` and `build_user_prompt` to present one target table and ask which source columns populate it, including SQL query generation
- [x] 1.3 Update LLM response schema in the prompt to match version 2 output (target-centric with `sql_query`)
- [x] 1.4 Update `map_source_to_target` to assemble the new version 2 output structure

## 2. BIRD Mapping Agent — Adapt to Target-Driven

- [x] 2.1 Refactor `bird_mapping_agent.py`: reverse pre-filtering to score source tables against each target table (with BIRD framework/role bonus)
- [x] 2.2 Update BIRD-specific prompt to target-driven orientation while preserving BIRD vocabulary and `transformation_type` classification

## 3. UI — Parse New Output Format

- [x] 3.1 Update `_flatten_mapping` in `ui/pages/mapping.py` to handle version 2 (target-centric) structure
- [x] 3.2 Update `_build_graph` to work with version 2 structure (target nodes as primary, source nodes as secondary)
- [x] 3.3 Replace `_build_sql_preview` with display of LLM-generated `sql_query` from version 2 output
- [x] 3.4 Add version detection: dispatch to v1 or v2 parsing based on `version` field

## 4. Chat Agent — Update Mapping Reader

- [x] 4.1 Update `_tool_get_mapping` in `agents/chat_agent.py` to parse version 2 mapping structure

## 5. Regenerate Mappings & Verify

- [x] 5.1 Regenerate `mappings/banking_to_bird.yaml` with the new target-driven agent
- [x] 5.2 Regenerate `mappings/banking_to_crdm.yaml` with the new target-driven agent
- [x] 5.3 Verify UI loads and displays the new mapping files correctly

## 6. Selective Target Table Mapping

- [x] 6.1 Add `target_tables` filter parameter to `map_source_to_target` and `map_source_to_bird` to limit which target tables are processed
- [x] 6.2 Add table selection UI (multiselect with select/deselect all) in the mapping page sidebar before running the agent
- [x] 6.3 Implement merge semantics: after mapping selected tables, preserve existing mappings for non-selected tables

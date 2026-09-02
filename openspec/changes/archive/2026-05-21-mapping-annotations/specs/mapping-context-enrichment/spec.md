## ADDED Requirements

### Requirement: Annotations merged into mapping prompt
The mapping agent SHALL load annotation overlays for the source dataset and merge `user_description`, `mapping_instructions`, and `sample_values` into each source column's prompt line when building the LLM request.

#### Scenario: Source column with all annotation fields populated
- **WHEN** the mapping agent builds the prompt for a source column that has `user_description`, `mapping_instructions`, and `sample_values` in its annotation overlay
- **THEN** the prompt line for that column SHALL include all three fields as indented sub-lines below the column header

#### Scenario: Source column with no annotations
- **WHEN** the mapping agent builds the prompt for a source column that has no annotation data
- **THEN** the prompt line SHALL contain only the column name, type, and catalog description (unchanged from current behaviour)

#### Scenario: Source column with partial annotations
- **WHEN** the mapping agent builds the prompt for a source column that has only `user_description` but no `mapping_instructions`
- **THEN** the prompt line SHALL include the description sub-line and omit the mapping sub-line

### Requirement: Annotations parameter on mapping functions
The `map_source_to_target` and `map_source_to_target_stream` functions SHALL accept an optional `source_annotations` parameter. When provided, it SHALL be used to enrich source column prompt lines.

#### Scenario: Caller passes annotations dict
- **WHEN** the caller provides a `source_annotations` dict loaded from `load_annotations()`
- **THEN** the agent SHALL use it to look up per-column metadata during prompt construction

#### Scenario: Caller omits annotations
- **WHEN** the caller does not provide `source_annotations` (None)
- **THEN** the agent SHALL construct prompts identically to the current behaviour (no enrichment)

### Requirement: BIRD agent inherits enrichment
The BIRD mapping agent SHALL support the same `source_annotations` parameter and produce enriched prompts when annotations are provided.

#### Scenario: BIRD agent with annotations
- **WHEN** the BIRD agent is called with `source_annotations` for a banking source
- **THEN** the BIRD-specific prompt SHALL include annotation data on source columns alongside the existing framework/role context on target columns

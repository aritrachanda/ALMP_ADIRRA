## MODIFIED Requirements

### Requirement: Chat agent SHALL provide context-fetching tools
The chat agent SHALL expose tools for fetching project context. Large catalogs SHALL return summary views by default; drill-down tools allow fetching single-table or single-column detail.

Summary tools:
- `list_sources` — list available source dataset names
- `list_targets` — list available target data model names
- `list_mappings` — list available mapping files
- `get_glossary` — return glossary term IDs grouped by category
- `get_source_catalog` — return a summary of a source (table list with column counts)
- `get_target_catalog` — return a summary of a target (table list with descriptions and column counts)
- `get_mapping` — return a mapping summary (per-source-table mapped/unmapped counts)

Drill-down tools:
- `get_glossary_term` — return full details for a specific glossary term
- `get_source_table` — return full column details for a single source table
- `get_target_table` — return full column details for a single target table
- `get_mapping_table` — return column-level mapping details for a specific source table

Search tools:
- `search_column` — find columns by name (substring) across source/target catalogs
- `get_column` — return full metadata for a single column

Regulatory tools:
- `search_crr` — semantic search over CRR3 regulation text
- `get_crr_article` — retrieve a specific CRR3 article by number

#### Scenario: Get glossary
- **WHEN** the LLM calls `get_glossary`
- **THEN** the tool SHALL return all glossary term IDs grouped by category from `glossary/glossary.yaml`

#### Scenario: Get source catalog
- **WHEN** the LLM calls `get_source_catalog` with argument `source_name`
- **THEN** the tool SHALL return a table-level summary for that source (not the full column dump)

#### Scenario: Get target catalog
- **WHEN** the LLM calls `get_target_catalog` with argument `target_name`
- **THEN** the tool SHALL return a table-level summary for that target

#### Scenario: Get mapping
- **WHEN** the LLM calls `get_mapping` with arguments `source_name` and `target_name`
- **THEN** the tool SHALL return a per-source-table summary of mapped/unmapped column counts
- **AND** if the mapping file does not exist, return a message indicating no mapping exists

#### Scenario: Search column
- **WHEN** the LLM calls `search_column` with a `column_name` substring
- **THEN** the tool SHALL return all matching columns across the specified catalog(s) with table name, data type, and description

#### Scenario: Get column
- **WHEN** the LLM calls `get_column` with catalog type, catalog name, table name, and column name
- **THEN** the tool SHALL return full metadata for that single column

#### Scenario: Search CRR
- **WHEN** the LLM calls `search_crr` with a `query` string
- **THEN** the tool SHALL return up to 5 relevant CRR3 text chunks with relevance distances

#### Scenario: Get CRR article
- **WHEN** the LLM calls `get_crr_article` with an `article_num` string
- **THEN** the tool SHALL return the full article text and headline for that CRR3 article

#### Scenario: Tool output safety cap
- **WHEN** any tool returns output exceeding 30 000 characters
- **THEN** the output SHALL be truncated and a hint appended directing the LLM to use a more specific drill-down tool

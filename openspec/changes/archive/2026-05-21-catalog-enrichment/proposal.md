## Why

The Data Catalog page is currently a bare YAML editor — it shows column names, types, and free-text description inputs, but none of the rich metadata already available in catalogs (stats, PKs, FKs, sample values). Source database comments (DuckDB `COMMENT`, Snowflake `COMMENT`) are never extracted. There is no AI assistance for generating descriptions. The page needs to become a useful data exploration and documentation tool for demos, not just a form.

## What Changes

- **Extract source metadata comments**: Pull `COMMENT` metadata from DuckDB and Snowflake connectors during schema extraction, populating the existing `description` field from source.
- **Annotation overlay files**: Introduce `<name>.annotations.yaml` alongside catalog YAMLs to store user/AI-authored metadata (user descriptions, mapping instructions) that survive catalog rebuilds.
- **Richer catalog page UI**: Display column stats inline (distinct count, null %, min/max), show PK/FK indicators, add a sample values toggle, and show source descriptions as read-only context.
- **AI description generation**: "Improve with AI" buttons that send column/table context to the LLM and generate descriptions or mapping instructions, operating per-column or per-table in batch.
- **Coverage overview**: Show description completion metrics (e.g., "42 of 120 columns described") at the dataset level.

## Capabilities

### New Capabilities
- `source-metadata-extraction`: Extract table/column comments from database connectors (DuckDB, Snowflake) during schema extraction and populate the `description` field in catalog YAMLs.
- `annotation-overlay`: Separate annotation files (`<name>.annotations.yaml`) for user-authored and AI-generated metadata that persist across catalog rebuilds. Two hardcoded fields for now: `user_description` and `mapping_instructions`. Flexible/configurable annotation types is a future TODO.
- `catalog-page-redesign`: Richer catalog page showing stats, PK/FK indicators, source descriptions (read-only), user annotations (editable), sample value toggles, and a coverage overview.
- `ai-description-generation`: "Improve with AI" feature that generates descriptions and mapping instructions using the configured LLM, with optional user instructions. Supports per-column and per-table batch generation.

### Modified Capabilities

_None — no existing spec-level requirements change._

## Impact

- **`core/connectors.py`**: DuckDB and Snowflake connectors gain comment extraction in `_fetch_schema_rows()` or a new method.
- **`core/extractors/schema.py`**: `extract_schema_from_db()` passes comments through to the schema structure.
- **`core/catalog_builder.py`**: Preserves source `description` from connectors. No changes to rebuild logic (annotations live in separate files).
- **`ui/pages/catalog.py`**: Major rework — stats display, PK/FK indicators, annotation editing, AI generation UI, coverage metrics.
- **New file `core/annotations.py`** (or similar): Load/save/merge annotation overlay files.
- **New file `agents/catalog_agent.py`** (or similar): LLM-based description generation for catalog entries.
- **`sources/`, `targets/` directories**: Will contain new `*.annotations.yaml` files alongside existing catalog YAMLs.
- **Dependencies**: Uses existing Azure OpenAI / LLM infrastructure from `project.yaml` agent config. No new dependencies.

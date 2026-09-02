## 1. Source Metadata Extraction

- [x] 1.1 Add `fetch_comments()` method to `BaseConnector` with default empty-dict return
- [x] 1.2 Implement `fetch_comments()` in `DuckDBConnector` using `duckdb_tables()` and `duckdb_columns()` comment fields
- [x] 1.3 Implement `fetch_comments()` in `SnowflakeConnector` using `information_schema.tables.COMMENT` and `information_schema.columns.COMMENT`
- [x] 1.4 Update `extract_schema_from_db()` in `core/extractors/schema.py` to call `fetch_comments()` and merge into schema structure
- [x] 1.5 Verify catalog rebuild produces `description` fields from source comments (manual test with DuckDB)

## 2. Annotation Overlay System

- [x] 2.1 Create `core/annotations.py` with `load_annotations(dataset_name, catalog_dir)` and `save_annotations(dataset_name, catalog_dir, data)` functions
- [x] 2.2 Define annotation file schema: version, dataset, annotations dict keyed by `schema.table` with `user_description`, `mapping_instructions`, and `columns` sub-dict
- [x] 2.3 Handle missing annotation file gracefully (return empty structure)

## 3. Catalog Page Redesign

- [x] 3.1 Add table header section: table name, row count, PK columns, description coverage metric
- [x] 3.2 Display source `description` as read-only text for tables and columns
- [x] 3.3 Replace current single description field with two editable annotation fields: `user_description` and `mapping_instructions` (loaded from overlay)
- [x] 3.4 Add inline column stats: distinct count, null %, min/max
- [x] 3.5 Add PK (🔑) and FK (→) indicators on column names
- [x] 3.6 Add sample values toggle/expander (hidden by default)
- [x] 3.7 Rewire Save button to write to annotation overlay file only (not catalog YAML)

## 4. AI Description Generation

- [x] 4.1 Create `agents/catalog_agent.py` with `generate_descriptions()` function that takes table context and returns descriptions
- [x] 4.2 Build LLM prompt template including column name, type, stats, sample values, PK/FK, source description, and user instructions
- [x] 4.3 Support two generation modes: single-column and batch (all columns in a table)
- [x] 4.4 Support generating both `user_description` and `mapping_instructions` (separate prompt variants)
- [x] 4.5 Add "Improve with AI" button next to each annotation field on the catalog page
- [x] 4.6 Add optional user instructions text input for AI generation
- [x] 4.7 Add "Generate all" button for batch generation of all columns in current table
- [x] 4.8 Wire AI generation to use `agent` config from `project.yaml` (provider, model, API key)

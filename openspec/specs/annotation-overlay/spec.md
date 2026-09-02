## ADDED Requirements

### Requirement: Annotation file structure
The system SHALL store user-authored and AI-generated metadata in `<dataset>.annotations.yaml` files located in the same directory as the corresponding catalog YAML (`sources/` or `targets/`).

#### Scenario: Annotation file for a source dataset
- **WHEN** a user adds annotations to the "banking" source dataset
- **THEN** annotations SHALL be saved to `sources/banking.annotations.yaml`

#### Scenario: Annotation file for a target dataset
- **WHEN** a user adds annotations to the "crdm" target dataset
- **THEN** annotations SHALL be saved to `targets/crdm.annotations.yaml`

### Requirement: Annotation file schema
Each annotation file SHALL use the following structure: a `version` key (integer), a `dataset` key (string), and an `annotations` dict keyed by `schema_name.table_name`. Each table entry MAY contain `user_description`, `mapping_instructions`, and a `columns` dict keyed by column name. Each column entry MAY contain `user_description` and `mapping_instructions`.

#### Scenario: Annotation file with table and column annotations
- **WHEN** an annotation file is loaded
- **THEN** it SHALL parse table-level annotations via `annotations["schema.table"]["user_description"]` and column-level via `annotations["schema.table"]["columns"]["col_name"]["user_description"]`

### Requirement: Annotations survive catalog rebuild
Annotation files SHALL NOT be modified or deleted by `catalog_builder.py` during catalog rebuilds.

#### Scenario: Catalog rebuild with existing annotations
- **WHEN** `catalog_builder.py` rebuilds a catalog YAML due to schema hash change
- **THEN** the corresponding `.annotations.yaml` file SHALL remain unchanged

### Requirement: Load and save annotations
The system SHALL provide functions to load annotations for a dataset (returning an empty structure if no file exists) and to save annotations back to the file.

#### Scenario: Load annotations when file does not exist
- **WHEN** `load_annotations()` is called for a dataset with no annotation file
- **THEN** it SHALL return an empty annotation structure (no error)

#### Scenario: Save annotations
- **WHEN** `save_annotations()` is called with annotation data
- **THEN** it SHALL write the annotations to `<dataset>.annotations.yaml` in the correct directory

### Requirement: Two hardcoded annotation fields
The system SHALL support exactly two annotation fields per table and per column: `user_description` (general business description) and `mapping_instructions` (technical mapping notes including NULL handling, formats, transformations).

#### Scenario: User edits both fields on a column
- **WHEN** a user provides both `user_description` and `mapping_instructions` for a column
- **THEN** both values SHALL be persisted in the annotation file under that column's key

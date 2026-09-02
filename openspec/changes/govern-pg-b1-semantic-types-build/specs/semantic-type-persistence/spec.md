## ADDED Requirements

### Requirement: Semantic type persistence backend selection
The system SHALL support a `semantic_backend` configuration flag (`project.yaml` `database.semantic_backend`, overridable live via `ADM_SEMANTIC_BACKEND`) selecting between `yaml` (default) and `postgres` storage for semantic-type assignments, with `SemanticTypeStore`'s public method signatures unchanged regardless of the selected backend.

#### Scenario: Default backend is unchanged
- **WHEN** no `semantic_backend` override is configured
- **THEN** `SemanticTypeStore` reads and writes `governance/semantic_type_assignments.yaml` exactly as it does today, with no behavior change

#### Scenario: Postgres backend selected
- **WHEN** `semantic_backend` resolves to `postgres`
- **THEN** `SemanticTypeStore`'s methods delegate to the Postgres-backed repository instead of the YAML file, using identical method signatures and return shapes

### Requirement: Sticky disposition is preserved exactly
The system SHALL preserve `SemanticTypeStore.set_record()`'s `preserve_disposed` rule: when an existing record's `state` is `confirmed` or `rejected`, a new proposal MUST be stored as a nested `latest_proposal` rather than overwriting the disposed top-level record, in both backends.

#### Scenario: New proposal for a confirmed column
- **WHEN** `set_record()` is called for a key whose existing record has `state == "confirmed"`
- **THEN** the confirmed record's top-level fields are unchanged, and the new proposal is stored under `latest_proposal`

#### Scenario: New proposal for a non-disposed column
- **WHEN** `set_record()` is called for a key whose existing record has `state` in `{"proposed", "suggested", "unresolved"}` (or no existing record)
- **THEN** the new record replaces the existing one at the top level


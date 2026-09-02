## ADDED Requirements

### Requirement: Semantic type YAML-to-Postgres migration
The system SHALL provide a migration script that reads every key in `governance/semantic_type_assignments.yaml` and writes exactly one corresponding `semantic_type_assignment` current row, preserving every field the table has a column for without reshaping or summarising.

#### Scenario: Every key migrates to exactly one current row
- **WHEN** the migration runs against a YAML file containing N keys
- **THEN** the `semantic_type_assignment` table contains exactly N rows, one per key, and no key is represented more than once

#### Scenario: A disposed record's parked proposal survives
- **WHEN** a record carries a nested `latest_proposal` (a machine re-resolution parked under a confirmed or rejected decision)
- **THEN** the migrated row preserves that `latest_proposal` verbatim, and the steward's own disposition fields are unchanged

#### Scenario: History is not fabricated
- **WHEN** the migration completes
- **THEN** `semantic_type_assignment_history` contains zero rows, because the YAML file holds no submission history to migrate and no business-effective window may be invented

### Requirement: Migration is idempotent and re-runnable
The system SHALL skip any key that already has a `semantic_type_assignment` row on a non-forced run, and SHALL fully re-migrate (removing existing rows first) when run with `--force`.

#### Scenario: Re-running without --force does not duplicate
- **WHEN** the migration is run a second time without `--force` after a key was already migrated
- **THEN** that key's row is left unchanged and no duplicate row is created

#### Scenario: Re-running with --force replaces prior data
- **WHEN** the migration is run with `--force`
- **THEN** every previously-migrated row is removed and replaced with a fresh migration from the current YAML content

### Requirement: Migration parity check
The system SHALL provide a parity check comparing, for every key, the migrated Postgres row against the record `SemanticTypeStore` returns in YAML mode, reporting any field-level mismatch rather than passing silently.

#### Scenario: Parity holds
- **WHEN** the parity check runs after a successful migration
- **THEN** every key's migrated record matches the YAML store's output on every compared field, with zero reported mismatches

#### Scenario: A mismatch is surfaced, not hidden
- **WHEN** a key's migrated data differs from the YAML store's output in any compared field
- **THEN** the parity report includes that key and the specific field(s) that differ

#### Scenario: Parity is proven through the real stores
- **WHEN** the parity check reads each side
- **THEN** it calls the actual `SemanticTypeStore` (YAML mode) and `SemanticTypeRepo` (Postgres mode) public read methods, not an independent re-parse of the YAML file

### Requirement: The source YAML file is never modified
The system SHALL treat `governance/semantic_type_assignments.yaml` as read-only for the entire migration, leaving it intact as the rollback safety net.

#### Scenario: Source file survives a forced re-migration
- **WHEN** the migration is run with `--force`
- **THEN** `governance/semantic_type_assignments.yaml` is byte-identical to its content before the run

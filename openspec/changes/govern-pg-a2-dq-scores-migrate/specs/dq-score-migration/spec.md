## ADDED Requirements

### Requirement: DQ score YAML-to-Postgres migration
The system SHALL provide a migration script that reads every key in `governance/dq_scores.yaml` and writes its newest record as the `dq_score` current row and every older record as a `dq_score_history` row, deriving each row's `valid_from`/`valid_to` directly from the records' own `scored_at` timestamps with no fabricated placeholder.

#### Scenario: Single-record key migrates with no history
- **WHEN** a key has exactly one YAML record
- **THEN** migration creates one `dq_score` row with `valid_from` equal to that record's `scored_at`, and zero `dq_score_history` rows

#### Scenario: Multi-record key migrates with correct windows
- **WHEN** a key has multiple YAML records (newest first)
- **THEN** the newest record becomes the current `dq_score` row, every older record becomes a `dq_score_history` row, and each historical row's `valid_to` equals the `scored_at` of the record that superseded it

### Requirement: Migration is idempotent and re-runnable
The system SHALL skip any key that already has a `dq_score` row on a non-forced run, and SHALL fully re-migrate (truncating existing `dq_score`/`dq_score_history` rows first) when run with `--force`.

#### Scenario: Re-running without --force does not duplicate
- **WHEN** the migration is run a second time without `--force` after a key was already migrated
- **THEN** that key's rows are left unchanged and no duplicate `dq_score` row is created

#### Scenario: Re-running with --force replaces prior data
- **WHEN** the migration is run with `--force`
- **THEN** every previously-migrated `dq_score`/`dq_score_history` row is removed and replaced with a fresh migration from the current YAML content

### Requirement: Migration parity check
The system SHALL provide a parity check comparing, for every key, the migrated Postgres data's current score/state/grade_label/breakdown_version and history row count against `DQScoreStore`'s YAML-mode `latest()`/`history()` output, reporting any mismatch.

#### Scenario: Parity holds
- **WHEN** the parity check runs after a successful migration
- **THEN** every key's migrated current record and history depth match the YAML store's output exactly, with zero reported mismatches

#### Scenario: A mismatch is surfaced, not hidden
- **WHEN** a key's migrated data differs from the YAML store's output in any compared field
- **THEN** the parity report includes that key and the specific field(s) that differ, rather than silently passing

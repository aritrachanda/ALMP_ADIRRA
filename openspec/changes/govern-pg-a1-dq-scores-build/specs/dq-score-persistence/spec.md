## ADDED Requirements

### Requirement: DQ score persistence backend selection
The system SHALL support a `dq_backend` configuration flag (`project.yaml` `database.dq_backend`, overridable live via `ADM_DQ_BACKEND`) selecting between `yaml` (default) and `postgres` storage for DQ scores, with `DQScoreStore`'s public method signatures unchanged regardless of the selected backend.

#### Scenario: Default backend is unchanged
- **WHEN** no `dq_backend` override is configured
- **THEN** `DQScoreStore` reads and writes `governance/dq_scores.yaml` exactly as it does today, with no behavior change

#### Scenario: Postgres backend selected
- **WHEN** `dq_backend` resolves to `postgres` (via env or `project.yaml`)
- **THEN** `DQScoreStore`'s methods delegate to the Postgres-backed repository instead of the YAML file, using the identical method signatures and return shapes

### Requirement: DQ score current-plus-history schema with real SCD2 windows
The system SHALL persist each DQ score key's current record in a `dq_score` table (carrying a `valid_from`) and every superseded record in a `dq_score_history` table (each carrying a real, non-sentinel `valid_from` and `valid_to`), mirroring `reference_code`/`reference_code_history`'s point-in-time semantics rather than a plain unwindowed history list.

#### Scenario: First score for a key
- **WHEN** a key (column or dataset) is scored for the first time
- **THEN** a new `dq_score` row is inserted for that key and no `dq_score_history` row is created

#### Scenario: Score changes on a later re-score
- **WHEN** a key already has a `dq_score` row and is re-scored with a different `dq_score`, `state`, or `signal_fingerprint`
- **THEN** the prior current record is closed into `dq_score_history` with `valid_to` set to the new record's `scored_at`, and the `dq_score` row is updated in place with `valid_from` set to that same timestamp

### Requirement: No-op re-score does not append history
The system SHALL NOT create a new history entry when a re-score produces the same `dq_score`, `state`, and `signal_fingerprint` as the current record, matching the existing YAML store's fingerprint-based no-op detection (DQ §16.2-16.3).

#### Scenario: Identical re-score
- **WHEN** a key is re-scored and the resulting `dq_score`, `state`, and `signal_fingerprint` match the current `dq_score` row exactly
- **THEN** no `dq_score_history` row is created and the current row's `scored_at` is not advanced

#### Scenario: Same inputs but newer breakdown shape
- **WHEN** a key is re-scored with unchanged `dq_score`/`state`/`signal_fingerprint` but a newer `breakdown_version`
- **THEN** the current `dq_score` row's stored breakdown is refreshed in place without creating a `dq_score_history` row

### Requirement: History retention pruning
The system SHALL retain, per key, the oldest (baseline) `dq_score_history` record plus the most recent `N-1` records (default `N=50`), pruning any older records beyond that bound.

#### Scenario: History exceeds retention bound
- **WHEN** a key's `dq_score_history` row count exceeds the configured retention limit after an insert
- **THEN** the oldest baseline record is kept, the most recent `N-1` records are kept, and any remaining older records are deleted

### Requirement: Column and dataset keys share one schema
The system SHALL store both column-level scores (`source|schema|table|column` keys) and dataset-level roll-up scores (`source|schema|table` keys) in the same `dq_score`/`dq_score_history` tables, distinguished by a `key_kind` column, exactly matching today's single-YAML-file behavior.

#### Scenario: Column score recorded
- **WHEN** `DQScoreRepo.record()` is called with a column key produced by `DQScoreStore.key()`
- **THEN** the stored row's `key_kind` is `column`

#### Scenario: Dataset score recorded
- **WHEN** `DQScoreRepo.record()` is called with a dataset key produced by `DQScoreStore.dataset_key()`
- **THEN** the stored row's `key_kind` is `dataset`

### Requirement: Point-in-time DQ score lookup
The system SHALL provide an `as_of(key, as_of_date)` lookup that returns the score/grade applicable at a given business date by checking the current `dq_score` row first (only when its `state` is `scored` and `as_of_date >= valid_from`), then `dq_score_history` for a window covering `as_of_date`, returning "not found" if neither matches.

#### Scenario: Date falls within the current window
- **WHEN** `as_of()` is called with a date on or after the current `dq_score` row's `valid_from`, and that row's `state` is `scored`
- **THEN** the current row's score/grade is returned

#### Scenario: Date falls within a historical window
- **WHEN** `as_of()` is called with a date covered by a `dq_score_history` row's `valid_from`/`valid_to` window
- **THEN** that historical row's score/grade is returned

#### Scenario: Date falls before the key's first score
- **WHEN** `as_of()` is called with a date earlier than the key's earliest recorded `valid_from`
- **THEN** the lookup returns "not found"

### Requirement: Unscored state creates a point-in-time gap
The system SHALL treat a column's `state` transition to `unscored` (out-of-scope or an emptied table) the same way `reference_code`'s revoke is treated: the outgoing `scored` record is closed into `dq_score_history` with a real `valid_to`, and while the current row's `state` is `unscored`, `as_of()` MUST NOT treat that row as a valid answer for any date, including dates on or after its `valid_from`.

#### Scenario: Column goes out of scope
- **WHEN** a previously `scored` column's key is re-scored and its `state` becomes `unscored`
- **THEN** the previously current `scored` record is closed into `dq_score_history` with `valid_to` set to the new record's `scored_at`

#### Scenario: as_of() during an unscored gap
- **WHEN** `as_of()` is called with a date that falls after the current row became `unscored` and no `dq_score_history` window covers that date
- **THEN** the lookup returns "not found", even though the current row's `valid_from` is earlier than the requested date

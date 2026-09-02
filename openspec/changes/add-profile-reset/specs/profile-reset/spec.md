## ADDED Requirements

### Requirement: Table-level profile reset
The system SHALL provide a way to clear all profiling-derived and governance state for a single
dataset/table, returning it to the same pre-profiling shape a freshly onboarded (never profiled)
table would have. Column identity (names, data types, primary key, foreign keys, relations) is
schema metadata, not profiling state, and SHALL be preserved unchanged by the reset.

#### Scenario: Resetting a fully-governed table clears every affected store
- **WHEN** a table has catalog profile stats, a semantic-type assignment, a DQ score, an
  Interpretation lifecycle state with content, Reference Data per-code review rows, a
  reference-set binding, and catalog annotations, and a table-level reset is triggered for it
- **THEN** the catalog's stored stats for that table's columns (row/null/distinct counts,
  min/max, samples, code values) are cleared while column names, data types and descriptions
  remain, the semantic-type assignment is cleared, the DQ score becomes unscored, the
  Interpretation lifecycle status and content (descriptions, business names, submission overlay,
  assessment scope) return to their pre-governed default, the Reference Data per-code review rows
  are cleared, the reference-set binding and its review status are removed, and the catalog
  annotations for that table/its columns are removed

#### Scenario: Reset preserves what onboarding produced
- **WHEN** a table-level reset completes
- **THEN** the table's column list, each column's data type and description, and the table's
  declared primary key, foreign keys and relations are unchanged from before the reset, while
  profiling-derived counterparts (inferred primary key, inferred relations, orphan-FK counts) are
  cleared

### Requirement: Source-level profile reset
The system SHALL provide a way to apply the table-level profile reset to every table currently
present in a source's catalog, without affecting any other source.

#### Scenario: Resetting a source resets every one of its tables
- **WHEN** a source has multiple tables, each with governed state, and a source-level reset is
  triggered
- **THEN** every table in that source is cleared per the table-level profile reset requirement,
  and no table belonging to a different source is modified

### Requirement: Profile reset is idempotent
A profile reset (table- or source-level) SHALL succeed without error and report zero records
cleared when called on data that has already been reset, or was never profiled.

#### Scenario: Resetting an already-blank table is a no-op success
- **WHEN** a table-level reset is triggered for a table that has no profile stats, no semantic
  type, no DQ score, no Interpretation state, no reference data, and no annotations
- **THEN** the operation completes successfully and reports zero cleared records for every store,
  without raising an error

### Requirement: Profile reset never removes audit history
The audit log SHALL be append-only with respect to profile reset: the reset action itself SHALL
be recorded as a new audit event, and no existing audit event for the affected source/table SHALL
be deleted or altered by a reset.

#### Scenario: Audit history survives a reset
- **WHEN** a table with prior audit events undergoes a table-level reset
- **THEN** all of that table's prior audit events remain queryable afterward, and a new audit
  event describing the reset (scope, actor, timestamp) has been added

### Requirement: A failed reset changes nothing
A table-level profile reset SHALL be atomic: every affected store's clear operation runs inside a
single database transaction, and if any one of them fails, the transaction SHALL be rolled back so
that no store is left partially cleared. The failure SHALL be surfaced to the caller rather than
reported as a success. A source-level reset SHALL be atomic per table, continuing to the next table
after a failed one.

#### Scenario: One store failing rolls the whole table's reset back
- **WHEN** a table-level reset is triggered and one affected store's clear operation raises an
  error while the others would succeed
- **THEN** the transaction is rolled back, every affected store still holds exactly the data it
  held before the reset was attempted, and the operation reports the failure rather than returning
  an indistinguishable success

#### Scenario: A failed table does not block the rest of a source-level reset
- **WHEN** a source-level reset is triggered and one table's reset fails
- **THEN** that table is left completely unchanged, the remaining tables are still reset, and the
  result identifies which table failed

### Requirement: Profile reset reports live progress
A profile reset SHALL stream progress events describing which step is currently executing, using
the same event shape as the existing profile-rebuild operation.

#### Scenario: The user sees which step is running
- **WHEN** a table-level or source-level reset is executing
- **THEN** the UI displays a progress indicator naming the step currently in progress, and on
  failure displays that the reset was rolled back and nothing was changed

### Requirement: Unprofiled datasets render structural information only
For a dataset or source that has not been profiled — whether never profiled or reset — the UI SHALL
continue to show information obtained at onboarding (schema, tables, columns, data dictionary,
declared primary/foreign keys) and SHALL NOT show profiling-derived content as though it were
absent data.

#### Scenario: Profiling-derived UI reads as awaiting profiling
- **WHEN** a user opens an unprofiled source or dataset
- **THEN** stat cards, DQ grade and approval columns, and DQ Insights render blank or show an
  explicit "profile this dataset to see this" empty state rather than misleading zero values, while
  the structural information from onboarding remains visible

#### Scenario: The Data Model tab reflects what is actually known
- **WHEN** a user opens the Data Model tab for a dataset
- **THEN** relationships declared by the source are shown if the connector supplied them, inferred
  relationships are shown additionally only once the dataset has been profiled, and an empty state
  is shown when neither is available

### Requirement: Asset Workspace reset actions require confirmation
The Asset Workspace UI SHALL expose a destructive "Reset Profile" action at both the source level
and the dataset/table level, and SHALL require the user to confirm the action (via a warning
prompt) before it is executed.

#### Scenario: Table-level reset requires confirmation before executing
- **WHEN** a user selects the table-level "Reset Profile" action
- **THEN** a confirmation prompt is shown before any data is cleared, and the reset only proceeds
  if the user confirms

#### Scenario: Source-level reset warns about its larger scope before executing
- **WHEN** a user selects the source-level "Reset Profile" action
- **THEN** a confirmation prompt is shown that states how many tables will be reset, and the
  reset only proceeds if the user confirms

#### Scenario: A reset table/source visibly renders as pre-profiling afterward
- **WHEN** a table-level or source-level reset completes
- **THEN** the affected table(s) show no "Last profiled at" timestamp, no DQ score badge, an
  Interpretation tab back at its pre-governed default state, and no reference-set binding, so that
  triggering "Refresh Profile" or "Rebuild all profiles" afterward behaves as a first-ever
  profiling run

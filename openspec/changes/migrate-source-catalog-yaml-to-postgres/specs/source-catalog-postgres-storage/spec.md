## ADDED Requirements

### Requirement: Postgres catalog schema replaces YAML catalog storage
The system SHALL be able to persist source and target catalog schema and profiling metadata
(`catalog_source`, `catalog_dataset`, `catalog_element` tables) in Postgres, as an alternative to
`sources/generated/*.yaml` and `mappings/target_catalogs/*.yaml`, selected by the `catalog_backend`
configuration flag.

#### Scenario: Reading a catalog in Postgres mode matches YAML mode's shape
- **WHEN** `catalog_backend` is `postgres` and a caller reads a source's catalog
- **THEN** the returned schema/table/column structure has the same shape (fields and nesting) as
  the YAML-backed read for the same source's data

### Requirement: Backend flag gates catalog storage, default unchanged
The system SHALL select catalog storage via a `catalog_backend` flag (`yaml` or `postgres`),
defaulting to `yaml`, so behavior is unchanged until a user explicitly flips it.

#### Scenario: Default flag preserves existing YAML behavior
- **WHEN** `catalog_backend` is not set or set to `yaml`
- **THEN** catalog reads and writes behave exactly as before this change, with no Postgres
  dependency

#### Scenario: Flipped flag reads and writes via Postgres
- **WHEN** `catalog_backend` is set to `postgres`
- **THEN** catalog reads and writes go through the Postgres-backed repository instead of the YAML
  files

### Requirement: Single-table profile refresh updates only that table
In Postgres mode, refreshing one table's profile SHALL update only that table's `catalog_dataset`
row and its `catalog_element` rows, without rewriting or reprofiling any other table in the same
source.

#### Scenario: Refreshing one table leaves siblings untouched
- **WHEN** a table's profile is refreshed in Postgres mode
- **THEN** other tables belonging to the same source keep their existing `profiled_at` timestamp
  and stats unchanged

### Requirement: Annotation overlay continues to merge unchanged
The Postgres-backed catalog read path SHALL continue to merge `.annotations.yaml` overlays into
column and table descriptions using the same merge contract as `load_catalog_with_annotations`,
regardless of `catalog_backend`.

#### Scenario: Annotations still apply on top of a Postgres-backed catalog
- **WHEN** `catalog_backend` is `postgres` and an annotation exists for a table/column
- **THEN** the returned catalog data includes the annotation's `user_description`/
  `mapping_instructions` merged in, exactly as it would in `yaml` mode

### Requirement: Provenance is recorded per source and per table
Each `catalog_source` row SHALL record `connector_type` and an optional `connection_ref`; each
`catalog_dataset` row SHALL support an optional `origin_uri` and `ingested_at`, so future source
kinds (file upload, Azure Blob, other cloud databases) can be distinguished from today's
DB-connected sources without a schema change.

#### Scenario: A DB-connected source records its connector type
- **WHEN** a source catalog is built from a DuckDB connection
- **THEN** its `catalog_source` row's `connector_type` reflects that connection type, and its
  tables' `origin_uri`/`ingested_at` remain null (location is implied by the source's connection)

### Requirement: Table-level profiling status is tracked
Each `catalog_dataset` row SHALL carry a `profiling_status` of `discovered`, `profiled`, `failed`,
or `excluded`, distinguishing "known to exist" from "stats computed."

#### Scenario: A freshly profiled table is marked profiled
- **WHEN** a table completes a successful profile run
- **THEN** its `catalog_dataset.profiling_status` is `profiled`

### Requirement: Column structure supports nesting without affecting flat sources
`catalog_element` SHALL support representing nested or semi-structured fields via
`parent_element_id`, `qualified_column_name`, and `column_kind`, while columns from flat sources (CSV, relational,
plain Parquet) SHALL remain unaffected — top-level with no parent.

#### Scenario: A flat source's columns are all top-level
- **WHEN** a table is profiled from a flat, non-nested source
- **THEN** every one of its `catalog_element` rows has `parent_element_id` null and
  `column_kind` = `scalar`

### Requirement: Profile history is captured as append-only snapshots
On each profile refresh, the system SHALL append a snapshot row (`catalog_dataset_snapshot` /
`catalog_element_snapshot`) capturing the stats at that point in time, unless the stats are
unchanged from the previous snapshot (fingerprint match), and SHALL bound retention by pruning
older snapshots while always keeping the first (baseline) and the most recent entries.

#### Scenario: A changed profile appends a new snapshot
- **WHEN** a table is reprofiled and its stats differ from the last captured snapshot
- **THEN** a new snapshot row is appended reflecting the new stats

#### Scenario: A no-op refresh does not grow history
- **WHEN** a table is reprofiled and its stats are identical to the last captured snapshot
- **THEN** no new snapshot row is appended

#### Scenario: History retention prunes the middle, keeps first and latest
- **WHEN** the number of snapshots for a table exceeds the configured retention limit
- **THEN** the oldest (baseline) snapshot and the most recent snapshots are kept, and snapshots in
  between are pruned

### Requirement: Migration achieves parity with existing YAML catalogs
The system SHALL provide a migration path that loads existing `sources/generated/*.yaml` and
`mappings/target_catalogs/*.yaml` content into Postgres and verifies the migrated data reads back
identically to the original YAML.

#### Scenario: Migrated catalog reads back identically
- **WHEN** an existing source's YAML catalog is migrated into Postgres
- **THEN** reading that source in `postgres` mode returns schema, table, and column data
  equivalent to reading the original YAML file

### Requirement: Every refresh attempt is logged for precise historical lookups
The system SHALL record one `catalog_refresh_event` row per profile-refresh attempt on a dataset,
regardless of whether the resulting stats changed, so a historical snapshot can be located by
event count ("N refreshes ago") rather than only by calendar time.

#### Scenario: A no-op refresh still logs an event
- **WHEN** a table's profile is refreshed and none of its stats changed
- **THEN** a `catalog_refresh_event` row is still recorded for that refresh, even though no new
  `catalog_element_snapshot` rows were appended

#### Scenario: Locating the state N events ago
- **WHEN** a caller asks for a dataset's state as of its 3rd-most-recent refresh event
- **THEN** the system can resolve that event's timestamp from `catalog_refresh_event` and return
  each element's latest snapshot at or before that timestamp

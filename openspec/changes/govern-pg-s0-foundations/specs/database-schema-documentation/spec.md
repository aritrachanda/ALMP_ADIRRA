## ADDED Requirements

### Requirement: Every Postgres table and column SHALL carry a data-dictionary comment
Every table and every column in the application's Postgres database SHALL have a `COMMENT ON` description explaining, in plain language, what the table or column means and its purpose — not a restatement of its physical SQL type. This applies to every table already migrated (Glossary, Audit, Catalog, review/reference-lifecycle) and to every table added by any future migration.

#### Scenario: An existing table has a comment after the backfill migration
- **WHEN** a client queries Postgres's `pg_description` (e.g. via `obj_description`) for any table
  that existed before this change (e.g. `term`, `catalog_element`, `reference_code`,
  `audit_events`)
- **THEN** a non-null, non-empty comment describing the table's purpose is returned

#### Scenario: An existing column has a comment after the backfill migration
- **WHEN** a client queries `col_description` for any column on any table that existed before this
  change
- **THEN** a non-null, non-empty comment describing the column's meaning is returned

#### Scenario: A future migration is expected to add its own comments
- **WHEN** a new table or column is introduced by a migration authored after this change lands
- **THEN** that same migration SHALL include `COMMENT ON TABLE`/`COMMENT ON COLUMN` statements for
  every table/column it creates, as a standing convention (not automatically enforced by tooling,
  verified by review)

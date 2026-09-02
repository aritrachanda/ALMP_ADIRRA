## ADDED Requirements

### Requirement: Every reference code approval SHALL be historized as a point-in-time version
Each time a reference code's value or meaning is officially approved, the system SHALL be able to reproduce exactly what that code's value and meaning were as of any given past date, distinguishing periods with no officially approved value (gaps) from periods with one.

#### Scenario: A code's first-ever approval uses the business-effective sentinel date
- **WHEN** a reference code is approved for the very first time (no prior `reference_code_history` rows exist for it)
- **THEN** the current row's `valid_from` is set to the far-past sentinel date, not the approval's system timestamp

#### Scenario: Revoking an approved code closes its version with a real end date
- **WHEN** a steward revokes an approved reference code
- **THEN** the code's outgoing value/meaning is written into `reference_code_history` with `valid_to` set to the real revoke timestamp

#### Scenario: Re-approving after a revoke opens a new dated version, even with unchanged content
- **WHEN** a previously-revoked reference code is resubmitted and approved again, regardless of whether its value/meaning matches what it was before the revoke
- **THEN** the current row's `valid_from` is set to the real date of this new approval, not the sentinel and not the pre-revoke date

#### Scenario: A lookup for a date inside a revoked gap finds no approved value
- **WHEN** a caller asks what a reference code's value/meaning was as of a date that falls between a revoke and its next approval
- **THEN** the lookup returns "not found", not the pre-revoke value and not the post-re-approval value

#### Scenario: A lookup for a recent date is served from the current row
- **WHEN** a caller asks what a reference code's value/meaning was as of a date on or after the current row's `valid_from`
- **THEN** the lookup returns the current row's value/meaning without querying `reference_code_history`

#### Scenario: A lookup for an older date is served from history
- **WHEN** a caller asks what a reference code's value/meaning was as of a date before the current row's `valid_from`
- **THEN** the lookup returns the `reference_code_history` row whose `valid_from`/`valid_to` window covers that date, if one exists

### Requirement: Existing reference code reads SHALL remain unaffected by historization
Every existing `ReferenceCodeRepo` read method SHALL continue to return exactly one row per `(element_key, code)` — the current value only — with no code change required to exclude historical rows.

#### Scenario: The existing summaries read sees only current rows
- **WHEN** `ReferenceCodeRepo._build_summaries()` or any other existing read method runs after this change ships
- **THEN** it returns the same one-row-per-code shape as before, with no historical rows appearing in its result

### Requirement: Pre-existing reference codes SHALL be backfilled without fabricating history
Every reference code that existed before this change SHALL have its `valid_from` set to the business-effective sentinel date, and this backfill SHALL NOT create any `reference_code_history` rows.

#### Scenario: Backfill sets the sentinel with no history rows created
- **WHEN** the backfill migration runs against existing `reference_code` rows
- **THEN** every row's `valid_from` becomes the sentinel date
- **AND** `reference_code_history` remains empty as a direct result of the backfill

## ADDED Requirements

### Requirement: Governed reference set store

The system SHALL load reference sets from a governed YAML file
(`governance/reference_sets.yaml`). Each reference set MUST carry a stable `id`, a `name`, a `kind`
of `standard` or `local`, a `status`, and an `entries` list where each entry has a `code`, a
`meaning`, and a `status` of `active` or `deprecated`. Each set MAY carry an optional `standard_ref`
(e.g. `ISO 4217`) and each entry MAY carry optional `aliases`, `effective_from`, and `effective_to`
fields.

#### Scenario: Sets load from the governed file
- **WHEN** the reference set store is initialised
- **THEN** it returns every set defined in `governance/reference_sets.yaml` with its `id`, `name`,
  `kind`, `status`, and `entries`

#### Scenario: Seeded standard sets are present
- **WHEN** the store is loaded with the seeded file
- **THEN** it contains a `standard` set for ISO 4217 currency and a `standard` set for ISO 3166
  country, each with a representative subset of active entries

#### Scenario: Optional fields default safely
- **WHEN** a set or entry omits the optional `standard_ref`, `aliases`, `effective_from`, or
  `effective_to` fields
- **THEN** the store loads the set without error and treats the missing fields as unset

### Requirement: List reference sets endpoint

The system SHALL expose a read-only `GET /reference-sets` endpoint that returns all governed
reference sets.

#### Scenario: List returns seeded sets
- **WHEN** a client requests `GET /reference-sets`
- **THEN** the response includes the ISO 4217 and ISO 3166 seeded sets with their `id`, `name`,
  `kind`, and entry counts

### Requirement: Fetch a single reference set

The system SHALL expose a read-only `GET /reference-sets/{id}` endpoint that returns one reference
set including its full `entries` list.

#### Scenario: Fetch an existing set by id
- **WHEN** a client requests `GET /reference-sets/iso_4217_currency`
- **THEN** the response returns that set with all of its entries

#### Scenario: Unknown set id returns not found
- **WHEN** a client requests `GET /reference-sets/{id}` for an id that does not exist
- **THEN** the system responds with HTTP 404

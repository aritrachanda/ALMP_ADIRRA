## ADDED Requirements

### Requirement: Role-aware read gate on reference-data endpoints

The system SHALL apply a read-access check on the reference-data read endpoints
(`GET /reference-data`, `GET /reference-sets`, `GET /reference-sets/{id}`). The check reads an
optional `X-Role` header from the governed role vocabulary (`data_analyst`, `data_architect`,
`data_steward`, `business_user`). Any known role MUST be permitted, and a request with no role
header MUST be permitted as a default reader. A request that presents an explicitly unknown role
MUST be rejected with HTTP 403.

#### Scenario: Read allowed without a role header
- **WHEN** a client requests `GET /reference-data` with no `X-Role` header
- **THEN** the request succeeds (HTTP 200)

#### Scenario: Read allowed for any known role
- **WHEN** a client requests `GET /reference-sets` with `X-Role: business_user`
- **THEN** the request succeeds (HTTP 200)

#### Scenario: Unknown role is rejected
- **WHEN** a client requests `GET /reference-data` with `X-Role: intruder`
- **THEN** the system responds with HTTP 403

### Requirement: Reference-data read/update behaviour is covered by tests

The per-field reference-data endpoints SHALL have direct test coverage: `GET
/element/{source}/{table}/{column}/reference-data` returns the code list with `status`,
`bound_set_id`, and `set_kind` (resolving meanings from a bound set), and `PATCH` persists meanings
and status so a subsequent read reflects them.

#### Scenario: Per-field read reflects a bound set
- **WHEN** a field is bound to a reference set and its per-field reference-data is read
- **THEN** the response reports the `bound_set_id`, a `set_kind` from the set, and code meanings
  drawn from the set

#### Scenario: Per-field update persists meanings and status
- **WHEN** a client PATCHes meanings and a status for a coded field
- **THEN** a subsequent read of that field returns the updated meanings and status

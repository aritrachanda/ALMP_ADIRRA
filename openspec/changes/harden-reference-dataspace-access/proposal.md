## Why

The reference-data read endpoints (`GET /reference-data`, `GET /reference-sets`,
`GET /reference-sets/{id}`) ship with no access check — the Phase 0 discovery explicitly flagged
"no API authorization/permission gate exists" as a hardening gap. The app already defines a session
role vocabulary (`data_analyst`, `data_architect`, `data_steward`, `business_user`) but never
enforces it. This change adds a light, consistent read gate and closes the remaining reference-data
test gaps, without over-restricting reads.

## What Changes

- Add a reusable read-access dependency that accepts an optional `X-Role` header (mirroring the
  existing frontend role vocabulary). Reading is broadly allowed: any known role — and the
  no-header default — passes; only an explicitly **unknown** role is rejected with 403.
- Apply the gate to `GET /reference-data`, `GET /reference-sets`, and `GET /reference-sets/{id}`.
- Fill reference-data test gaps: the per-field `GET /element/{source}/{table}/{column}/reference-data`
  (codes, status, `bound_set_id`/`set_kind`, meanings resolved from a bound set) and the per-field
  `PATCH` meanings/status behaviour, plus the new gate (allow/deny) cases.
- Confirm no regressions across Asset Workspace, Review Workspace, and the existing per-field
  endpoint via the full suites.

## Capabilities

### New Capabilities
- `reference-data-access-control`: A light, role-aware read gate on the reference-data read
  endpoints that broadly allows reading and rejects only an explicitly unknown role.

### Modified Capabilities
<!-- The reference-data read/aggregate and per-field behaviours were introduced in earlier changes
     without requirement-level auth; this adds a new access-control capability rather than modifying
     an existing spec's requirements. -->

## Impact

- **Modified files**: `api/deps.py` (new `require_read_access` dependency + known-role set);
  `api/routes/reference_data.py` and `api/routes/reference_sets.py` (apply the dependency).
- **No frontend changes required**: the gate defaults to allow when no `X-Role` header is present,
  so the existing read-only store (which sends plain GET requests) keeps working unchanged.
- **Tests**: new coverage for the per-field GET/PATCH and the access gate.
- **Backwards compatible**: no existing client breaks; reads without a role header continue to work.

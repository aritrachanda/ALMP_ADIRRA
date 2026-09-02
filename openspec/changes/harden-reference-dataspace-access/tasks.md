## 1. Read-access gate

- [x] 1.1 Add a `KNOWN_ROLES` set and a `require_read_access` dependency to `api/deps.py` (optional `X-Role` header; default-allow; 403 only for an explicitly unknown role)
- [x] 1.2 Apply the dependency to `GET /reference-data` in `api/routes/reference_data.py`
- [x] 1.3 Apply the dependency to `GET /reference-sets` and `GET /reference-sets/{id}` in `api/routes/reference_sets.py`

## 2. Fill test gaps

- [x] 2.1 Test the per-field `GET /element/{source}/{table}/{column}/reference-data` (codes, status, `bound_set_id`/`set_kind`, meanings resolved from a bound set)
- [x] 2.2 Test the per-field `PATCH` persisting meanings and status (subsequent read reflects them)
- [x] 2.3 Test the read gate: no header → 200, known role → 200, unknown role → 403

## 3. Regression + acceptance

- [x] 3.1 Run the full backend suite (`pytest -q`) — no regressions in Asset Workspace, Review Workspace, or the per-field endpoint
- [x] 3.2 Run the full frontend suite (`npm --prefix frontend test`) — no regressions
- [x] 3.3 Walk the acceptance criteria and confirm each item is satisfied

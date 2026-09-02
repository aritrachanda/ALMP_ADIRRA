## ADDED Requirements

### Requirement: Postgres-backed routes SHALL return a clean 503 when the database is unreachable
Every API route family whose data is served by a Postgres-selectable backend flag (catalog routes today; every governance route added by later slices of the governance-migration plan) SHALL respond with HTTP `503` and an actionable message when its backend flag is set to `postgres` and the database is unreachable, instead of allowing a raw connection exception to propagate to the client. This mirrors the existing behavior already shipped for the Business Glossary and BIRD routes.

#### Scenario: A catalog route returns 503 when Postgres is down and catalog_backend is postgres
- **WHEN** `catalog_backend` is `postgres`, the database is unreachable, and a client requests any
  catalog-family endpoint (`/catalogs`, `/element/...`, `/insights/...`, `/semantic-types/...`,
  `/discovery/...`)
- **THEN** the API responds with HTTP `503` and a message that names the database as the cause and
  suggests how to bring it up (matching the wording style already used by the Glossary route's
  existing guard)

#### Scenario: A catalog route behaves unchanged when the backend flag is yaml
- **WHEN** `catalog_backend` is `yaml` (default)
- **THEN** the same catalog-family endpoints behave exactly as they did before this change, with no
  Postgres dependency and no new guard triggered

#### Scenario: A catalog route succeeds normally when Postgres is reachable
- **WHEN** `catalog_backend` is `postgres` and the database is reachable
- **THEN** the same catalog-family endpoints return their normal successful response, unaffected by
  the new guard

### Requirement: The 503 guard SHALL be one shared implementation reused across route families
The database-unreachable guard SHALL be implemented once, reusing the existing backend-agnostic health check (`core.glossary_db.db.health()`), and every covered route module SHALL call the same shared guard rather than each implementing its own duplicate check.

#### Scenario: Two different route families use the identical guard call
- **WHEN** the guard is invoked from `api/routes/catalogs.py` and from `api/routes/element.py`
- **THEN** both calls resolve to the same underlying shared helper function, not two independent
  implementations

## Why

There is currently no way to return a source or a single dataset/table to a genuine
pre-profiling baseline. Every dataset in the app has either never been profiled (rare, only
right after a raw onboarding) or has accumulated profile stats, a semantic-type assignment, a
DQ score, an Interpretation lifecycle state, reference-code review rows, and a reference-set
binding — with no supported way to clear all of that back to zero short of hand-deleting rows
across 7+ Postgres tables. That makes it impossible to see, demo, or test the "first ever
profiling run" experience (profiling + semantic resolution + DQ scoring kicking in from a truly
blank slate) on anything other than a freshly onboarded source nobody has touched yet.

## What Changes

- New backend orchestrator (`core/profile_reset.py`) that, given a source name (and optionally a
  single `schema.table`), wipes every profiling-derived and governance artifact for the affected
  column(s)/table(s) back to a pre-profiling baseline:
    - Catalog profiling stats (`catalog_db`/`CatalogDataset`/`CatalogElement`) — a pre-reset
    snapshot is captured, then only profiling-derived fields are nulled. Column names, data types,
    descriptions and declared PK/FK/relations are onboarding's output and are kept.
    - Semantic-type assignments (`semantic_type_repo`) — open history window closed, current row
    blanked (soft reset).
    - DQ scores (`dq_score_repo`) — set to `unscored` with reason `profile_reset`, reusing the
    existing window-closing path; history is retained, not deleted. Both column-level and the
    dataset-level rollup.
    - Element Interpretation lifecycle + content (`element_lifecycle_repo`,
    `element_content_repo`) — descriptions, business names, submission overlay, assessment scope
    reset to draft-default.
    - Reference Data per-code review (`reference_code_repo`) — codes revoked via the existing
    window-closing path; history retained.
    - Reference-set binding + its review lifecycle (`reference_set_repo`,
    `reference_binding_review_repo`) — binding cleared, review status deleted.
    - Catalog annotations (`annotation_repo`) — AI-drafted/user-edited table & column descriptions
    deleted.
    - One audit event logged per reset (append-only — the audit log itself is never purged, by
    this feature or by anything it triggers).
- New API endpoints in `api/routes/discovery.py`: `POST /discovery/{dataset}/reset`
  (source-level — every table under the source) and `POST /discovery/{dataset}/{table}/reset`
  (single dataset/table-level), alongside the existing `refresh`/`rebuild-all` endpoints.
- New Asset Workspace UI: a destructive "Reset Profile" action at both the source level and the
  dataset/table level, behind a confirmation modal mirroring the existing "Rebuild all profiles"
  warning-card pattern (source-level confirmation is the stronger of the two, given the larger
  blast radius). After a reset, the source/table renders as never-profiled (no "Last profiled
  at", no DQ badge, Interpretation tab back to draft, no reference binding) so that clicking
  "Refresh Profile" / "Rebuild all profiles" afterwards is genuinely a first-ever profiling run.
- **Postgres-only.** All affected stores are Postgres-backed today; this feature does not add a
  YAML-mode implementation for any of them — YAML is a legacy rollback path this change does not
  need to preserve.
- Test-only groundwork: a fixture/seeding script that fabricates a small dummy source (~10
  records in each affected store) so the reset flow can be exercised end-to-end without touching
  any real onboarded source.

## Capabilities

### New Capabilities
- `profile-reset`: source- and dataset/table-level ability to wipe all profiling-derived and
  governance state for a dataset back to a pre-profiling baseline, exposed via new API endpoints
  and an Asset Workspace UI action.

### Modified Capabilities
(none — this is purely additive; no existing capability's requirements change. The stores it
touches gain a new delete/clear operation each, but their existing read/write contracts are
unchanged.)

## Impact

- New: `core/profile_reset.py` (orchestrator), reset endpoints in `api/routes/discovery.py`,
  reset button + confirmation modal in `frontend/src/pages/AssetWorkspace.vue`, corresponding
  `frontend/src/api/discovery.ts` client functions.
- Modified (new bulk-clear method added, existing methods untouched): `core/catalog_db/repository.py`
  (or `core/catalog.py` dispatch layer), `core/semantic_type_repo.py`, `core/dq_score_repo.py`,
  `core/element_lifecycle_repo.py`, `core/element_content_repo.py`, `core/reference_code_repo.py`,
  `core/reference_set_repo.py`, `core/reference_binding_review_repo.py`, `core/annotation_repo.py`.
- New tests: `tests/test_profile_reset.py`, plus a dummy-source fixture/seeding helper (test-only,
  never touches a real project.yaml source).
- Audit: one new audit event type recorded per reset action; no changes to audit read paths and
  no purging capability added anywhere.
- Not touched: audit history itself, catalog schema extraction/connector logic, YAML/DuckDB
  legacy backend code paths (explicitly out of scope).

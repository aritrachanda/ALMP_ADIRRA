## Why

The Reference Dataspace already builds an `asset_link` for every field
(`/workspace?source=..&schema=..&table=..&column=..&tab=refdata`), but the Asset Workspace
ignores the query string entirely — it restores its last selection from `localStorage`. So the
"View in Asset Workspace →" link lands on the workspace but not on the intended field or tab, and a
selection cannot be shared or bookmarked.

## What Changes

- Make `AssetWorkspace.vue` honor a query contract: `source`, `schema`, `table`, `column`, `tab`.
- On mount, after sources/tables load, **parse and validate** the query, then drive
  `selectedSource`, `selectedTableSchema`, `selectedTable`, `selectedColumn`, and `activeTab`.
- Query params take **precedence** over the `localStorage` selection when a `source` param is
  present; otherwise the existing `localStorage` restore is used unchanged.
- Validate each level against loaded data (source ∈ sources, table ∈ tables, column ∈ table
  columns); on an invalid level, fall back to the deepest valid selection.
- Heal the legacy `tab=definition` value to `interpretation`, consistent with the existing restore.
- No change to the Reference Dataspace or the `asset_link` it already emits.

## Capabilities

### New Capabilities
- `asset-workspace-deep-link`: The Asset Workspace resolves a `source/schema/table/column/tab` query
  into its selection state, with validation, precedence over `localStorage`, and graceful fallback.

### Modified Capabilities
<!-- No existing OpenSpec spec defines the Asset Workspace selection/restore behaviour; this is
     introduced as a new capability. -->

## Impact

- **Modified files**: `frontend/src/pages/AssetWorkspace.vue` (add `useRoute`, a query-driven
  selection path in `onMounted`, and validation).
- **No backend changes**; the `asset_link` produced by `api/routes/reference_data.py` is unchanged
  and now resolves correctly.
- **Backwards compatible**: with no query params, behaviour is identical to today
  (`localStorage`-based restore).

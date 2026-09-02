## 1. Deep-link resolution helper

- [x] 1.1 Add `frontend/src/pages/assetWorkspaceDeepLink.ts` with `parseDeepLinkQuery(query)` (normalize source/schema/table/column/tab, heal `definition→interpretation`, accept only known tab keys)
- [x] 1.2 Add `resolveTableColumn(tables, table, schema, column)` returning the deepest valid level (`source` | `table` | `column`), matching `schema` when provided

## 2. Wire into AssetWorkspace

- [x] 2.1 Import `useRoute` and the helpers in `frontend/src/pages/AssetWorkspace.vue`
- [x] 2.2 Add `applySelectionFromQuery(parsed)` that sets `selectedSource`/`selectedTableSchema`/`selectedTable`/`selectedColumn`/`activeTab` and loads the deepest valid level (mirroring `restoreSelection`)
- [x] 2.3 In `onMounted`, after `loadSources()`, use the query path when `source` is present and valid; otherwise fall back to `restoreSelection()`

## 3. Tests

- [x] 3.1 `parseDeepLinkQuery`: full parse, tab healing, missing/array params, unknown tab
- [x] 3.2 `resolveTableColumn`: full valid → column; unknown column → table; unknown/absent table → source; schema matching
- [x] 3.3 Run frontend suite; confirm no regressions

## 4. Verify link-back

- [x] 4.1 Confirm the Phase 1 `asset_link` (`/workspace?source=..&schema=..&table=..&column=..&tab=refdata`) resolves to the field's Reference Data tab

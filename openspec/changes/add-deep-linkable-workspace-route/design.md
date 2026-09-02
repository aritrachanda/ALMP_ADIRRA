## Context

`AssetWorkspace.vue` holds its selection in local refs (`selectedSource`, `selectedTable`,
`selectedTableSchema`, `selectedColumn`, `viewMode`, `activeTab`). On mount it calls
`store.loadSources()` then `restoreSelection()`, which reads a `workspace_selection` object from
`localStorage` and reloads the corresponding source/table/column. Vue Router and Pinia are already
installed; `store.sources` is `string[]`, `store.tables` is `TableEntry[]` (each with `schema`,
`table_name`, and a `columns` array). The Reference Dataspace emits
`/workspace?source=..&schema=..&table=..&column=..&tab=refdata` but the page never reads
`route.query`.

## Goals / Non-Goals

**Goals:**
- Resolve a `source/schema/table/column/tab` query into the page's selection state.
- Give query params precedence over `localStorage` when `source` is present.
- Validate each level against loaded data and fall back gracefully on invalid input.
- Preserve today's `localStorage` behaviour exactly when no query is present.

**Non-Goals:**
- Continuously syncing selection back into the URL as the user navigates (one-way, on-load only).
- Adding a named route or route params; the existing `/workspace` path with a query string is kept.
- Changing the Reference Dataspace, the `asset_link` format, or any backend endpoint.

## Decisions

**D1 — Query is applied once, on mount, taking precedence over `localStorage`.**
In `onMounted`, after `store.loadSources()`, branch: if `route.query.source` is present, run a new
`applySelectionFromQuery()`; otherwise run the existing `restoreSelection()`. This is the minimal,
predictable contract ("a link wins over your last visit") and avoids fighting the existing
`saveSelection` watchers, which will persist the query-driven selection normally afterward.
*Alternative rejected:* merging query over localStorage field-by-field — more complex, ambiguous
precedence, and harder to reason about.

**D2 — Validate top-down against already-loaded data; fall back to the deepest valid level.**
Resolve `source` against `store.sources`; if invalid, fall back to `restoreSelection()`. After
`loadTables(source)`, resolve `table` against `store.tables` (matching `table_name`, and `schema`
when supplied); if invalid, stop at source view. Resolve `column` against that table's `columns`; if
invalid, stop at table view. This reuses the same load calls `restoreSelection` already makes and
never leaves the UI on a phantom selection. *Alternative rejected:* trusting params blindly like the
current restore — a bad link would spin on a non-existent element.

**D3 — Reuse the existing selection-setting sequence and tab-healing.**
Set the same refs and `viewMode` that `restoreSelection` sets, run the same parallel loads
(`loadElement` / `loadDatasetOverview` / `loadInsights` / `loadDataStory`), and apply the same
`definition → interpretation` tab heal. Keeps one behavioural path for "restore a deep selection",
differing only in the source of the values.

## Risks / Trade-offs

- **Schema ambiguity** → a link may omit `schema` or the table may exist under multiple schemas.
  *Mitigation:* match `table_name` + `schema` when `schema` is provided; otherwise match the first
  `table_name` — the same tolerance `_resolve_table_column` uses server-side.
- **Invalid `tab` value** → an unknown tab could select a non-existent panel. *Mitigation:* accept
  only known tab keys, heal `definition→interpretation`, and default to `profile`.
- **Race with `saveSelection` watchers** → applying the query mutates refs that trigger
  `saveSelection`. *Mitigation:* acceptable — persisting the query-driven selection to
  `localStorage` is the desired end state, matching how `restoreSelection` already behaves.

## Open Questions

- Should an invalid deep link surface a small toast ("field not found, showing source")? Assumed
  **no** for this phase — silent graceful fallback keeps scope minimal; can add later.

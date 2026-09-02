## Why

Today every coded field carries its own inline list of code meanings, keyed to that one
`source|schema|table|column`. Identical lists (e.g. ISO currency codes) are re-typed field by
field, with no shared source of truth, no way to see that ten fields all mean the same list, and no
concept of an official standard to measure a field against. This change introduces governed
**reference sets** as first-class, reusable objects a field can bind to — additive to the current
per-field model, not a replacement.

## What Changes

- Introduce a governed **reference set** object (`ReferenceSet`): stable `id`, `name`, `kind`
  (`standard` | `local`), optional `standard_ref` (e.g. `ISO 4217`), `status`, and `entries[]` of
  `{ code, meaning, status: active | deprecated }`. `aliases` and `effective_from` / `effective_to`
  are defined as **optional** fields for later use.
- Add a **binding**: a composite field key (`source|schema|table|column`) → `reference_set_id`,
  stored alongside the existing `ElementStateStore` overlays. A field keeps today's inline-list
  behavior **or** binds to a shared set — never both authoritative at once.
- **Seed two standard sets** to demonstrate: ISO 4217 currency and ISO 3166 country, each with a
  small representative subset (hand-authored, not externally fetched).
- Add **read-only endpoints** to list reference sets and fetch a single set.
- **Extend `GET /reference-data`**: when a field is bound, populate `bound_set_id` and `set_kind`
  from the binding and resolve `codes` from the bound set — still reconciled against observed source
  data (the existing `in_source` / `in_list` / `rogue` / `unused` logic).
- **Asset Workspace binding UI**: on a field's Reference Data tab, add a "Bind to reference set"
  action that lets an analyst pick a governed set, with a **suggestion** derived from the field's
  `semantic_type` (`currency_code` → ISO 4217, `country_code` → ISO 3166). Binding is an edit action
  and lives here, not in the read-only Dataspace.
- **Reference Dataspace "Browse by set" view**: a toggle alongside the default source-tree view.
  In set view each set is shown once with its entries and the fields bound to it ("used by N
  fields"), surfacing duplicate/consolidatable lists.

## Capabilities

### New Capabilities
- `reference-set-management`: A governed store of reusable reference sets (standard or local kind)
  with codes, meanings, and lifecycle, seeded with ISO 4217 and ISO 3166 subsets, exposed through
  read-only list and detail endpoints.
- `reference-set-binding`: Binding a source field to a governed reference set from the Asset
  Workspace with a semantic-type-driven suggestion, and resolving a bound field's codes from its set
  (reconciled against observed data) in the aggregate reference-data endpoint.
- `reference-dataspace-set-view`: A read-only "Browse by set" view in the Reference Dataspace that
  groups the register by reference set and shows which fields consume each set.

### Modified Capabilities
<!-- No existing OpenSpec spec defines the reference-data register or its aggregate endpoint; the
     Phase 1-2 work was built without a spec. All behavior here is introduced as new capabilities. -->

## Impact

- **New files**: `governance/reference_sets.yaml` (seeded standard sets), a reference-set store in
  `core/` (same pattern as `semantic_type_store.py` / `element_state.py`), and reference-set read
  routes (extending or beside `api/routes/reference_data.py`).
- **Modified files**: `api/routes/reference_data.py` (resolve `bound_set_id` / `set_kind` / bound
  `codes` for bound fields); `core/element_state.py` (persist the field→set binding overlay);
  `frontend/src/pages/AssetWorkspace.vue` (bind action + suggestion on the Reference Data tab);
  `frontend/src/pages/ReferenceDataPage.vue` and `referenceDataspaceDisplay.ts` (Browse-by-set
  toggle and grouping); `frontend/src/stores/referenceDataStore.ts` (load reference sets).
- **Persistence**: new `reference_sets.yaml` governed file plus a binding overlay in the existing
  element-state store; both survive profile refresh/rebuild.
- **Backwards compatible**: unbound fields behave exactly as today; `set_kind` / `bound_set_id`
  placeholders already present in the API response become populated only for bound fields.
- **LLM-agnostic**: the semantic-type-driven binding suggestion is a deterministic mapping, no
  provider-specific logic.

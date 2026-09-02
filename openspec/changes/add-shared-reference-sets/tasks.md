## 1. Reference set store and seed data

- [x] 1.1 Create `governance/reference_sets.yaml` with two seeded `standard` sets: `iso_4217_currency` and `iso_3166_country`, each with a representative subset of `active` entries (`code`, `meaning`, `status`) and a `standard_ref`
- [x] 1.2 Add `core/reference_set_store.py` (mirroring `core/semantic_type_store.py`) that loads and caches `reference_sets.yaml`, tolerating missing optional fields (`standard_ref`, `aliases`, `effective_from/to`)
- [x] 1.3 Wire the store into `api/deps.py` as a dependency provider

## 2. Reference set read endpoints

- [x] 2.1 Add `GET /reference-sets` (list all sets with id, name, kind, status, entry counts)
- [x] 2.2 Add `GET /reference-sets/{id}` (single set with full entries; 404 for unknown id)
- [x] 2.3 Register the routes in `api/main.py`

## 3. Field-to-set binding persistence

- [x] 3.1 Add `refdata_bound_set_id` overlay support to `core/element_state.py` (get/set/clear), keyed by `source|schema|table|column`, surviving re-profiling
- [x] 3.2 Add a PATCH action (extend the existing reference-data update route in `api/routes/element.py`) to set or clear a field's binding

## 4. Aggregate endpoint resolution

- [x] 4.1 In `api/routes/reference_data.py`, when a field has a binding, populate `bound_set_id` and `set_kind` from the bound set and resolve `codes[].meaning` from the set's entries
- [x] 4.2 Keep observed-data reconciliation (`share_pct`, `in_source`, `in_list`, `rogue`, `unused`) driven by source data; ensure unbound fields are byte-for-byte unchanged

## 5. Asset Workspace binding UI

- [x] 5.1 Add a "Bind to reference set" action on the Reference Data tab in `frontend/src/pages/AssetWorkspace.vue`, with an unbind option
- [x] 5.2 Load available sets (via `GET /reference-sets`) and add a deterministic semantic-type → set suggestion (`currency_code` → ISO 4217, `country_code` → ISO 3166)
- [x] 5.3 Call the binding PATCH action on confirm and refresh the field's resolved code list

## 6. Reference Dataspace "Browse by set" view

- [x] 6.1 Load reference sets into `frontend/src/stores/referenceDataStore.ts`
- [x] 6.2 Add a set-grouping helper in `frontend/src/pages/referenceDataspaceDisplay.ts` that joins sets with fields' `bound_set_id` to compute "used by N fields"
- [x] 6.3 Add a read-only "Browse by set" toggle to `frontend/src/pages/ReferenceDataPage.vue` (no create/edit/bind controls)

## 7. Tests

- [x] 7.1 Backend: reference-set store load + seeded sets present; `GET /reference-sets` and `/reference-sets/{id}` (incl. 404)
- [x] 7.2 Backend: binding persistence (set/clear, survives reprofile) and aggregate resolution (bound meanings + kind, rogue/unused, unbound unchanged)
- [x] 7.3 Frontend: semantic-type suggestion mapping; set-grouping/used-by helper; extend `reference-dataspace-display.test.ts` and store test
- [x] 7.4 Run full suites (`pytest -q`; `npm --prefix frontend test`) and confirm no regressions

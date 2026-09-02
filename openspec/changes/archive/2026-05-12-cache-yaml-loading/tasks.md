## 1. Create shared caching utility

- [x] 1.1 Create `core/yaml_cache.py` with a `load_yaml_cached(path)` function that wraps `yaml.safe_load` with `@st.cache_data` keyed on file path + `os.path.getmtime()`

## 2. Wire up caching in UI loading points

- [x] 2.1 Update `agents/mapping_agent.py` `load_catalog()` to use `load_yaml_cached()`
- [x] 2.2 Update `ui/pages/catalog.py` `_load_catalog()` to use `load_yaml_cached()`
- [x] 2.3 Update `ui/pages/mapping.py` `_load_mapping_yaml()` to use `load_yaml_cached()`
- [x] 2.4 Update `core/catalog_builder.py` `load_project()` to use `load_yaml_cached()`

## 3. Verify invalidation behavior

- [x] 3.1 Confirm that pages calling `st.rerun()` after YAML writes pick up fresh data (no stale cache)

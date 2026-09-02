## Why

The Streamlit UI feels sluggish during form interactions (selectbox changes, text inputs, toggles) because large YAML catalog files (bird.yaml at 1.7 MB, crdm.yaml at 1 MB) are re-parsed from disk on every Streamlit rerun. Since Streamlit reruns the entire page script on every widget interaction, users experience 400-800ms delays even when the underlying files haven't changed.

## What Changes

- Add mtime-based caching to all YAML loading functions in the UI layer so files are only re-parsed when they actually change on disk
- Wrap `load_catalog()`, `load_project()`, and mapping YAML loaders with `@st.cache_data` keyed on file path + `os.path.getmtime()`
- During typical form-filling interactions (where YAML is unchanged), loading drops from ~400ms to <1ms
- After saves that modify YAML files, the next rerun detects the new mtime and re-parses automatically — no stale data

## Capabilities

### New Capabilities
- `yaml-caching`: Mtime-based caching layer for YAML file loading in the Streamlit UI, ensuring files are parsed only when modified

### Modified Capabilities
<!-- None — no existing specs to modify -->

## Impact

- **Code affected**: `ui/pages/catalog.py`, `ui/pages/discovery.py`, `ui/pages/mapping.py`, `agents/mapping_agent.py`, `core/catalog_builder.py`
- **Dependencies**: No new dependencies (uses built-in `os.path.getmtime` and existing `st.cache_data`)
- **Risk**: Minimal — caching is invalidated automatically by filesystem mtime; no possibility of stale data as long as writes happen before `st.rerun()`

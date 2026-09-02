## Context

The Streamlit UI loads YAML catalogs (up to 1.7 MB) on every page rerun. Streamlit reruns the full page script on every widget interaction. Currently no caching exists on YAML loading functions — only the initial catalog *building* step (DB extraction) is cached via `@st.cache_resource`.

Key loading sites:
- `agents/mapping_agent.py` → `load_catalog()` — called for source + target on mapping page
- `ui/pages/catalog.py` → `_load_catalog()` — called for selected catalog
- `ui/pages/discovery.py` → imports `load_catalog` from mapping_agent
- `ui/pages/mapping.py` → imports `load_catalog` from mapping_agent + `_load_mapping_yaml()`
- `core/catalog_builder.py` → `load_project()` — called on every page

## Goals / Non-Goals

**Goals:**
- Eliminate redundant YAML parsing during form-filling interactions (where files are unchanged)
- Automatically invalidate cache when files are modified (no stale data)
- Minimal code change — decorator-based, no architectural restructuring

**Non-Goals:**
- Changing the YAML file format or switching to a binary serialization format
- Adding a manual "refresh" button or cache management UI
- Optimizing the initial catalog building step (already cached)
- Partial/lazy loading of catalog subsets

## Decisions

### 1. Use `@st.cache_data` with `os.path.getmtime()` as cache key

**Rationale:** `st.cache_data` is Streamlit's built-in caching for serializable data. By including the file's mtime in the function signature, the cache auto-invalidates when the file is written to. No TTL needed — invalidation is precise.

**Alternatives considered:**
- `@st.cache_data(ttl=N)` — simpler but risks stale data during demos where files are actively edited
- `@st.cache_resource` — doesn't deep-copy on return; mutations could corrupt cache
- Session-state manual cache — more boilerplate, same effect
- Pre-serialized binary format (msgpack/pickle) — fastest load but adds build complexity, overkill for demo app

### 2. Create a shared `core/yaml_cache.py` utility

**Rationale:** Multiple modules need cached YAML loading. A single utility avoids duplicating the cache decorator pattern across 4-5 files and ensures consistent behavior.

### 3. Keep `os.path.getmtime()` over content hashing

**Rationale:** `getmtime()` is a single stat syscall (~0.01ms). Content hashing a 1.7 MB file would take ~5ms — still fast but unnecessary since mtime reliably changes on write in all relevant scenarios (local dev, demo environments).

## Risks / Trade-offs

- **[Risk] mtime doesn't change if file is written with same content** → Acceptable; in practice this means the data IS the same, so serving "stale" cache is correct.
- **[Risk] Cache persists across Streamlit sessions** → `st.cache_data` is scoped to the Streamlit server process. A server restart clears it. This is fine for a demo app.
- **[Risk] Write + immediate render without `st.rerun()`** → If a page writes YAML and continues rendering without rerunning, the cached value from earlier in the same run will be used. Mitigation: ensure `st.rerun()` is called after writes (already the pattern in existing code).

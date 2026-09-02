## ADDED Requirements

### Requirement: YAML files are cached based on filesystem modification time
The system SHALL cache parsed YAML file contents in memory and serve the cached version on subsequent loads when the file's modification time has not changed.

#### Scenario: Repeated loads without file change
- **WHEN** a YAML file is loaded multiple times without being modified on disk
- **THEN** the file SHALL be parsed from disk only on the first load; subsequent loads SHALL return the cached in-memory result

#### Scenario: File is modified between loads
- **WHEN** a YAML file is modified on disk (mtime changes) and then loaded again
- **THEN** the system SHALL re-parse the file from disk and update the cache

### Requirement: All UI YAML loading points use the cache
The system SHALL route all YAML loading in the UI layer through the caching mechanism. This includes catalog loading, project config loading, and mapping result loading.

#### Scenario: Catalog page loads cached catalog
- **WHEN** the user navigates to the catalog page and interacts with widgets
- **THEN** the catalog YAML SHALL be served from cache if the file has not changed since last parse

#### Scenario: Mapping page loads cached source and target
- **WHEN** the mapping page loads source and target catalogs
- **THEN** both YAML files SHALL be served from cache if their mtimes have not changed

#### Scenario: Project config is cached
- **WHEN** `load_project()` is called on any page rerun
- **THEN** the project.yaml SHALL be served from cache if its mtime has not changed

### Requirement: Cache invalidates immediately on file write
The system SHALL detect file modifications via `os.path.getmtime()` and invalidate the cache entry for that file on the next load after a write.

#### Scenario: User saves mapping and page reruns
- **WHEN** the application writes a new mapping YAML and triggers `st.rerun()`
- **THEN** the next load of that file SHALL return the freshly written content, not stale cached data

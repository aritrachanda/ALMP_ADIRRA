## Why

In short: our source catalog (the schema + profiling stats for every connected data source) lives
in one giant YAML file per source, and that's causing real, measurable problems.

- ALM Bank's catalog file alone is 3.5MB.
- Refreshing the profile for a **single table** rewrites the **entire file** — not just that
  table's part.
- Every column is stored **twice** inside the file (once in a nested tree, once again in a flat
  list kept purely for quick lookup).
- This file sits directly behind two of the busiest Data Governance pages (Discovery, Data
  Catalog) — pages we're actively trying to make less dependent on Data Governance's own YAML
  habits.

Moving this to Postgres fixes the storage and rewrite problems today. If we design the schema
correctly now, it also prepares us for onboarding data in new ways later — file uploads, Azure
Blob, other cloud databases, nested JSON/XML — without needing to redo this migration a second
time.

## What Changes

- **New Postgres tables** (`catalog_source`, `catalog_dataset`, `catalog_element`) become the real
  home for source & target schema/profiling data, replacing the YAML files once we cut over. Each
  table's identity column is named for what it represents (`source_id`, `dataset_id`,
  `element_id`) so the same `element_id` can later be reused as the shared join key once
  governance data (business name, semantic type, lifecycle) links in — see D1/D7 in `design.md`.
- **A handful of "future-ready" columns**, added now because they're cheap now and expensive
  later: which connector/source kind a row came from, when a file/table was ingested, whether
  it's been profiled yet, a fingerprint to detect changes, which legal entity/business unit it
  belongs to, size/volume info, and a catch-all for file-format quirks.
- **The column table is a tree, not just a flat list** — so later we can profile nested data like
  JSON/XML/Parquet structs without another migration. Today's flat sources (CSV, databases, plain
  Parquet) are completely unaffected.
- **A simple history log** (append-only snapshots, plus a lightweight refresh-event log so a
  historical snapshot can be located precisely by "N refreshes ago", not just by calendar date)
  so we can look back at how a table's stats changed over time — without slowing down everyday
  reads.
- **A flag turns this on**: `catalog_backend: yaml | postgres`, defaulting to `yaml` — nothing
  changes until it's explicitly flipped. Same safe pattern already proven by the Business Glossary
  move.
- **NOT included in this change**:
  - `.annotations.yaml` (user/AI descriptions) stays YAML for now — that's part of the separately
    tracked Data Governance migration list.
  - Building the actual nested-data profiling logic.
  - Letting users write custom data-quality rules.
  - Updating Data Governance stores (DQ scores, semantic types, glossary, element states) to use
    the new catalog's IDs.
  - This proposal only builds the **schema and storage** — it does not change what the app *does*
    with the data.

## Capabilities

### New Capabilities
- `source-catalog-postgres-storage`: Postgres-backed storage for source/target catalog schema and
  profiling metadata (current tables + append-only history snapshots), replacing
  `sources/generated/*.yaml` and `mappings/target_catalogs/*.yaml` as the live store, behind a
  backend flag, with the read/write contract designed to accommodate future source kinds and
  nested/semi-structured data without a further schema change.

### Modified Capabilities
<!-- source-metadata-extraction (connector comment extraction) and annotation-overlay (YAML
     description overlay) are unaffected: extraction still produces the same canonical
     schema+stats shape, and annotations stay YAML and merge the same way — just against a new
     underlying catalog store instead of a YAML file. No requirement-level behavior changes for
     either existing spec. -->

## Impact

- **New**: `db/migrations/` (Alembic) for the new tables; a `core/catalog_db/` repository layer
  (same pattern as the existing `core/glossary_db/`).
- **Changed, at cutover only**: every current YAML catalog reader/writer —
  `core/catalog_builder.py`, `core/catalog.py`, `api/routes/discovery.py`,
  `api/routes/catalogs.py`, `api/routes/element.py`, `api/semantic_types.py`,
  `api/routes/insights.py` — repoints behind the flag; none of their public behavior changes.
- **No frontend changes required** until cutover — API responses stay the same shape.
- **Tests**: new repository-level tests (Postgres-gated), plus a migration/parity script that
  checks Postgres output against YAML output before anything is flipped live.
- This is a large effort, similar in shape to the Business Glossary v1→v2 migration. This
  proposal is the **design** step. Implementation happens in reviewable phases (see `tasks.md`),
  not all at once.

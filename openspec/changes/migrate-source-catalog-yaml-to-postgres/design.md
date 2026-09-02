## Context

Today, one YAML file per source (`sources/generated/*.yaml`) holds everything — schema and
profiling stats — for that source. ALM Bank's is 3.5MB. It's read through
`core/catalog.py::load_catalog_with_annotations_cached` (parses the whole file, cached by file
modified-time) and written through two places: `core/catalog_builder.py::save_catalog` (full
rebuild) and `api/routes/discovery.py::_writeback_table_profile` (single-table refresh — but it
still rewrites the whole file). The same shape is reused for target catalogs
(`mappings/target_catalogs/bird.yaml` / `crdm.yaml`). Every column appears twice inside the file:
once nested under `schemas -> tables -> columns`, once again in a flat list for quick lookup.

Alongside each catalog file sits a `.annotations.yaml` overlay (user/AI descriptions, mapping
instructions), merged in at read time. **That overlay is out of scope for this change** (see
`proposal.md`) — it stays YAML, and whatever we build here must keep merging with it exactly as
today.

**Who reads/writes this today:** Discovery, Data Catalog, and Asset Workspace all read it; profile
refresh and catalog rebuild both write it.

**Our precedent:** the Business Glossary migration already proved how we move a YAML store to
Postgres in this codebase — build the new schema, gate it behind a flag (default stays legacy),
migrate the real data with a parity check, and only flip the flag once the user has validated it.
We're following the same playbook here.

## Goals / Non-Goals

**Goals**
- Stop rewriting the whole file when only one table's profile changes, and stop storing every
  column twice.
- Design the schema so future source kinds (file upload, Azure Blob, other cloud databases) and
  nested formats (JSON, XML, Parquet structs) fit in later, without a second migration — even
  though we're not building any of that yet.
- Keep the shape of what callers read today, so cutover is a backend swap, not a frontend rewrite.
- Keep the "annotations survive a profile rebuild" guarantee exactly as it works today.

**Non-Goals**
- Not building nested-data profiling logic, a custom data-quality rule engine, or new connectors
  (CSV/JSON/XML upload, Azure Blob, other cloud databases) — schema only, nothing functional.
- Not moving `.annotations.yaml` to Postgres — that's tracked separately.
- Not repointing Data Governance stores (DQ scores, semantic types, glossary links, element
  lifecycle) to use the new catalog's numeric IDs — a follow-on decision, not part of this change.
- Not locking in history-table-vs-SCD2 in code yet — a direction is recommended below, but it's
  still open for sign-off.

## Decisions

Quick-reference summary — full reasoning for each is below.

| # | Decision | In one line |
|---|---|---|
| D1 | Three core tables | `catalog_source` → `catalog_dataset` → `catalog_element`, mirrors what we already produce today |
| D2 | JSONB for PK/FK/relations/sample values | Always used as one block today; not worth normalizing yet |
| D3 | Provenance columns | Record which connector/source kind produced each row |
| D4 | `profiling_status` | Separates "we know it exists" from "we've profiled it" |
| D5 | `content_hash` / `source_modified_at` | Lets us skip reprofiling unchanged files later |
| D6 | `legal_entity`, volume, format-hint columns | Cheap now, expensive to retrofit later |
| D7 | Tree-shaped columns | Supports nested/semi-structured data later, no effect on flat sources today |
| D8 | Append-only snapshots, not SCD2 | Keeps every hot-path read fast; matches an existing pattern in this codebase |
| D9 | Flag-gated cutover | Same safe pattern as the Business Glossary migration |
| D10 | Refresh-event log | Gives an authoritative timeline so "N events ago" lookups work despite per-column dedupe |

### D1 — Three core tables
```
catalog_source (source_id, source_name, kind 'source'|'target', connector_type, connection_ref,
  version, schema_hash, generated_at)
catalog_dataset (dataset_id, source_id FK, schema_name, table_name, description, row_count,
  row_count_error, primary_key JSONB, inferred_primary_key JSONB, foreign_keys JSONB,
  relations JSONB, duplicate_count, duplicate_pct, orphan_fk_count, completeness_summary,
  pct_columns_described, profiled_at)
catalog_element (element_id, dataset_id FK, column_name, ordinal, data_type, description,
  row_count, null_count, null_pct, distinct_count, duplicate_count, uniqueness_pct,
  empty_string_count, placeholder_count, min_value, max_value, length_min, length_max,
  length_avg, inferred_pattern, pattern_confidence, invalid_format_count, code_values JSONB,
  value_distribution JSONB, numeric_avg, numeric_median, numeric_stddev, numeric_outlier_count,
  outlier_detection, decimal_scale_distribution JSONB, future_date_count,
  suspicious_date_count, type_mismatch_count, validator_pass_rates JSONB,
  constant_run_warning JSONB, stats_error, sample_values JSONB, top_values JSONB)
UNIQUE (source_id, schema_name, table_name) on catalog_dataset
UNIQUE (dataset_id, column_name) on catalog_element
INDEX (source_id, schema_name, table_name), INDEX (dataset_id)
```
Identity columns are named for what they represent (`source_id`/`dataset_id`/`element_id`), not
generically `id` — `element_id` in particular is the anticipated shared key for the future
governance join (see D7's boundary note and the Open Questions entry below). `catalog_dataset`'s
and `catalog_element`'s field lists mirror the full profiler output
(`core/extractors/profiler.py`, table- and column-level) exactly — including derived/validation
results like `orphan_fk_count` (a real anti-join check for FK values with no matching parent row,
not something the `foreign_keys`/`relations` JSONB declarations alone provide), the
load-bearing `validator_pass_rates` (consumed directly by `semantic_resolver.py` and
`dq_scorer.py` — not just a display stat), and the diagnostic `stats_error`/`row_count_error`
fields the profiler writes when a computation fails — every stat the profiler already computes
gets a column, nothing summarized away.
**Why this shape:** it mirrors the `schemas -> tables -> columns` structure our extraction code
already produces, so the extraction logic barely changes — only how it gets saved changes.
**Alternative considered:** one giant flat table (source+table+column all in one row, no
relationships). Rejected — it can't cheaply hold table-level facts (row count, primary key)
without repeating them on every single column row.

### D2 — Keep PK/FK/relations and sample/top values as JSONB, don't fully break them into tables
Every place that reads or writes these today treats them as one whole block — nobody queries "just
one foreign key" on its own. Splitting them into their own tables would add 2-3 more tables for no
real benefit right now. **Flagged for your review:** if we ever need to query FKs individually
(e.g. "show every orphan FK across a source"), this is the piece to revisit.

### D3 — Record where each row came from
New fields: `catalog_source.connector_type`/`connection_ref`, `catalog_dataset.origin_uri`/
`ingested_at`. We already support multiple connector types today (DuckDB, YAML, Excel)
producing the same output shape — a brand new source kind (CSV/JSON/XML upload, Azure Blob,
another cloud database) just needs a new connector, not a schema change. These fields exist purely
so we can always answer "where did this table actually come from," which matters once a "source"
isn't always one single named database connection.

### D4 — Track whether a table has actually been profiled
New field: `catalog_dataset.profiling_status` (`discovered | profiled | failed | excluded`). Today,
finding a table and profiling it happen in one step. Once we're onboarding from large blob
storage or big cloud databases, those become two separate steps — "we know it's there" arrives
long before "we've computed its stats." This field is ready for that split.

### D5 — Detect when a specific file/table actually changed
New fields: `catalog_dataset.content_hash` + `source_modified_at`. We already have a `schema_hash` at
the whole-source level ("did anything in this source change"). This is finer-grained — "did THIS
one file/table change" — so a future profiler can skip reprofiling anything that hasn't changed.
Matters a lot once we're profiling real-volume blob storage instead of a small demo file.

### D6 — A few more cheap, future-facing fields
`catalog_source.legal_entity` (mirrors the `legal_entity` field the audit system already has),
plus `catalog_dataset.size_bytes`/`file_count`, and a catch-all `format_hint` JSONB field for file
quirks (delimiter, encoding, date format). All nullable, all free to carry until we actually need
them — expensive to bolt on after the fact.

### D7 — Let columns nest, for future JSON/XML/Parquet support
New fields on `catalog_element`: `parent_element_id` (points to a parent element, null = top-level),
`qualified_column_name` (e.g. `address.city`, `items[].sku`), `column_kind` (`scalar | object | array |
array_of_object`), `nesting_level`, `type_distribution` (e.g. a field that's 82% string, 12% null,
6% number — `data_type` still shows the single dominant type so nothing existing changes), and
array-length stats.
- **Flat sources (CSV, databases, plain Parquet) are entirely unaffected** — none of these new
  fields ever get populated for them.
- A field holding many simple values (e.g. `tags: [...]`) is just one row with array-length stats.
- A field holding many sub-objects (e.g. `line_items: [{...}]`) is a parent row with a child row
  per nested field.
- All the usual stats (distinct values, top values, etc.) get computed by flattening across every
  element in every record — the standard approach.
- **One rule to keep straight**: "this record has no value for this field" and "one entry inside
  this field's array is null" are two *different* facts and must never get mixed up.
- **A real boundary, not solved by any schema**: this only works when the data has *some* repeating
  shape (JSON Lines, arrays of objects, repeating XML elements). A one-off, freeform, deeply
  nested document with no repetition has no "row" concept at all — that's a different kind of
  problem (a document catalog, not a column profiler), and it's out of scope here.

### D8 — Keep a history of changes as a separate, append-only log
```
catalog_dataset_snapshot (id, dataset_id FK, captured_at, fingerprint, <frozen copy of catalog_dataset fields>)
catalog_element_snapshot (id, element_id FK, captured_at, fingerprint, <frozen copy of catalog_element fields>)
```
The "current" tables (`catalog_dataset`/`catalog_element`) always describe *right now* — nothing
extra to filter on every read. Every profile refresh adds one snapshot row, unless nothing
actually changed (skipped, using a fingerprint check), and old snapshots get pruned over time
while always keeping the very first one and the most recent ones. This is the exact pattern
`core/dq_score_store.py` already uses in this codebase — reusing an existing convention instead of
inventing a new one.
**Alternative considered**: the classic "SCD2" pattern (adding `valid_from`/`valid_to`/`is_current`
directly onto the live rows). Rejected as the default because it would force every single
everyday read across Discovery/Catalog/Asset Workspace to filter on `is_current`.
**Flagged for your sign-off**: this is a judgment call, not a hard requirement — worth confirming
before we build it.

### D9 — Turn it on with a flag, same as the Glossary migration
`catalog_backend: yaml | postgres` in `project.yaml`, defaulting to `yaml`. Build the schema first,
build a repository layer that reads the same shape as today, migrate the real data with a parity
check, and only the user flips the flag once they've validated it. The old YAML stays in place as
a safety net until it's explicitly retired later.

### D10 — A refresh-event log, for precise "N events ago" lookups
```
catalog_refresh_event (id, dataset_id FK, refreshed_at, triggered_by, changed BOOLEAN)
```
One row per refresh **attempt** for a dataset, always — whether or not the resulting stats
actually changed. This solves a real gap in D8: because snapshots are skipped when nothing
changed, different columns accumulate snapshots at different rates, so "the 3rd most recent
snapshot row" means something different per column. This log gives one authoritative timeline:
to find "N events ago," look up the Nth-most-recent row here for its exact timestamp, then pull
"the latest snapshot at or before that timestamp" per dataset/element — a standard point-in-time
lookup, not a per-column row count. Small and cheap: one narrow row per refresh call, independent
of how many columns the dataset has.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| Tree-shaped columns add complexity even though every source today is flat | `parent_element_id IS NULL` is always true today — zero behavior change, just unused fields until nested sources exist |
| JSONB for PK/FK/relations gives up relational queryability | Nothing needs it today; explicitly flagged as reversible (D2) |
| Two history tables double the writes on every profile refresh | Fingerprint-based dedupe skips no-op refreshes; retention caps growth |
| One more small table + one write per refresh attempt (`catalog_refresh_event`) | Tiny fixed-width row, independent of dataset size — cheap |
| Large, multi-phase migration effort (same shape as the Glossary move) | Phased, flag-gated, non-breaking rollout — no forced timeline |
| Future-readiness columns sit unused until new source kinds exist | Accepted on purpose — cheap now, expensive later, already agreed with you |

## Migration Plan

Same shape as the Business Glossary v1→v2 migration, done in reviewable phases, not all at once:

1. **Schema** — Alembic migration for all 6 tables (3 current + 2 history + 1 refresh-event log),
   purely additive.
2. **Repository layer** — new `core/catalog_db/` reading the same shape as
   `load_catalog_with_annotations`, so callers barely notice.
3. **Flag wiring** — `catalog_backend` in `project.yaml`, default `yaml`, behavior unchanged until
   flipped.
4. **Migration + parity script** — load every existing YAML catalog into Postgres, verify it reads
   back identically.
5. **Repoint readers/writers** — behind the flag, contract unchanged, across all the files listed
   in `proposal.md`'s Impact section.
6. **User validation** — manual check across Discovery/Catalog/Asset Workspace on Postgres.
7. **Flag flip** — the user explicitly switches to `postgres`; YAML stays as the rollback path.

**Rollback:** flip the flag back to `yaml` at any point before the old files are deleted — same
safety net the Glossary migration still keeps today.

## Open Questions

- **D2** (JSONB vs separate tables for PK/FK/relations) — **CONFIRMED 2026-08-05**: proceed with
  JSONB for now; revisit normalization post-cutover only if a real need to query these
  individually shows up.
- **D8** (history as snapshots vs classic SCD2) — **CONFIRMED 2026-08-05**: proceed with the
  snapshot-table approach for now; revisit post-cutover if needed.
- **When to repoint Data Governance stores** (DQ scores, semantic types, glossary links, element
  lifecycle) to use `catalog_element.element_id` instead of their current string composite key —
  you've confirmed this should happen "whenever the time is right," just not decided when yet. The
  identity column is deliberately named `element_id` now (D1/D7) specifically so that future join
  is a natural fit rather than reaching into an anonymous numeric PK.
  **Standing reminder**: bring this up again whenever this migration is greenlit, and whenever any
  Data Governance store migration is next discussed (see
  `/memories/repo/source-catalog-postgres-design.md`).
- **Whether/when to store the actual profiling logic itself** (not just the resulting numbers) —
  the groundwork for future user-defined data-quality rules. You've explicitly parked this for
  later; the only thing worth keeping in mind when this schema actually gets built is a
  `profiler_version` tag, mirroring the existing `RESOLVER_VERSION` pattern in
  `core/semantic_resolver.py`.
- **`value_distribution`** is carried in `catalog_element` (JSONB, nullable) but the profiler never
  actually computes it today — it's `null` in every real catalog file that exists right now.
  Decision: keep the column and populate it as `NULL` for now; do **not** drop it. Properly
  implementing it later (most likely a full value-frequency histogram for categorical columns, or
  a bucketed histogram for numeric/date columns that captures the *shape* of the distribution —
  something the existing single-number `numeric_avg`/`numeric_median`/`numeric_stddev` fields can't
  show) is profiler-**engine** work, out of scope for this storage migration. Flagged explicitly so
  it isn't quietly forgotten — revisit when profiling-engine improvements are next picked up.
- **`constant_run_warning`** is carried in `catalog_element` (JSONB, nullable) for the exact same
  reason as `value_distribution` — `dq_scorer.py` reads it defensively but nothing anywhere in the
  codebase (not even real generated catalogs) ever sets it. Same decision: keep, populate `NULL`
  for now, implement properly later as profiler-engine work.
- **Read-side materialization (a flattened/dimensional fact table)** — deliberately NOT built now.
  The normalized tables' read patterns (one dataset's elements, one source's datasets) are simple
  indexed lookups at a small real scale (~715 columns for our biggest source today), so there's no
  measured problem to solve yet. Plan: once this migration is implemented, measure real read/write
  performance against the YAML baseline (evidence, not speculation) as part of user validation.
  Revisit specifically when governance data (lifecycle, semantic type, DQ score) also migrates to
  Postgres and joins in via `element_id` (see the governance-ID reminder above) — that's when a
  lightweight dimensional fact table (flattening source+dataset+element+governance together for
  the Asset Workspace's aggregate charts) becomes the natural next step, built incrementally then,
  not speculatively now.

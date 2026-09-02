## Why

The CRR agent's `generate_batch()` currently reads column names from source/target catalogs and searches CRR3 for regulatory context. Column names are cryptic abbreviations (e.g., `EXPSR_VL`, `DFLT_STTS`) that rarely match regulation text. The glossary already contains human-readable titles and descriptions — using these as search input will produce far better CRR3 matches.

## What Changes

- **Replace** the batch input source: read glossary terms (title, business_description, detailed_description) instead of catalog columns
- **Improve** search quality by constructing queries from the term's title and descriptions rather than underscore-split column names
- **Remove** the catalog-reading logic from `generate_batch()` (catalog enrichment is no longer needed)
- Update `generate_batch()` signature to accept optional filters (domain, category) instead of catalog_name/schema_name

## Capabilities

### New Capabilities
- `glossary-enrichment`: CRR agent reads glossary items and enriches them with regulatory context using their title and descriptions as search input

### Modified Capabilities

(none)

## Impact

- `agents/crr_agent.py` — `generate_batch()` rewritten to iterate glossary terms
- `core/glossary.py` — no changes (existing `iter_terms()` / `upsert_term()` already sufficient)
- CLI interface (`--catalog` / `--schema` args) replaced with `--domain` / `--category` filters

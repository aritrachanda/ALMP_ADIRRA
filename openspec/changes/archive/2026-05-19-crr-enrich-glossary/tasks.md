## 1. Load glossary terms

- [x] 1.1 Add `_load_glossary_terms()` helper that reads `glossary/glossary.yaml` and returns list of term dicts (title, business_description, detailed_description, domain, category)
- [x] 1.2 Support optional domain/category filtering in the helper

## 2. Rewrite generate_batch

- [x] 2.1 Change `generate_batch()` signature to `generate_batch(domain=None, category=None, force=False)`
- [x] 2.2 Replace catalog-reading logic with `_load_glossary_terms()` call
- [x] 2.3 Build search query as `"{title}. {business_description}"` (title-only fallback if description empty)
- [x] 2.4 Pass title + business_description + detailed_description to LLM prompt
- [x] 2.5 Skip terms that already have non-empty `regulatory_context` (unless `force=True`)
- [x] 2.6 Upsert enriched `regulatory_context` back into glossary and save

## 3. Update CLI

- [x] 3.1 Replace `--catalog`/`--schema` args with `--domain`, `--category`, `--force`
- [x] 3.2 Wire new args to updated `generate_batch()` call

## 4. Verify

- [x] 4.1 Run batch enrichment on glossary and confirm terms get `regulatory_context` populated

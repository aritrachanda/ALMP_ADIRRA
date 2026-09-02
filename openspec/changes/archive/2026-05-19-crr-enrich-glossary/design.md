## Context

`generate_batch()` in `agents/crr_agent.py` currently accepts a catalog name, loads the catalog YAML, iterates column names, replaces underscores with spaces, and uses that as the CRR3 search query. This produces poor results because abbreviated column names (e.g., `PRBBLT_DFLT` → "PRBBLT DFLT") don't resemble the language used in the regulation.

The glossary (`glossary/glossary.yaml`) already contains well-written titles and descriptions for each business term. These provide much richer search queries for the CRR3 FAISS index.

## Goals / Non-Goals

**Goals:**
- Use glossary term titles + descriptions as CRR3 search input
- Produce higher-quality `regulatory_context` enrichments
- Keep the same output: upsert `regulatory_context` back into glossary terms

**Non-Goals:**
- Changing the glossary data model (already has `regulatory_context` field)
- Modifying `generate_interactive()` (single-query mode stays the same)
- Changing the FAISS index or embedding logic

## Decisions

**D1: Build search query from title + business_description**

Concatenate `"{title}. {business_description}"` as the search input. This gives the embedding model enough semantic signal without being too long. The detailed_description is available as additional LLM context but not used in the embedding query (to stay within optimal embedding length).

Alternative considered: embed all three fields — rejected because longer inputs dilute the semantic signal for FAISS similarity search.

**D2: Pass all three fields to the LLM prompt**

The LLM receives title, business_description, and detailed_description alongside the CRR3 chunks. This gives it full context to produce a targeted regulatory citation.

**D3: Filter by domain/category instead of catalog**

Replace `--catalog`/`--schema` CLI args with `--domain`/`--category` to filter which glossary terms to enrich. If neither is specified, enrich all terms that lack `regulatory_context`.

**D4: Skip terms that already have regulatory_context**

By default, only enrich terms where `regulatory_context` is empty. Add `--force` flag to re-enrich all.

## Risks / Trade-offs

[Risk: glossary format mismatch] → The flat `terms:` list in `glossary.yaml` vs the categorized structure in `core/glossary.py`. The current `iter_terms()` reads the categorized format. We need to handle both or standardize. → Mitigation: Read directly from the flat YAML list since that's the current file format.

[Risk: terms without descriptions] → Some glossary entries may lack business_description. → Mitigation: Fall back to title-only search when descriptions are empty.

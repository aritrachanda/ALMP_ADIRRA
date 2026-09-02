## ADDED Requirements

### Requirement: Batch enrichment reads from glossary
The `generate_batch()` function SHALL read glossary terms from `glossary/glossary.yaml` and use each term's title and business_description as the CRR3 search query.

#### Scenario: Enrich term with descriptions
- **WHEN** `generate_batch()` is called and a glossary term has title="Loss Given Default" and business_description="The ratio of loss..."
- **THEN** the system constructs the search query as "Loss Given Default. The ratio of loss..." and searches the CRR3 FAISS index

#### Scenario: Enrich term with title only
- **WHEN** a glossary term has an empty business_description
- **THEN** the system uses only the title as the search query

### Requirement: LLM receives full term context
The LLM prompt SHALL include the term's title, business_description, and detailed_description alongside the CRR3 chunks so it can produce a targeted regulatory citation.

#### Scenario: Full context sent to LLM
- **WHEN** a relevant CRR3 chunk is found for a term
- **THEN** the LLM receives all three fields (title, business_description, detailed_description) plus the CRR3 context chunks

### Requirement: Skip already-enriched terms
By default, `generate_batch()` SHALL skip terms that already have a non-empty `regulatory_context` field.

#### Scenario: Term already enriched
- **WHEN** a term has `regulatory_context` set to a non-empty string
- **THEN** the system skips it and moves to the next term

#### Scenario: Force re-enrichment
- **WHEN** `generate_batch(force=True)` is called
- **THEN** all terms are processed regardless of existing `regulatory_context`

### Requirement: Filter by domain and category
`generate_batch()` SHALL accept optional `domain` and `category` parameters to filter which glossary terms to enrich.

#### Scenario: Filter by domain
- **WHEN** `generate_batch(domain="Financial")` is called
- **THEN** only terms with `domain == "Financial"` are processed

#### Scenario: No filter
- **WHEN** `generate_batch()` is called without filters
- **THEN** all glossary terms without `regulatory_context` are processed

### Requirement: CLI interface
The CLI SHALL accept `--domain`, `--category`, and `--force` arguments instead of the current `--catalog`/`--schema`.

#### Scenario: CLI batch enrichment
- **WHEN** user runs `python agents/crr_agent.py --domain Financial --category Banking`
- **THEN** the agent enriches all Financial/Banking terms lacking regulatory_context

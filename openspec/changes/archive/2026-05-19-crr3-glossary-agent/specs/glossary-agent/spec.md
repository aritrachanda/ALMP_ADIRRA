## ADDED Requirements

### Requirement: Batch regulatory glossary generation
The system SHALL iterate columns from a target catalog (e.g., BIRD, CRDM), search CRR3 for each column name, and generate regulatory glossary terms for columns with relevant matches.

#### Scenario: Batch generation from target catalog
- **WHEN** `generate_batch(catalog_name, schema_name)` is called
- **THEN** the agent iterates all columns in the specified schema, searches CRR3 for each column name, and generates a regulatory term for columns with sufficiently close semantic matches

#### Scenario: Skip irrelevant columns
- **WHEN** a column's best CRR3 match has a FAISS distance above the relevance threshold
- **THEN** no glossary term is generated for that column

#### Scenario: Upsert generated terms to glossary
- **WHEN** a regulatory term is successfully generated
- **THEN** it is upserted to the glossary via `core/glossary.py` with the `regulatory_context` field populated

### Requirement: Interactive regulatory query
The system SHALL accept a free-text query, search CRR3, and synthesize a regulatory answer with article citations.

#### Scenario: Interactive query returns synthesis
- **WHEN** `generate_interactive(query)` is called with a regulatory question
- **THEN** the agent searches CRR3 chunks, sends relevant context to the LLM, and returns a synthesized answer with article references

#### Scenario: Interactive result includes term structure
- **WHEN** a result is returned from interactive mode
- **THEN** it SHALL include title, regulatory_context, and related_objects fields matching the glossary Term schema, so the caller can decide whether to save it

### Requirement: LLM synthesis with CRR3 context
The system SHALL construct a prompt that includes retrieved CRR3 chunks and instructs the LLM to synthesize a regulatory definition with article citations.

#### Scenario: Prompt includes retrieved chunks
- **WHEN** the LLM is called for synthesis
- **THEN** the prompt includes the top-k retrieved CRR3 chunks as context

#### Scenario: Output format
- **WHEN** the LLM generates a response
- **THEN** the response SHALL be structured as JSON with fields: title, regulatory_context, related_objects

#### Scenario: Article citation in regulatory_context
- **WHEN** regulatory_context is generated
- **THEN** it SHALL reference specific CRR3 article numbers (e.g., "Per CRR3 Art. 4(55), ...")

### Requirement: Regulatory context field on Term
The glossary `Term` dataclass SHALL include a `regulatory_context` field (optional string) for storing CRR3-derived citations, separate from business_description and detailed_description.

#### Scenario: New term with regulatory context
- **WHEN** a term is created with regulatory_context populated
- **THEN** it is persisted in glossary.yaml with the regulatory_context field

#### Scenario: Existing terms without regulatory context
- **WHEN** existing glossary terms are loaded that lack a regulatory_context field
- **THEN** they SHALL load successfully with regulatory_context defaulting to empty string

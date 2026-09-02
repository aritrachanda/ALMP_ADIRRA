## ADDED Requirements

### Requirement: Load FAISS index and chunk texts
The system SHALL load the FAISS index from `crr_indexes/crr3_index.faiss` and parse chunk texts from `crr_indexes/crr3_index.txt` (split by `===CHUNK_SEPARATOR===`) on first use, caching in module globals.

#### Scenario: First retrieval call loads index
- **WHEN** `search_chunks()` is called for the first time
- **THEN** the FAISS index and chunk text list are loaded into memory and reused for subsequent calls

#### Scenario: Chunk count validation
- **WHEN** the index is loaded
- **THEN** the system SHALL verify that the number of FAISS vectors equals the number of non-empty chunks (length > 50 chars)

### Requirement: Embed queries with Gemini text-embedding-004
The system SHALL embed user queries using Google Gemini `text-embedding-004` model, producing 768-dimensional vectors compatible with the rebuilt FAISS index.

#### Scenario: Query embedding
- **WHEN** a text query is provided to `embed_query()`
- **THEN** a 768-dimensional float vector is returned using the Gemini embedding API

#### Scenario: API key from environment
- **WHEN** embedding is requested
- **THEN** the system SHALL use the API key from the environment variable configured in `project.yaml` (agent.api_key_env)

### Requirement: Semantic search over CRR3 chunks
The system SHALL search the FAISS index with an embedded query and return the top-k most relevant chunks with their distances.

#### Scenario: Search returns top-k results
- **WHEN** `search_chunks(query, k=5)` is called
- **THEN** up to k chunk texts are returned, ordered by ascending L2 distance

#### Scenario: Chunk truncation
- **WHEN** a retrieved chunk exceeds 4000 characters
- **THEN** it SHALL be truncated to 4000 characters before being returned

#### Scenario: Distance threshold filtering
- **WHEN** results are returned
- **THEN** chunks with L2 distance above a configurable threshold MAY be excluded to avoid irrelevant results

### Requirement: Article lookup by number
The system SHALL provide direct article lookup from `crr3_articles.json` by article number string key.

#### Scenario: Lookup existing article
- **WHEN** `lookup_article("4")` is called
- **THEN** the full text content of Article 4 is returned as a joined string

#### Scenario: Lookup with headline
- **WHEN** an article is looked up
- **THEN** the corresponding headline from `articles_headlines_crr3.txt` SHALL be included in the result

#### Scenario: Lookup non-existent article
- **WHEN** `lookup_article("999")` is called for a non-existent article
- **THEN** None is returned

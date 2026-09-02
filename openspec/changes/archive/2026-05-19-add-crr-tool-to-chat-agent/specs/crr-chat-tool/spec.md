## ADDED Requirements

### Requirement: Chat agent SHALL provide CRR3 semantic search tool
The chat agent SHALL expose a `search_crr` tool that performs semantic search over CRR3 regulation text. The tool SHALL accept a `query` string parameter and return up to 5 relevant text chunks from the CRR3 FAISS index. Chunks with L2 distance exceeding 1.5 SHALL be filtered out.

#### Scenario: Semantic search returns relevant chunks
- **WHEN** the LLM calls `search_crr` with query "own funds requirements"
- **THEN** the tool SHALL embed the query, search the FAISS index, and return matching CRR3 text chunks
- **AND** each result SHALL include the chunk text and relevance distance

#### Scenario: No relevant chunks found
- **WHEN** the LLM calls `search_crr` with a query that has no chunks within distance 1.5
- **THEN** the tool SHALL return an empty results list with a message indicating no relevant CRR3 content was found

### Requirement: Chat agent SHALL provide CRR3 article lookup tool
The chat agent SHALL expose a `get_crr_article` tool that retrieves a specific CRR3 article by number. The tool SHALL accept an `article_num` string parameter and return the full article text and headline.

#### Scenario: Article exists
- **WHEN** the LLM calls `get_crr_article` with article_num "92"
- **THEN** the tool SHALL return the full article text and headline for CRR3 Article 92

#### Scenario: Article not found
- **WHEN** the LLM calls `get_crr_article` with an article number that does not exist
- **THEN** the tool SHALL return an error message indicating the article was not found

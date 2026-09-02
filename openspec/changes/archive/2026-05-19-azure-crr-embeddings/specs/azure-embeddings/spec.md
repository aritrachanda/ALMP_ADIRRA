## ADDED Requirements

### Requirement: Embed queries using Azure Foundry
The system SHALL embed text using Azure OpenAI's `text-embedding-3-large` model via the `AZURE_FOUNDRY_ENDPOINT` and `AZURE_FOUNDRY_KEY` environment variables.

#### Scenario: Query embedding returns 3072d vector
- **WHEN** `embed_query("loss given default")` is called
- **THEN** a 3072-dimensional float32 numpy array is returned

#### Scenario: Uses Azure credentials from environment
- **WHEN** an embedding is requested
- **THEN** the system uses `AZURE_FOUNDRY_KEY` and `AZURE_FOUNDRY_ENDPOINT` from environment variables

### Requirement: Build FAISS index using Azure Foundry embeddings
The build script SHALL embed all valid chunks using Azure OpenAI's `text-embedding-3-large` and write an IndexFlatL2 with d=3072.

#### Scenario: Successful index build
- **WHEN** `build_index.py` is executed
- **THEN** it embeds 230 valid chunks via Azure and writes `crr3_index.faiss` with dimension 3072

#### Scenario: Batch embedding with retry
- **WHEN** an embedding API call fails with a retryable error (429, 5xx)
- **THEN** the script retries with exponential backoff up to 6 attempts

### Requirement: Embedding model configured in project.yaml
The embedding model name SHALL be read from `project.yaml` at `agent.embedding_model`.

#### Scenario: Model name from config
- **WHEN** the embedding pipeline starts
- **THEN** it reads `agent.embedding_model` from `project.yaml` to determine which model to call

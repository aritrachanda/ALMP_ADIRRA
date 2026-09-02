## 1. Update crr_retrieval.py

- [x] 1.1 Replace `embed_query()` to use `AzureOpenAI.embeddings.create()` instead of `google.genai`
- [x] 1.2 Update `_get_api_key()` to return Azure endpoint + key (or replace with Azure client setup)
- [x] 1.3 Update `EMBEDDING_MODEL` constant to read from `project.yaml` (`agent.embedding_model`)

## 2. Update build_index.py

- [x] 2.1 Replace `embed_chunks()` to use `AzureOpenAI.embeddings.create()` with batching
- [x] 2.2 Update `EMBEDDING_DIM` to 3072 (matches `text-embedding-3-large`)
- [x] 2.3 Update API key/endpoint loading to use Azure env vars

## 3. Config & Rebuild

- [x] 3.1 Update `project.yaml` `agent.embedding_model` to `text-embedding-3-large`
- [x] 3.2 Run `build_index.py` to rebuild the FAISS index
- [x] 3.3 Verify with a test query (e.g., `generate_interactive("loss given default")`)

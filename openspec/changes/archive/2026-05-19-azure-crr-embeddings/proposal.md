## Why

The project has moved to Azure Foundry as its LLM provider, but the CRR3 embedding pipeline (index building and runtime search) still uses Google Gemini. This creates an unnecessary second API dependency and requires maintaining a separate Gemini API key. Switching to Azure Foundry's `text-embedding-3-large` unifies on a single provider.

## What Changes

- **BREAKING**: Replace Gemini embedding calls with Azure OpenAI embedding calls in `crr_retrieval.py` and `build_index.py`
- Rebuild FAISS index with `text-embedding-3-large` (3072d) — same dimension as current Gemini index
- Remove `google-genai` dependency from the embedding path (still used elsewhere if needed)
- Update `project.yaml` embedding_model config to reference the Azure model

## Capabilities

### New Capabilities
- `azure-embeddings`: Azure Foundry embedding integration for CRR3 index building and query-time search

### Modified Capabilities

## Impact

- `agents/agent_utils/crr_retrieval.py`: Replace `google.genai` with `openai.AzureOpenAI` for `embed_query()`
- `crr_indexes/build_index.py`: Replace Gemini embedding calls with Azure OpenAI embedding calls
- `crr_indexes/crr3_index.faiss`: Rebuilt file (same d=3072 but different vector space)
- `project.yaml`: Update `embedding_model` value
- Environment: Uses existing `AZURE_FOUNDRY_KEY` and `AZURE_FOUNDRY_ENDPOINT` env vars (no new secrets)

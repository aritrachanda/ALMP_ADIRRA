## Context

The CRR3 embedding pipeline currently uses `google.genai` with `gemini-embedding-001` (3072d). The rest of the project has moved to Azure Foundry (`gpt-5.4-mini` via `AzureOpenAI` client). Two files need updating:
- `crr_indexes/build_index.py` — one-time index build
- `agents/agent_utils/crr_retrieval.py` — runtime query embedding

Both currently import `google.genai` and use a Gemini API key. The project already has `AZURE_FOUNDRY_KEY` and `AZURE_FOUNDRY_ENDPOINT` configured and working (used by `chat_agent.py`).

## Goals / Non-Goals

**Goals:**
- Use Azure Foundry's `text-embedding-3-large` for both index building and query-time embedding
- Reuse existing Azure credentials (`AZURE_FOUNDRY_KEY`, `AZURE_FOUNDRY_ENDPOINT`)
- Rebuild the FAISS index with the new embeddings
- Keep the same simple architecture (IndexFlatL2, lazy-load, module-level cache)

**Non-Goals:**
- Changing the chunking strategy or chunk text
- Removing the `google-genai` package from the project (still used by other agents if needed)
- Changing the FAISS index type or search parameters

## Decisions

### 1. Use `text-embedding-3-large` (3072d)

**Choice**: `text-embedding-3-large` over `text-embedding-3-small`
**Rationale**: Same dimension (3072) as the current Gemini index, so no structural changes to the FAISS index. Cost is negligible at 230 chunks (~$0.02 to build). Better quality than `small` for dense legal text.

### 2. Use the same `AzureOpenAI` client pattern as chat_agent.py

**Choice**: `openai.AzureOpenAI` with `client.embeddings.create()`
**Rationale**: Consistent with existing Azure integration. Same client library, same auth pattern, same endpoint.

### 3. API version from chat_agent.py

**Choice**: Use the same `api_version` as `chat_agent.py` for consistency.
**Rationale**: The endpoint already supports this version for the chat agent, so embeddings should work too.

### 4. Config in project.yaml

**Choice**: Update `agent.embedding_model` to `text-embedding-3-large`
**Rationale**: Single source of truth for model names. Both build script and retrieval read from here.

## Risks / Trade-offs

- **Index rebuild required** → One-time operation, ~$0.02, no rate limit issues with Azure (unlike Gemini free tier)
- **Vector space change** → Old and new embeddings are incompatible. The `.faiss` file is overwritten atomically by the build script. No gradual migration needed.
- **Azure endpoint must support embeddings** → If the Foundry endpoint only supports chat completions, embeddings will fail. Mitigation: test with a single embedding call before full rebuild.

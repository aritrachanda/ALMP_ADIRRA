## Context

The project has pre-built CRR3 indexes in `crr_indexes/`:
- `crr3_index.faiss`: IndexFlatL2, currently d=1536, n=231 vectors (OpenAI embeddings)
- `crr3_index.txt`: 232 chunks delimited by `===CHUNK_SEPARATOR===` (FAISS ID = positional index into chunk list)
- `crr3_articles.json`: Article number (string key) → array of text strings (full article content)
- `articles_headlines_crr3.txt`: One line per article with "Article N: Headline"

Chunk sizes vary (2–31,329 chars, avg 2,663). These are section-boundary splits, not fixed-size.

The glossary (`core/glossary.py`) has a `Term` dataclass with: title, business_description, detailed_description, related_objects. No regulatory field exists yet.

LLM calls go through `agents/agent_utils/llm.py` which supports JSON, text, and chat modes via Gemini.

## Goals / Non-Goals

**Goals:**
- Rebuild FAISS index with Gemini `text-embedding-004` (d=768) so the project uses one provider
- Provide a retrieval utility that loads the index, embeds queries, and returns relevant CRR3 chunks + article references
- Build a glossary agent with batch mode (catalog columns → regulatory terms) and interactive mode (user query → answer)
- Add `regulatory_context` field to glossary terms for CRR3 citations
- Keep the index in-process (file-based, lazy-loaded) — no external vector DB

**Non-Goals:**
- UI integration (glossary page changes are a future change)
- Chat page integration (future: detect regulatory intent → pre-fetch)
- Supporting multiple regulations (only CRR3 for now)
- Production-grade chunking optimization (current chunks are sufficient for demo)

## Decisions

### 1. Gemini embeddings instead of OpenAI

**Choice**: Rebuild index with `text-embedding-004` (768 dimensions)
**Alternatives**: Keep OpenAI ada-002 (1536d), use both providers
**Rationale**: Single provider simplifies config and API key management. Gemini embedding is free-tier eligible. Smaller vectors = smaller index file. The project already uses Gemini for all LLM calls.

### 2. Index rebuild as a standalone script

**Choice**: `crr_indexes/build_index.py` script that reads `crr3_index.txt`, embeds chunks, writes new `.faiss` file
**Alternatives**: Rebuild on first load, rebuild via CLI command
**Rationale**: Index building is a one-time operation. A script is simple, debuggable, and can be re-run if the source text changes. No need for runtime rebuilding.

### 3. Retrieval utility in agent_utils

**Choice**: `agents/agent_utils/crr_retrieval.py` with functions: `load_index()`, `embed_query()`, `search_chunks()`, `lookup_article()`
**Alternatives**: Put retrieval in `core/`, make it a class
**Rationale**: This is agent infrastructure (only agents use it), so it belongs in `agent_utils/`. Functions over classes since there's no complex state — the FAISS index is loaded once and cached.

### 4. Lazy-load with module-level cache

**Choice**: Load FAISS index and chunk texts on first call, cache in module globals
**Alternatives**: Load at import time, use `@st.cache_resource`
**Rationale**: Avoids import-time I/O. Module globals work because the agent runs in a single process. No Streamlit dependency in agent code.

### 5. Glossary agent modes

**Choice**: Two modes in `agents/glossary_agent.py`:
- `generate_batch(catalog_name, schema_name)`: Iterates target columns, searches CRR3, generates regulatory terms, upserts to glossary
- `generate_interactive(query)`: Single query → search → synthesize → return result (caller decides whether to save)

**Alternatives**: Single unified interface, separate agents per mode
**Rationale**: Batch covers the "enrich entire catalog" use case. Interactive covers future chat integration. Same retrieval + synthesis logic, different orchestration.

### 6. Article attribution via headline index

**Choice**: After retrieving chunks, cross-reference `articles_headlines_crr3.txt` and `crr3_articles.json` to cite specific articles in the `regulatory_context` field
**Alternatives**: Include article refs in chunk metadata, rely on LLM to extract article numbers
**Rationale**: Chunk text already contains article references (e.g., "Article 4 is amended as follows"). The LLM can extract these from context. Headlines file provides clean labels for citations.

### 7. Regulatory context as a separate field

**Choice**: Add `regulatory_context: str` to the `Term` dataclass — holds "Per CRR3 Art. X, ..." style citations
**Alternatives**: Merge into detailed_description, use a list of citations
**Rationale**: Keeps business descriptions (human-authored) separate from regulation-derived content (agent-authored). A single string is simpler than structured citations for a demo.

## Risks / Trade-offs

- **Chunk size variance** → Some chunks are 31K chars, exceeding typical context limits. Mitigation: truncate retrieved chunks to ~4000 chars before sending to LLM.
- **Embedding model mismatch after rebuild** → If someone regenerates chunks but forgets to rebuild the index, results will be wrong. Mitigation: build script validates chunk count matches.
- **Gemini embedding rate limits** → 232 chunks embedded at build time is fine. Runtime is single queries. Low risk.
- **Batch mode could produce low-quality terms** → Not every catalog column has a CRR3 definition. Mitigation: agent uses a relevance threshold on FAISS distance; skips columns with no close matches.
- **One-off trailing chunk** → The 232nd chunk is 2 chars (likely whitespace). Mitigation: build script filters chunks shorter than a minimum length (e.g., 50 chars).

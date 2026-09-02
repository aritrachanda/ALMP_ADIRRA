## Context

The chat agent (`agents/chat_agent.py`) provides a multi-turn conversational interface with LLM-native tool calling. It currently has tools for glossary, source/target catalogs, mappings, and column search. Separately, the CRR agent (`agents/crr_agent.py`) uses FAISS semantic search over CRR3 regulation text via `agents/agent_utils/crr_retrieval.py` to answer regulatory questions — but this is only available as a standalone batch/interactive agent, not through the chat interface.

The retrieval infrastructure is already built:
- `crr_retrieval.search_chunks(query, k)` — embeds query and returns top-k CRR3 text chunks with distances
- `crr_retrieval.lookup_article(article_num)` — returns full article text and headline by number
- FAISS index and chunk texts live in `crr_assets/`

## Goals / Non-Goals

**Goals:**
- Let chat users ask CRR3 regulatory questions and get answers backed by actual regulation text
- Reuse existing retrieval infrastructure — no new indexes or embedding pipelines
- Keep the tool interface simple: semantic search + article lookup

**Non-Goals:**
- Building a full regulatory reasoning agent (that's `crr_agent.py`'s job)
- Generating structured glossary entries from chat (use `/glossary` page for that)
- Adding new CRR3 indexing or re-indexing capabilities
- Changing the retrieval module itself

## Decisions

### 1. Two tools: `search_crr` and `get_crr_article`

**Decision**: Expose two separate tools rather than one combined tool.

**Rationale**: The LLM can use `search_crr` for open-ended regulatory questions (semantic search), and `get_crr_article` when the user asks about a specific article number. This mirrors the existing pattern of summary/drill-down tool pairs in the chat agent.

**Alternatives considered**:
- Single `query_crr` tool that auto-detects intent — harder for the LLM to use correctly, mixes concerns
- Exposing raw chunk retrieval — too low-level, LLM would need to assemble answers from fragments

### 2. Filter by relevance distance

**Decision**: Apply the existing `MAX_DISTANCE` threshold (1.5) to filter out irrelevant chunks in `search_crr`.

**Rationale**: Prevents the LLM from receiving noisy, off-topic chunks that would confuse answers. The threshold is already validated in the CRR agent.

### 3. Return top 5 chunks by default

**Decision**: `search_crr` returns up to 5 chunks (same as `crr_retrieval.search_chunks` default).

**Rationale**: Balances context richness vs. token budget. 5 chunks × ~4000 chars max = 20K chars, well within the 30K tool output cap.

### 4. System prompt update

**Decision**: Add a brief section to the chat system prompt mentioning CRR3 tools and when to use them.

**Rationale**: The LLM needs guidance to know when to reach for regulatory tools vs. glossary/catalog tools.

## Risks / Trade-offs

- **[Cold start latency]** → First `search_crr` call loads the FAISS index (~1s). Mitigation: acceptable for demo; same behavior as standalone CRR agent.
- **[Embedding API cost]** → Each `search_crr` call makes one embedding API request. Mitigation: bounded by chat usage; low volume in demo context.
- **[FAISS dependency in chat path]** → Adds `faiss-cpu` and `numpy` as runtime dependencies for chat. Mitigation: already installed for the CRR agent.

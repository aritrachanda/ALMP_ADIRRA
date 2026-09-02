## Why

The chat agent currently has tools for glossary, source/target catalogs, and mappings, but cannot answer questions about CRR3 regulation text directly. The CRR retrieval infrastructure (FAISS semantic search, article lookup) already exists in `agents/agent_utils/crr_retrieval.py` and is used by the standalone `crr_agent.py`, but isn't wired into the conversational chat agent. Users asking regulatory questions in chat get no CRR3 context.

## What Changes

- Add a `search_crr` tool to the chat agent that performs semantic search over CRR3 regulation text chunks using the existing FAISS index
- Add a `get_crr_article` tool to the chat agent that retrieves a specific CRR3 article by number
- Update the chat agent's system prompt to inform the LLM about CRR3 tool availability and when to use them

## Capabilities

### New Capabilities

- `crr-chat-tool`: Chat agent tools for querying CRR3 regulation text (semantic search and article lookup)

### Modified Capabilities

- `chat-agent`: Adding new tools to the existing chat agent tool set

## Impact

- `agents/chat_agent.py` — new tool implementations, tool definitions, dispatch entries, and system prompt update
- `agents/agent_utils/crr_retrieval.py` — consumed by chat agent (no changes needed, already provides the required functions)
- Dependencies: `faiss-cpu` and `numpy` already in requirements (used by crr_agent)

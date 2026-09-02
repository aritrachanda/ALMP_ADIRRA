## Why

The chat page in the UI is currently a stub that echoes user messages. To demonstrate the value of agentic data mapping in client demos, the chat needs to be a context-aware assistant that can answer questions about the project's sources, targets, mappings, and glossary. It should use LLM-native tool calling to fetch relevant data on demand rather than stuffing everything into the system prompt.

## What Changes

- Create a new `agents/chat_agent.py` module that implements a multi-turn conversational agent with tool calling via the Azure Responses API
- Define tools for reading project context: glossary terms, source/target catalogs, existing mappings, and project configuration
- Implement a tool-calling loop: send conversation → LLM may request tool calls → execute tools → return results → LLM generates final response
- Wire `ui/pages/chat.py` to call the chat agent instead of returning a stub reply
- Add a text-mode (non-JSON) LLM call path for conversational responses

## Capabilities

### New Capabilities
- `chat-agent`: Multi-turn conversational agent with LLM-native tool calling for fetching project context (glossary, source schemas, target schemas, mappings)

### Modified Capabilities
- `chat-ui`: Chat page wired to the real chat agent instead of a stub reply

## Impact

- **New code**: `agents/chat_agent.py` (~150-200 lines)
- **Modified code**: `ui/pages/chat.py` (replace stub with agent call, ~15 lines)
- **Config**: Optional `agent_chat` block in `project.yaml`
- **Dependencies**: None — uses existing `openai` SDK for Azure Responses API
- **Existing code reused as-is**: `chat_history.py`, `glossary.py`, `yaml_cache.py`, `mapping_agent.py`

## Context

The chat page (`ui/pages/chat.py`) is a Streamlit UI stub that returns `"Orchestrator not connected yet — your message was: {msg}"`. The underlying chat history system (`core/chat_history.py`) already persists conversations as JSON files with `{role, content, ts}` messages. The LLM provider dispatch (`agents/mapping_agent.py`) supports `openai`, `gemini`, and `azure` but is hardcoded to JSON response mode — chat needs text mode.

The Azure Foundry Responses API supports:
- Multi-turn via `input` as an array of `{role, content}` messages
- Tool calling via `tools` parameter with function definitions
- Text mode by omitting the `text.format` parameter

## Goals / Non-Goals

**Goals:**
- Multi-turn conversational agent that sends full message history to the LLM
- LLM-native tool calling (Azure Responses API `tools` parameter) to fetch project context on demand
- Tools: `get_glossary`, `get_source_catalog`, `get_target_catalog`, `get_mapping`, `list_sources`, `list_targets`, `list_mappings`
- Text-mode responses (not JSON) for natural conversation
- Wire into existing chat UI replacing the stub reply

**Non-Goals:**
- Triggering mapping or other agents from chat (future phase)
- Streaming responses
- Refactoring the existing `call_llm` / `_PROVIDERS` dispatch in `mapping_agent.py`
- Chat-specific config block in `project.yaml` (reuse `agent` block)

## Decisions

**1. Separate chat LLM call function, not shared with mapping agent**
- Rationale: The mapping agent's `call_llm` is designed for single-shot JSON-mode calls. Chat needs multi-turn messages, text mode, and tool calling. These are fundamentally different call patterns. A separate `_call_chat_llm()` in `chat_agent.py` is cleaner than making `call_llm` handle both.
- Alternative considered: Adding `json_mode`, `messages`, `tools` parameters to `call_llm`. Rejected — would complicate mapping agent code for no benefit.

**2. Read provider config from `project.yaml` `agent` block**
- Rationale: No need for a separate `agent_chat` config. The same model/provider/key used for mapping works for chat. Keeps config simple.
- The chat agent imports `load_project` from `mapping_agent` to read config.

**3. Tool calling loop with max iterations**
- Rationale: The LLM may request multiple tool calls in sequence. The agent runs a loop: send messages → check for tool calls → execute → append results → repeat. Cap at 10 iterations to prevent runaway loops.
- Tool results are appended to the message array as `{role: "tool", tool_call_id, content}` for the Responses API.

**4. Tools load data lazily via existing modules**
- Rationale: All context data (glossary, catalogs, mappings) already has loaders in `core/`. Tools are thin wrappers that call these loaders and return serialized YAML/JSON. No new data access code needed.

**5. System prompt provides project overview, tools provide detail**
- Rationale: The system prompt gives the LLM awareness of what tools are available and the project structure (source names, target names). When the user asks about specifics, the LLM calls the appropriate tool. This keeps the system prompt small (~500 tokens) while allowing deep context when needed.

## Risks / Trade-offs

- **[Token usage]** → Multi-turn chat with tool results can accumulate large context. For a demo app this is acceptable. If it becomes an issue, older messages could be truncated.
- **[Blocking UI]** → Tool calls + LLM round trips may take 5-15 seconds. Streamlit will show a spinner but the page is unresponsive. Acceptable for demo.
- **[Azure Responses API tool calling format]** → The Responses API has a specific format for tool results. Need to match it precisely. Mitigated by: we test it incrementally.
- **[Provider portability]** → The chat agent initially targets Azure Responses API only. Gemini and OpenAI Chat Completions have different tool calling formats. Acceptable for now — only Azure is configured.

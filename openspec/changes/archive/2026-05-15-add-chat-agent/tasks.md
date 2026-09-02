## 1. Chat agent core

- [x] 1.1 Create `agents/chat_agent.py` with system prompt builder that includes project overview (source names, target names, available tools description)
- [x] 1.2 Implement `_call_chat_azure()` — text-mode Azure Responses API call accepting multi-turn message array and tool definitions (no JSON mode)
- [x] 1.3 Implement tool-calling loop: send messages → check for tool calls → execute → append results → repeat (max 10 iterations)

## 2. Tool definitions and implementations

- [x] 2.1 Implement `list_sources`, `list_targets`, `list_mappings` tools (read from project.yaml / mappings directory)
- [x] 2.2 Implement `get_glossary` tool (load and return glossary YAML via `core/glossary.py`)
- [x] 2.3 Implement `get_source_catalog` and `get_target_catalog` tools (load catalog YAML for a named source/target)
- [x] 2.4 Implement `get_mapping` tool (load mapping YAML for a source-target pair)
- [x] 2.5 Register all tools as function definitions in the Azure Responses API format

## 3. Wire chat UI

- [x] 3.1 Update `ui/pages/chat.py` to import and call the chat agent instead of returning `_STUB_REPLY`
- [x] 3.2 Pass full conversation message history from `chat_history` to the chat agent on each turn

## 4. Verify

- [x] 4.1 Test multi-turn conversation: ask a question, then a follow-up referencing the previous answer
- [x] 4.2 Test tool calling: ask "what sources do I have?" and verify the LLM calls `list_sources`
- [x] 4.3 Test context-aware answer: ask "describe the counterparties table" and verify the LLM fetches the source catalog

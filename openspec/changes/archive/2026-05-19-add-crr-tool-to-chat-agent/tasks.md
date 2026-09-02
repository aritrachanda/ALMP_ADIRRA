## 1. Tool Implementations

- [x] 1.1 Add `_tool_search_crr(query)` function that calls `search_chunks` with distance filtering and returns JSON results
- [x] 1.2 Add `_tool_get_crr_article(article_num)` function that calls `lookup_article` and returns JSON result or error

## 2. Tool Registration

- [x] 2.1 Add `search_crr` and `get_crr_article` entries to `_TOOL_DISPATCH` dict
- [x] 2.2 Add `search_crr` tool definition to `TOOL_DEFINITIONS` list (query parameter, description)
- [x] 2.3 Add `get_crr_article` tool definition to `TOOL_DEFINITIONS` list (article_num parameter, description)

## 3. System Prompt Update

- [x] 3.1 Update `_build_system_prompt()` to mention CRR3 regulatory tools and when to use them

## 4. Import and Integration

- [x] 4.1 Add import for `search_chunks` and `lookup_article` from `agents.agent_utils.crr_retrieval` at top of `chat_agent.py`

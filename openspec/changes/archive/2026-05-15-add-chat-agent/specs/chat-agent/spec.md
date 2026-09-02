## ADDED Requirements

### Requirement: Chat agent SHALL process messages using LLM with multi-turn history
The chat agent SHALL send the full conversation history (all previous messages) to the LLM on each turn, enabling context-aware multi-turn conversations. The system prompt SHALL provide a project overview and describe available tools.

#### Scenario: First message in a conversation
- **WHEN** the user sends their first message in a new conversation
- **THEN** the chat agent SHALL send the system prompt plus the user message to the LLM
- **AND** return the LLM's text response as the assistant reply

#### Scenario: Subsequent messages include history
- **WHEN** the user sends a follow-up message in an existing conversation
- **THEN** the chat agent SHALL send the system prompt plus all prior messages (user and assistant) plus the new user message to the LLM
- **AND** return the LLM's text response

### Requirement: Chat agent SHALL support LLM-native tool calling
The chat agent SHALL define tools as function definitions passed to the Azure Responses API. When the LLM requests a tool call, the agent SHALL execute the corresponding function, return the result to the LLM, and let the LLM generate a final text response.

#### Scenario: LLM requests a tool call
- **WHEN** the LLM response contains a tool call request (e.g. `get_glossary`)
- **THEN** the chat agent SHALL execute the requested function with the provided arguments
- **AND** append the tool result to the message array
- **AND** send the updated messages back to the LLM for a final response

#### Scenario: Tool calling loop is bounded
- **WHEN** the LLM makes repeated tool call requests
- **THEN** the chat agent SHALL execute up to 10 iterations of tool calls
- **AND** if the limit is reached, return whatever response is available

### Requirement: Chat agent SHALL provide context-fetching tools
The chat agent SHALL expose the following tools for fetching project context:

- `list_sources` — list available source dataset names
- `list_targets` — list available target data model names
- `list_mappings` — list available mapping files
- `get_glossary` — return the full business glossary
- `get_source_catalog` — return the schema and profiling data for a named source
- `get_target_catalog` — return the schema for a named target
- `get_mapping` — return an existing mapping between a source and target

#### Scenario: Get glossary
- **WHEN** the LLM calls `get_glossary`
- **THEN** the tool SHALL return all glossary categories, subcategories, and terms from `glossary/glossary.yaml`

#### Scenario: Get source catalog
- **WHEN** the LLM calls `get_source_catalog` with argument `source_name`
- **THEN** the tool SHALL return the full catalog YAML content for that source from `sources/<source_name>.yaml`

#### Scenario: Get target catalog
- **WHEN** the LLM calls `get_target_catalog` with argument `target_name`
- **THEN** the tool SHALL return the full catalog YAML content for that target from `targets/<target_name>.yaml`

#### Scenario: Get mapping
- **WHEN** the LLM calls `get_mapping` with arguments `source_name` and `target_name`
- **THEN** the tool SHALL return the mapping YAML content from `mappings/<source>_to_<target>.yaml`
- **AND** if the mapping file does not exist, return a message indicating no mapping exists

#### Scenario: List sources
- **WHEN** the LLM calls `list_sources`
- **THEN** the tool SHALL return the names of all sources defined in `project.yaml`

#### Scenario: List targets
- **WHEN** the LLM calls `list_targets`
- **THEN** the tool SHALL return the names of all targets defined in `project.yaml`

#### Scenario: List mappings
- **WHEN** the LLM calls `list_mappings`
- **THEN** the tool SHALL return the filenames of all mapping YAML files in the `mappings/` directory

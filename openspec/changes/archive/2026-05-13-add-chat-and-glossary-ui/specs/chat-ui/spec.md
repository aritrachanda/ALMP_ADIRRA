# Spec delta — chat-ui (ADDED)

## ADDED Requirements

### Requirement: The Chat page SHALL provide a clean, conversation-focused surface

The Chat page SHALL be the landing page of the Chat section and SHALL present a minimal, conversation-focused UI: a centered hero greeting when no active conversation exists, a single chat input, a running list of turns rendered above the input, and a list of previous conversations. Assistant replies in this version SHALL be a stubbed placeholder string until the orchestrator backend is merged.

#### Scenario: First-time visit shows a hero greeting and input

- **WHEN** the user opens the Chat page with no active conversation
- **THEN** a centered hero headline (e.g. "What can I help you figure out?") is shown
- **AND** a single chat input is presented
- **AND** a "Previous conversations" list is visible (empty if none exist)

#### Scenario: Submitting a message records both user and stubbed assistant turns

- **WHEN** the user types a message and submits
- **THEN** a user turn is appended to the active conversation
- **AND** a stubbed assistant reply is appended (e.g. "Orchestrator not connected yet — your message was: …")
- **AND** both turns are persisted immediately to the conversation's JSON file
- **AND** the page re-renders to show both turns above the input

#### Scenario: Starting a new chat resets the surface

- **WHEN** the user clicks "New chat"
- **THEN** a new conversation is created with a fresh ID
- **AND** the chat surface returns to the empty hero state
- **AND** the new conversation appears in the "Previous conversations" list once the first message is sent

#### Scenario: Selecting a previous conversation loads it

- **WHEN** the user clicks a conversation in the "Previous conversations" list
- **THEN** that conversation's turns are loaded into the chat surface
- **AND** subsequent messages append to that conversation

### Requirement: Chat conversations SHALL be persisted as JSON files

Each conversation SHALL be persisted as a single JSON file under `chat_history/<id>.json`, written immediately after every turn (write-on-turn). The persistence layer SHALL live in `core/chat_history.py` and MUST NOT import Streamlit so the same module can be reused by future non-Streamlit frontends.

#### Scenario: Each conversation is one file

- **WHEN** a conversation is created
- **THEN** a JSON file is written to `chat_history/<id>.json`
- **AND** the file contains: `id`, `title`, `created_at`, `updated_at`, `messages[]`

#### Scenario: Each turn rewrites the file

- **WHEN** a message is appended via `append_message(...)`
- **THEN** `updated_at` is set to the current timestamp
- **AND** the entire JSON file is rewritten

#### Scenario: Persistence module is Streamlit-free

- **WHEN** `core/chat_history.py` is imported
- **THEN** it does NOT import `streamlit`
- **AND** it can be called from any Python context (CLI, future Django views, tests)

### Requirement: The chat_history directory SHALL be gitignored

The `chat_history/` directory SHALL be excluded from version control so that user-generated conversations do not pollute the repository.

#### Scenario: New chats do not pollute the repo

- **WHEN** the user creates conversations
- **THEN** `chat_history/` and its contents are excluded from version control

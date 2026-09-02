# Spec — vue-chat-page (ADDED)

## ADDED Requirements

### Requirement: Two-pane chat layout with conversation list

The Chat page SHALL display a left panel with a searchable list of saved conversations and a main panel for the active conversation. The left panel SHALL include a "New conversation" button and search input. Each conversation item SHALL show title and last-updated timestamp.

#### Scenario: Fresh conversation shows hero greeting

- **WHEN** the user creates a new conversation (or no conversation is selected)
- **THEN** the main panel SHALL display a centered hero greeting
- **AND** 3–6 suggestion chips below the greeting
- **AND** clicking a chip SHALL create a conversation with that message as the first user turn

#### Scenario: Message display

- **GIVEN** an active conversation with messages
- **THEN** user messages SHALL be right-aligned with a distinct background color
- **AND** assistant messages SHALL be left-aligned
- **AND** messages SHALL be scrollable with the newest message visible

### Requirement: Chat input and message sending

The page SHALL display a bottom-pinned text input. Submitting a message SHALL call `POST /chat/conversations/{id}/messages` and display the assistant's response when it arrives.

#### Scenario: Send message and receive response

- **WHEN** the user types a message and presses Enter or clicks Send
- **THEN** the user message SHALL appear immediately in the conversation
- **AND** a loading indicator SHALL display while waiting for the assistant response
- **AND** the assistant response SHALL appear when the API returns

### Requirement: Conversation CRUD

- Creating a conversation SHALL call `POST /chat/conversations`.
- Selecting a conversation SHALL load its full message history via `GET /chat/conversations/{id}`.
- Deleting a conversation SHALL call `DELETE /chat/conversations/{id}` and remove it from the list.

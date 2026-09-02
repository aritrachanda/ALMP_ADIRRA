# Spec delta — chat-ui (MODIFIED)

## MODIFIED Requirements

### Requirement: The Chat page SHALL provide a clean, conversation-focused surface

The Chat page SHALL be the landing page of the Chat section and SHALL present a minimal, conversation-focused UI based on Desktop frames 122 and 124. It SHALL render in two columns: a **left conversations panel** (search input + "+ New conversation" + flat list of previous conversations) and a **main conversation surface** (centered hero greeting + 3 suggestion cards on a fresh conversation, OR conversation title + transcript + chat input on an active one). Assistant replies in this version SHALL be a stubbed placeholder string until the orchestrator backend is merged.

#### Scenario: First-time visit shows a hero greeting, three suggestion cards, and the conversations panel

- **WHEN** the user opens the Chat page with no active conversation
- **THEN** a left conversations panel is rendered with a search input, a "+ New conversation" button, and (if any) a list of previous conversations
- **AND** a centered hero headline (e.g. "Hello! What can I help you with?") is shown in the main column
- **AND** three suggestion **cards** are shown below the headline, each with a title and a one-line subtitle
- **AND** a single chat input is presented (bottom-pinned `st.chat_input`)

#### Scenario: Clicking a suggestion card prefills the chat input

- **WHEN** the user clicks one of the three suggestion cards on the empty hero state
- **THEN** the card's title text is placed into the chat input as a prefill the user can edit before submitting

#### Scenario: Hero state collapses after the first turn

- **WHEN** the active conversation has at least one message
- **THEN** the hero headline and the three suggestion cards are no longer rendered
- **AND** the active conversation's title is rendered at the top of the main column
- **AND** the chat input remains visible at its normal location

#### Scenario: User and assistant messages are styled distinctly

- **WHEN** a user turn is rendered
- **THEN** the message appears as a right-aligned light-blue rounded pill bubble
- **AND** when an assistant turn is rendered it appears as plain left-aligned text without an avatar or bubble

#### Scenario: Submitting a message records both user and stubbed assistant turns

- **WHEN** the user types a message and submits
- **THEN** a user turn is appended to the active conversation
- **AND** a stubbed assistant reply is appended (e.g. "Orchestrator not connected yet — your message was: …")
- **AND** both turns are persisted immediately to the conversation's JSON file
- **AND** the page re-renders to show both turns above the input

#### Scenario: Starting a new conversation resets the surface

- **WHEN** the user clicks "+ New conversation" in the left panel
- **THEN** a new conversation is created with a fresh ID
- **AND** the main column returns to the empty hero state (with the three suggestion cards)
- **AND** the new conversation appears in the left panel's list once the first message is sent

#### Scenario: Selecting a previous conversation loads it

- **WHEN** the user clicks a conversation in the left panel's list
- **THEN** that conversation's turns are loaded into the main column
- **AND** the conversation title is shown at the top of the main column
- **AND** subsequent messages append to that conversation

#### Scenario: Searching filters the conversations list

- **WHEN** the user types into the search input above the conversations list
- **THEN** only conversations whose title contains the search text (case-insensitive) are shown
- **AND** clearing the search restores the full list

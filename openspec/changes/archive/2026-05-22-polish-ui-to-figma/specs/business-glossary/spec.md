# Spec delta — business-glossary (ADDED)

## ADDED Requirements

### Requirement: The New term form SHALL include an AI-assist side panel (stub)

When the user opens the "Add new +" form **or** views an existing term, the page SHALL render the form / detail on the left and a small AI-assist chat surface on the right whenever the user has the AI panel toggled on. The assistant in this version SHALL be a stubbed placeholder; submissions SHALL append a user turn and a stubbed assistant turn ("AI assist not connected yet — your message was: …") to an in-memory list scoped to the current page session. The AI-assist panel MUST NOT write to `chat_history/` or to `glossary/glossary.yaml`.

#### Scenario: AI assist panel is toggleable from the term detail and the New term form

- **WHEN** the user clicks the "AI assist" toggle button on the term detail view or on the New term form
- **THEN** an AI-assist chat surface is rendered on the right with its own chat input
- **AND** clicking the toggle again hides the panel

#### Scenario: AI-assist messages are session-scoped and not persisted

- **WHEN** the user submits a prompt in the AI-assist panel
- **THEN** a user turn and a stubbed assistant turn are appended to an in-memory list
- **AND** no file is written under `chat_history/`
- **AND** the glossary YAML is NOT modified by AI-assist activity

#### Scenario: AI-assist defaults to hidden

- **WHEN** the user opens any glossary surface for the first time in a session
- **THEN** the AI-assist panel is hidden until the user toggles it on

### Requirement: Glossary saves SHALL surface a confirmation toast

When a glossary section save succeeds and the YAML is written, the UI SHALL show a non-blocking confirmation via `st.toast`. Failures SHALL surface as an `st.error`.

#### Scenario: Successful section save shows a toast

- **WHEN** the user saves an edited section and the file write succeeds
- **THEN** a non-blocking toast (e.g. "Saved.") is displayed
- **AND** the section returns to read mode showing the new value

#### Scenario: Failed save surfaces an error

- **WHEN** the user saves an edited section and the file write fails
- **THEN** an `st.error` message is shown
- **AND** the section remains in edit mode with the user's input preserved

### Requirement: The term tree SHALL include a search input

The secondary panel of the Glossary page SHALL render a search input above the term tree. Typing into the search SHALL filter the visible terms by case-insensitive substring match against the term title.

#### Scenario: Search filters the term tree

- **WHEN** the user types into the search input above the term tree
- **THEN** only terms whose title contains the search text (case-insensitive) remain visible
- **AND** clearing the search restores the full tree

### Requirement: The New term form SHALL place Save and Cancel at the top right

On the "Add new +" form, the Save and Cancel actions SHALL be placed at the top-right of the main detail panel (matching Desktop 2939), not at the bottom of the form.

#### Scenario: Save and Cancel appear top-right on the New term form

- **WHEN** the user opens the "Add new +" form
- **THEN** Save and Cancel buttons are rendered at the top-right of the main detail panel
- **AND** clicking Save persists the new term and shows a "Saved." toast
- **AND** clicking Cancel discards the in-progress entry without writing the glossary YAML

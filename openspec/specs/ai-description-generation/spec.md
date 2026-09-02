## ADDED Requirements

### Requirement: Improve with AI button per field
The catalog page SHALL provide an "Improve with AI" button next to each editable annotation field (table-level `user_description`, `mapping_instructions`, and per-column `user_description`, `mapping_instructions`).

#### Scenario: AI generates a column user description
- **WHEN** a user clicks "Improve with AI" on a column's `user_description` field
- **THEN** the system SHALL call the LLM with column context and fill the field with the generated description

#### Scenario: AI generates mapping instructions
- **WHEN** a user clicks "Improve with AI" on a column's `mapping_instructions` field
- **THEN** the system SHALL call the LLM with column context and fill the field with generated mapping instructions

### Requirement: Optional user instructions for AI
The catalog page SHALL provide a text input where the user can enter optional instructions that guide the AI generation (e.g., "Use formal language", "This is a regulatory banking dataset").

#### Scenario: User provides custom instructions
- **WHEN** a user enters "Keep descriptions under 20 words" and clicks "Improve with AI"
- **THEN** the LLM prompt SHALL include those instructions as a constraint

#### Scenario: No custom instructions
- **WHEN** a user clicks "Improve with AI" without entering custom instructions
- **THEN** the LLM SHALL use default prompting without additional constraints

### Requirement: Batch generation per table
The catalog page SHALL provide a "Generate all" button that generates the selected annotation field for all columns in the current table in a single operation.

#### Scenario: Generate all user descriptions for a table
- **WHEN** a user clicks "Generate all" for `user_description`
- **THEN** the system SHALL send one LLM call with the full table context and fill `user_description` for all columns

#### Scenario: Generate all preserves existing user edits
- **WHEN** a user has manually edited some column descriptions and clicks "Generate all"
- **THEN** the system SHALL overwrite all fields with AI-generated values (user can undo by not saving)

### Requirement: AI context includes available metadata
The LLM prompt for description generation SHALL include: column name, data type, table name, schema name, sibling columns, column stats (distinct count, null %, min/max, sample values), PK/FK relationships, and the source description (if available).

#### Scenario: AI uses stats for description quality
- **WHEN** a column has `distinct_count: 4` and `sample_values: [SavingsAccount, TermDeposit, CurrentAccount, CustodyAccount]`
- **THEN** the AI-generated description SHALL reference the fact that this is a categorical/enum-like field

### Requirement: AI works on columns with existing source descriptions
The "Improve with AI" feature SHALL work on columns that already have a source description. The source description SHALL be included in the LLM context as reference material, but the generated annotation SHALL be a separate value in the overlay file.

#### Scenario: AI improves on an existing source description
- **WHEN** a column has a source description "Foreign key to DimAccountingStandard" and the user clicks "Improve with AI" on `user_description`
- **THEN** the AI SHALL use the source description as context and generate an enriched user description; the source description SHALL remain unchanged

### Requirement: AI uses project agent configuration
The AI description generation SHALL use the LLM provider, model, API key, and temperature settings from the `agent` block in `project.yaml`.

#### Scenario: Azure OpenAI configured
- **WHEN** `project.yaml` has `agent.provider: azure` and `agent.model: gpt-5.4-mini`
- **THEN** the catalog AI generation SHALL use that provider and model

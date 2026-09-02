## ADDED Requirements

### Requirement: Azure provider calls Azure AI Foundry via Responses API
The system SHALL support `azure` as a valid LLM provider. When `provider` is set to `azure` in `project.yaml`, the system SHALL use the `AzureOpenAI` client from the `openai` package and call the Responses API (`client.responses.create()`).

#### Scenario: Successful LLM call with azure provider
- **WHEN** `project.yaml` has `provider: azure` and valid `AZURE_FOUNDRY_KEY` and `AZURE_FOUNDRY_ENDPOINT` environment variables are set
- **THEN** the system SHALL create an `AzureOpenAI` client, send the system prompt as `instructions` and user prompt as `input`, and return parsed JSON from `resp.output_text`

#### Scenario: Missing endpoint environment variable
- **WHEN** `provider` is `azure` but `AZURE_FOUNDRY_ENDPOINT` is not set
- **THEN** the system SHALL raise an error indicating the missing endpoint

### Requirement: Azure provider uses JSON mode
The system SHALL request JSON output from Azure Foundry by passing `text={"format": {"type": "json_object"}}` to the Responses API.

#### Scenario: JSON response from Azure
- **WHEN** an LLM call is made with the `azure` provider
- **THEN** the response SHALL be parsed as JSON and returned as a Python dict

### Requirement: Azure provider is registered in both agents
The `azure` provider SHALL be available in both `mapping_agent.py` and `bird_mapping_agent.py` provider dispatch dictionaries.

#### Scenario: Mapping agent uses azure provider
- **WHEN** the generic mapping agent is configured with `provider: azure`
- **THEN** mapping operations SHALL use the Azure Foundry endpoint

#### Scenario: BIRD mapping agent uses azure provider
- **WHEN** the BIRD mapping agent is configured with `provider: azure`
- **THEN** BIRD mapping operations SHALL use the Azure Foundry endpoint

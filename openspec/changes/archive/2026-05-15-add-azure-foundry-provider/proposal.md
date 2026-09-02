## Why

The project currently supports only Gemini and OpenAI as LLM providers. We have an Azure AI Foundry API key and endpoint available and want to use Azure-hosted models (starting with gpt-5.4-mini) for mapping operations. This avoids managing separate OpenAI/Gemini API keys and consolidates LLM access through a single Azure resource.

## What Changes

- Add a new `azure` LLM provider that calls Azure AI Foundry using the OpenAI SDK's Responses API (`client.responses.create()`)
- Read endpoint and API key from environment variables (`AZURE_FOUNDRY_ENDPOINT`, `AZURE_FOUNDRY_KEY`)
- Register the new provider in the `_PROVIDERS` dispatch dictionary in both `mapping_agent.py` and `bird_mapping_agent.py`
- Allow `project.yaml` to select `azure` as a provider with the appropriate config fields

## Capabilities

### New Capabilities
- `azure-foundry-provider`: Adds Azure AI Foundry as an LLM provider using the OpenAI SDK's Responses API, with JSON mode support and env-var-based configuration (Option C — no signature changes to `call_llm`)

### Modified Capabilities

_None — no existing spec-level behavior changes._

## Impact

- **Code**: `agents/mapping_agent.py` (new `_call_azure` function + `_PROVIDERS` entry), `agents/bird_mapping_agent.py` (same if it has its own provider dispatch)
- **Config**: `project.yaml` gains `azure` as a valid provider value
- **Environment**: Requires `AZURE_FOUNDRY_KEY` and `AZURE_FOUNDRY_ENDPOINT` in `.env`
- **Dependencies**: None — uses the existing `openai` package which already includes `AzureOpenAI`

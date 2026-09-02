## 1. Add Azure provider function

- [x] 1.1 Add `_call_azure` function to `agents/mapping_agent.py` using `AzureOpenAI` + Responses API (`client.responses.create()` with `instructions`, `input`, and `text.format` for JSON mode). Read endpoint from `AZURE_FOUNDRY_ENDPOINT` env var.
- [x] 1.2 Register `"azure": _call_azure` in the `_PROVIDERS` dict in `agents/mapping_agent.py`

## 2. Enable in BIRD mapping agent

- [x] 2.1 Add the same `_call_azure` function and `_PROVIDERS` entry to `agents/bird_mapping_agent.py` (or import from `mapping_agent` if it already shares the dispatch)

## 3. Update configuration

- [x] 3.1 Update `project.yaml` to use `provider: azure`, `model: gpt-5.4-mini`, and `api_key_env: AZURE_FOUNDRY_KEY`

## 4. Verify

- [x] 4.1 Run a mapping operation end-to-end with the azure provider to confirm it works
- [x] 4.2 Delete `test_api.py` (no longer needed)

## Context

The codebase uses a provider-dispatch pattern for LLM calls: a `_PROVIDERS` dictionary maps provider names to functions with the signature `(system_prompt, user_prompt, model, api_key, temperature) -> dict`. The `call_llm()` function dispatches to the right provider and handles retries.

Currently two providers exist: `openai` (Chat Completions API) and `gemini`. We need to add `azure` for Azure AI Foundry, which uses the OpenAI SDK but routes through the **Responses API** — different from the Chat Completions API used by the direct OpenAI provider.

Key constraint discovered during exploration: the Azure Foundry endpoint is configured for the Responses API, which uses `client.responses.create()` with `input` instead of `messages`, and `text.format` instead of `response_format`.

## Goals / Non-Goals

**Goals:**
- Add `azure` as a new provider in `_PROVIDERS` using `AzureOpenAI` + Responses API
- Read endpoint from `AZURE_FOUNDRY_ENDPOINT` env var inside `_call_azure` (Option C — no `call_llm` signature change)
- Support JSON mode via `text={"format": {"type": "json_object"}}`
- Work with both `mapping_agent.py` and `bird_mapping_agent.py`

**Non-Goals:**
- Refactoring the `call_llm()` signature or provider dispatch pattern
- Supporting Azure Chat Completions API (our endpoint uses Responses API)
- Adding Anthropic SDK support (models are accessed through Azure Foundry, not directly)
- Making endpoint configurable in `project.yaml` (env var is sufficient for this demo)

## Decisions

**1. Use `AzureOpenAI` from the existing `openai` package (not `azure-ai-inference`)**
- Rationale: Zero new dependencies. The `openai>=1.30.0` already in `requirements.txt` includes `AzureOpenAI` with Responses API support.
- Alternative considered: `azure-ai-inference` SDK — rejected because it adds a dependency and the OpenAI SDK already works.

**2. Use Responses API (`client.responses.create()`) instead of Chat Completions API**
- Rationale: The Azure Foundry endpoint is configured for the Responses API and rejects Chat Completions parameters (`messages`, `response_format`).
- The Responses API maps system prompts to `instructions` and user input to `input`.

**3. Read endpoint from env var inside `_call_azure` (Option C)**
- Rationale: Smallest change — no modifications to `call_llm()` signature or callers. Acceptable for a demo app.
- Alternative considered: Pass `agent_cfg` dict through `call_llm` — cleaner but larger refactor. Can be done later.

**4. Extract response text via `resp.output_text`**
- The Responses API returns `output_text` (a convenience property) rather than `resp.choices[0].message.content`.

## Risks / Trade-offs

- **[API version pinning]** → The `api_version` is hardcoded. If Azure deprecates it, we update one line. Acceptable for a demo.
- **[Endpoint in env var only]** → Not in `project.yaml`, so less visible. Mitigated by being consistent with how `api_key_env` works — the key name is in YAML, the value is in env.
- **[Responses API is newer]** → Less community examples. Mitigated by: we already tested it and it works with JSON mode.

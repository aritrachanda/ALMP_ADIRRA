## Why

Today every column's semantic type comes from `_infer_semantic_type()` in `api/routes/element.py` — a crude, name-and-dtype heuristic that returns one of a handful of coarse buckets (`identifier`, `coded`, `date`, `monetary`, `other`) with no confidence, no evidence, and no way for a steward to confirm or correct it. This guess is the silent foundation for the semantic-type-mix charts, the chat context, and (downstream) DQ expectations, data-story grain, and BIRD mapping. A weak guess at the spine weakens everything keyed off it. We are replacing it with a confidence-scored, steward-confirmable resolution against a governed vocabulary.

## What Changes

- **BREAKING**: Remove `_infer_semantic_type()` and make the new resolver the single source of semantic typing. No side-by-side; the old heuristic is deleted, not deprecated.
- Introduce a **governed semantic-type vocabulary** (`taxonomy/semantic_types.yaml`, ~30 banking entries) with detectors, validators, and expectations — types are chosen from this list, never invented.
- Add a **deterministic resolution spine** (`core/semantic_resolver.py` + `core/type_validators.py`): multi-evidence scoring (name, schema, pattern, validator, distribution, structural, glossary) producing a ranked, evidence-backed `type_id`, `domain_role`, and `confidence` per column — read from existing catalog stats, no re-profiling.
- Add a **per-column semantic-type store** (`core/semantic_type_store.py`) with its own lifecycle (`proposed` → `confirmed` / `rejected`), keyed `source|schema|table|column`, sticky confirmed types across re-profiling.
- Add an **optional LLM layer** (`agents/semantic_type_agent.py`) for entity resolution and the ambiguous residual only, gated behind `include_ai`, defensive-empty on failure.
- Emit type/value **conflicts through the existing assessment finding shape** — one signal, two consumers, no parallel model.
- Add **API routes** (`api/semantic_types.py`): resolve, get, confirm, reject, steward queue — each audited.
- **Rewire all current consumers** of `_infer_semantic_type` (semantic-type-mix charts, column summaries, chat context) to read from the store, deriving the coarse chart bucket from `domain_role`. Columns not yet resolved report `unresolved` instead of a guess.

## Capabilities

### New Capabilities
- `semantic-type-deduction`: Governed-vocabulary resolution of each source column to a confidence-scored, evidence-backed, steward-confirmable semantic type, with deterministic-first / LLM-for-residual passes, its own confirmation lifecycle, and a conflict-to-finding seam.

### Modified Capabilities
<!-- No existing spec defines _infer_semantic_type at the requirement level; it is internal implementation. Consumers (charts, chat context) are rewired but their observable contract is preserved by deriving the bucket from domain_role. No requirement-level changes to existing specs. -->

## Impact

- **New files**: `taxonomy/semantic_types.yaml`, `core/type_validators.py`, `core/semantic_resolver.py`, `core/semantic_type_store.py`, `agents/semantic_type_agent.py`, `api/semantic_types.py` (router registered in `api/main.py`).
- **Modified files**: `api/routes/element.py` (delete `_infer_semantic_type`, rewire `semantic_type_mix` and per-column `semantic_type`), `agents/chat_agent.py` (semantic-type context now from store).
- **Config**: new resolver thresholds and `include_ai` default in `project.yaml`; LLM uses existing `foundry_client` / agent config (LLM-agnostic constraint preserved).
- **Persistence**: new `semantic_types.yaml` store file (same pattern as `element_states.yaml` / `annotations.yaml`); confirmed types survive profile refresh/rebuild.
- **Behavioural change**: unresolved columns now surface as `unresolved` rather than a heuristic guess — an honest "not yet typed" replaces a crude bucket.
- **Audit**: confirm/reject/resolve recorded via the existing `AuditStore`.

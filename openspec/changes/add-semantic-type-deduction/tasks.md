# Tasks

> Build order follows the deterministic spine first; the LLM layer lands last, gated and inert by default.
> Before building, confirm in place: the catalog loader + column-stats shape, `core/element_state.py`,
> the assessment finding shape (`core/assessment.py`), `foundry_client` / `project.yaml` agent config,
> and router registration in `api/main.py`.

## 1. Vocabulary and validators

- [x] 1.1 Create `taxonomy/semantic_types.yaml` with the ~30-entry banking starter set (identifiers, monetary, temporal, codes, textual, technical), each with `id`, `label`, `category`, `primitive`, `detectors` (name_tokens, value_regex, named validator), `expectations`, optional `regulatory`.
- [x] 1.2 Add a vocabulary loader (pure) that reads the YAML and exposes the id list + per-entry detectors; assignable types are limited to vocabulary ids or `unresolved`.
- [x] 1.3 Create `core/type_validators.py` with pure, LLM-free validators: `mod97`, `iso4217`, `iso3166`, `lei_checksum`, `date_range` (each accepts samples, returns a pass rate, no side effects).
- [x] 1.4 Tests: each validator passes on valid samples, fails on invalid; loader rejects/ignores unknown ids.

## 2. Semantic-type store

- [x] 2.1 Create `core/semantic_type_store.py` cloning `ElementStateStore` (thread-safe, `yaml.safe_dump`, key `source|schema|table|column`).
- [x] 2.2 Record shape: `type_id`, `domain_role`, `confidence`, `state` (`proposed`/`confirmed`/`rejected`), `source` (`rule`/`ai`), `candidates`, `evidence`, `conflict`, `storage_mismatch`, `format`/`format_source`/`format_rationale`, `resolver_version`, `resolved_at`, `confirmed_by`, `confirmed_at`.
- [x] 2.3 Sticky-confirmed merge: re-resolution layers under a `confirmed` record and never overwrites it.
- [x] 2.4 Sticky-rejected merge: a `rejected` record (with any corrected `type_id`) is remembered and not re-surfaced as a fresh `proposed` on re-resolution.
- [x] 2.5 Tests: write/read round-trip; confirmed record preserved across a re-resolution write; rejected record (with correction) preserved and not re-proposed.

## 3. Deterministic resolver (the usable spine)

- [x] 3.1 Create `core/semantic_resolver.py` — Pass 0 evidence gathering from catalog stats only (name, schema, pattern, validator, distribution, structural, glossary), no re-profiling, no source writes.
- [x] 3.2 Pass 1 scoring: weight evidence into ranked `candidates` + top `confidence`; validator pass = decisive(+), validator fail on a name/pattern match = decisive(−) + `conflict: true`.
- [x] 3.3 Convertibility handling: numeric-VARCHAR-to-canonical-date confirms `date` at high confidence with `storage_mismatch: true` (no confidence penalty); fix direction deterministically when a sample forces it; otherwise set `format: undecided`.
- [x] 3.4 Thresholds from `project.yaml` (`≥0.85` propose-high, `0.60–0.85` propose-flag, `<0.60` unresolved); route results, skip LLM when top ≥0.85 and no conflict.
- [x] 3.5 Pass 3 persist: write `proposed` records to the store; respect sticky-confirmed.
- [x] 3.6 Fingerprint cache: re-resolve only when a column's profile fingerprint changes.
- [x] 3.7 Tests: high-confidence IBAN → `iban`, ≥0.85, `source: rule`, no LLM; ambiguous numeric → `unresolved` + queued; date-in-VARCHAR → `date` + `storage_mismatch`; leading-pair>12 → `DDMMYYYY` deterministically; ambiguous direction → `undecided`, queued, no guess.

## 4. Conflict → finding seam

- [x] 4.1 Emit each `conflict: true` through the existing assessment finding shape (`scope`, `target`, `severity`, `category: validity`, `title`, `rationale`, `evidence`, `source`) — no parallel model.
- [x] 4.2 Test: column named `iban` with values failing mod-97 → `conflict: true`, low confidence, and a finding emitted.

> Forward-seam note (not a task): the finding model has no disposition/dismissal overlay yet, so a conflict finding re-fires on every resolve with no "reviewed, acceptable" state. Accepted for the first cut — these findings inherit the finding-disposition overlay when that lands; this re-firing is expected behaviour, not a bug.

## 5. API surface

- [x] 5.1 Create `api/semantic_types.py`: `GET /semantic-types/{source}/{table}` (types + candidates + evidence), `POST .../resolve` (`{include_ai: bool}`), `POST .../{column}/confirm`, `POST .../{column}/reject`, `GET /semantic-types/{source}/queue`.
- [x] 5.2 Confirm sets `confirmed` + `confirmed_by`/`confirmed_at`; reject sets `rejected` + optional corrected `type_id`; both patch the cached value inline (no force-refetch).
- [x] 5.3 Audit confirm/reject/resolve via the existing `AuditStore`; register the router in `api/main.py`.
- [x] 5.4 Tests: GET returns evidence-backed types; resolve honours `include_ai`; queue lists unresolved/low-confidence/conflicted; disposition is audited.

## 6. Replace the legacy heuristic (the rewire)

- [x] 6.1 Inventory every `_infer_semantic_type` call site (source/dataset/table `semantic_type_mix`, per-column summaries, `agents/chat_agent.py`).
- [x] 6.2 Define the explicit `domain_role → legacy bucket` mapping (all 8 roles → `identifier`/`coded`/`date`/`monetary`/`other`): `key`+`identifier` → `identifier`; `code` → `coded`; `temporal` → `date`; `measure` → `monetary`; `dimension`+`descriptive`+`technical` → `other`. Pin this mapping in one shared helper so charts and summaries agree; `unresolved` maps to `other` (or a dedicated `unresolved` bucket if the chart legend allows).
- [x] 6.3 Delete `_infer_semantic_type` from `api/routes/element.py`.
- [x] 6.4 Rewire charts to derive the coarse bucket from the resolved `domain_role` via the 6.2 mapping; rewire per-column `semantic_type` and chat context to read `type_id` (+ role) from the store, with `unresolved` fallback.
- [x] 6.5 Backfill / first-read resolution so day one is not a blank-chart regression: run a one-time deterministic backfill resolve across all catalogs as part of this step (and/or auto-resolve unresolved columns on first read). Charts must show real buckets immediately after the rewire, not 100% `unresolved`.
- [x] 6.6 Regression test: `semantic_type_mix` response shape AND bucket assignments match the 6.2 mapping (not merely the shape); after backfill, a populated catalog yields non-`unresolved` buckets; genuinely unresolved columns report `unresolved`, not a guess.

## 7. Entity profiles (Pass 2a heuristic)

- [x] 7.1 Add a minimal deterministic entity-profile set (e.g. Account, Counterparty) matched against the table's column signature; resolve the entity deterministically on high coverage, with no LLM.
- [x] 7.2 Feed the resolved entity as context prior into residual scoring.
- [x] 7.3 Test: a matching column signature resolves the entity with no LLM call.

## 8. Priors index

- [x] 8.1 Maintain a confirmed-exemplars index (name token + pattern + `type_id`); on confirm, add the column.
- [x] 8.2 Pass 1 consults the index to boost similar columns across the same source.
- [x] 8.3 Test: confirming `counterparty_identifier` boosts a sibling `cpty_ref` on the next resolve.

## 9. Profile-refresh integration

- [x] 9.1 On profile refresh / rebuild, invalidate and re-run the deterministic spine (Passes 0/1/3) for affected columns; reconcile the resolver fingerprint against refreshed stats; re-queue columns dropping below the floor.
- [x] 9.2 Confirmed types stay sticky; refreshed evidence contradicting a confirmed type emits a conflict finding instead of overwriting.
- [x] 9.3 Tests: refresh re-resolves affected columns and reconciles the fingerprint; confirmed-then-contradicted → record holds + conflict finding.

## 10. LLM layer (gated, last)

- [x] 10.1 Create `agents/semantic_type_agent.py` mirroring `agents/assessment_agent.py`: `foundry_client`, json_object output, constrained `type_id` from the supplied vocabulary list, defensive-empty on any error; no hardcoded provider/key/endpoint.
- [x] 10.2 Pass 2a-fallback (entity naming when the heuristic is ambiguous) and Pass 2b (residual column resolution conditioned on entity + siblings + vocabulary id list); for `undecided` formats, propose a `format_*` sub-attribute with `format_source: ai` without re-deciding the `type_id`.
- [x] 10.3 Gate everything behind `include_ai` (default off in `project.yaml`); cache LLM calls by fingerprint.
- [x] 10.4 Tests: with `include_ai=false` no agent is imported/called and deterministic results still return; LLM failure leaves columns `unresolved`/queued with no exception; format facet tie-break is `proposed`, not auto-confirmed.

## 11. Validation

- [x] 11.1 Run the full new test suite (validators, resolver, store, API, rewire regression, gating).
- [x] 11.2 `npx openspec validate "add-semantic-type-deduction" --strict`.
- [x] 11.3 Confirm `project.yaml` carries resolver thresholds + `include_ai` default; confirm no provider/key/endpoint is hardcoded anywhere in the new files.

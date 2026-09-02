## Context

Semantic typing today is a single private helper, `_infer_semantic_type(col)` in `api/routes/element.py`, called from 6+ sites (source/dataset/table `semantic_type_mix` charts, per-column summaries, and the chat context builder in `agents/chat_agent.py`). It maps a column to a coarse bucket from name tokens and `data_type` alone — no confidence, no evidence, no steward control, no persistence.

The codebase already provides every pattern this feature needs, verified in place:

- **Per-element YAML store with a lock**: `core/element_state.py` (`ElementStateStore`, `threading.Lock`, `_load`/`_save`, key `source|schema|table|column`).
- **Deterministic rule layer + gated AI layer**: `core/assessment.py` (pure deterministic findings) paired with `agents/assessment_agent.py` (LLM, `foundry_client`, `text={"format":{"type":"json_object"}}`, defensive `return []` on any failure).
- **Catalog YAML as the stats source** (row/null/distinct/sample stats already computed — no re-profiling needed).
- **Router registration** in `api/main.py` (`app.include_router(...)`), audit via the existing `AuditStore` as `api/routes/insights.py` does.
- **Fingerprint/schema-hash caching** in `catalog_builder.py` / `assessment_agent.py`.

The LLM-agnostic constraint is hard: provider/keys/endpoint come only from `project.yaml` + env via `foundry_client.create_foundry_client()`; no provider name is hardcoded.

## Goals / Non-Goals

**Goals:**
- Resolve each column to a governed-vocabulary `type_id` + `domain_role` + `confidence`, with an explainable evidence trail.
- Deterministic spine fully usable and testable **standalone**; LLM is an optional enhancement behind `include_ai`, off by default.
- Steward lifecycle (`proposed` → `confirmed`/`rejected`) owned by the type, separate from definition lifecycle; confirmed types sticky across re-profiling.
- Type/value conflicts emitted through the **existing** assessment finding shape (one signal, two consumers).
- Full, clean replacement of `_infer_semantic_type` — all consumers rewired to the store; no coexistence.

**Non-Goals:**
- Re-profiling or writing to source data (read catalog stats only).
- Inventing type labels (LLM constrained to the supplied vocabulary id list, or `unresolved`).
- Auto-confirming (resolution only ever proposes).
- Solving the broader data-freshness backlog (DF1 server-response-as-truth, DF4 profile-version stamping) — build to current cache/refresh behaviour, revisit knowingly when those land.
- BIRD/DQ-expectation consumption of the type — out of scope here; the vocabulary carries `expectations`/`regulatory` fields as a forward seam only.

## Decisions

**1. Governed vocabulary as a YAML file (`taxonomy/semantic_types.yaml`), not LLM free-text.**
~30 banking entries (iban, bic, lei, monetary_amount, currency_code, country_code, reporting_date, technical_flag, …), each with `category`, `primitive`, `detectors` (name_tokens, value_regex, named validator), `expectations`, optional `regulatory`. Rationale: a constrained, maintained vocabulary is the primary hallucination control and the join key for downstream DQ/BIRD. Alternative (free LLM labels) rejected — unbounded, unmappable, untestable.

**2. Two facets per column: `domain_role` and `type_id`.** Role (key/identifier/measure/dimension/code/temporal/descriptive/technical) is the structural job; type_id is the specific concept. Keep both — role drives some behaviour even when type_id is `unresolved`, **and** the existing coarse chart bucket is derived from `domain_role`, preserving the current chart UI with zero frontend change.

**3. Deterministic-first, LLM-for-residual.** Passes 0–1 (evidence + scoring) resolve the easy majority deterministically; only the ambiguous tail (`<0.85` or conflicted) reaches the LLM, and only when `include_ai=true`. Rationale: cost control across ~2290 columns and a testable pure core. Validator pass = decisive(+), validator fail on a name/pattern-matched candidate = decisive(−) + `conflict:true`.

**4. Store clones `ElementStateStore`.** `core/semantic_type_store.py` reuses the exact key shape, lock discipline, and `yaml.safe_dump` persistence. Confirmed records are sticky: re-resolution layers *under* a confirmed type (mirrors the `annotations.yaml` merge); contradiction emits a conflict finding rather than overwriting.

**5. Conflict reuses the assessment finding shape.** A `conflict:true` is both a low-confidence type and a validity finding; emit once through the existing shape (`scope/target/severity/category/title/rationale/evidence/source`). Rationale: avoids building observations twice — the seam flagged between typing and DQ.

**6. Full replacement of `_infer_semantic_type`.** Delete the helper; rewire all consumers to the store. Charts derive the bucket from `domain_role`; per-column `semantic_type` becomes the richer `type_id` (+role) with `unresolved` fallback for not-yet-resolved columns. Rationale: an honest "not yet typed" beats a crude guess; one source of truth.

**7. LLM layer mirrors `assessment_agent.py` exactly.** `agents/semantic_type_agent.py` uses `foundry_client`, json_object output, constrained `type_id` choice, and defensive-empty on any error. No provider hardcoding.

**8. Semantic type is the meaning, not the storage — four orthogonal flags, never collapsed.** A field carrying dates is semantically a `date` even when stored as a non-canonical VARCHAR. The resolver therefore separates four distinct signals that a naive design would conflate:

- **`conflict`** — values *refute* the hypothesis (named `iban`, fails mod-97). Questions the *meaning*; higher severity; emits a finding (Decision 5).
- **`storage_mismatch` / `format_*`** — values *confirm* the hypothesis but the representation is untidy (it **is** a date, stored as an ambiguous string). A *cleanup* flag, not a doubt. MUST NOT be collapsed into `conflict`.
- **`unresolved`** — too *little* signal; needs more evidence. Queue says "type this."
- **`undecided`** — *strong but conflicting* signal (clearly a date, genuinely ambiguous direction); needs a *human decision*, not more evidence. Modelled as a high-confidence `type_id` with one flagged sub-attribute (e.g. `format: undecided`) so the field keeps its semantic story while only the doubtful facet is queued.

Convertibility is *confirmation, not detection*: a numeric VARCHAR whose values parse to a canonical date under one consistent direction resolves to `date` at **high** confidence with `storage_mismatch: true` — the VARCHAR-ness is a flag, never a confidence penalty. Determinism disambiguates where it can (any first-pair > 12 forces `DDMMYYYY`); where no sample disambiguates, it is genuinely `undecided` and is **not** guessed. The LLM (Pass 2b, residual only) is handed the *specific* question — "which direction?" — with locale/sibling/regulatory context, proposes a `format_*` sub-attribute (`format_source: ai`), and never re-decides what convertibility already settled. Rationale: a blank "AI, type this column" is both costlier and less accurate; AI is the residual tie-breaker, not the typing layer.

## Risks / Trade-offs

- **Rewiring breakage across 6+ call sites** → Inventory every `_infer_semantic_type` caller first; keep the chart bucket contract identical by deriving from `domain_role`; add a regression test asserting `semantic_type_mix` shape is unchanged.
- **`unresolved` appears where a guess used to** → Intended, but the resolve trigger must be reachable from the flows that render these charts; document the behavioural change and provide the resolve endpoint + queue.
- **Priors index (confirm-propagation) is the hardest piece to test** → Keep the first cut dead simple (name-token + pattern + type_id exemplars consulted in Pass 1); ship it last; isolate behind one test.
- **Profile refresh/rebuild must re-trigger deterministic resolution** → On refresh, invalidate and re-run Passes 0/1/3 for affected columns and reconcile the resolver's own fingerprint (clearing the element cache alone does not invalidate fingerprint-keyed resolution). Confirmed types hold.
- **Sparse glossary** → Treat glossary linkage as a weak vote only, never a requirement (design already mandates this).
- **Vocabulary drift / regex brittleness** → Validators are pure, named functions in `core/type_validators.py` with targeted pass/fail tests; vocabulary changes are data, not code.

## Migration Plan

1. Land deterministic spine + store + API (no consumer changes yet) — additive, safe.
2. Rewire consumers in one focused change: delete `_infer_semantic_type`, point charts/summaries/chat at the store, derive bucket from `domain_role`. Single regression checkpoint on chart shape + chat context.
3. Add LLM layer behind `include_ai=false` default — inert until explicitly enabled.
4. Rollback: the resolver files are additive; reverting the consumer rewire (step 2) restores prior behaviour without touching the new store. No data migration — the store file is created lazily like `element_states.yaml`.

## Open Questions

- Final threshold values (`≥0.85` propose-high, `0.60–0.85` propose-flag, `<0.60` unresolved) — start with these in `project.yaml`, tune against the real ~2290-column corpus.
- Entity-profile set for Pass 2a heuristic (Account, Counterparty, …) — seed a minimal set; expand as confirmations accumulate.

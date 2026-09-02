## Context

The Reference Dataspace (Phases 1–2) already exposes a read-only aggregate at `GET /reference-data`
that scans source catalogs, selects fields whose effective semantic `type_id` ∈
`{reference_code, currency_code, country_code}`, and returns per-field code lists reconciled against
observed data (`in_source` / `in_list` / `rogue` / `unused`). Each field response already carries
placeholder fields `set_kind` (always `"local"`), `bound_set_id` (always `null`), and `domain`
(always `null`) — reserved precisely for this change.

Code meanings today live per field in `ElementStateStore` metadata (`refdata_meanings`,
`refdata_status`), keyed by the composite `source|schema|table|column`. Governed vocabularies in this
repo are file-based YAML (`governance/semantic_types.yaml`, `glossary/glossary.yaml`) loaded through
small store classes (`core/semantic_type_store.py`, `core/element_state.py`). This change follows the
same pattern rather than introducing a database.

## Goals / Non-Goals

**Goals:**
- Make a reference code list a reusable, governed object (`ReferenceSet`) that many fields can share.
- Let an analyst bind a field to a set from the Asset Workspace, with a suggestion from the field's
  semantic type.
- Resolve a bound field's codes from its set (still reconciled against observed data) in the existing
  aggregate endpoint, populating the reserved `set_kind` / `bound_set_id` placeholders.
- Give the Reference Dataspace a read-only "Browse by set" view that shows each set once and the
  fields that consume it.
- Ship two seeded standard sets (ISO 4217, ISO 3166) as a representative subset.

**Non-Goals:**
- External ingestion of full standards from iso.org or any registry (later phase).
- Editing set contents through the UI, or steward approval workflow for sets (sets are hand-authored
  and read-only this phase).
- Approval provenance (`approved_by` / `approved_at`), deep-link consumption in Asset Workspace, and
  write-path status validation — tracked separately, out of scope here.
- Multi-set binding per field, versioning, aliases, and effective dates (fields defined as optional
  in the model but not exercised).

## Decisions

**D1 — Store sets in one governed YAML (`governance/reference_sets.yaml`).**
Matches `semantic_types.yaml` / `glossary.yaml`; no new infra, human-readable, git-diffable, seedable
by hand. A small `core/reference_set_store.py` loads and caches it (mirroring
`semantic_type_store.py`). *Alternative rejected:* per-source YAML or DB table — overkill at prototype
scale and inconsistent with existing governance files.

**D2 — Store the field→set binding as a new overlay in `ElementStateStore`.**
Bindings are per-field facts keyed by the same `source|schema|table|column` composite already used for
meanings/status, and must survive re-profiling — exactly what the element-state overlays already do.
Add a `refdata_bound_set_id` key alongside `refdata_meanings`. *Alternative rejected:* a separate
binding store — needless duplication of the same key space and lifecycle.

**D3 — Bound set is authoritative for meanings; inline meanings become fallback.**
When a field is bound, `codes[].meaning` resolves from the set's `entries`; the field's own
`refdata_meanings` are retained (so unbinding restores them) but not shown as authoritative. Observed
data still drives `share_pct`, `in_source`, `rogue`, `unused` — reconciliation is unchanged, only the
meaning source swaps. `set_kind` becomes the bound set's `kind`; unbound fields stay `"local"`.

**D4 — Suggestion is a deterministic semantic-type → standard map, not an LLM call.**
`currency_code → iso_4217_currency`, `country_code → iso_3166_country`. Keeps the feature
LLM-agnostic and predictable; the analyst always confirms. *Alternative rejected:* LLM-proposed
binding — unnecessary for a fixed, tiny mapping and adds a provider dependency.

**D5 — Two new read-only endpoints; "used by N fields" computed on the client.**
`GET /reference-sets` (list) and `GET /reference-sets/{id}` (detail). The Browse-by-set view reuses
the existing `/reference-data` response (which now carries `bound_set_id` per field) and the set list,
grouping client-side in `referenceDataspaceDisplay.ts`. *Alternative rejected:* a dedicated
server-side "sets with consumers" endpoint — the client already holds both halves; avoids a third API.

**D6 — Stable snake_case set IDs.** e.g. `iso_4217_currency`, `iso_3166_country`. IDs are the binding
target and must never change; `name` / `standard_ref` are display and may evolve.

## Risks / Trade-offs

- **Seed subset is incomplete** → valid real codes absent from the subset will show as `rogue`
  ("in source, not in list"). *Mitigation:* seed sets are explicitly representative demos; note this
  in the UI/set metadata so the flag is understood, not mistaken for a data error.
- **Binding vs inline-meaning ambiguity** → a field could have both. *Mitigation:* D3 precedence rule
  (set wins, inline kept as restorable fallback); only one is ever authoritative.
- **Set entry status (`active`/`deprecated`) vs field `refdata_status`** → two different status
  concepts. *Mitigation:* keep them separate and named distinctly; the field's governance status is
  unchanged by binding.
- **No auth gate on the new read endpoints** → consistent with the rest of the prototype; acceptable
  now, flagged for the future security pass.
- **Backwards compatibility** → unbound fields must behave exactly as today. *Mitigation:* resolution
  only diverges when `refdata_bound_set_id` is present; all existing tests must stay green.

## Open Questions

- Is **unbinding** (clearing a field's set) in scope for this phase, or bind-only? (Assumed: include a
  simple unbind, since D3 already retains inline meanings for restore.)
- Should the seeded sets carry a `status` of `approved` so they read as "of record", or `candidate`
  until a steward blesses them? (Assumed: `approved`, since they represent published standards.)

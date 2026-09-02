## ADDED Requirements

### Requirement: Governed semantic-type vocabulary

The system SHALL maintain a governed vocabulary of semantic types in `taxonomy/semantic_types.yaml`. Each entry SHALL define an `id`, `label`, `category`, allowed `primitive` types, `detectors` (name tokens, value regex, and optional named validator), and `expectations`. Resolution SHALL only assign a `type_id` that exists in this vocabulary, or the reserved value `unresolved`.

#### Scenario: Vocabulary loads and is the only allowed type source
- **WHEN** the resolver loads the vocabulary
- **THEN** every assignable `type_id` comes from the vocabulary file
- **AND** no type label is invented outside the vocabulary

#### Scenario: Technical category excludes business mapping
- **WHEN** a column resolves to a type whose category is `technical`
- **THEN** the column is marked as never linking to a glossary term or BIRD target
- **AND** this is distinguished from an `unresolved` column

### Requirement: Pure type validators

The system SHALL provide pure, LLM-free validators in `core/type_validators.py` (at minimum `mod97`, `iso4217`, `iso3166`, `lei_checksum`, `date_range`). Each validator SHALL accept sample values and return a pass rate without side effects.

#### Scenario: Validator passes on valid samples
- **WHEN** a validator runs against values that conform to its rule
- **THEN** it reports a pass rate at or near 1.0

#### Scenario: Validator fails on invalid samples
- **WHEN** a validator runs against values that violate its rule
- **THEN** it reports a reduced pass rate reflecting the violations

### Requirement: Deterministic column resolution

The system SHALL resolve each column deterministically from existing catalog statistics without re-profiling source data. It SHALL gather multi-source evidence (name, schema, pattern, validator, distribution, structural, glossary), weight it into ranked candidates, and produce a top `type_id`, a `domain_role`, a `confidence` in [0.0, 1.0], a ranked `candidates` list, and an `evidence` trail. The resolver SHALL never write to source data.

#### Scenario: High-confidence deterministic resolution skips the LLM
- **WHEN** a column named with an IBAN token has sample values passing the mod97 validator
- **THEN** it resolves to `type_id: iban` with confidence ≥ 0.85 and `source: rule`
- **AND** no LLM call is made for that column

#### Scenario: Ambiguous column becomes unresolved
- **WHEN** an ambiguous numeric column has no entity context and no decisive evidence
- **THEN** it resolves to `unresolved`
- **AND** it is placed on the steward queue with no fabricated type

#### Scenario: Confidence thresholds drive routing
- **WHEN** a column's top confidence is below the configured high threshold but above the floor
- **THEN** it is proposed but flagged for review
- **WHEN** a column's top confidence is below the floor
- **THEN** it is marked `unresolved` and queued

### Requirement: Type/value conflict detection and finding emission

The system SHALL set `conflict: true` when decisive evidence disagrees (for example, a name or pattern matches a candidate but its validator refutes the values). For each conflict the system SHALL emit a finding using the existing assessment finding shape (`scope`, `target`, `severity`, `category`, `title`, `rationale`, `evidence`, `source`) rather than a parallel model.

#### Scenario: Name/value conflict raises a finding
- **WHEN** a column named with an IBAN token has values that fail the mod97 validator
- **THEN** the record has `conflict: true` and low confidence
- **AND** a finding is emitted with category `validity` describing the conflict

### Requirement: Context-aware entity and residual resolution

The system SHALL resolve a table's business entity once from its column ensemble using deterministic entity profiles first, falling back to the LLM only when ambiguous. Residual (low-confidence) columns SHALL then be re-resolved conditioned on the resolved entity and sibling column types. The LLM SHALL be constrained to choose a `type_id` from the supplied vocabulary list or `unresolved`, and SHALL never invent a label.

#### Scenario: Deterministic entity profile match avoids the LLM
- **WHEN** a table's column signature matches an entity profile with high coverage
- **THEN** the entity is resolved deterministically with no LLM call

#### Scenario: LLM residual resolution is constrained
- **WHEN** the LLM resolves a residual column
- **THEN** it returns a `type_id` drawn only from the supplied vocabulary list or `unresolved`
- **AND** any failure leaves the column `unresolved` and queued

### Requirement: LLM layer is gated and defensive

The system SHALL gate all LLM resolution behind an `include_ai` flag that defaults to off. The deterministic spine SHALL return complete results with `include_ai=false`. The LLM agent SHALL use the existing `foundry_client` and `project.yaml` agent configuration with no hardcoded provider, key, or endpoint, and SHALL return empty/`unresolved` on any error.

#### Scenario: AI disabled still returns deterministic results
- **WHEN** resolution runs with `include_ai=false`
- **THEN** no semantic-type agent is imported or called
- **AND** deterministic results are still returned

#### Scenario: LLM failure is non-fatal
- **WHEN** the LLM call errors or returns malformed output
- **THEN** the affected columns remain `unresolved` and queued
- **AND** no exception propagates to the caller

### Requirement: Semantic-type persistence and lifecycle

The system SHALL persist one semantic-type record per column in `core/semantic_type_store.py`, keyed `source|schema|table|column`, using thread-safe YAML persistence via `yaml.safe_dump`. Each record SHALL carry its own lifecycle state: `proposed`, `confirmed`, or `rejected`, independent of any definition lifecycle. Resolution SHALL only ever produce `proposed` records and SHALL NOT auto-confirm. Both `confirmed` and `rejected` records SHALL be sticky across re-resolution: re-resolution layers under them and never re-surfaces a disposed type as a fresh `proposed`.

#### Scenario: Resolution proposes only
- **WHEN** the resolver writes a result
- **THEN** the record state is `proposed`
- **AND** no record is automatically set to `confirmed`

#### Scenario: Confirmed types are sticky across re-resolution
- **WHEN** a column has a `confirmed` type and resolution runs again
- **THEN** the confirmed record is preserved and not overwritten by a fresh `proposed` record

#### Scenario: Rejected types are sticky across re-resolution
- **WHEN** a column has a `rejected` record (with any corrected `type_id`) and resolution runs again
- **THEN** the rejected record is preserved and the same type is not re-surfaced as a fresh `proposed`

#### Scenario: Refreshed evidence contradicting a confirmed type raises a finding
- **WHEN** a column confirmed as `iban` is re-profiled with values that now fail the mod97 validator
- **THEN** the confirmed record is preserved
- **AND** a conflict finding is emitted rather than a silent overwrite

### Requirement: Steward disposition and queue

The system SHALL allow a steward to confirm or reject a proposed type. Confirm SHALL set state `confirmed` with `confirmed_by`/`confirmed_at`; reject SHALL set state `rejected` and MAY persist a corrected `type_id`. Disposition SHALL persist to the store and patch the cached value inline without forcing a refetch. The system SHALL expose a queue of unresolved, low-confidence, and conflicted columns as a steward worklist. Confirm, reject, and resolve actions SHALL be audited via the existing `AuditStore`.

#### Scenario: Confirm updates state and patches cache inline
- **WHEN** a steward confirms a proposed type
- **THEN** the record state becomes `confirmed` with confirmer and timestamp
- **AND** the cached value is patched inline without a force-refetch

#### Scenario: Reject with correction persists the correction
- **WHEN** a steward rejects a proposed type and supplies a corrected `type_id`
- **THEN** the record state becomes `rejected` and the corrected type is persisted

#### Scenario: Queue surfaces the steward worklist
- **WHEN** a steward requests the queue for a source
- **THEN** the response lists unresolved, low-confidence, and conflicted columns

#### Scenario: Disposition is audited
- **WHEN** a confirm, reject, or resolve action completes
- **THEN** the action is recorded via the existing audit store

### Requirement: Confirmation priors propagation

The system SHALL maintain a priors index of confirmed exemplars (name token, pattern, `type_id`). Deterministic scoring SHALL consult this index to boost similar columns across the same source, so that confirmations compound.

#### Scenario: Confirmation boosts a similar sibling
- **WHEN** a steward confirms a `counterparty_identifier` column
- **THEN** a subsequent resolve boosts a similar sibling column (for example `cpty_ref`) toward the same type

### Requirement: Resolution re-triggers on profile refresh

The system SHALL re-run deterministic resolution for affected columns when a profile refresh or rebuild changes the catalog statistics. It SHALL reconcile its own fingerprint cache against the refreshed statistics, since clearing the element cache alone does not invalidate fingerprint-keyed resolution. Columns whose confidence drops below the floor SHALL be re-queued. Confirmed types SHALL remain sticky per the persistence requirement.

#### Scenario: Profile refresh re-resolves affected columns
- **WHEN** a profile refresh or rebuild updates a table's statistics
- **THEN** deterministic resolution re-runs for the affected columns
- **AND** the resolver fingerprint is reconciled against the refreshed statistics

### Requirement: Replacement of legacy semantic-type inference

The system SHALL remove the legacy `_infer_semantic_type` heuristic and make the semantic-type store the single source of semantic typing. All existing consumers — the source, dataset, and table `semantic_type_mix` charts, per-column summaries, and the chat context builder — SHALL read from the store. The coarse chart bucket SHALL be derived from the resolved `domain_role`, preserving the existing chart contract. Columns not yet resolved SHALL report `unresolved` rather than a heuristic guess.

#### Scenario: Legacy helper is removed
- **WHEN** the change is implemented
- **THEN** `_infer_semantic_type` no longer exists and no code calls it

#### Scenario: Chart bucket derived from domain_role
- **WHEN** a `semantic_type_mix` chart is built
- **THEN** each column's coarse bucket is derived from its resolved `domain_role`
- **AND** the chart response shape is unchanged from before the replacement

#### Scenario: domain_role maps to a fixed legacy bucket
- **WHEN** a resolved `domain_role` is converted to a coarse chart bucket
- **THEN** `key` and `identifier` map to `identifier`, `code` maps to `coded`, `temporal` maps to `date`, `measure` maps to `monetary`, and `dimension`, `descriptive`, and `technical` map to `other`
- **AND** the same mapping is used by charts and per-column summaries

#### Scenario: Backfill prevents a blank-chart regression
- **WHEN** the legacy helper is replaced and a catalog has already been profiled
- **THEN** a one-time deterministic backfill resolves its columns so charts show real buckets immediately
- **AND** charts do not report every column as `unresolved` solely because resolution had not been triggered

#### Scenario: Unresolved columns are honest
- **WHEN** a column has not yet been resolved
- **THEN** consumers report its semantic type as `unresolved`
- **AND** no heuristic guess is substituted

### Requirement: Semantic-type API surface

The system SHALL expose routes in `api/semantic_types.py`, registered in `api/main.py`: get resolved types for a table (with candidates and evidence), trigger resolution (body `{include_ai: bool}`), confirm a column type, reject a column type, and get the steward queue for a source.

#### Scenario: Get returns evidence-backed types
- **WHEN** a client requests resolved types for a table
- **THEN** the response includes each column's `type_id`, `domain_role`, `confidence`, ranked `candidates`, and `evidence`

#### Scenario: Resolve honours include_ai
- **WHEN** a client triggers resolution with `include_ai` in the body
- **THEN** the LLM layer runs only when `include_ai` is true

### Requirement: Storage mismatch and ambiguous-format handling

The system SHALL treat the semantic type as the meaning a field carries, not its physical storage. When a column's values confirm a type but the representation is non-canonical (for example dates stored as a numeric VARCHAR), the system SHALL resolve the type at full confidence and set a `storage_mismatch` flag rather than lowering confidence or setting `conflict`. The system SHALL keep four signals distinct and never collapse them: `conflict` (values refute the type), `storage_mismatch`/`format_*` (values confirm the type but storage is untidy), `unresolved` (too little signal), and `undecided` (strong but genuinely ambiguous facet). Convertibility SHALL be treated as confirmation; deterministic resolution SHALL disambiguate format where a sample forces it and SHALL NOT guess where no sample disambiguates.

#### Scenario: Date in a VARCHAR resolves with a storage flag
- **WHEN** a numeric VARCHAR column's values all convert to a canonical date under one consistent direction
- **THEN** it resolves to `type_id: date` at high confidence with `storage_mismatch: true`
- **AND** `conflict` is false and confidence is not penalised for the storage format

#### Scenario: Ambiguous date direction is undecided, not unresolved
- **WHEN** a column clearly carries dates but no sample disambiguates the direction
- **THEN** the type resolves as `date` with high confidence and a `format` sub-attribute flagged `undecided`
- **AND** the column is queued for a human format decision rather than marked `unresolved`
- **AND** the resolver does not guess a direction

#### Scenario: Distribution forces a deterministic format decision
- **WHEN** any sample value's leading pair exceeds 12 (for example `25112021`)
- **THEN** the resolver fixes the direction to `DDMMYYYY` deterministically without an LLM call

#### Scenario: LLM tie-breaks the format facet only
- **WHEN** the format facet is `undecided` and resolution runs with `include_ai=true`
- **THEN** the LLM proposes a `format_*` sub-attribute with `format_source: ai` and a grounded rationale
- **AND** it does not re-decide the already-confirmed `type_id`

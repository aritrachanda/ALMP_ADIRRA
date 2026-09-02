import { apiFetch, apiPatch, apiPost, apiPut } from './client';
import { fetchWithRealProgress } from './sse';
import type { DQBadge } from '../pages/dqBadgeDisplay';
import type { DatasetDQBadge } from '../pages/datasetDqDisplay';
import type { AiError } from '../composables/useAiError';

export interface GovStateCounts {
  empty: number; draft: number; in_review: number; approved: number; bounced: number;
  // Legacy yaml-backend keys that may still appear in old stored data.
  defined?: number; returned?: number; rejected?: number; withdrawn?: number; revoked?: number;
}

export type { DQBadge } from '../pages/dqBadgeDisplay';
export type { DatasetDQBadge } from '../pages/datasetDqDisplay';

export interface SubmissionStatus {
  submitted_at: string | null;
  submitted_by: string | null;
  decided_at: string | null;
  decided_by: string | null;
  /** Postgres mode also emits 'returned' | 'withdrawn' | 'revoked'; kept broad. */
  decision: 'approved' | 'rejected' | 'returned' | 'withdrawn' | 'revoked' | null;
  reject_reason: string | null;
}

export interface ColumnStats {
  null_pct: number | null;
  distinct_count: number | null;
  min_value: unknown;
  max_value: unknown;
  row_count: number | null;
  sample_values: unknown[];
  duplicate_count?: number | null;
  placeholder_count?: number | null;
  uniqueness_pct?: number | null;
  top_values?: { value: unknown; count: number }[];
  length_min?: number | null;
  length_max?: number | null;
  length_avg?: number | null;
  inferred_pattern?: string | null;
  pattern_confidence?: number | null;
}

export interface GlossaryTermRef {
  id: string;
  title: string;
  business_description: string;
  detailed_description: string;
  status: string;
  steward: string;
  related_objects: string[];
}

export interface MappingCandidate {
  target: string;
  target_schema: string;
  target_table: string;
  target_framework: string;
  target_column: string;
  confidence: number | null;
  rationale: string;
  transformation_type: string;
  status: string;
  notes: string;
}

/**
 * Canonical Phase-5 governance vocabulary (Postgres backend). The legacy
 * draft/defined/approved words remain in the union so the app keeps type-checking
 * while YAML mode is still live (pre-flip). Prefer the canonical words for new code.
 */
export type CanonicalStatus =
  | 'empty' | 'draft' | 'in_review' | 'approved' | 'returned' | 'rejected';
export type LegacyLifecycleState = 'draft' | 'defined' | 'approved';
export type LifecycleState = CanonicalStatus | LegacyLifecycleState;

export type ForeignKeyBasis = 'exact_name' | 'table_reference' | 'abbreviation';
export type ForeignKeyConfidence = 'high' | 'medium';

export interface ForeignKeyRef {
  references_table: string;
  references_column: string | null;
  /** true = DB-declared FOREIGN KEY constraint; false = name/type-inferred (no physical constraint). */
  declared: boolean;
  confidence?: ForeignKeyConfidence | null;
  basis?: ForeignKeyBasis | null;
  /** Count of child rows whose FK value has no matching parent row. */
  orphan_count?: number | null;
}

export interface ForeignKeyEntry extends ForeignKeyRef {
  column: string;
}

export interface ReferencedByEntry {
  table: string;
  schema: string;
  columns: string[];
  references_column: string[];
  declared: boolean;
  confidence?: ForeignKeyConfidence | null;
  basis?: ForeignKeyBasis | null;
}

export interface ElementDetail {
  source: string;
  schema: string;
  table: string;
  column: string;
  data_type: string;
  foreign_key?: ForeignKeyRef | null;
  semantic_type: string;
  semantic_domain_role?: string;
  semantic_evidence?: Array<{ kind?: string; signal?: string; weight?: string }>;
  business_name: string;
  stats: ColumnStats;
  lifecycle_state: LifecycleState;
  /** PII flag (semantic vocabulary is_pii OR profiler value-pattern). */
  pii?: boolean;
  pii_category?: string | null;
  /** DQ badge (U2b) — full breakdown on the element view; null when unavailable. */
  dq?: DQBadge | null;
  /** Assessment scope (U2c); absent = in-scope. */
  assessment_scope?: 'in_scope' | 'out_of_scope';
  findings: unknown[];
  glossary_term: GlossaryTermRef | null;
  mapping_candidates: MappingCandidate[];
  audit_history: unknown[];
  table_description: string | null;
  column_description: string | null;
  metadata?: {
    created_by: string | null;
    created_at: string | null;
    updated_at: string | null;
    is_ai_generated: boolean;
    business_name_is_ai: boolean;
    mapping_instructions: string | null;
  };
  submission?: SubmissionStatus;
  /** Latest lifecycle status update for the interpretation (5b.3.2 #12). */
  last_status?: { action: string | null; at: string | null };
}

export interface TableEntry {
  schema: string;
  table_name: string;
  description: string | null;
  row_count: number | null;
  columns: {
    name: string; data_type: string; finding_count?: number; dq?: DQBadge | null;
    distinct_count?: number | null; pii?: boolean;
    /** Governance lifecycle state, already bulk-fetched — no per-column call needed. */
    lifecycle_state?: LifecycleState;
    /** Derived semantic-type disposition: accepted | pending | unresolved. */
    semantic_state?: string;
  }[];
}

export interface SemanticTypeMix {
  type: string;
  /** Display override for types that are a subset of another category rather
   *  than a same-level sibling (e.g. "key" → "Identifier (Key)") — use this
   *  instead of capitalizing `type` when present. */
  label?: string | null;
  count: number;
  color: string;
}

export interface ObservationMatrixEntry {
  severity: string;
  rule_count: number;
  ai_count: number;
}

export interface ColumnSummary {
  name: string;
  data_type: string;
  semantic_type: string;
  /** Semantic domain role (natural_id | surrogate_id | key | code | ...). 'key' tags a primary-key column. */
  semantic_domain_role?: string;
  /** Derived semantic-type disposition (U2c): accepted | pending | unresolved. */
  semantic_state?: string;
  /** null when this column has never been profiled — "not yet measured" */
  completeness: number | null;
  lifecycle_state: LifecycleState;
  observation_count: number;
  dq?: DQBadge | null;
  /** Assessment scope (U2c); absent = in-scope. */
  assessment_scope?: 'in_scope' | 'out_of_scope';
  distinct_count: number | null;
  description: string | null;
  description_is_ai: boolean;
  business_name: string | null;
  business_name_is_ai: boolean;
  /** PII flag (semantic vocabulary is_pii OR profiler value-pattern). */
  pii?: boolean;
  foreign_key?: ForeignKeyRef | null;
}

export interface DatasetOverview {
  source: string;
  schema: string;
  table_name: string;
  description: string | null;
  row_count: number;
  column_count: number;
  /** null when no column has ever been profiled — "not yet measured", not 0%/100% */
  completeness: number | null;
  duplicate_rows: number;
  primary_key: string[];
  inferred_primary_key?: string[];
  generated_at: string | null;
  /** Real "has this table ever been profiled" timestamp, no catalog-generation fallback. */
  profiled_at: string | null;
  /** D11's authoritative "has this table been profiled" flag — false for a freshly-onboarded
   *  or reset-to-baseline table. */
  is_profiled: boolean;
  semantic_type_mix: SemanticTypeMix[];
  governance_state: GovStateCounts;
  columns_summary: ColumnSummary[];
  foreign_keys: ForeignKeyEntry[];
  referenced_by: ReferencedByEntry[];
  /** Dataset-level DQ roll-up (U4a, §15) with score-history trend; null when unavailable. */
  dataset_dq?: DatasetDQBadge | null;
}

export async function getSourceTables(source: string): Promise<TableEntry[]> {
  return apiFetch<TableEntry[]>(`/api/element/${source}/tables`);
}

export async function getTableOverview(
  source: string,
  table: string,
  schema?: string,
): Promise<DatasetOverview> {
  const qs = schema ? `?schema=${encodeURIComponent(schema)}` : '';
  return apiFetch<DatasetOverview>(`/api/element/${source}/${table}/overview${qs}`);
}

/** Same data as {@link getTableOverview}, with real (non-fabricated) stage progress. */
export async function streamTableOverview(
  source: string,
  table: string,
  schema: string | undefined,
  onProgress: (completed: number) => void,
  onDetail: (text: string, fraction?: number, total?: number) => void,
  signal?: AbortSignal,
): Promise<DatasetOverview> {
  const qs = schema ? `?schema=${encodeURIComponent(schema)}` : '';
  return fetchWithRealProgress<DatasetOverview>(
    `/api/element/${source}/${table}/overview/stream${qs}`, onProgress, onDetail, signal,
  );
}

export async function getDatasetDq(
  source: string,
  table: string,
  schema?: string,
): Promise<DatasetDQBadge> {
  const qs = schema ? `?schema=${encodeURIComponent(schema)}` : '';
  return apiFetch<DatasetDQBadge>(`/api/element/${source}/${table}/dataset-dq${qs}`);
}

export async function getElement(
  source: string,
  table: string,
  column: string,
  schema?: string,
): Promise<ElementDetail> {
  const qs = schema ? `?schema=${encodeURIComponent(schema)}` : '';
  return apiFetch<ElementDetail>(`/api/element/${source}/${table}/${column}${qs}`);
}

/** Same data as {@link getElement}, with real (non-fabricated) stage progress. */
export async function streamElement(
  source: string,
  table: string,
  column: string,
  schema: string | undefined,
  onProgress: (completed: number) => void,
  onDetail: (text: string, fraction?: number) => void,
  signal?: AbortSignal,
): Promise<ElementDetail> {
  const qs = schema ? `?schema=${encodeURIComponent(schema)}` : '';
  return fetchWithRealProgress<ElementDetail>(
    `/api/element/${source}/${table}/${column}/stream${qs}`, onProgress, onDetail, signal,
  );
}

export async function updateLifecycleState(
  source: string,
  table: string,
  column: string,
  state: LifecycleState,
  schema?: string,
): Promise<{ lifecycle_state: LifecycleState }> {
  const qs = schema ? `?schema=${encodeURIComponent(schema)}` : '';
  return apiPatch<{ lifecycle_state: LifecycleState }>(
    `/api/element/${source}/${table}/${column}/state${qs}`,
    { state },
  );
}

/**
 * Force a fresh DQ score for one column (Polish Batch Task 6) — the manual
 * escape hatch bypassing the cached/heal path `getElement`'s `dq` field uses.
 * Returns the full breakdown, same shape as the element's `dq` badge.
 */
export async function refreshElementDq(
  source: string,
  table: string,
  column: string,
  schema?: string,
): Promise<DQBadge> {
  const qs = schema ? `?schema=${encodeURIComponent(schema)}` : '';
  return apiPost<DQBadge>(`/api/element/${source}/${table}/${column}/dq/refresh${qs}`, {});
}

export interface ScopeUpdateResult {
  column: string;
  schema: string;
  assessment_scope: 'in_scope' | 'out_of_scope';
  scope_reason: string | null;
  scoped_by: string | null;
  scoped_at: string | null;
}

/**
 * Set the assessment scope for one or more columns (U2c). A single column is a
 * one-element array; stewards typically descope several technical columns at
 * once. Descoping is always an explicit steward act.
 */
export async function setAssessmentScope(
  source: string,
  table: string,
  columns: string[],
  scope: 'in_scope' | 'out_of_scope',
  opts: { scopeReason?: string; scopedBy?: string; schema?: string } = {},
): Promise<{ source: string; table: string; updated: ScopeUpdateResult[] }> {
  const qs = opts.schema ? `?schema=${encodeURIComponent(opts.schema)}` : '';
  return apiPost<{ source: string; table: string; updated: ScopeUpdateResult[] }>(
    `/api/element/${source}/${table}/scope${qs}`,
    { columns, scope, scope_reason: opts.scopeReason ?? null, scoped_by: opts.scopedBy ?? null },
  );
}

export async function updateDescription(
  source: string,
  table: string,
  column: string,
  description: string,
  schema?: string,
  isAiGenerated: boolean = false,
): Promise<{ column_description: string; lifecycle_state: LifecycleState }> {
  const qs = schema ? `?schema=${encodeURIComponent(schema)}` : '';
  return apiPatch<{ column_description: string; lifecycle_state: LifecycleState }>(
    `/api/element/${source}/${table}/${column}/description${qs}`,
    { description, is_ai_generated: isAiGenerated },
  );
}

export async function draftDescription(
  source: string,
  table: string,
  column: string,
  schema?: string,
): Promise<{ draft: string; error?: AiError }> {
  const qs = schema ? `?schema=${encodeURIComponent(schema)}` : '';
  return apiPost<{ draft: string; error?: AiError }>(
    `/api/element/${source}/${table}/${column}/draft-description${qs}`,
    {},
  );
}

export async function updateBusinessName(
  source: string,
  table: string,
  column: string,
  businessName: string,
  schema?: string,
  isAiGenerated: boolean = false,
): Promise<{ business_name: string; business_name_is_ai: boolean }> {
  const qs = schema ? `?schema=${encodeURIComponent(schema)}` : '';
  return apiPatch<{ business_name: string; business_name_is_ai: boolean }>(
    `/api/element/${source}/${table}/${column}/business-name${qs}`,
    { business_name: businessName, is_ai_generated: isAiGenerated },
  );
}

export async function draftBusinessName(
  source: string,
  table: string,
  column: string,
  schema?: string,
): Promise<{ draft: string; error?: AiError }> {
  const qs = schema ? `?schema=${encodeURIComponent(schema)}` : '';
  return apiPost<{ draft: string; error?: AiError }>(
    `/api/element/${source}/${table}/${column}/draft-business-name${qs}`,
    {},
  );
}

export interface CodeEntry {
  code: string;
  value: string | null;
  meaning: string | null;
  share_pct: number | null;
  // Phase 5b.2 (Postgres backend): per-code review fields.
  origin?: 'profiled' | 'declared' | 'master_list';
  status?: 'empty' | 'draft' | 'in_review' | 'approved' | 'returned' | 'rejected' | 'governed';
  in_source?: boolean;
  // 2026-08-16 redesign: true for a code the bound reference set recognises — read-only,
  // its value/meaning come from the master list, never has its own reference_code row.
  governed?: boolean;
}

export type RefdataSetBadge = 'empty' | 'draft' | 'in_review' | 'partially_approved' | 'approved';
export type RefdataBindingStatus = 'draft' | 'in_review' | 'approved';

export interface ReferenceData {
  source: string;
  schema: string;
  table: string;
  column: string;
  is_coded: boolean;
  status: string | null;
  codes: CodeEntry[];
  bound_set_id: string | null;
  set_kind: 'local' | 'standard';
  // Phase 5b.2 additive fields.
  backend?: 'yaml' | 'postgres';
  semantic_accepted?: boolean;
  set_badge?: RefdataSetBadge;
  // 2026-08-16 redesign: the binding decision's OWN submit/approve status — only meaningful
  // when bound_set_id is set.
  binding_status?: RefdataBindingStatus | null;
  binding_submitted_at?: string | null;
  binding_submitted_by?: string | null;
  binding_decided_at?: string | null;
  binding_decided_by?: string | null;
  binding_decision?: string | null;
}

export interface ReferenceSetSummary {
  id: string;
  name: string;
  kind: 'local' | 'standard';
  standard_ref: string | null;
  status: string;
  entry_count: number;
}

/** Deterministic semantic-type → seeded standard set suggestion (Phase 3). */
export const REFERENCE_SET_SUGGESTIONS: Record<string, string> = {
  currency_code: 'iso_4217_currency',
  country_code: 'iso_3166_country',
};

export async function listReferenceSets(): Promise<ReferenceSetSummary[]> {
  const body = await apiFetch<{ sets: ReferenceSetSummary[] }>('/api/reference-sets');
  return body.sets;
}

export async function getReferenceData(
  source: string,
  table: string,
  column: string,
  schema?: string,
): Promise<ReferenceData> {
  const qs = schema ? `?schema=${encodeURIComponent(schema)}` : '';
  return apiFetch<ReferenceData>(`/api/element/${source}/${table}/${column}/reference-data${qs}`);
}

export async function updateReferenceData(
  source: string,
  table: string,
  column: string,
  payload: { meanings?: Record<string, string>; values?: Record<string, string>; status?: string; bound_set_id?: string; unbind?: boolean },
  schema?: string,
): Promise<{ refdata_status: string; meanings_count: number; values_count: number; bound_set_id: string | null }> {
  const qs = schema ? `?schema=${encodeURIComponent(schema)}` : '';
  return apiPatch<{ refdata_status: string; meanings_count: number; values_count: number; bound_set_id: string | null }>(
    `/api/element/${source}/${table}/${column}/reference-data${qs}`,
    payload,
  );
}

// ── Reference Data — per-code save/submit (Phase 5b.2, Postgres backend) ────

export interface ReferenceCodeEdit {
  code: string;
  value?: string | null;
  meaning?: string | null;
  origin?: 'profiled' | 'declared';
}

export async function saveReferenceCodes(
  source: string,
  table: string,
  column: string,
  codes: ReferenceCodeEdit[],
  schema?: string,
  actor?: { actor?: string; actor_role?: string },
): Promise<{ codes: CodeEntry[]; set_badge: RefdataSetBadge }> {
  const qs = schema ? `?schema=${encodeURIComponent(schema)}` : '';
  return apiPut<{ codes: CodeEntry[]; set_badge: RefdataSetBadge }>(
    `/api/element/${source}/${table}/${column}/reference-data/codes${qs}`,
    { codes, ...(actor ?? {}) },
  );
}

export async function submitReferenceCodes(
  source: string,
  table: string,
  column: string,
  codes: string[] | null,
  schema?: string,
  actor?: { actor?: string; actor_role?: string },
): Promise<{ submitted: number; codes: CodeEntry[]; set_badge: RefdataSetBadge }> {
  const qs = schema ? `?schema=${encodeURIComponent(schema)}` : '';
  return apiPost<{ submitted: number; codes: CodeEntry[]; set_badge: RefdataSetBadge }>(
    `/api/element/${source}/${table}/${column}/reference-data/submit-codes${qs}`,
    { codes, ...(actor ?? {}) },
  );
}

// Phase 5b.3.1 — analyst bulk pull-backs / delete (Postgres backend, unbound fields).
export async function withdrawReferenceCodes(
  source: string,
  table: string,
  column: string,
  codes: string[],
  schema?: string,
  actor?: { actor?: string; actor_role?: string },
): Promise<{ withdrawn: number; codes: CodeEntry[]; set_badge: RefdataSetBadge }> {
  const qs = schema ? `?schema=${encodeURIComponent(schema)}` : '';
  return apiPost<{ withdrawn: number; codes: CodeEntry[]; set_badge: RefdataSetBadge }>(
    `/api/element/${source}/${table}/${column}/reference-data/withdraw-codes${qs}`,
    { codes, ...(actor ?? {}) },
  );
}

export async function revokeReferenceCodes(
  source: string,
  table: string,
  column: string,
  codes: string[],
  schema?: string,
  actor?: { actor?: string; actor_role?: string },
): Promise<{ revoked: number; codes: CodeEntry[]; set_badge: RefdataSetBadge }> {
  const qs = schema ? `?schema=${encodeURIComponent(schema)}` : '';
  return apiPost<{ revoked: number; codes: CodeEntry[]; set_badge: RefdataSetBadge }>(
    `/api/element/${source}/${table}/${column}/reference-data/revoke-codes${qs}`,
    { codes, ...(actor ?? {}) },
  );
}

export async function removeReferenceCodes(
  source: string,
  table: string,
  column: string,
  codes: string[],
  schema?: string,
  actor?: { actor?: string; actor_role?: string },
): Promise<{ removed: number; codes: CodeEntry[]; set_badge: RefdataSetBadge }> {
  const qs = schema ? `?schema=${encodeURIComponent(schema)}` : '';
  return apiPost<{ removed: number; codes: CodeEntry[]; set_badge: RefdataSetBadge }>(
    `/api/element/${source}/${table}/${column}/reference-data/remove-codes${qs}`,
    { codes, ...(actor ?? {}) },
  );
}

// ── Governance workflow (submit / approve / reject via steward review) ─────

export async function submitDefinitionForReview(
  source: string,
  table: string,
  column: string,
  submittedBy?: string,
  schema?: string,
  submittedByRole?: string,
): Promise<{ submission: SubmissionStatus; last_status?: { action: string | null; at: string | null } }> {
  const qs = schema ? `?schema=${encodeURIComponent(schema)}` : '';
  return apiPost<{ submission: SubmissionStatus; last_status?: { action: string | null; at: string | null } }>(
    `/api/element/${source}/${table}/${column}/submit${qs}`,
    { submitted_by: submittedBy ?? null, submitted_by_role: submittedByRole ?? null },
  );
}

export async function approveDefinitionViaReview(
  source: string,
  table: string,
  column: string,
  decidedBy?: string,
  schema?: string,
): Promise<LifecycleActionResult> {
  const qs = schema ? `?schema=${encodeURIComponent(schema)}` : '';
  return apiPost<LifecycleActionResult>(
    `/api/element/${source}/${table}/${column}/approve${qs}`,
    { decided_by: decidedBy ?? null },
  );
}

export async function rejectDefinitionViaReview(
  source: string,
  table: string,
  column: string,
  reason?: string,
  decidedBy?: string,
  schema?: string,
): Promise<LifecycleActionResult> {
  const qs = schema ? `?schema=${encodeURIComponent(schema)}` : '';
  return apiPost<LifecycleActionResult>(
    `/api/element/${source}/${table}/${column}/reject${qs}`,
    { reason: reason ?? null, decided_by: decidedBy ?? null },
  );
}

// ── Phase 5b.1 canonical interpretation-set actions ────────────────────────

export interface LifecycleActionResult {
  lifecycle_state: string;
  submission: SubmissionStatus;
  last_status?: { action: string | null; at: string | null };
}

/** Holistic Save of the interpretation set (single 'Save draft' button). */
export async function saveInterpretation(
  source: string,
  table: string,
  column: string,
  opts: {
    description?: string | null;
    descriptionIsAi?: boolean;
    businessName?: string | null;
    businessNameIsAi?: boolean;
    actor?: string;
    actorRole?: string;
    schema?: string;
  } = {},
): Promise<LifecycleActionResult> {
  const qs = opts.schema ? `?schema=${encodeURIComponent(opts.schema)}` : '';
  return apiPost<LifecycleActionResult>(
    `/api/element/${source}/${table}/${column}/save${qs}`,
    {
      description: opts.description ?? null,
      description_is_ai: opts.descriptionIsAi ?? false,
      business_name: opts.businessName ?? null,
      business_name_is_ai: opts.businessNameIsAi ?? false,
      actor: opts.actor ?? null,
      actor_role: opts.actorRole ?? null,
    },
  );
}

/** Analyst pulls an In-Review submission back → Draft (spontaneous). */
export async function withdrawInterpretation(
  source: string,
  table: string,
  column: string,
  opts: { actor?: string; actorRole?: string; schema?: string } = {},
): Promise<LifecycleActionResult> {
  const qs = opts.schema ? `?schema=${encodeURIComponent(opts.schema)}` : '';
  return apiPost<LifecycleActionResult>(
    `/api/element/${source}/${table}/${column}/withdraw${qs}`,
    { actor: opts.actor ?? null, actor_role: opts.actorRole ?? null },
  );
}

/** Analyst pulls a prior approval back → Draft (re-open for editing). */
export async function revokeInterpretation(
  source: string,
  table: string,
  column: string,
  opts: { actor?: string; actorRole?: string; schema?: string } = {},
): Promise<LifecycleActionResult> {
  const qs = opts.schema ? `?schema=${encodeURIComponent(opts.schema)}` : '';
  return apiPost<LifecycleActionResult>(
    `/api/element/${source}/${table}/${column}/revoke${qs}`,
    { actor: opts.actor ?? null, actor_role: opts.actorRole ?? null },
  );
}

/** Steward returns a submission for rework → Returned (fix-and-resubmit). */
export async function returnInterpretation(
  source: string,
  table: string,
  column: string,
  opts: { decidedBy?: string; decidedByRole?: string; reason?: string; schema?: string } = {},
): Promise<LifecycleActionResult> {
  const qs = opts.schema ? `?schema=${encodeURIComponent(opts.schema)}` : '';
  return apiPost<LifecycleActionResult>(
    `/api/element/${source}/${table}/${column}/return${qs}`,
    { decided_by: opts.decidedBy ?? null, decided_by_role: opts.decidedByRole ?? null, reason: opts.reason ?? null },
  );
}

/** Steward outright-rejects a submission → Rejected (distinct from Return). */
export async function declineInterpretation(
  source: string,
  table: string,
  column: string,
  opts: { decidedBy?: string; decidedByRole?: string; reason?: string; schema?: string } = {},
): Promise<LifecycleActionResult> {
  const qs = opts.schema ? `?schema=${encodeURIComponent(opts.schema)}` : '';
  return apiPost<LifecycleActionResult>(
    `/api/element/${source}/${table}/${column}/decline${qs}`,
    { decided_by: opts.decidedBy ?? null, decided_by_role: opts.decidedByRole ?? null, reason: opts.reason ?? null },
  );
}

export interface SourceConnection {
  source_system: string | null;
  system_type: string | null;
  database: string | null;
  schema: string | null;
  access_mode: string | null;
}

export interface DatasetSummaryEntry {
  schema: string;
  table_name: string;
  description: string | null;
  row_count: number;
  column_count: number;
  governance: Record<string, number>;
  has_story: boolean;
  story_is_ai: boolean;
  /** Dataset-level DQ roll-up (§15) — same stored badge the dataset overview reads. */
  dataset_dq?: DatasetDQBadge | null;
  /** Declared or inferred key present — same check a future onboarding flow
   *  would run before offering to draw a conceptual data model. */
  has_primary_key?: boolean;
  /** D11's authoritative "has this table been profiled" flag — false for a
   *  freshly-onboarded table or one reset to its pre-profiling baseline. */
  is_profiled: boolean;
}

/** One PK/FK edge in the source's conceptual data model. `from` is the child
 *  table holding the FK (the "many" side); `to` is the referenced parent
 *  table (the "one" side) — cardinality is always 1:N by construction. */
export interface SourceRelationship {
  from_table: string;
  from_schema: string;
  from_columns: string[];
  to_table: string;
  to_schema: string;
  to_columns: string[];
  declared: boolean;
  confidence?: string | null;
}

/** One row of the Semantic Type × Governance State cross-tab (source level). */
export interface SemanticGovernanceRow {
  type: string;
  label?: string | null;
  color: string;
  empty: number;
  draft: number;
  in_review: number;
  approved: number;
  bounced: number;
}

export interface SourceInfo {
  source: string;
  connection: SourceConnection;
  generated_at: string | null;
  /** Real "has any table in this source ever been profiled" timestamp, null if none has. */
  last_profiled_at: string | null;
  schema_hash: string | null;
  table_count: number;
  column_count: number;
  total_row_count: number;
  schemas: string[];
  semantic_type_mix: SemanticTypeMix[];
  semantic_governance_matrix: SemanticGovernanceRow[];
  governance_state: GovStateCounts;
  /** Source-wide semantic-type disposition tally (Dashboard's Semantic Resolution card). */
  semantic_state?: { accepted: number; pending: number; unresolved: number };
  observation_summary: ObservationMatrixEntry[];
  datasets: DatasetSummaryEntry[];
  relationships: SourceRelationship[];
}

export async function getSourceInfo(source: string): Promise<SourceInfo> {
  return apiFetch<SourceInfo>(`/api/element/${source}/info`);
}

/** Same data as {@link getSourceInfo}, with real (non-fabricated) stage progress. */
export async function streamSourceInfo(
  source: string,
  onProgress: (completed: number) => void,
  onDetail: (text: string, fraction?: number) => void,
  signal?: AbortSignal,
): Promise<SourceInfo> {
  return fetchWithRealProgress<SourceInfo>(`/api/element/${source}/info/stream`, onProgress, onDetail, signal);
}

export async function bulkDraftDescriptions(
  source: string,
  table: string,
  schema?: string,
): Promise<{ generated: number; skipped: number; total: number; error?: AiError }> {
  const qs = schema ? `?schema=${encodeURIComponent(schema)}` : '';
  return apiPost(`/api/element/${source}/${table}/bulk-draft-descriptions${qs}`, {});
}

export async function bulkDraftBusinessNames(
  source: string,
  table: string,
  schema?: string,
): Promise<{ generated: number; skipped: number; total: number; error?: AiError }> {
  const qs = schema ? `?schema=${encodeURIComponent(schema)}` : '';
  return apiPost(`/api/element/${source}/${table}/bulk-draft-business-names${qs}`, {});
}

export interface DataStory {
  tagline: string | null;
  narrative: string | null;
  is_ai_generated: boolean;
  generated_at: string | null;
}

export async function getDataStory(
  source: string,
  table: string,
  schema?: string,
): Promise<DataStory> {
  const qs = schema ? `?schema=${encodeURIComponent(schema)}` : '';
  return apiFetch<DataStory>(`/api/element/${source}/${table}/data-story${qs}`);
}

export async function draftDataStory(
  source: string,
  table: string,
  schema?: string,
): Promise<DataStory> {
  const qs = schema ? `?schema=${encodeURIComponent(schema)}` : '';
  return apiPost<DataStory>(`/api/element/${source}/${table}/draft-data-story${qs}`, {});
}

export async function saveDataStory(
  source: string,
  table: string,
  tagline: string,
  narrative: string,
  schema?: string,
): Promise<DataStory> {
  const qs = schema ? `?schema=${encodeURIComponent(schema)}` : '';
  return apiPut<DataStory>(`/api/element/${source}/${table}/data-story${qs}`, { tagline, narrative });
}

export async function bulkDraftDataStories(
  source: string,
): Promise<{ generated: number; already_existed: number; failed: number; total: number; ai_unavailable: boolean }> {
  return apiPost(`/api/element/${source}/bulk-draft-data-stories`, {});
}

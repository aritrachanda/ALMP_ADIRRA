// Domain type interfaces

import type { AiError } from 'src/composables/useAiError';

export interface Column {
  name: string;
  description?: string | null;
  data_type?: string | null;
  row_count?: number | null;
  null_count?: number | null;
  null_pct?: number | null;
  distinct_count?: number | null;
  duplicate_count?: number | null;
  min_value?: string | null;
  max_value?: string | null;
  sample_values?: string[] | null;
}

export interface Table {
  schema_name: string;
  table_name: string;
  description?: string | null;
  row_count?: number | null;
  primary_key?: string[] | null;
  foreign_keys?: string[] | null;
  relations?: Record<string, unknown>[] | null;
  columns: Column[];
}

export interface Schema {
  name: string;
  tables: Table[];
}

export interface Catalog {
  version?: number;
  source?: string;
  connection?: string;
  generated_at?: string;
  schema_hash?: string;
  schemas: Schema[];
}

export interface CatalogListItem {
  name: string;
}

export interface ColumnMapping {
  target_column: string;
  source_schema?: string | null;
  source_table?: string | null;
  source_column?: string | null;
  confidence?: number | null;
  rationale?: string | null;
  transformation_type?: string | null;
  notes?: string | null;
  status: string;
}

export interface MappingTable {
  target_schema: string;
  target_table: string;
  target_framework?: string | null;
  table_confidence?: number | null;
  table_rationale?: string | null;
  sql_query?: string | null;
  status?: string;
  columns: ColumnMapping[];
}

export interface MappingResult {
  version?: number;
  agent?: string;
  source?: string;
  target?: string;
  provider?: string;
  model?: string;
  generated_at?: string;
  status?: string;
  tables: MappingTable[];
}

export interface MappingListItem {
  source: string;
  target: string;
  filename: string;
}

export interface GlossaryTerm {
  id: string;
  title: string;
  domain?: string;
  category?: string;
  business_description?: string;
  detailed_description?: string;
  synonyms?: string[];
  related_objects?: string[];
  steward?: string;
  tags?: string[];
  status?: string;
  CRR_context?: string;
  DPM_context?: string;
  ai_generated_fields?: string[];
  last_updated?: string | null;
  last_reviewed?: string | null;
  is_cde?: boolean | null;
  ai_provenance?: Record<string, AIProvenance>;
}

// ── Business Glossary v2 (PostgreSQL-backed) ──────────────────────────────────
export interface AIProvenance {
  model?: string;
  prompt_id?: string;
  generated_at?: string;
}

export interface GlossaryV2Summary {
  id: string;
  parent: string | null;
  title: string;
  domain: string;
  category: string;
  status: string;
  is_cde: boolean | null;
  has_linkage: boolean;
  ai_generated: boolean;
  has_children: boolean;
}

export interface GlossaryV2Version {
  version_no: number;
  title: string;
  status: string;
  serving: boolean;
  authored_by: string | null;
  authored_at: string | null;
  ai_provenance: Record<string, AIProvenance>;
}

export interface GlossaryV2Transition {
  from_status: string | null;
  to_status: string;
  actor: string | null;
  actor_role: string | null;
  reason: string | null;
  occurred_at: string | null;
}

export interface GlossaryV2History {
  term: string;
  versions: GlossaryV2Version[];
  transitions: GlossaryV2Transition[];
}

export interface GlossaryV2Coverage {
  terms_total: number;
  by_status: Record<string, number>;
  approved: number;
  linkages_total: number;
  by_granularity: Record<string, number>;
  distinct_linked_source_columns: number;
  triage_total: number;
  needs_revalidation: number;
  total_source_columns: number;
  column_coverage_pct: number;
}

export interface AttributeConfig {
  key: string;
  label: string;
  attribute: string;
  hint: string;
  generator: string;
}

/** A row in the bulk review queue: a draft, AI-generated term awaiting steward approval. */
export interface GlossaryV2QueueItem extends GlossaryV2Summary {
  assigned_to: string | null;
}

/** Result of an AI field generation (v2): the drafted value plus its provenance. */
export interface GlossaryV2GenerateResult {
  field: string;
  value: string | string[] | null;
  provenance: AIProvenance | null;
  message?: string;
  error?: AiError;
}

export interface UncoveredConcept {
  kind: string;
  dataset: string;
  schema_name: string;
  table: string;
  column: string;
  data_type: string;
  description: string;
  related_object: string;
}

export interface Message {
  role: string;
  content: string;
  ts?: string;
}

export interface ConversationSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: Message[];
}

export interface TableAnnotation {
  user_description?: string | null;
  mapping_instructions?: string | null;
  columns: Record<string, { user_description?: string | null; mapping_instructions?: string | null }>;
}

export interface AnnotationOverlay {
  version: number;
  dataset: string;
  annotations: Record<string, TableAnnotation>;
}

export interface SSEEvent {
  event: string;
  data: {
    type: string;
    target_table?: string;
    index?: number;
    total?: number;
    message?: string;
    timestamp?: string;
    data?: Record<string, unknown>;
  };
}

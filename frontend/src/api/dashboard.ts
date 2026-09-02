import { apiFetch } from './client';

export interface CatalogCounts {
  datasets: number;
  tables: number;
  columns: number;
}

export interface ConfidenceBand {
  band: string;
  columns: number;
}

export interface SourceTableMapping {
  source_table: string;
  columns: number;
  mapped: number;
  unmapped: number;
  avg_confidence: number;
}

export interface MappingDetail {
  total: number;
  with_results: number;
  mapped_columns: number;
  derived_columns: number;
  unmapped_columns: number;
  confidence_bands: ConfidenceBand[];
  by_source_table: SourceTableMapping[];
}

export interface GlossaryBreakdown {
  status: string;
  count: number;
}

export interface CategoryBreakdown {
  category: string;
  count: number;
}

export interface AiComponent {
  component: string;
  coverage: number;
}

export interface GlossaryDetail {
  terms: number;
  ai_terms: number;
  by_status: GlossaryBreakdown[];
  by_category: CategoryBreakdown[];
  ai_components: AiComponent[];
}

export interface DashboardSummary {
  sources: CatalogCounts;
  targets: CatalogCounts;
  mappings: MappingDetail;
  glossary: GlossaryDetail;
}

export function getDashboardSummary(): Promise<DashboardSummary> {
  return apiFetch<DashboardSummary>('/api/dashboard/summary');
}

import { apiFetch } from './client';

export interface InsightFinding {
  scope: string;
  target: string;
  severity: 'high' | 'attention' | 'info';
  category: string;
  title: string;
  rationale: string;
  evidence: Record<string, unknown>;
  source: 'rule' | 'ai';
  regulatory_note?: string;
}

export interface InsightHypothesis {
  title: string;
  body: string;
  recommendation: string;
  confidence: number;
  based_on: string[];
  sev: 'high' | 'attention' | 'info';
}

export interface InsightsReadiness {
  blocking: number;
  medium: number;
  info: number;
  not_ready: boolean;
}

export interface InsightsResult {
  source: string;
  table: string;
  findings: InsightFinding[];
  hypotheses: InsightHypothesis[];
  readiness: InsightsReadiness;
}

export async function getInsights(
  source: string,
  table: string,
  schema?: string,
  includeAi = false,
): Promise<InsightsResult> {
  const params = new URLSearchParams();
  if (schema) params.set('schema', schema);
  if (includeAi) params.set('include_ai', 'true');
  const qs = params.toString() ? `?${params.toString()}` : '';
  return apiFetch<InsightsResult>(`/api/insights/${source}/${table}${qs}`);
}

import { apiFetch, apiPatch, apiPost, apiPut } from './client';
import { fetchWithRealProgress } from './sse';
import type {
  GlossaryV2Summary, GlossaryTerm, GlossaryV2History, GlossaryV2Coverage, AttributeConfig,
  GlossaryV2QueueItem, GlossaryV2GenerateResult,
} from 'src/types';

/** Steward decision payload for confirm/reject. */
export interface ReviewDecision {
  decided_by?: string;
  decided_by_role?: string;
  reason?: string;
}

const BASE = '/api/glossary/v2';

export interface SearchParams {
  q?: string;
  domain?: string;
  category?: string;
  status?: string;
  steward?: string;
  has_linkage?: boolean;
  ai_generated?: boolean;
}

function qs(params: SearchParams): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : '';
}

export function getTree(): Promise<GlossaryV2Summary[]> {
  return apiFetch(`${BASE}/tree`);
}

export function getFacets(): Promise<Record<string, Record<string, number>>> {
  return apiFetch(`${BASE}/facets`);
}

export function search(params: SearchParams): Promise<GlossaryV2Summary[]> {
  return apiFetch(`${BASE}/search${qs(params)}`);
}

export function getTerm(slug: string): Promise<GlossaryTerm> {
  return apiFetch(`${BASE}/terms/${encodeURIComponent(slug)}`);
}

export function getHistory(slug: string): Promise<GlossaryV2History> {
  return apiFetch(`${BASE}/terms/${encodeURIComponent(slug)}/history`);
}

export function getCoverage(): Promise<GlossaryV2Coverage> {
  return apiFetch(`${BASE}/coverage`);
}

/** Same data as {@link getCoverage}, with real (non-fabricated) stage progress. */
export function streamCoverage(
  onProgress: (completed: number) => void,
  onDetail: (text: string) => void,
  signal?: AbortSignal,
): Promise<GlossaryV2Coverage> {
  return fetchWithRealProgress<GlossaryV2Coverage>(`${BASE}/coverage/stream`, onProgress, onDetail, signal);
}

export function getAttributesConfig(): Promise<AttributeConfig[]> {
  return apiFetch(`${BASE}/attributes-config`);
}

export function reparent(slug: string, parent: string | null): Promise<GlossaryTerm> {
  return apiPatch(`${BASE}/terms/${encodeURIComponent(slug)}/parent`, { parent });
}

// ── Review queue + steward actions (Phase 4c) ────────────────────────────────

export function getReviewQueue(): Promise<GlossaryV2QueueItem[]> {
  return apiFetch(`${BASE}/review-queue`);
}

export function assignReview(slug: string, assignee: string | null): Promise<unknown> {
  return apiPatch(`${BASE}/terms/${encodeURIComponent(slug)}/assign`, { assignee });
}

export function confirmTerm(slug: string, decision: ReviewDecision = {}): Promise<GlossaryTerm> {
  return apiPost(`${BASE}/terms/${encodeURIComponent(slug)}/confirm`, decision);
}

export function rejectTerm(slug: string, decision: ReviewDecision = {}): Promise<GlossaryTerm> {
  return apiPost(`${BASE}/terms/${encodeURIComponent(slug)}/reject`, decision);
}

export function updateTerm(slug: string, term: Partial<GlossaryTerm>): Promise<GlossaryTerm> {
  return apiPut(`${BASE}/terms/${encodeURIComponent(slug)}`, term);
}

export function generateField(slug: string, field: string): Promise<GlossaryV2GenerateResult> {
  return apiPost(`${BASE}/terms/${encodeURIComponent(slug)}/generate`, { field });
}


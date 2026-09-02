/**
 * File Overview
 * Frontend API wrapper for Discovery page operations.
 *
 * Purpose
 * - Keep all Discovery-related backend calls in one place.
 * - Provide typed function contracts for pages/stores.
 * - Centralize URL-safe dataset/table handling.
 *
 * Structure
 * - Dataset listing and table stats/profile fetchers.
 * - SQL query execution helper for preview/exploration.
 * - Discovery chat wrapper with typed visual payload support.
 */

import { apiFetch, apiPost } from './client';
import type { Column, Table } from 'src/types';

export interface DatasetItem {
  name: string;
  kind: 'source' | 'target';
}

/** A profiled column: the base catalog `Column` plus the profile-only per-column metrics
 *  the Discovery stats table renders. */
export interface ProfileColumn extends Column {
  uniqueness_pct?: number | null;
  empty_string_count?: number | null;
  placeholder_count?: number | null;
  inferred_pattern?: string | null;
  top_values?: { value?: unknown; count?: number }[];
}

/** Table profile payload. Superset of the live-stats `Table` shape plus a handful of
 *  profile-only aggregate metrics; everything else the backend adds is passed through
 *  untyped via the index signature. */
export interface TableProfile {
  schema_name?: string;
  table_name?: string;
  description?: string | null;
  row_count?: number | null;
  columns?: ProfileColumn[];
  primary_key?: string[];
  foreign_keys?: string[];
  inferred_primary_key?: string[];
  relations?: Record<string, unknown>[];
  duplicate_count?: number | null;
  orphan_fk_count?: number | null;
  completeness_summary?: number | null;
  pct_columns_described?: number | null;
  [key: string]: unknown;
}

export async function listDatasets(): Promise<DatasetItem[]> {
  return apiFetch('/api/discovery/datasets');
}

export async function getTableStats(dataset: string, table: string): Promise<Table> {
  // Encode dynamic path segments to avoid breaking routes on spaces/special chars.
  const ds = encodeURIComponent(dataset);
  const tb = encodeURIComponent(table);
  return apiFetch(`/api/discovery/${ds}/${tb}/stats`);
}

export async function getTableProfile(dataset: string, table: string): Promise<TableProfile> {
  // Keep profile route construction consistent with stats/chat endpoints.
  const ds = encodeURIComponent(dataset);
  const tb = encodeURIComponent(table);
  return apiFetch(`/api/discovery/${ds}/${tb}/profile`);
}

/** Compute a live profile AND write the stats back to the source YAML catalog.
 *  Safe to call any time — only profiling stats are overwritten; descriptions
 *  and governance metadata are preserved. */
export async function refreshTableProfile(dataset: string, table: string): Promise<TableProfile> {
  const ds = encodeURIComponent(dataset);
  const tb = encodeURIComponent(table);
  return apiPost(`/api/discovery/${ds}/${tb}/refresh`, {});
}

/** Re-profile every table in a source from the live database, streaming SSE progress.
 *  Calls onEvent for each SSE frame. Returns when the stream closes.
 *
 *  `includeSemantic`/`includeDq` (default true) mirror the single-table refresh's
 *  always-on semantic+DQ pairing (SD-R5) — opt-out here only because a bulk rebuild
 *  can span many tables, unlike a single-table refresh which always does all three. */
export async function rebuildSourceProfiles(
  dataset: string,
  onEvent: (event: string, data: Record<string, unknown>) => void,
  signal?: AbortSignal,
  opts?: { includeSemantic?: boolean; includeDq?: boolean },
): Promise<void> {
  const ds = encodeURIComponent(dataset);
  const params = new URLSearchParams({
    include_semantic: String(opts?.includeSemantic ?? true),
    include_dq: String(opts?.includeDq ?? true),
  });
  const res = await fetch(`/api/discovery/${ds}/rebuild-all?${params}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
    signal,
  });
  if (!res.ok) throw new Error(`Rebuild failed: ${res.status} ${res.statusText}`);

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  let evtName = '';
  let evtData = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split('\n');
    buf = lines.pop() ?? '';
    for (const line of lines) {
      if (line.startsWith('event: ')) { evtName = line.slice(7).trim(); }
      else if (line.startsWith('data: ')) { evtData = line.slice(6); }
      else if (line === '') {
        if (evtName && evtData) {
          try { onEvent(evtName, JSON.parse(evtData)); } catch { /* skip */ }
        }
        evtName = ''; evtData = '';
      }
    }
  }
}

/** Reset one dataset/table back to a pre-profiling baseline, streaming SSE progress.
 *  Clears catalog stats, semantic types, DQ scores, Interpretation lifecycle + content,
 *  Reference Data, reference-set binding + its review, and annotations. Calls onEvent for
 *  each SSE frame (`started`/`progress`/`error`/`done`); nothing commits on the backend
 *  until the whole reset completes (one shared transaction) — an `error` frame means
 *  everything was rolled back, not a partial reset. */
export async function resetTableProfile(
  dataset: string,
  table: string,
  onEvent: (event: string, data: Record<string, unknown>) => void,
  signal?: AbortSignal,
  opts?: { actor?: string },
): Promise<void> {
  const ds = encodeURIComponent(dataset);
  const tb = encodeURIComponent(table);
  await _streamResetSse(`/api/discovery/${ds}/${tb}/reset`, onEvent, signal, opts);
}

/** Reset every table in a source back to a pre-profiling baseline, streaming SSE progress.
 *  ONE transaction spans every table in the source — a single failing table rolls back
 *  every table's work for this call, not just its own. See `resetTableProfile`. */
export async function resetSourceProfile(
  dataset: string,
  onEvent: (event: string, data: Record<string, unknown>) => void,
  signal?: AbortSignal,
  opts?: { actor?: string },
): Promise<void> {
  const ds = encodeURIComponent(dataset);
  await _streamResetSse(`/api/discovery/${ds}/reset`, onEvent, signal, opts);
}

async function _streamResetSse(
  url: string,
  onEvent: (event: string, data: Record<string, unknown>) => void,
  signal?: AbortSignal,
  opts?: { actor?: string },
): Promise<void> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actor: opts?.actor ?? null }),
    signal,
  });
  if (!res.ok) throw new Error(`Reset failed: ${res.status} ${res.statusText}`);

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  let evtName = '';
  let evtData = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split('\n');
    buf = lines.pop() ?? '';
    for (const line of lines) {
      if (line.startsWith('event: ')) { evtName = line.slice(7).trim(); }
      else if (line.startsWith('data: ')) { evtData = line.slice(6); }
      else if (line === '') {
        if (evtName && evtData) {
          try { onEvent(evtName, JSON.parse(evtData)); } catch { /* skip */ }
        }
        evtName = ''; evtData = '';
      }
    }
  }
}

export interface SmartFinding {
  scope: 'dataset' | 'column';
  target: string;
  severity: 'info' | 'attention' | 'high';
  category: string;
  title: string;
  rationale: string;
  evidence?: Record<string, unknown>;
  regulatory_note?: string;
  source: 'rule' | 'ai';
}

export interface AssessmentResult {
  table_name: string;
  schema_name: string;
  findings: SmartFinding[];
  summary: {
    total: number;
    by_severity: Record<string, number>;
    by_scope: Record<string, number>;
    by_category: Record<string, number>;
  };
  ai_status: 'skipped' | 'generated' | 'cached' | 'unavailable';
}

export async function getTableAssessment(
  dataset: string,
  table: string,
  opts: { includeAi?: boolean; refresh?: boolean } = {},
): Promise<AssessmentResult> {
  // Advisory Smart Data Assessment findings; AI layer is opt-in via includeAi.
  const ds = encodeURIComponent(dataset);
  const tb = encodeURIComponent(table);
  const params = new URLSearchParams();
  if (opts.includeAi) params.set('include_ai', 'true');
  if (opts.refresh) params.set('refresh', 'true');
  const qs = params.toString();
  return apiFetch(`/api/discovery/${ds}/${tb}/assessment${qs ? `?${qs}` : ''}`);
}

export async function executeQuery(dataset: string, table: string, sql: string, limit = 100): Promise<{
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
}> {
  // The backend executes the SQL in a constrained table context and returns a tabular shape.
  const ds = encodeURIComponent(dataset);
  const tb = encodeURIComponent(table);
  return apiPost(`/api/discovery/${ds}/${tb}/query`, { sql, limit });
}

export interface ChatVisual {
  type: 'chart' | 'dataframe' | 'error';
  spec?: {
    chart_type: string;
    title: string;
    x: string;
    y: string;
    color?: string;
  };
  data?: Record<string, unknown>[];
  columns?: string[];
  message?: string;
}

export async function discoveryChat(
  dataset: string,
  table: string,
  messages: { role: string; content: string }[],
): Promise<{ reply: string; visuals: ChatVisual[] }> {
  // Chat can return both plain text and visuals; callers should render both channels.
  const ds = encodeURIComponent(dataset);
  const tb = encodeURIComponent(table);
  return apiPost(`/api/discovery/${ds}/${tb}/chat`, { messages });
}

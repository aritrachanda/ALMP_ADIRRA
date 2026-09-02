import { apiFetch } from './client';

export interface AuditEvent {
  id: number;
  occurred_at: string;
  event_class: 'business' | 'ai';
  event_type: string;
  actor_user_id: string | null;
  actor_role: string | null;
  legal_entity: string | null;
  subject_type: string | null;
  subject_id: string | null;
  payload: Record<string, unknown> | null;
  request_id: string | null;
}

export interface AuditSummaryRow {
  day: string;
  event_type: string;
  count: number;
}

export interface ListEventsParams {
  event_class?: string;
  event_type?: string;
  event_prefix?: string;
  subject_type?: string;
  subject_id?: string;
  from_ts?: string;
  to_ts?: string;
  limit?: number;
  offset?: number;
}

export async function listEvents(params: ListEventsParams = {}): Promise<AuditEvent[]> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') qs.set(k, String(v));
  }
  const query = qs.toString() ? `?${qs}` : '';
  return apiFetch(`/api/audit/events${query}`);
}

export async function getEvent(id: number): Promise<AuditEvent> {
  return apiFetch(`/api/audit/events/${id}`);
}

export async function getSummary(days = 30): Promise<AuditSummaryRow[]> {
  return apiFetch(`/api/audit/summary?days=${days}`);
}

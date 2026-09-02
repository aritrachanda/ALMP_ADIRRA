export interface StatusTone {
  label: string;
  textColor: string;
  bgColor: string;
  borderColor: string;
  accentColor: string;
}

function toTitleCase(value: string): string {
  return value
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

export function getStatusTone(status: string): StatusTone {
  const normalized = String(status || '').trim().toLowerCase();

  switch (normalized) {
    case 'approved':
    case 'accepted':
    case 'done':
    case 'complete':
    case 'live':
      return {
        label: toTitleCase(normalized),
        textColor: '#166534',
        bgColor: '#dcfce7',
        borderColor: '#86efac',
        accentColor: '#16a34a',
      };
    case 'draft':
    case 'saved':
    case 'pending':
      return {
        label: toTitleCase(normalized),
        textColor: '#9a3412',
        bgColor: '#ffedd5',
        borderColor: '#fdba74',
        accentColor: '#ea580c',
      };
    case 'running':
      return {
        label: toTitleCase(normalized),
        textColor: '#1d4ed8',
        bgColor: '#dbeafe',
        borderColor: '#93c5fd',
        accentColor: '#2563eb',
      };
    case 'retired':
    case 'deprecated':
    case 'discarded':
    case 'error':
      return {
        label: toTitleCase(normalized),
        textColor: '#b91c1c',
        bgColor: '#fee2e2',
        borderColor: '#fca5a5',
        accentColor: '#dc2626',
      };
    case 'in_review':
      return {
        label: 'In-Review',
        textColor: '#1d4ed8',
        bgColor: '#dbeafe',
        borderColor: '#93c5fd',
        accentColor: '#2563eb',
      };
    case 'returned':
      return {
        label: toTitleCase(normalized),
        textColor: '#9a3412',
        bgColor: '#ffedd5',
        borderColor: '#fdba74',
        accentColor: '#ea580c',
      };
    case 'rejected':
      return {
        label: 'Rejected',
        textColor: '#b91c1c',
        bgColor: '#fee2e2',
        borderColor: '#fca5a5',
        accentColor: '#dc2626',
      };
    case 'empty':
    case 'initiated':
    case 'withdrawn':
    case 'revoked':
      return {
        label: toTitleCase(normalized),
        textColor: '#475569',
        bgColor: '#f1f5f9',
        borderColor: '#cbd5e1',
        accentColor: '#64748b',
      };
    default:
      return {
        label: normalized ? toTitleCase(normalized) : 'Unknown',
        textColor: '#475569',
        bgColor: '#f1f5f9',
        borderColor: '#cbd5e1',
        accentColor: '#64748b',
      };
  }
}

export function statusAccent(status: string): string {
  return getStatusTone(status).accentColor;
}

export function statusLabel(status: string): string {
  return getStatusTone(status).label;
}

// Fold a canonical (Phase-5) or legacy lifecycle status into one of five display
// buckets. Mirrors the backend `_gov_display_bucket` so optimistic count updates
// stay consistent after the element_backend flip.
const GOV_DISPLAY_BUCKET: Record<string, GovBucket> = {
  empty: 'empty', initiated: 'empty',
  draft: 'draft', saved: 'draft', defined: 'draft',
  in_review: 'in_review',
  returned: 'bounced', rejected: 'bounced', withdrawn: 'bounced', revoked: 'bounced',
  approved: 'approved',
};

export type GovBucket = 'empty' | 'draft' | 'in_review' | 'approved' | 'bounced';

export function govDisplayBucket(state: string): GovBucket {
  return GOV_DISPLAY_BUCKET[state] ?? 'draft';
}

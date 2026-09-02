/**
 * Shared shapes for the visualisation cards used at dataset, source and app
 * (Dashboard) level. One catalog of card types, mounted at whichever scope is
 * valid — see /memories/repo/dashboard-viz-redesign.md for the level model.
 */

/** One coloured slice of a proportional bar (semantic mix, governance, DQ grades). */
export interface VizSegment {
  label: string;
  count: number;
  /** 0–100 share of the whole bar. */
  pct: number;
  /** Any CSS colour — callers pass a token, e.g. `var(--gov-draft-vivid)`. */
  color: string;
}

/** One KPI tile in a KPI strip. */
export interface VizKpi {
  label: string;
  /** Pre-formatted for display (callers own thousands separators, % signs). */
  value: string | number;
  /** When set (0–100), renders a micro progress meter under the value. */
  meterPct?: number | null;
  /** Any CSS colour, applied to the value text and the meter fill. */
  color?: string | null;
  /** Optional hover explanation. */
  hint?: string | null;
}

/** One plotted dataset in the Quality Map (bubble) card. */
export interface VizQualityPoint {
  label: string;
  schema: string;
  /** X axis — 0–100 share of this dataset's elements that have left Draft. */
  governancePct: number;
  /** Y axis — DQ score 0–100, or null when the dataset has never been scored. */
  score: number | null;
  /** Bubble area — row count. */
  rows: number;
  /** Shown in the tooltip only; no longer an axis. */
  columns: number;
  /** Any CSS colour, normally the DQ grade band. */
  color: string;
}

export const GOV_SEGMENT_ORDER = ['empty', 'draft', 'in_review', 'approved', 'bounced'] as const;

export type GovSegmentKey = (typeof GOV_SEGMENT_ORDER)[number];

export const GOV_SEGMENT_LABEL: Record<GovSegmentKey, string> = {
  empty: 'Empty',
  draft: 'Draft',
  in_review: 'In-Review',
  approved: 'Approved',
  bounced: 'Bounced',
};

/** Chart-surface (vivid) token per governance state — the journey ramp. */
export const GOV_SEGMENT_COLOR: Record<GovSegmentKey, string> = {
  empty: 'var(--gov-empty-vivid)',
  draft: 'var(--gov-draft-vivid)',
  in_review: 'var(--gov-in-review-vivid)',
  approved: 'var(--gov-approved-vivid)',
  bounced: 'var(--gov-bounced-vivid)',
};

/** Plain-language meaning of each governance state, shown as a legend tooltip. */
export const GOV_SEGMENT_HINT: Record<GovSegmentKey, string> = {
  empty: 'Not started yet',
  draft: 'Not submitted yet',
  in_review: 'Submitted for review',
  approved: 'Reviewed and approved by a steward',
  bounced: 'Reviewed but not approved',
};

/** Counts keyed by governance state, as returned by the element API. */
export type GovCounts = Partial<Record<GovSegmentKey, number>> | null | undefined;

/** DQ grade "colour intent" (as carried on every scored badge) -> ramp token. */
export const DQ_INTENT_COLOR: Record<string, string> = {
  'positive-strong': 'var(--dq-excellent)',
  positive: 'var(--dq-good)',
  warning: 'var(--dq-adequate)',
  'warning-strong': 'var(--dq-weak)',
  negative: 'var(--dq-critical)',
};

export function dqIntentColor(intent: string | null | undefined): string {
  return DQ_INTENT_COLOR[intent ?? ''] ?? 'var(--adirra-ink-3)';
}

/**
 * Turn raw governance counts into ordered, percentage-sized bar segments.
 * Zero-count states are dropped so the bar never renders invisible slivers.
 */
export function govSegments(counts: GovCounts): VizSegment[] {
  const total = GOV_SEGMENT_ORDER.reduce((sum, key) => sum + (counts?.[key] ?? 0), 0);
  if (!total) return [];
  return GOV_SEGMENT_ORDER.flatMap((key) => {
    const count = counts?.[key] ?? 0;
    if (!count) return [];
    return [{
      label: GOV_SEGMENT_LABEL[key],
      count,
      pct: (count / total) * 100,
      color: GOV_SEGMENT_COLOR[key],
    }];
  });
}

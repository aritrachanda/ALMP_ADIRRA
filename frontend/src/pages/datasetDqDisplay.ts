/**
 * Pure display helpers for the dataset-level Data Quality badge (U4a, DQ §15).
 *
 * Extracted so the dataset roll-up presentation — donut geometry (column
 * roll-up + integrity arcs), the contribution breakdown (which columns dragged
 * the score down), the integrity line, the un-scored/fully-descoped fallback,
 * and the trend sparkline — is unit-testable without mounting AssetWorkspace.
 * The roll-up math lives in the backend (core/dq_dataset_scorer.py); nothing
 * here recomputes a score.
 */

import { DQ_GRADE_BANDS, formatDqScore } from './dqBadgeDisplay';

export type DatasetDQState = 'scored' | 'unscored';

export interface DatasetDQGrade {
  label?: string | null;
  color_intent?: string | null;
}

/** column_rollup line-item: one per in-scope scored column. */
export interface DatasetContribution {
  key: string;
  dq_score: number;
  weight: number;
  /** Share of the 0–100 mean (w·DQ/Σw); contributions sum to the mean. */
  contribution: number;
  /** Grade label/colour for this column's own score (e.g. "Weak"). */
  grade_label?: string | null;
  grade_color_intent?: string | null;
  /** Count of outstanding improvement actions for this column. */
  action_count?: number | null;
}

/** dataset_integrity line-item: PK uniqueness / referential integrity. */
export interface DatasetIntegrityItem {
  label: string;
  formula?: string | null;
  evidence_note?: string | null;
  earned: number;
  max: number;
  evidence?: Record<string, unknown> | null;
}

export interface DatasetDQComponent {
  name: string; // 'column_rollup' | 'dataset_integrity'
  earned: number;
  base_max: number;
  scaled_max?: number | null;
  scaled_earned?: number | null;
  grade?: DatasetDQGrade | null;
  /** integrity profile name on the dataset_integrity component. */
  profile?: string | null;
  column_count?: number | null;
  mean_score?: number | null;
  line_items?: (DatasetContribution | DatasetIntegrityItem)[] | null;
}

export interface DatasetDQTrendPoint {
  dq_score?: number | null;
  scored_at?: string | null;
  state?: string | null;
}

export interface DatasetDQBadge {
  state: DatasetDQState;
  reason?: string | null;
  dq_score?: number | null;
  grade_label?: string | null;
  grade_color_intent?: string | null;
  integrity_profile?: string | null;
  column_count?: number | null;
  applicable_components?: string[] | null;
  reallocation_factor?: number | null;
  model_version?: string | null;
  scored_at?: string | null;
  components?: DatasetDQComponent[] | null;
  trend?: DatasetDQTrendPoint[] | null;
}

/** Component → colour role class suffix (donut arc + legend dot). */
export const DATASET_DQ_COMPONENT_COLOR: Record<string, string> = {
  column_rollup: 'rollup',
  dataset_integrity: 'integrity',
};

export const DATASET_DQ_COMPONENT_LABELS: Record<string, string> = {
  column_rollup: 'Average DQ Score',
  dataset_integrity: 'Dataset integrity',
};

export function datasetComponentLabel(name: string): string {
  return DATASET_DQ_COMPONENT_LABELS[name] || name;
}

export function datasetComponentColorKey(name: string): string {
  return DATASET_DQ_COMPONENT_COLOR[name] || 'other';
}

export function isDatasetScored(badge: DatasetDQBadge | null | undefined): boolean {
  return !!badge && badge.state === 'scored' && badge.dq_score != null;
}

/** True when the whole table is descoped (all columns out of scope). */
export function isFullyDescoped(badge: DatasetDQBadge | null | undefined): boolean {
  return !!badge && badge.state === 'unscored' && badge.reason === 'fully_descoped';
}

/** Centre number of the donut: the integer score, or a dash when un-scored. */
export function datasetScoreText(badge: DatasetDQBadge | null | undefined): string {
  return isDatasetScored(badge) ? String(badge!.dq_score) : '—';
}

/**
 * Precise composite score for the donut centre — the sum of the scaled
 * component earns (what the integer `dq_score` is rounded from), shown with one
 * decimal when it isn't whole. The pill keeps the rounded integer. Falls back to
 * the integer score when component detail isn't available.
 */
export function datasetScorePreciseText(badge: DatasetDQBadge | null | undefined): string {
  if (!isDatasetScored(badge)) return '—';
  const comps = badge!.components;
  if (comps && comps.length) {
    const sum = comps.reduce((acc, c) => acc + (c.scaled_earned ?? 0), 0);
    if (sum > 0) return formatDqScore(sum);
  }
  return String(badge!.dq_score);
}

/** Band label, e.g. "Good" — falls back to a neutral phrase per reason. */
export function datasetBandLabel(badge: DatasetDQBadge | null | undefined): string {
  if (isDatasetScored(badge) && badge!.grade_label) return badge!.grade_label as string;
  if (badge?.state === 'unscored') {
    if (badge.reason === 'fully_descoped') return 'Fully descoped';
    return 'Not scored';
  }
  return 'Not scored';
}

/** Header chip text, e.g. "85 · Good". */
export function datasetBadgeText(badge: DatasetDQBadge | null | undefined): string {
  if (!isDatasetScored(badge)) return datasetBandLabel(badge);
  return `${badge!.dq_score} · ${badge!.grade_label ?? ''}`.trim();
}

/** CSS class for the grade band colour intent. */
export function datasetBandClass(badge: DatasetDQBadge | null | undefined): string {
  const intent = isDatasetScored(badge) ? badge!.grade_color_intent : null;
  return `dq-band--${intent || 'neutral'}`;
}

function component(
  badge: DatasetDQBadge | null | undefined,
  name: string,
): DatasetDQComponent | null {
  return badge?.components?.find((c) => c.name === name) ?? null;
}

export interface DatasetDonutSegment {
  name: string;
  colorKey: string;
  sweepFraction: number;
  fillFraction: number;
}

/** Donut geometry (§15.4): one arc per applicable component. */
export function datasetDonutSegments(
  badge: DatasetDQBadge | null | undefined,
): DatasetDonutSegment[] {
  if (!badge?.components) return [];
  return badge.components.map((c) => {
    const base = c.base_max || 0;
    const scaledMax = c.scaled_max ?? base;
    return {
      name: c.name,
      colorKey: datasetComponentColorKey(c.name),
      sweepFraction: Math.max(0, Math.min(1, scaledMax / 100)),
      fillFraction: base ? Math.max(0, Math.min(1, c.earned / base)) : 0,
    };
  });
}

export interface DatasetLegendRow {
  name: string;
  label: string;
  colorKey: string;
  earned: number;
  max: number;
  gradeLabel: string | null;
  gradeColorIntent: string | null;
}

/** Legend rows: one entry per applicable component. */
export function datasetComponentDisplays(
  badge: DatasetDQBadge | null | undefined,
): DatasetLegendRow[] {
  if (!badge?.components) return [];
  // Read the RE-ALLOCATED scale (§6), not the raw base_max — when a
  // component is inapplicable (e.g. no dataset_integrity for a table with
  // no PK/FK to check), the other component's max is scaled up to fill the
  // full 100 points, and the legend needs to reflect that, not the
  // un-rescaled base figures (previously showed e.g. "63.2/85" even when the
  // roll-up had actually been rescaled to /100).
  const factor = badge.reallocation_factor ?? 1;
  return badge.components.map((c) => ({
    name: c.name,
    label: datasetComponentLabel(c.name),
    colorKey: datasetComponentColorKey(c.name),
    earned: round2(c.scaled_earned ?? c.earned * factor),
    max: round2(c.scaled_max ?? (c.base_max || 0) * factor),
    gradeLabel: c.grade?.label ?? null,
    gradeColorIntent: c.grade?.color_intent ?? null,
  }));
}

/**
 * The contribution breakdown: the columns that dragged the roll-up down,
 * lowest score first (the backend already sorts them this way).
 */
export function datasetContributions(
  badge: DatasetDQBadge | null | undefined,
): DatasetContribution[] {
  const rollup = component(badge, 'column_rollup');
  return (rollup?.line_items as DatasetContribution[] | undefined) ?? [];
}

/** Score at/above which a column is Good or Excellent — i.e. not "dragging". */
export const DATASET_DRAG_THRESHOLD = DQ_GRADE_BANDS.find((b) => b.label === 'Good')?.min ?? 75;

/**
 * The subset of `datasetContributions` worth surfacing under "Columns
 * dragging the score down": a column already at Good/Excellent isn't
 * dragging the roll-up down, so it's filtered out here rather than the full
 * (unfiltered) column list the backend returns.
 */
export function datasetDraggingContributions(
  badge: DatasetDQBadge | null | undefined,
): DatasetContribution[] {
  return datasetContributions(badge).filter((c) => c.dq_score < DATASET_DRAG_THRESHOLD);
}

/** The integrity line-items (PK uniqueness / referential integrity), if any. */
export function datasetIntegrityItems(
  badge: DatasetDQBadge | null | undefined,
): DatasetIntegrityItem[] {
  const integrity = component(badge, 'dataset_integrity');
  return (integrity?.line_items as DatasetIntegrityItem[] | undefined) ?? [];
}

/** Human-readable label for an integrity profile. */
export const DATASET_INTEGRITY_PROFILE_LABELS: Record<string, string> = {
  pk_and_fk: 'PK + FK',
  pk_only: 'Primary key',
  fk_only: 'Foreign key',
};

export function integrityProfileLabel(profile: string | null | undefined): string | null {
  if (!profile) return null;
  return DATASET_INTEGRITY_PROFILE_LABELS[profile] ?? profile;
}

export interface SparklinePoint {
  x: number;
  y: number;
  score: number;
}

export interface SparklineGeometry {
  points: SparklinePoint[];
  /** "x,y x,y …" for an SVG polyline. */
  polyline: string;
  min: number;
  max: number;
  /** Last point — for the leading dot. */
  last: SparklinePoint;
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

/**
 * Sparkline geometry from the score history trend (§14 trend affordance).
 * Returns null when there are fewer than two scored points — a one-point
 * history is not a trend yet, so the caller shows the badge without a line.
 */
export function sparklineGeometry(
  trend: DatasetDQTrendPoint[] | null | undefined,
  width = 96,
  height = 26,
  pad = 3,
): SparklineGeometry | null {
  const scores = (trend ?? [])
    .filter((p) => p.dq_score != null)
    .map((p) => p.dq_score as number);
  if (scores.length < 2) return null;
  const min = Math.min(...scores);
  const max = Math.max(...scores);
  const span = max - min || 1;
  const n = scores.length;
  const points: SparklinePoint[] = scores.map((score, i) => {
    const x = pad + (i / (n - 1)) * (width - 2 * pad);
    const y = pad + (1 - (score - min) / span) * (height - 2 * pad);
    return { x: round2(x), y: round2(y), score };
  });
  return {
    points,
    polyline: points.map((p) => `${p.x},${p.y}`).join(' '),
    min,
    max,
    last: points[points.length - 1]!,
  };
}

/**
 * U4a — dataset DQ display helpers (datasetDqDisplay.ts).
 *
 * Covers the pure presentation logic behind the dataset roll-up badge:
 *  - score text + band label per grade band, incl. the fully-descoped fallback
 *  - donut segment geometry (sweep ∝ scaled_max)
 *  - the contribution breakdown (columns that dragged the score down)
 *  - the integrity line-items + profile label
 *  - the trend sparkline (null under two points; geometry otherwise)
 */

import { describe, it, expect } from 'vitest';
import {
  isDatasetScored,
  isFullyDescoped,
  datasetScoreText,
  datasetScorePreciseText,
  datasetBandLabel,
  datasetBadgeText,
  datasetBandClass,
  datasetDonutSegments,
  datasetComponentDisplays,
  datasetContributions,
  datasetDraggingContributions,
  datasetIntegrityItems,
  integrityProfileLabel,
  sparklineGeometry,
  type DatasetDQBadge,
} from '../src/pages/datasetDqDisplay';

// Worked example — dataset `exposures` → 85 · Good (§15.3).
const exposuresBadge: DatasetDQBadge = {
  state: 'scored',
  dq_score: 85,
  grade_label: 'Good',
  grade_color_intent: 'positive',
  integrity_profile: 'fk_only',
  column_count: 3,
  applicable_components: ['column_rollup', 'dataset_integrity'],
  reallocation_factor: 1.0,
  components: [
    {
      name: 'column_rollup', earned: 70.8, base_max: 85, scaled_max: 85, scaled_earned: 70.8,
      grade: { label: 'Adequate', color_intent: 'warning' },
      line_items: [
        { key: 'exposure_amount', dq_score: 73, weight: 1, contribution: 24.33,
          grade_label: 'Adequate', grade_color_intent: 'warning', action_count: 3 },
        { key: 'counterparty_country', dq_score: 81, weight: 1, contribution: 27.0,
          grade_label: 'Good', grade_color_intent: 'positive', action_count: 1 },
        { key: 'exposure_id', dq_score: 96, weight: 1, contribution: 32.0,
          grade_label: 'Excellent', grade_color_intent: 'positive-strong', action_count: 0 },
      ],
    },
    {
      name: 'dataset_integrity', earned: 14.3, base_max: 15, scaled_max: 15, scaled_earned: 14.3,
      profile: 'fk_only', grade: { label: 'Excellent', color_intent: 'positive-strong' },
      line_items: [
        { label: 'Referential integrity', earned: 14.3, max: 15,
          evidence_note: '0.25% of rows have an orphan foreign key → 14.3/15.' },
      ],
    },
  ],
  trend: [
    { dq_score: 82, scored_at: '2026-07-01T10:00:00', state: 'scored' },
    { dq_score: 84, scored_at: '2026-07-05T10:00:00', state: 'scored' },
    { dq_score: 85, scored_at: '2026-07-09T10:00:00', state: 'scored' },
  ],
};

const fullyDescoped: DatasetDQBadge = { state: 'unscored', reason: 'fully_descoped' };
const noScored: DatasetDQBadge = { state: 'unscored', reason: 'no_scored_columns' };

describe('dataset badge state + labels', () => {
  it('reads the scored badge', () => {
    expect(isDatasetScored(exposuresBadge)).toBe(true);
    expect(datasetScoreText(exposuresBadge)).toBe('85');
    expect(datasetBandLabel(exposuresBadge)).toBe('Good');
    expect(datasetBadgeText(exposuresBadge)).toBe('85 · Good');
    expect(datasetBandClass(exposuresBadge)).toBe('dq-band--positive');
  });

  it('donut shows the precise composite (decimals); the pill keeps the integer', () => {
    // scaled_earned 70.8 + 14.3 = 85.1 — donut shows 85.1, pill shows 85.
    expect(datasetScorePreciseText(exposuresBadge)).toBe('85.1');
    expect(datasetScoreText(exposuresBadge)).toBe('85');
    expect(datasetScorePreciseText(fullyDescoped)).toBe('—');
  });

  it('handles the fully-descoped fallback', () => {
    expect(isDatasetScored(fullyDescoped)).toBe(false);
    expect(isFullyDescoped(fullyDescoped)).toBe(true);
    expect(datasetScoreText(fullyDescoped)).toBe('—');
    expect(datasetBandLabel(fullyDescoped)).toBe('Fully descoped');
    expect(datasetBandClass(fullyDescoped)).toBe('dq-band--neutral');
  });

  it('handles the plain un-scored fallback', () => {
    expect(isFullyDescoped(noScored)).toBe(false);
    expect(datasetBandLabel(noScored)).toBe('Not scored');
  });

  it('handles null', () => {
    expect(isDatasetScored(null)).toBe(false);
    expect(datasetScoreText(null)).toBe('—');
    expect(datasetBandLabel(undefined)).toBe('Not scored');
  });
});

describe('donut + legend', () => {
  it('emits one arc per applicable component', () => {
    const segs = datasetDonutSegments(exposuresBadge);
    expect(segs.map((s) => s.name)).toEqual(['column_rollup', 'dataset_integrity']);
    expect(segs.map((s) => s.colorKey)).toEqual(['rollup', 'integrity']);
    expect(segs[0]!.sweepFraction).toBeCloseTo(0.85, 5); // 85/100
    expect(segs[1]!.sweepFraction).toBeCloseTo(0.15, 5); // 15/100
    expect(segs[0]!.fillFraction).toBeCloseTo(70.8 / 85, 5);
  });

  it('builds legend rows', () => {
    const rows = datasetComponentDisplays(exposuresBadge);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatchObject({ name: 'column_rollup', label: 'Average DQ Score', earned: 70.8, max: 85 });
    expect(rows[1]!.label).toBe('Dataset integrity');
  });
});

describe('contribution + integrity breakdown', () => {
  it('lists the columns that dragged the score down (backend order preserved)', () => {
    const contribs = datasetContributions(exposuresBadge);
    expect(contribs.map((c) => c.key)).toEqual([
      'exposure_amount', 'counterparty_country', 'exposure_id',
    ]);
    expect(contribs[0]!.dq_score).toBe(73);
  });

  it('carries the per-column grade + improvement-action count through', () => {
    const contribs = datasetContributions(exposuresBadge);
    expect(contribs[0]).toMatchObject({
      grade_label: 'Adequate', grade_color_intent: 'warning', action_count: 3,
    });
  });

  it('exposes the integrity line-items', () => {
    const items = datasetIntegrityItems(exposuresBadge);
    expect(items).toHaveLength(1);
    expect(items[0]!.label).toBe('Referential integrity');
    expect(items[0]!.earned).toBe(14.3);
  });

  it('labels the integrity profile', () => {
    expect(integrityProfileLabel('fk_only')).toBe('Foreign key');
    expect(integrityProfileLabel('pk_and_fk')).toBe('PK + FK');
    expect(integrityProfileLabel(null)).toBeNull();
  });

  it('returns empty breakdown for an un-scored badge', () => {
    expect(datasetContributions(fullyDescoped)).toEqual([]);
    expect(datasetIntegrityItems(fullyDescoped)).toEqual([]);
  });
});

describe('dragging-the-score-down filter', () => {
  it('drops columns already at Good/Excellent (>= 75)', () => {
    const dragging = datasetDraggingContributions(exposuresBadge);
    // exposure_amount=73 (Adequate), counterparty_country=81 (Good, dropped),
    // exposure_id=96 (Excellent, dropped).
    expect(dragging.map((c) => c.key)).toEqual(['exposure_amount']);
  });

  it('returns empty when every column is already Good/Excellent', () => {
    const allGood: DatasetDQBadge = {
      ...exposuresBadge,
      components: [
        {
          ...exposuresBadge.components![0]!,
          line_items: [
            { key: 'a', dq_score: 80, weight: 1, contribution: 40 },
            { key: 'b', dq_score: 95, weight: 1, contribution: 60 },
          ],
        },
        exposuresBadge.components![1]!,
      ],
    };
    expect(datasetDraggingContributions(allGood)).toEqual([]);
  });

  it('returns empty for an un-scored badge', () => {
    expect(datasetDraggingContributions(fullyDescoped)).toEqual([]);
  });
});

describe('trend sparkline', () => {
  it('builds geometry from ≥2 scored points', () => {
    const spark = sparklineGeometry(exposuresBadge.trend, 96, 26, 3);
    expect(spark).not.toBeNull();
    expect(spark!.points).toHaveLength(3);
    expect(spark!.min).toBe(82);
    expect(spark!.max).toBe(85);
    // First point at the left pad, last point at the right pad.
    expect(spark!.points[0]!.x).toBe(3);
    expect(spark!.last.x).toBe(93);
    // Highest score (85) sits at the top (min y = pad).
    expect(spark!.last.y).toBe(3);
    expect(spark!.polyline.split(' ')).toHaveLength(3);
  });

  it('returns null for a one-point history (not a trend yet)', () => {
    expect(sparklineGeometry([{ dq_score: 85 }])).toBeNull();
    expect(sparklineGeometry([])).toBeNull();
    expect(sparklineGeometry(null)).toBeNull();
  });
});

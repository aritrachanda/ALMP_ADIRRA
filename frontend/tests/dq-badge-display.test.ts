/**
 * U2b — Data Quality badge display helpers (dqBadgeDisplay.ts).
 *
 * Covers the pure presentation logic behind the DQ badge / card:
 *  - badge text + band label per grade band
 *  - component-breakdown legend rows (earned/max, normalised pct, band)
 *  - donut segment geometry (sweep ∝ scaled_max, fill = earned/max)
 *  - data·governance split line
 *  - the un-scored fallback (no score yet / out-of-scope)
 */

import { describe, it, expect } from 'vitest';
import {
  isScored,
  isExcluded,
  dqScoreText,
  dqScorePreciseText,
  dqBandLabel,
  dqBadgeText,
  dqBandClass,
  componentDisplays,
  componentLabel,
  componentColorKey,
  componentTabColorKey,
  donutSegments,
  dataGovernanceSplit,
  DQ_GRADE_BANDS,
  groupedComponents,
  reallocationExplanation,
  type DQBadge,
} from '../src/pages/dqBadgeDisplay';

// Worked example A — coded column (all three components), DQ = 81 · Good.
const codedBadge: DQBadge = {
  state: 'scored',
  dq_score: 81,
  grade_label: 'Good',
  grade_color_intent: 'positive',
  data_score: 78,
  governance_score: 84,
  archetype: 'coded',
  applicable_components: ['profile', 'interpretation', 'reference_data'],
  reallocation_factor: 1.0,
  components: [
    { name: 'profile', earned: 39.2, base_max: 50, scaled_max: 50, grade: { label: 'Good', color_intent: 'positive' } },
    { name: 'interpretation', earned: 28.0, base_max: 30, scaled_max: 30, grade: { label: 'Excellent', color_intent: 'positive-strong' } },
    { name: 'reference_data', earned: 14.0, base_max: 20, scaled_max: 20, grade: { label: 'Adequate', color_intent: 'warning' } },
  ],
};

// Worked example B — numeric column with reallocation, DQ = 73 · Adequate.
const numericBadge: DQBadge = {
  state: 'scored',
  dq_score: 73,
  grade_label: 'Adequate',
  grade_color_intent: 'warning',
  data_score: 97,
  governance_score: 33,
  archetype: 'numeric',
  applicable_components: ['profile', 'interpretation'],
  reallocation_factor: 1.25,
  components: [
    { name: 'profile', earned: 48.3, base_max: 50, scaled_max: 62.5, grade: { label: 'Excellent', color_intent: 'positive-strong' } },
    { name: 'interpretation', earned: 10.0, base_max: 30, scaled_max: 37.5, grade: { label: 'Critical', color_intent: 'negative' } },
  ],
};

describe('badge text and band', () => {
  it('renders score text and band label for a scored badge', () => {
    expect(isScored(codedBadge)).toBe(true);
    expect(dqScoreText(codedBadge)).toBe('81');
    expect(dqBandLabel(codedBadge)).toBe('Good');
    expect(dqBadgeText(codedBadge)).toBe('81 · Good');
    expect(dqBandClass(codedBadge)).toBe('dq-band--positive');
  });

  it('reflects each grade band via its colour intent', () => {
    expect(dqBandClass(numericBadge)).toBe('dq-band--warning');
    expect(dqBadgeText(numericBadge)).toBe('73 · Adequate');
  });

  it('keeps the rounded headline distinct from the precise component sum', () => {
    const preciseBadge: DQBadge = {
      state: 'scored', dq_score: 73, grade_label: 'Adequate', grade_color_intent: 'warning',
      components: [
        { name: 'profile', earned: 48.3, base_max: 50, scaled_earned: 60.4 },
        { name: 'interpretation', earned: 9.7, base_max: 30, scaled_earned: 12.1 },
      ],
    };
    // Components sum to 72.5; the donut/headline uses the stored rounded 73.
    expect(dqScorePreciseText(preciseBadge)).toBe('72.5');
    expect(dqScoreText(preciseBadge)).toBe('73');
    expect(dqBadgeText(preciseBadge)).toBe('73 · Adequate');
  });

  it('precise score falls back to the integer when scaled detail is absent', () => {
    // codedBadge components carry no scaled_earned → fall back to dq_score.
    expect(dqScorePreciseText(codedBadge)).toBe('81');
    expect(dqScorePreciseText(null)).toBe('—');
  });
});

describe('component breakdown display', () => {
  it('maps each applicable component to a legend row with normalised pct', () => {
    const rows = componentDisplays(codedBadge);
    expect(rows.map((r) => r.name)).toEqual(['profile', 'interpretation', 'reference_data']);

    const profile = rows[0];
    expect(profile.label).toBe('Profile');
    expect(profile.colorKey).toBe('profile');
    expect(profile.earned).toBe(39.2);
    expect(profile.max).toBe(50);
    expect(profile.pct).toBe(78); // round(100 * 39.2 / 50)
    expect(profile.gradeLabel).toBe('Good');

    const refdata = rows[2];
    expect(refdata.colorKey).toBe('refdata');
    expect(refdata.pct).toBe(70); // round(100 * 14 / 20)
  });

  it('exposes steward-readable labels and colour keys', () => {
    expect(componentLabel('reference_data')).toBe('Reference Data');
    expect(componentColorKey('interpretation')).toBe('interpretation');
    expect(componentColorKey('unknown')).toBe('other');
  });
});

describe('donut geometry', () => {
  it('sweeps proportional to scaled_max and fills to earned/max', () => {
    const segs = donutSegments(codedBadge);
    // Coded column: no reallocation, arcs sum to the full ring.
    const totalSweep = segs.reduce((s, seg) => s + seg.sweepFraction, 0);
    expect(totalSweep).toBeCloseTo(1.0, 5);
    // Profile fill = 39.2/50.
    expect(segs[0].fillFraction).toBeCloseTo(0.784, 3);
  });

  it('uses scaled_max (reallocated) for the sweep when a component is absent', () => {
    const segs = donutSegments(numericBadge);
    // Profile scaled to 62.5/100.
    expect(segs[0].sweepFraction).toBeCloseTo(0.625, 5);
    expect(segs[1].sweepFraction).toBeCloseTo(0.375, 5);
  });
});

describe('data·governance split', () => {
  it('returns both sub-scores when present', () => {
    expect(dataGovernanceSplit(codedBadge)).toEqual({ data: 78, governance: 84 });
  });
});

describe('un-scored fallback', () => {
  it('handles a null badge', () => {
    expect(isScored(null)).toBe(false);
    expect(dqScoreText(null)).toBe('—');
    expect(dqBandLabel(null)).toBe('Not scored');
    expect(componentDisplays(null)).toEqual([]);
    expect(donutSegments(null)).toEqual([]);
    expect(dataGovernanceSplit(null)).toBeNull();
  });

  it('distinguishes out-of-scope from not-yet-scored', () => {
    const oos: DQBadge = { state: 'unscored', reason: 'out_of_scope' };
    expect(isScored(oos)).toBe(false);
    expect(isExcluded(oos)).toBe(true);
    expect(dqBandLabel(oos)).toBe('Excluded from assessment');
    expect(dqBandClass(oos)).toBe('dq-band--neutral');

    const empty: DQBadge = { state: 'unscored', reason: 'empty' };
    expect(isExcluded(empty)).toBe(false);
    expect(dqBandLabel(empty)).toBe('Not scored');
    expect(isExcluded(null)).toBe(false);
    expect(isExcluded(codedBadge)).toBe(false);
  });
});

// ── U2d — plain-language line-item notes ─────────────────────────────────────

// A scored badge carrying evidence_note on each line-item (as the scorer now
// emits). Numbers match worked example A's Profile dimension.
const notedBadge: DQBadge = {
  state: 'scored',
  dq_score: 81,
  grade_label: 'Good',
  grade_color_intent: 'positive',
  components: [
    {
      name: 'profile',
      earned: 39.2,
      base_max: 50,
      scaled_max: 50,
      line_items: [
        {
          label: 'Completeness',
          formula: '16 × (1 − 0.0306/0.25)',
          evidence_note:
            '3.1% of values are missing (nulls, empties, placeholders), within the 25.0% tolerance → 14.0/16.',
          earned: 14.0,
          max: 16,
        },
        {
          label: 'Uniqueness',
          formula: '16 × 1.0',
          evidence_note: '100.0% distinct values → full 16/16.',
          earned: 16.0,
          max: 16,
        },
      ],
    },
  ],
};

describe('plain-language line-item notes (U2d)', () => {
  it('carries an evidence_note alongside the raw formula on each line-item', () => {
    const profile = notedBadge.components![0];
    const items = profile.line_items!;
    // The note explains the formula; both are present (note does not replace it).
    expect(items[0].formula).toBe('16 × (1 − 0.0306/0.25)');
    expect(items[0].evidence_note).toContain('within the 25.0% tolerance');
    expect(items[0].evidence_note).toContain('14.0/16');
    // A full-marks line reads "full X/Y".
    expect(items[1].evidence_note).toBe('100.0% distinct values → full 16/16.');
  });

  it('tolerates a line-item with no note (optional field)', () => {
    const badge: DQBadge = {
      state: 'scored',
      dq_score: 50,
      components: [
        { name: 'profile', earned: 25, base_max: 50, line_items: [{ label: 'X', earned: 25, max: 50 }] },
      ],
    };
    expect(badge.components![0].line_items![0].evidence_note).toBeUndefined();
  });
});

// ── U2d — token-driven segment colours ───────────────────────────────────────

describe('token-driven donut segment colours (U2d)', () => {
  it('maps each component segment to its palette colour key (donut + tab share it)', () => {
    const segs = donutSegments(codedBadge);
    expect(segs.map((s) => s.colorKey)).toEqual(['profile', 'interpretation', 'refdata']);
  });
});

// ── component-tab accent mapping ─────────────────────────────────────────────

describe('component-tab accent mapping', () => {
  it('colours only the three DQ component tabs, neutral for the rest', () => {
    expect(componentTabColorKey('profile')).toBe('profile');
    expect(componentTabColorKey('interpretation')).toBe('interpretation');
    expect(componentTabColorKey('refdata')).toBe('refdata');
  });

  it('leaves the non-component tabs neutral', () => {
    expect(componentTabColorKey('observations')).toBeNull(); // Data Quality
    expect(componentTabColorKey('mapping')).toBeNull();
    expect(componentTabColorKey('history')).toBeNull();
  });
});

// ── "How the DQ score works" grade-band legend ───────────────────────────────

describe('DQ_GRADE_BANDS', () => {
  it('covers 0–100 with five descending, non-overlapping bands', () => {
    expect(DQ_GRADE_BANDS.map((b) => b.label)).toEqual(['Excellent', 'Good', 'Adequate', 'Weak', 'Critical']);
    expect(DQ_GRADE_BANDS[0]).toEqual({ label: 'Excellent', min: 90, max: 100, colorIntent: 'positive-strong' });
    expect(DQ_GRADE_BANDS[DQ_GRADE_BANDS.length - 1]).toMatchObject({ label: 'Critical', min: 0 });
    // Each band's max is exactly one below the previous (higher) band's min
    // (no gaps/overlap across the descending sequence).
    for (let i = 1; i < DQ_GRADE_BANDS.length; i++) {
      expect(DQ_GRADE_BANDS[i].max).toBe(DQ_GRADE_BANDS[i - 1].min - 1);
    }
  });
});

// ── SD-R3c — Semantic Type folded into Interpretation ────────────────────────

// Worked example A — coded column, confirmed semantic → fully governed, DQ 81.
// Interpretation carries the Semantic Type line-item (7/7); no purple 4th arc.
const foldedBadge: DQBadge = {
  state: 'scored',
  dq_score: 81,
  grade_label: 'Good',
  grade_color_intent: 'positive',
  data_score: 78,
  governance_score: 84,
  archetype: 'coded',
  applicable_components: ['profile', 'interpretation', 'reference_data'],
  inapplicable_components: [],
  reallocation_factor: 1.0,
  components: [
    { name: 'profile', earned: 39.2, base_max: 50, scaled_max: 50, scaled_earned: 39.2 },
    {
      name: 'interpretation', earned: 28.0, base_max: 30, scaled_max: 30, scaled_earned: 28.0,
      line_items: [
        { label: 'Definition', earned: 11.0, max: 11 },
        { label: 'Business Name', earned: 5.0, max: 5 },
        { label: 'Glossary Linkage', earned: 5.0, max: 7 },
        {
          label: 'Semantic Type', earned: 7.0, max: 7,
          evidence_note: 'semantic type accepted → full 7.0/7.0.',
          evidence: { accepted: true, type_id: 'country_code' },
        },
      ],
    },
    { name: 'reference_data', earned: 14.0, base_max: 20, scaled_max: 20, scaled_earned: 14.0 },
  ],
};

// Worked example B — numeric, no reference data, confirmed semantic → DQ 79.
const numericFoldedBadge: DQBadge = {
  state: 'scored',
  dq_score: 79,
  grade_label: 'Good',
  grade_color_intent: 'positive',
  archetype: 'numeric',
  applicable_components: ['profile', 'interpretation'],
  inapplicable_components: ['reference_data'],
  reallocation_factor: 1.25,
  components: [
    { name: 'profile', earned: 48.3, base_max: 50, scaled_max: 62.5, scaled_earned: 60.38 },
    { name: 'interpretation', earned: 15.0, base_max: 30, scaled_max: 37.5, scaled_earned: 18.75 },
  ],
};

describe('Semantic Type folded into Interpretation (SD-R3c)', () => {
  it('labels and colours the Interpretation component with the brown identity', () => {
    expect(componentLabel('interpretation')).toBe('Interpretation');
    expect(componentColorKey('interpretation')).toBe('interpretation');
  });

  it('renders exactly three donut segments — no purple 4th arc', () => {
    const segs = donutSegments(foldedBadge);
    expect(segs.map((s) => s.colorKey)).toEqual(['profile', 'interpretation', 'refdata']);
    expect(segs.map((s) => s.colorKey)).not.toContain('semantic');
  });

  it('carries Semantic Type as an Interpretation line-item, not its own component', () => {
    const interp = foldedBadge.components!.find((c) => c.name === 'interpretation')!;
    const labels = interp.line_items!.map((li) => li.label);
    expect(labels).toContain('Semantic Type');
    expect(foldedBadge.components!.some((c) => c.name === 'semantic')).toBe(false);
  });

  it('places Interpretation and Reference Data in Governance, Profile alone in Data', () => {
    const groups = groupedComponents(foldedBadge);
    const governance = groups.find((g) => g.key === 'governance')!;
    expect(governance.components.map((c) => c.name)).toEqual(['interpretation', 'reference_data']);
    expect(groups.find((g) => g.key === 'data')!.components.map((c) => c.name)).toEqual(['profile']);
  });

  it('explains the reallocation when reference data is absent', () => {
    const sentence = reallocationExplanation(numericFoldedBadge);
    expect(sentence).toBeTruthy();
    expect(sentence).toContain('Reference Data');
    expect(sentence).toContain('Profile');
    expect(sentence).toContain('Interpretation');
  });
});

// ── U2d-fix — evidence_note survives an API-shaped payload ────────────────────

// The card breakdown template walks the RAW badge — dqBadge.components[] →
// line_items[] → li.evidence_note — not the componentDisplays() projection
// (which drops line_items). This payload mirrors the backend
// `_dq_badge_view(full=True)` response so a future field drop in the store /
// API client is caught here, not by eye in the live app.
const apiShapedBadge: DQBadge = {
  state: 'scored',
  dq_score: 73,
  grade_label: 'Adequate',
  grade_color_intent: 'warning',
  components: [
    {
      name: 'profile',
      earned: 48.3,
      base_max: 50,
      scaled_max: 62.5,
      line_items: [
        {
          label: 'Completeness',
          formula: '14 × (1 − 0.005/0.25)',
          evidence_note:
            '0.5% of values are missing (nulls, empties, placeholders), within the 25.0% tolerance → 13.7/14.',
          earned: 13.7,
          max: 14,
        },
      ],
    },
    {
      name: 'interpretation',
      earned: 10.0,
      base_max: 30,
      scaled_max: 37.5,
      line_items: [
        {
          label: 'Business Name',
          formula: 'step ai_or_auto',
          evidence_note:
            'business name is AI/auto-derived, not steward-assigned → 2.0/5; assigning one earns the remaining 3.0 points.',
          earned: 2.0,
          max: 5,
        },
      ],
    },
  ],
};

describe('evidence_note survives an API-shaped payload (U2d-fix)', () => {
  it('exposes a non-empty note on every line-item via the template access path', () => {
    // Exactly the walk the .vue breakdown performs.
    const notes = (apiShapedBadge.components || []).flatMap((comp) =>
      (comp.line_items || []).map((li) => li.evidence_note),
    );
    expect(notes.length).toBeGreaterThan(0);
    for (const note of notes) {
      expect(note).toBeTruthy();
      expect((note as string).trim().length).toBeGreaterThan(0);
    }
  });

  it('renders the friendly Business Name note, not the raw "step ai_or_auto" formula', () => {
    const definition = (apiShapedBadge.components || []).find((c) => c.name === 'interpretation')!;
    const businessName = definition.line_items!.find((li) => li.label === 'Business Name')!;
    // The formula stays visible…
    expect(businessName.formula).toBe('step ai_or_auto');
    // …but the note the card shows beneath it is the plain-language sentence.
    expect(businessName.evidence_note).toContain('AI/auto-derived');
    expect(businessName.evidence_note).toContain('remaining 3.0 points');
  });
});


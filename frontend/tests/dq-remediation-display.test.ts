/**
 * U4b — remediation slab + legibility display helpers (dqBadgeDisplay.ts).
 *
 * Covers the pure presentation logic added for the element DQ card:
 *  - the improvement-action list (backend-derived, impact-sorted)
 *  - the path-to-next-grade payload, including the already-top-band case
 *  - the data·governance pillar % placement (Profile → data, Interpretation → governance)
 *  - the §6 reallocation explanation across bases (80, 70, full-100 → none)
 *
 * The authoritative point-delta derivation lives in the backend
 * (core/dq_remediation.py, tested in pytest); these tests assert the display
 * helpers read and shape that data faithfully and never contradict the score.
 */

import { describe, it, expect } from 'vitest';
import {
  dqActions,
  dqPathToNextGrade,
  pillarForComponent,
  reallocationExplanation,
  actionCaption,
  railDqBadge,
  scaledBreakdown,
  groupedComponents,
  observationsForAction,
  unmatchedObservations,
  lineItemForFindingCategory,
  dqGradeDistribution,
  type DQBadge,
  type DQAction,
  type DQObservation,
} from '../src/pages/dqBadgeDisplay';

// Worked example A — coded column, 81 · Good, all three components apply.
const codedBadge: DQBadge = {
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
    { name: 'profile', earned: 39.2, base_max: 50 },
    { name: 'interpretation', earned: 28.0, base_max: 30 },
    { name: 'reference_data', earned: 14.0, base_max: 20 },
  ],
  actions: [
    { component: 'profile', line_item: 'Consistency', step: 'Investigate…', action_type: 'data', points: 6.0 },
    { component: 'reference_data', line_item: 'Codes documented', step: 'Document…', action_type: 'governance', points: 3.0 },
    { component: 'reference_data', line_item: 'Code set approved', step: 'Submit…', action_type: 'governance', points: 3.0 },
    { component: 'profile', line_item: 'Validity', step: 'Fix…', action_type: 'data', points: 2.8 },
  ],
  path_to_next_grade: {
    at_top_band: false,
    current_score: 81,
    current_grade: 'Good',
    next_grade: 'Excellent',
    next_grade_min: 90,
    points_needed: 9.0,
    reachable: true,
    actions: [
      { component: 'profile', line_item: 'Consistency', step: 'Investigate…', action_type: 'data', points: 6.0 },
      { component: 'reference_data', line_item: 'Codes documented', step: 'Document…', action_type: 'governance', points: 3.0 },
    ],
  },
};

// Worked example B — numeric column, 73 · Adequate, reference data reallocated out (basis 80).
const numericBadge: DQBadge = {
  state: 'scored',
  dq_score: 73,
  grade_label: 'Adequate',
  grade_color_intent: 'warning',
  data_score: 97,
  governance_score: 33,
  archetype: 'numeric',
  applicable_components: ['profile', 'interpretation'],
  inapplicable_components: ['reference_data'],
  reallocation_factor: 1.25,
  components: [
    { name: 'profile', earned: 48.3, base_max: 50 },
    { name: 'interpretation', earned: 10.0, base_max: 30 },
  ],
  actions: [
    { component: 'interpretation', line_item: 'Glossary Linkage', step: 'Link…', action_type: 'governance', points: 12.5 },
  ],
  path_to_next_grade: {
    at_top_band: false,
    current_score: 73,
    current_grade: 'Adequate',
    next_grade: 'Good',
    next_grade_min: 75,
    points_needed: 2.0,
    reachable: true,
    actions: [
      { component: 'interpretation', line_item: 'Glossary Linkage', step: 'Link…', action_type: 'governance', points: 12.5 },
    ],
  },
};

const topBandBadge: DQBadge = {
  state: 'scored',
  dq_score: 95,
  grade_label: 'Excellent',
  grade_color_intent: 'positive-strong',
  data_score: 98,
  governance_score: 92,
  applicable_components: ['profile', 'interpretation'],
  inapplicable_components: ['reference_data'],
  reallocation_factor: 1.25,
  components: [
    { name: 'profile', earned: 49, base_max: 50 },
    { name: 'interpretation', earned: 27, base_max: 30 },
  ],
  actions: [
    { component: 'interpretation', line_item: 'Glossary Linkage', step: 'Link…', action_type: 'governance', points: 3.8 },
  ],
  path_to_next_grade: {
    at_top_band: true,
    current_score: 95,
    current_grade: 'Excellent',
    next_grade: null,
    next_grade_min: null,
    points_needed: 0,
    reachable: true,
    actions: [],
  },
};

const unscoredBadge: DQBadge = { state: 'unscored', reason: 'out_of_scope' };

// ── actions ──────────────────────────────────────────────────────────────────

describe('dqActions', () => {
  it('returns the backend-derived action list, impact-sorted (largest first)', () => {
    const actions = dqActions(codedBadge);
    expect(actions).toHaveLength(4);
    expect(actions.map((a) => a.points)).toEqual([...actions.map((a) => a.points)].sort((x, y) => y - x));
    expect(actions[0].line_item).toBe('Consistency');
    expect(actions[0].points).toBe(6.0);
  });

  it('returns an empty list for an un-scored (out-of-scope) column — no slab', () => {
    expect(dqActions(unscoredBadge)).toEqual([]);
    expect(dqActions(null)).toEqual([]);
  });

  it('carries the governance/data action_type split through', () => {
    const actions = dqActions(numericBadge);
    expect(actions[0].action_type).toBe('governance');
    expect(actions[0].component).toBe('interpretation');
  });
});

// ── path to next grade ───────────────────────────────────────────────────────

describe('dqPathToNextGrade', () => {
  it('exposes the minimal action set that crosses the next band', () => {
    const path = dqPathToNextGrade(codedBadge)!;
    expect(path.at_top_band).toBe(false);
    expect(path.next_grade).toBe('Excellent');
    expect(path.points_needed).toBe(9.0);
    expect(path.actions.map((a) => a.line_item)).toEqual(['Consistency', 'Codes documented']);
  });

  it('reports the already-top-band case with no actions needed', () => {
    const path = dqPathToNextGrade(topBandBadge)!;
    expect(path.at_top_band).toBe(true);
    expect(path.next_grade).toBeNull();
    expect(path.actions).toEqual([]);
  });

  it('returns null for an un-scored column', () => {
    expect(dqPathToNextGrade(unscoredBadge)).toBeNull();
  });
});

// ── data·governance pillar placement (legibility #1) ─────────────────────────

describe('pillarForComponent', () => {
  it('places the data % beside Profile and the governance % beside Interpretation', () => {
    expect(pillarForComponent(codedBadge, 'profile')).toEqual({ label: 'data', pct: 78 });
    expect(pillarForComponent(codedBadge, 'interpretation')).toEqual({ label: 'governance', pct: 84 });
  });

  it('shows no pillar on any other component or when un-scored', () => {
    expect(pillarForComponent(codedBadge, 'reference_data')).toBeNull();
    expect(pillarForComponent(unscoredBadge, 'profile')).toBeNull();
  });
});

// ── reallocation explanation (legibility #4) ─────────────────────────────────

describe('reallocationExplanation', () => {
  it('explains on the composite 100 scale, naming the missing component and the scaled blocks', () => {
    expect(reallocationExplanation(numericBadge)).toBe(
      "Reference Data doesn't apply to this field, so Profile and Interpretation are "
        + 'scaled to fill the full 100 (Profile 62.5 + Interpretation 37.5). '
        + '73 of 100 earned = 73%.',
    );
  });

  it('is correct for any basis — e.g. a synthetic out-of-70 case rescaled to 100', () => {
    const badge70: DQBadge = {
      state: 'scored',
      dq_score: 64,
      grade_label: 'Adequate',
      inapplicable_components: ['reference_data'],
      reallocation_factor: 100 / 70,
      components: [
        { name: 'profile', earned: 35, base_max: 50 },
        { name: 'interpretation', earned: 10, base_max: 20 },
      ],
    };
    expect(reallocationExplanation(badge70)).toBe(
      "Reference Data doesn't apply to this field, so Profile and Interpretation are "
        + 'scaled to fill the full 100 (Profile 71.4 + Interpretation 28.6). '
        + '64 of 100 earned = 64%.',
    );
  });

  it('shows nothing when the full 100 basis applies (no reallocation)', () => {
    expect(reallocationExplanation(codedBadge)).toBeNull();
  });

  it('shows nothing for an un-scored column', () => {
    expect(reallocationExplanation(unscoredBadge)).toBeNull();
  });
});

// ── U4b-fix — one scale everywhere: scaled breakdown reconciliation (Task 1) ──

// A reallocated column (factor 1.25, out-of-80): every raw line-item / block
// rescaled to the composite 0–100 scale. Values chosen to mirror the arrears
// worked example so the reconciliation is exact.
const reallocatedBadge: DQBadge = {
  state: 'scored',
  dq_score: 56,
  grade_label: 'Weak',
  archetype: 'numeric',
  applicable_components: ['profile', 'interpretation'],
  inapplicable_components: ['reference_data'],
  reallocation_factor: 1.25,
  components: [
    {
      name: 'profile', earned: 35.8, base_max: 50, scaled_earned: 44.75, scaled_max: 62.5,
      line_items: [
        { label: 'Completeness', formula: '14 × (1 − 0.6987/0.25)', earned: 0, max: 14 },
        { label: 'Validity', formula: '10 × (1 − 0/0.10)', earned: 10, max: 10 },
        { label: 'Consistency', formula: '18 − 0.2', earned: 17.8, max: 18 },
        { label: 'Findings overlay', formula: '8 − 0', earned: 8, max: 8 },
      ],
    },
    {
      name: 'interpretation', earned: 9.0, base_max: 30, scaled_earned: 11.25, scaled_max: 37.5,
      line_items: [
        { label: 'Definition', formula: '4 + 1 + 3', earned: 8, max: 14 },
        { label: 'Business Name', formula: 'step ai_or_auto', earned: 1, max: 6 },
        { label: 'Glossary Linkage', formula: 'unlinked → 0', earned: 0, max: 10 },
      ],
    },
  ],
};

// A full-100-basis column (factor 1.0): nothing changes under rescale.
const fullBasisBadge: DQBadge = {
  state: 'scored',
  dq_score: 81,
  grade_label: 'Good',
  archetype: 'coded',
  applicable_components: ['profile', 'interpretation', 'reference_data'],
  inapplicable_components: [],
  reallocation_factor: 1.0,
  components: [
    {
      name: 'profile', earned: 39.2, base_max: 50, scaled_earned: 39.2, scaled_max: 50,
      line_items: [
        { label: 'Completeness', formula: '16 × (1 − 0.0306/0.25)', earned: 14, max: 16 },
        { label: 'Validity', formula: '14 × (1 − 0.02/0.10)', earned: 11.2, max: 14 },
        { label: 'Consistency', formula: '12 − 6', earned: 6, max: 12 },
        { label: 'Findings overlay', formula: '8 − 0', earned: 8, max: 8 },
      ],
    },
  ],
};

describe('scaledBreakdown', () => {
  it('rescales a reallocated column to the composite scale and reconciles', () => {
    const comps = scaledBreakdown(reallocatedBadge);
    // Line-items rescaled ×1.25 (Completeness 0/17.5, Validity 12.5/12.5).
    const profile = comps.find((c) => c.name === 'profile')!;
    const completeness = profile.line_items.find((li) => li.label === 'Completeness')!;
    const validity = profile.line_items.find((li) => li.label === 'Validity')!;
    expect(completeness.earned).toBe(0);
    expect(completeness.max).toBe(17.5);
    expect(validity.earned).toBe(12.5);
    expect(validity.max).toBe(12.5);
    // Line-items sum to their block.
    const liEarned = profile.line_items.reduce((s, li) => s + li.earned, 0);
    expect(Math.round(liEarned * 100) / 100).toBe(profile.earned);
    expect(profile.earned).toBe(44.75);
    expect(profile.max).toBe(62.5);
    // Blocks sum to the composite = the headline score.
    const blockEarned = comps.reduce((s, c) => s + c.earned, 0);
    expect(Math.round(blockEarned)).toBe(reallocatedBadge.dq_score);
  });

  it('makes the ×factor reallocation step visible on the formula (bridge)', () => {
    const comps = scaledBreakdown(reallocatedBadge);
    const completeness = comps[0].line_items.find((li) => li.label === 'Completeness')!;
    expect(completeness.formula).toContain('× 1.25');
  });

  it('leaves a full-100-basis column unchanged and reconciling', () => {
    const comps = scaledBreakdown(fullBasisBadge);
    const profile = comps.find((c) => c.name === 'profile')!;
    // No ×factor reallocation step appended when factor is 1 (formula unchanged).
    expect(profile.line_items[0].formula).toBe('16 × (1 − 0.0306/0.25)');
    expect(profile.line_items[0].formula).not.toContain('× 1');
    const liEarned = profile.line_items.reduce((s, li) => s + li.earned, 0);
    expect(Math.round(liEarned * 100) / 100).toBe(profile.earned);
    expect(profile.earned).toBe(39.2);
    expect(profile.max).toBe(50);
  });

  it('returns nothing for an un-scored column', () => {
    expect(scaledBreakdown(unscoredBadge)).toEqual([]);
  });
});

// ── Data·Governance group headers (grouped breakdown) ─────────────────────────

describe('groupedComponents', () => {
  it('groups Profile alone under Data and the rest under Governance, carrying the pillar % and summed points', () => {
    const groups = groupedComponents(codedBadge);
    expect(groups.map((g) => g.key)).toEqual(['data', 'governance']);

    const data = groups.find((g) => g.key === 'data')!;
    expect(data.label).toBe('Data');
    expect(data.pct).toBe(78);
    expect(data.components.map((c) => c.name)).toEqual(['profile']);
    expect(data.earned).toBe(39.2);
    expect(data.max).toBe(50);

    const governance = groups.find((g) => g.key === 'governance')!;
    expect(governance.label).toBe('Governance');
    expect(governance.pct).toBe(84);
    expect(governance.components.map((c) => c.name)).toEqual(['interpretation', 'reference_data']);
    expect(governance.earned).toBe(42);
    expect(governance.max).toBe(50);
  });

  it('omits the Governance group when no non-Profile component applies', () => {
    const groups = groupedComponents(numericBadge);
    expect(groups.map((g) => g.key)).toEqual(['data', 'governance']);
    const governance = groups.find((g) => g.key === 'governance')!;
    expect(governance.components.map((c) => c.name)).toEqual(['interpretation']);
  });

  it('returns an empty list for an un-scored column', () => {
    expect(groupedComponents(unscoredBadge)).toEqual([]);
  });
});

// ── U4b-fix — action destination + path landing (Task 2) ─────────────────────

const badgeWithDestinations: DQBadge = {
  state: 'scored',
  dq_score: 56,
  grade_label: 'Weak',
  applicable_components: ['profile', 'interpretation'],
  reallocation_factor: 1.25,
  components: [{ name: 'profile', earned: 35.8, base_max: 50 }],
  actions: [
    {
      component: 'profile', line_item: 'Completeness', step: 'Fill…',
      action_type: 'data', points: 17.5, resulting_score: 73.5, resulting_grade: 'Adequate',
    },
  ],
  path_to_next_grade: {
    at_top_band: false,
    current_score: 56,
    current_grade: 'Weak',
    next_grade: 'Adequate',
    next_grade_min: 60,
    points_needed: 4.0,
    landing_score: 73.5,
    landing_grade: 'Adequate',
    reachable: true,
    actions: [
      {
        component: 'profile', line_item: 'Completeness', step: 'Fill…',
        action_type: 'data', points: 17.5, resulting_score: 73.5, resulting_grade: 'Adequate',
      },
    ],
  },
};

describe('action destination + path landing', () => {
  it('each action carries its resulting score + grade (destination, not a bare delta)', () => {
    const actions = dqActions(badgeWithDestinations);
    expect(actions[0].resulting_score).toBe(73.5);
    expect(actions[0].resulting_grade).toBe('Adequate');
  });

  it('the path exposes the real landing score, not the band threshold', () => {
    const path = dqPathToNextGrade(badgeWithDestinations)!;
    // Threshold is 60, but +17.5 actually lands at 73.5.
    expect(path.next_grade_min).toBe(60);
    expect(path.landing_score).toBe(73.5);
    expect(path.landing_grade).toBe('Adequate');
  });
});

// ── U4b-fix — observations folded into actions as evidence (Task 5) ───────────

const OBSERVATIONS: DQObservation[] = [
  {
    title: 'High proportion of missing values', category: 'completeness',
    rationale: "69.9% of values in 'arrears' are NULL.", severity: 'high', source: 'rule',
  },
  {
    title: 'Numeric outliers detected', category: 'consistency',
    rationale: '12 values sit far outside the normal range.', severity: 'attention', source: 'rule',
  },
  {
    title: 'Values not matching expected IBAN format', category: 'regulatory',
    rationale: 'Some values are not valid IBANs.', severity: 'high', source: 'rule',
  },
];

const ACTIONS: DQAction[] = [
  { component: 'profile', line_item: 'Completeness', step: 'Fill…', action_type: 'data', points: 17.5 },
  { component: 'profile', line_item: 'Consistency', step: 'Check…', action_type: 'data', points: 6.0 },
];

describe('observation folding (Task 5)', () => {
  it('maps a finding category to its scored line-item', () => {
    expect(lineItemForFindingCategory('completeness')).toBe('Completeness');
    expect(lineItemForFindingCategory('consistency')).toBe('Consistency');
    expect(lineItemForFindingCategory('regulatory')).toBeNull();
    expect(lineItemForFindingCategory(null)).toBeNull();
  });

  it('attaches the completeness observation to the completeness action (no JSON)', () => {
    const completeness = ACTIONS[0];
    const obs = observationsForAction(completeness, OBSERVATIONS);
    expect(obs).toHaveLength(1);
    expect(obs[0].rationale).toBe("69.9% of values in 'arrears' are NULL.");
  });

  it('attaches the outlier observation to the consistency (plausibility) action', () => {
    const consistency = ACTIONS[1];
    const obs = observationsForAction(consistency, OBSERVATIONS);
    expect(obs).toHaveLength(1);
    expect(obs[0].category).toBe('consistency');
  });

  it('keeps observations with no matching action as standalone (regulatory here)', () => {
    const unmatched = unmatchedObservations(ACTIONS, OBSERVATIONS);
    expect(unmatched).toHaveLength(1);
    expect(unmatched[0].category).toBe('regulatory');
  });

  it('treats a matched category with no action as unmatched (line-item already full)', () => {
    // Only a Consistency action exists → the completeness observation has no home.
    const unmatched = unmatchedObservations([ACTIONS[1]], OBSERVATIONS);
    expect(unmatched.map((o) => o.category).sort()).toEqual(['completeness', 'regulatory']);
  });
});

// ── U4b-fix-2 — bold issue caption per action (Task 2) ───────────────────────

describe('actionCaption', () => {
  const cap = (line_item: string, step = ''): string =>
    actionCaption({ component: 'x', line_item, step, action_type: 'data', points: 1 });

  it('names the data-side issues (not the fix)', () => {
    expect(cap('Completeness')).toBe('Too many missing values');
    expect(cap('Consistency')).toBe('Unusual values found');
    expect(cap('Validity')).toBe("Values don't match the expected format");
    expect(cap('Uniqueness')).toBe('Duplicate key values');
  });

  it('reads the Definition present/absent nuance off the gap-aware step', () => {
    expect(cap('Definition', 'Write a short business-friendly description for this column.'))
      .toBe('No description');
    expect(cap('Definition', "Advance this column's description to approved."))
      .toBe('Description not approved');
  });

  it('reads the Business Name and Glossary nuances off the step', () => {
    expect(cap('Business Name', 'Give this column a plain-English business name.'))
      .toBe('No business name');
    expect(cap('Business Name', 'A business name exists but it was auto-generated. Confirm…'))
      .toBe('Business name not confirmed');
    expect(cap('Glossary Linkage', 'Link this column to a glossary term.'))
      .toBe('Not linked to glossary');
    expect(cap('Glossary Linkage', "…the term is only 'draft'. Advance the term to Published…"))
      .toBe('Glossary term not published');
  });

  it('captions the reference-data line-items', () => {
    expect(cap('Codes documented')).toBe('Codes not documented');
    expect(cap('Code set approved')).toBe('Code set not approved');
  });

  it('reads the Semantic Type resolve/accept nuance off the step (SD-R3c)', () => {
    expect(cap('Semantic Type', 'No semantic type is resolved for this column. Resolve and accept one on the Interpretation tab.'))
      .toBe('Semantic type not resolved');
    expect(cap('Semantic Type', 'A semantic type is suggested for this column but not yet accepted. Accept it on the Interpretation tab.'))
      .toBe('Semantic type not accepted');
  });

  it('falls back to a generic caption for an unknown line-item', () => {
    expect(cap('Something New')).toBe('Improve Something New');
  });
});

// ── U4b-fix-2 — rail DQ grade badge (Task 4) ─────────────────────────────────

describe('railDqBadge', () => {
  it('renders a grade-coloured score pill for a scored column', () => {
    const badge = railDqBadge(numericBadge);
    expect(badge.scored).toBe(true);
    expect(badge.excluded).toBe(false);
    expect(badge.score).toBe('73');
    expect(badge.bandClass).toBe('dq-band--warning');
  });

  it('marks an out-of-scope column excluded (dashed marker, no score)', () => {
    const badge = railDqBadge(unscoredBadge);
    expect(badge.scored).toBe(false);
    expect(badge.excluded).toBe(true);
    expect(badge.score).toBe('');
  });

  it('shows neither pill nor marker for a null / not-yet-scored column', () => {
    const badge = railDqBadge(null);
    expect(badge.scored).toBe(false);
    expect(badge.excluded).toBe(false);
    expect(badge.score).toBe('');
  });
});

// ── Polish Batch Task 4 — path any_one_suffices passthrough ──────────────────

describe('dqPathToNextGrade — any_one_suffices', () => {
  it('passes the backend tie flag through untouched', () => {
    const tiedBadge: DQBadge = {
      ...codedBadge,
      path_to_next_grade: {
        ...codedBadge.path_to_next_grade!,
        any_one_suffices: true,
        actions: [
          { component: 'interpretation', line_item: 'Business Name', step: 'x', action_type: 'governance', points: 17.5 },
          { component: 'interpretation', line_item: 'Glossary Linkage', step: 'y', action_type: 'governance', points: 17.5 },
        ],
      },
    };
    const path = dqPathToNextGrade(tiedBadge)!;
    expect(path.any_one_suffices).toBe(true);
    expect(path.actions).toHaveLength(2);
  });

  it('defaults to falsy when the backend omits the flag (older record shape)', () => {
    const path = dqPathToNextGrade(codedBadge)!;
    expect(path.any_one_suffices).toBeFalsy();
  });
});

// ── Polish Batch Task 9 — DQ grade distribution (source/table overview) ──────

describe('dqGradeDistribution', () => {
  it('counts scored columns per grade band, worst-to-best order', () => {
    const columns = [
      { dq: { state: 'scored', dq_score: 20, grade_label: 'Critical' } },
      { dq: { state: 'scored', dq_score: 81, grade_label: 'Good' } },
      { dq: { state: 'scored', dq_score: 95, grade_label: 'Excellent' } },
      { dq: { state: 'scored', dq_score: 78, grade_label: 'Good' } },
    ] as { dq: DQBadge }[];
    const dist = dqGradeDistribution(columns);
    expect(dist.map((d) => d.grade)).toEqual(['Critical', 'Good', 'Excellent']);
    const good = dist.find((d) => d.grade === 'Good')!;
    expect(good.count).toBe(2);
    expect(good.pct).toBe(50); // 2 of 4 scored columns
    expect(good.colorIntent).toBe('positive');
  });

  it('excludes unscored and excluded columns from the count', () => {
    const columns = [
      { dq: { state: 'scored', dq_score: 81, grade_label: 'Good' } },
      { dq: { state: 'unscored', reason: 'out_of_scope' } },
      { dq: null },
    ] as { dq: DQBadge | null }[];
    const dist = dqGradeDistribution(columns);
    expect(dist).toEqual([{ grade: 'Good', count: 1, colorIntent: 'positive', pct: 100 }]);
  });

  it('returns an empty list when there are no columns or nothing scored', () => {
    expect(dqGradeDistribution([])).toEqual([]);
    expect(dqGradeDistribution([{ dq: null }])).toEqual([]);
  });
});


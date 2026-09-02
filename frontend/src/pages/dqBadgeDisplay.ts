/**
 * Pure display helpers for the Data Quality badge / card (U2b, DQ §14).
 *
 * Extracted so the badge presentation — donut geometry, component legend,
 * grade-band label and the un-scored fallback — is unit-testable without
 * mounting AssetWorkspace. The DQ scoring math lives in the backend
 * (core/dq_scorer.py); nothing here recomputes a score.
 */

export type DQState = 'scored' | 'unscored';

/**
 * Minimal "score summary" shape shared by the column DQ badge (DQBadge) and the dataset DQ
 * badge (DatasetDQBadge). The small state/grade helpers below only read these top-level fields,
 * so they accept either badge — the two badges' `components`/`line_items` genuinely differ and
 * are irrelevant here.
 */
export interface DQScoreLike {
  state: 'scored' | 'unscored';
  reason?: string | null;
  dq_score?: number | null;
  grade_label?: string | null;
  grade_color_intent?: string | null;
}

export interface DQLineItem {
  label: string;
  validation?: string | null;
  formula?: string | null;
  /** Plain-language explanation of the score line-item (U2d, descriptive only). */
  evidence_note?: string | null;
  earned: number;
  max: number;
  evidence?: Record<string, unknown> | null;
  findings?: unknown[] | null;
}

export interface DQGrade {
  label?: string | null;
  color_intent?: string | null;
}

export interface DQComponent {
  name: string;
  earned: number;
  base_max: number;
  scaled_max?: number | null;
  scaled_earned?: number | null;
  grade?: DQGrade | null;
  line_items?: DQLineItem[] | null;
}

/** One improvement action derived from a line-item gap (U4b, DQ §17). */
export interface DQAction {
  component: string;
  line_item: string;
  step: string;
  /** `governance` — fixable inside ADIRRA · `data` — must be fixed at source. */
  action_type?: string | null;
  /** Composite points recoverable (gap × reallocation factor). */
  points: number;
  /** Composite score this column reaches if this action is taken (U4b-fix). */
  resulting_score?: number | null;
  /** Grade band label at `resulting_score` (U4b-fix). */
  resulting_grade?: string | null;
  evidence_note?: string | null;
}

/** Shortest path to the next grade band (U4b, DQ §17.2). */
export interface DQPathToNextGrade {
  at_top_band: boolean;
  current_score: number;
  current_grade?: string | null;
  next_grade?: string | null;
  next_grade_min?: number | null;
  points_needed?: number | null;
  /** Where the chosen actions actually land the score (not the band threshold). */
  landing_score?: number | null;
  /** Grade band label at `landing_score` (U4b-fix). */
  landing_grade?: string | null;
  actions: DQAction[];
  reachable?: boolean | null;  /**
   * True when the pivotal action that closed the gap has one or more other
   * actions of EXACTLY equal impact (Polish Batch Task 4) — any one of the
   * listed `actions` would have worked, so the wording should say "any one of
   * these" rather than implying this specific set is uniquely required.
   */
  any_one_suffices?: boolean | null;}

export interface DQBadge {
  state: DQState;
  reason?: string | null;
  dq_score?: number | null;
  grade_label?: string | null;
  grade_color_intent?: string | null;
  data_score?: number | null;
  governance_score?: number | null;
  archetype?: string | null;
  archetype_reason?: string | null;
  applicable_components?: string[] | null;
  inapplicable_components?: string[] | null;
  reallocation_factor?: number | null;
  model_version?: string | null;
  scored_at?: string | null;
  components?: DQComponent[] | null;
  actions?: DQAction[] | null;
  /** Count of outstanding improvement actions — present on compact badges too. */
  action_count?: number | null;
  path_to_next_grade?: DQPathToNextGrade | null;
}

/** Steward-readable component names. */
export const DQ_COMPONENT_LABELS: Record<string, string> = {
  profile: 'Profile',
  interpretation: 'Interpretation',
  reference_data: 'Reference Data',
};

/** Component → colour role class suffix (donut arc + legend dot). */
export const DQ_COMPONENT_COLOR: Record<string, string> = {
  profile: 'profile',
  interpretation: 'interpretation',
  reference_data: 'refdata',
};

export function componentLabel(name: string): string {
  return DQ_COMPONENT_LABELS[name] || name;
}

export function componentColorKey(name: string): string {
  return DQ_COMPONENT_COLOR[name] || 'other';
}

/**
 * Element tab-key → component colour key (U2d). Only the three DQ *component*
 * tabs carry an identity accent; every other tab (Data Quality, Mapping,
 * History) returns null and stays neutral. The Interpretation tab carries the
 * brown governance identity (the Semantic Type line-item lives inside it now).
 */
export const DQ_COMPONENT_TAB_COLOR: Record<string, string> = {
  profile: 'profile',
  interpretation: 'interpretation',
  refdata: 'refdata',
};

export function componentTabColorKey(tabKey: string): string | null {
  return DQ_COMPONENT_TAB_COLOR[tabKey] ?? null;
}

export function isScored(badge: DQScoreLike | null | undefined): boolean {
  return !!badge && badge.state === 'scored' && badge.dq_score != null;
}

/** Label shown wherever an out-of-scope column would otherwise show a badge. */
export const DQ_EXCLUDED_LABEL = 'Excluded from assessment';

/** True when the column is descoped (out_of_scope) — badge is suppressed (U2c). */
export function isExcluded(badge: DQBadge | null | undefined): boolean {
  return !!badge && badge.state === 'unscored' && badge.reason === 'out_of_scope';
}

/** Rounded headline score shown in the donut, or a dash when un-scored. */
export function dqScoreText(badge: DQBadge | null | undefined): string {
  return isScored(badge) ? String(badge!.dq_score) : '—';
}

/** Format a composite score: one decimal when it isn't a whole number. */
export function formatDqScore(n: number): string {
  const r = Math.round(n * 10) / 10;
  return Number.isInteger(r) ? String(r) : r.toFixed(1);
}

/**
 * Actual composite score for the detail-card pill — the sum of the scaled
 * component earns (what the integer `dq_score` is rounded from), shown with one
 * decimal when it isn't whole. Falls back to the integer score when component
 * detail isn't available.
 */
export function dqScorePreciseText(badge: DQBadge | null | undefined): string {
  if (!isScored(badge)) return '—';
  const comps = badge!.components;
  if (comps && comps.length) {
    const sum = comps.reduce((acc, c) => acc + (c.scaled_earned ?? 0), 0);
    if (sum > 0) return formatDqScore(sum);
  }
  return String(badge!.dq_score);
}

/** Band label above the card, e.g. "Good" — falls back to a neutral phrase. */
export function dqBandLabel(badge: DQBadge | null | undefined): string {
  if (isScored(badge) && badge!.grade_label) return badge!.grade_label as string;
  if (badge?.state === 'unscored') {
    return badge.reason === 'out_of_scope' ? DQ_EXCLUDED_LABEL : 'Not scored';
  }
  return 'Not scored';
}

/** Header chip text, e.g. "81 · Good". */
export function dqBadgeText(badge: DQBadge | null | undefined): string {
  if (!isScored(badge)) return dqBandLabel(badge);
  return `${badge!.dq_score} · ${badge!.grade_label ?? ''}`.trim();
}

/** CSS class for the grade band colour intent (positive / warning / negative …). */
export function dqBandClass(badge: DQScoreLike | null | undefined): string {
  const intent = isScored(badge) ? badge!.grade_color_intent : null;
  return `dq-band--${intent || 'neutral'}`;
}

export interface DQGradeBandInfo {
  label: string;
  min: number;
  /** Upper bound of the band, or null for the top band (no ceiling). */
  max: number | null;
  colorIntent: string;
}

/**
 * Static grade-band legend for the "How the score works" explainer — mirrors
 * governance/dq_scoring_config.yaml `grade_bands` (labels/thresholds/colour
 * intents are config-owned but change rarely; this is a display-only mirror,
 * not read live from the badge, since no scored record carries the full list).
 */
export const DQ_GRADE_BANDS: DQGradeBandInfo[] = [
  { label: 'Excellent', min: 90, max: 100, colorIntent: 'positive-strong' },
  { label: 'Good', min: 75, max: 89, colorIntent: 'positive' },
  { label: 'Adequate', min: 60, max: 74, colorIntent: 'warning' },
  { label: 'Weak', min: 40, max: 59, colorIntent: 'warning-strong' },
  { label: 'Critical', min: 0, max: 39, colorIntent: 'negative' },
];

export interface DQComponentDisplay {
  name: string;
  label: string;
  colorKey: string;
  earned: number;
  max: number;
  /** 0–100 normalised, for the tab chip band lookup and legend meter. */
  pct: number;
  gradeLabel: string | null;
  gradeColorIntent: string | null;
}

/** Legend rows / tab chips: one entry per applicable component. */
export function componentDisplays(badge: DQBadge | null | undefined): DQComponentDisplay[] {
  if (!badge?.components) return [];
  return badge.components.map((c) => {
    const max = c.base_max || 0;
    const pct = max ? Math.round((100 * c.earned) / max) : 0;
    // One scale everywhere (Task 1): the legend reads on the composite 0–100
    // scale (scaled_earned / scaled_max), so it reconciles with the breakdown
    // and the actions. The grade/pct is the ratio, unchanged by the rescale.
    const factor = badge.reallocation_factor ?? 1;
    const scaledEarned = round2(c.scaled_earned ?? c.earned * factor);
    const scaledMax = round2(c.scaled_max ?? max * factor);
    return {
      name: c.name,
      label: componentLabel(c.name),
      colorKey: componentColorKey(c.name),
      earned: scaledEarned,
      max: scaledMax,
      pct,
      gradeLabel: c.grade?.label ?? null,
      gradeColorIntent: c.grade?.color_intent ?? null,
    };
  });
}

export interface DQDonutSegment {
  name: string;
  colorKey: string;
  /** Fraction of the full ring this component occupies (scaled_max / 100). */
  sweepFraction: number;
  /** Fraction of this component's arc that is filled (earned / base_max). */
  fillFraction: number;
}

/**
 * Donut geometry (DQ §14): one arc per applicable component, sweep ∝ its
 * scaled_max, filled portion = earned/max. Returns fractions so the SVG layer
 * stays a thin dash calculation.
 */
export function donutSegments(badge: DQBadge | null | undefined): DQDonutSegment[] {
  if (!badge?.components) return [];
  return badge.components.map((c) => {
    const base = c.base_max || 0;
    const scaledMax = c.scaled_max ?? base;
    return {
      name: c.name,
      colorKey: componentColorKey(c.name),
      sweepFraction: Math.max(0, Math.min(1, scaledMax / 100)),
      fillFraction: base ? Math.max(0, Math.min(1, c.earned / base)) : 0,
    };
  });
}

/** Secondary "data 77 · governance 84" split line (DQ §16.8). */
export function dataGovernanceSplit(
  badge: DQBadge | null | undefined,
): { data: number; governance: number } | null {
  if (!isScored(badge)) return null;
  if (badge!.data_score == null || badge!.governance_score == null) return null;
  return { data: badge!.data_score as number, governance: badge!.governance_score as number };
}

// ── U4b — remediation slab + legibility (DQ §17, §16.8, §6) ──────────────────

/** The impact-sorted improvement actions (backend-derived, §17). */
export function dqActions(badge: DQBadge | null | undefined): DQAction[] {
  if (!isScored(badge)) return [];
  return badge!.actions ?? [];
}

/** The path-to-next-grade payload, or null when un-scored (§17.2). */
export function dqPathToNextGrade(
  badge: DQBadge | null | undefined,
): DQPathToNextGrade | null {
  if (!isScored(badge)) return null;
  return badge!.path_to_next_grade ?? null;
}

export interface DQPillar {
  /** `data` or `governance`. */
  label: string;
  /** 0–100 pillar percentage. */
  pct: number;
}

/**
 * The data·governance pillar (§16.8) shown beside a component block header:
 * the data % sits beside Profile, the governance % beside Interpretation. Every
 * other component returns null so the header stays plain.
 */
export function pillarForComponent(
  badge: DQBadge | null | undefined,
  componentName: string,
): DQPillar | null {
  if (!isScored(badge)) return null;
  if (componentName === 'profile' && badge!.data_score != null) {
    return { label: 'data', pct: badge!.data_score as number };
  }
  if (componentName === 'interpretation' && badge!.governance_score != null) {
    return { label: 'governance', pct: badge!.governance_score as number };
  }
  return null;
}

/** Natural-language "A, B and C" join. */
function joinAnd(labels: string[]): string {
  if (labels.length <= 1) return labels[0] ?? '';
  if (labels.length === 2) return `${labels[0]} and ${labels[1]}`;
  return `${labels.slice(0, -1).join(', ')} and ${labels[labels.length - 1]}`;
}

/** One-decimal display, trailing ".0" dropped (62.5, 37.5, 71.4, 100). */
function fmt1(value: number): string {
  return String(Math.round(value * 10) / 10);
}

/**
 * Plain-language explanation of the §6 reallocation, when it applies — phrased
 * on the composite 0–100 scale the card actually shows (U4b-fix-2 Task 1). When
 * a component doesn't apply, the remaining components are scaled to fill the
 * full 100 (each block shows its ``scaled_max`` = base_max × factor). The
 * sentence must read those same scaled numbers, or it contradicts the blocks.
 *
 * Returns null when the full 100 basis applies (nothing to explain). Generated
 * from the actual applicable components + ``reallocation_factor``, so it is
 * correct for any basis. The old "scored out of 80" framing is gone — it
 * disagreed with the 62.5/37.5 blocks on screen.
 */
export function reallocationExplanation(badge: DQBadge | null | undefined): string | null {
  if (!isScored(badge)) return null;
  const factor = badge!.reallocation_factor ?? 1;
  const missing = badge!.inapplicable_components ?? [];
  if (Math.abs(factor - 1) < 1e-9 || missing.length === 0) return null;
  const comps = badge!.components ?? [];
  if (!comps.length) return null;

  const missingLabels = missing.map((m) => componentLabel(m));
  const missingPhrase =
    missingLabels.length === 1
      ? `${missingLabels[0]} doesn't apply to this field`
      : `${joinAnd(missingLabels)} don't apply to this field`;

  const appliedLabels = comps.map((c) => componentLabel(c.name));
  const appliedPhrase =
    appliedLabels.length === 1
      ? `${appliedLabels[0]} is scaled to fill the full 100`
      : `${joinAnd(appliedLabels)} are scaled to fill the full 100`;
  const scaledParts = comps
    .map((c) => `${componentLabel(c.name)} ${fmt1(c.scaled_max ?? (c.base_max || 0) * factor)}`)
    .join(' + ');

  const pct = badge!.dq_score;
  return `${missingPhrase}, so ${appliedPhrase} (${scaledParts}). `
    + `${pct} of 100 earned = ${pct}%.`;
}

/**
 * Short, bold problem caption for a remediation action (U4b-fix-2 Task 2). It
 * names the *issue* (not the fix) so the action row reads "problem → fix →
 * destination". Derived only from the action's own ``line_item`` and its
 * gap-aware ``step`` text — both already computed from real line-item state
 * (core/dq_remediation.py); nothing here is fabricated. The two governance
 * line-items with a "present-but-not-approved" nuance (Definition, Business
 * Name, Glossary Linkage) read that nuance off the step wording the backend
 * already varied by state.
 */
export function actionCaption(action: DQAction): string {
  const step = (action.step || '').toLowerCase();
  switch (action.line_item) {
    case 'Completeness':
      return 'Too many missing values';
    case 'Validity':
      return "Values don't match the expected format";
    case 'Uniqueness':
      return 'Duplicate key values';
    case 'Consistency':
      return 'Unusual values found';
    case 'Findings overlay':
      return 'Open observations to resolve';
    case 'Definition':
      return step.includes('write a short') ? 'No description' : 'Description not approved';
    case 'Business Name':
      return step.includes('auto-generated') ? 'Business name not confirmed' : 'No business name';
    case 'Glossary Linkage':
      return step.includes('link this column') ? 'Not linked to glossary' : 'Glossary term not published';
    case 'Codes documented':
      return 'Codes not documented';
    case 'Code set approved':
      return 'Code set not approved';
    case 'Semantic Type':
      return step.includes('no semantic type is resolved')
        ? 'Semantic type not resolved'
        : 'Semantic type not accepted';
    default:
      return `Improve ${action.line_item}`;
  }
}

export interface RailDqBadge {
  /** Show the grade-coloured score pill. */
  scored: boolean;
  /** Show the dashed "excluded from assessment" marker instead. */
  excluded: boolean;
  /** Integer score text for the pill (empty when not scored). */
  score: string;
  /** Grade-band colour class (dq-band--*), consistent with the element card. */
  bandClass: string;
}

/**
 * The left-rail column badge (U4b-fix-2 Task 4): a small grade-coloured DQ
 * score pill, scored-on-view from the same ``col.dq`` the element card reads.
 * Centralises the three-state (scored / excluded / neither) decision the rail
 * rows make so it is unit-testable and the two rail lists stay in step.
 */
export function railDqBadge(badge: DQBadge | null | undefined): RailDqBadge {
  const scored = isScored(badge);
  return {
    scored,
    excluded: isExcluded(badge),
    score: scored ? String(badge!.dq_score) : '',
    bandClass: dqBandClass(badge),
  };
}

/** Round to 2 decimals (the scorer's scaled-component rounding law, §5). */
function round2(value: number): number {
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

// ── U4b-fix — one scale everywhere: rescaled breakdown (Task 1) ──────────────

export interface DQScaledLineItem {
  label: string;
  /** Formula string with the reallocation step made visible when factor ≠ 1. */
  formula?: string | null;
  evidence_note?: string | null;
  /** Composite-scale earned (raw × reallocation factor). */
  earned: number;
  /** Composite-scale max (raw × reallocation factor). */
  max: number;
}

export interface DQScaledComponent {
  name: string;
  label: string;
  colorKey: string;
  /** Composite-scale earned (scaled_earned). */
  earned: number;
  /** Composite-scale max (scaled_max). */
  max: number;
  line_items: DQScaledLineItem[];
}

/**
 * The component breakdown rescaled to the composite 0–100 scale (Task 1), so
 * every number on the card reads on one ruler and reconciles: line-items sum to
 * their block, blocks sum to the composite = the headline score. The scorer
 * still emits RAW values (worked examples 81/73 untouched); this is a pure
 * display rescale using the ``reallocation_factor`` already on the badge.
 *
 * For a full-100-basis column (factor 1.0) nothing changes. When the factor is
 * not 1, the reallocation step is appended to each formula (``… × 1.25``) so
 * the shown contribution never appears unexplained — the formula-vs-result
 * bridge of Task 1.
 */
export function scaledBreakdown(badge: DQBadge | null | undefined): DQScaledComponent[] {
  if (!badge?.components) return [];
  const factor = badge.reallocation_factor ?? 1;
  const reallocated = Math.abs(factor - 1) > 1e-9;
  return badge.components.map((c) => {
    const base = c.base_max || 0;
    const compEarned = round2(c.scaled_earned ?? c.earned * factor);
    const compMax = round2(c.scaled_max ?? base * factor);
    const lineItems: DQScaledLineItem[] = (c.line_items || []).map((li) => {
      let formula = li.formula ?? null;
      if (reallocated && formula) {
        formula = `(${formula}) × ${factor}`;
      }
      return {
        label: li.label,
        formula,
        evidence_note: li.evidence_note ?? null,
        earned: round2(li.earned * factor),
        max: round2(li.max * factor),
      };
    });
    return {
      name: c.name,
      label: componentLabel(c.name),
      colorKey: componentColorKey(c.name),
      earned: compEarned,
      max: compMax,
      line_items: lineItems,
    };
  });
}

export interface DQComponentGroup {
  /** `data` or `governance`. */
  key: 'data' | 'governance';
  label: string;
  /** Pillar % for the group header badge, or null when un-scored. */
  pct: number | null;
  /** Composite-scale points earned, summed across the group's components. */
  earned: number;
  /** Composite-scale points possible, summed across the group's components. */
  max: number;
  components: DQScaledComponent[];
}

/**
 * The scaled component breakdown grouped into the data·governance pillars:
 * Profile is the sole Data component; Interpretation and Reference Data (when
 * applicable) roll into Governance. A group is only returned when it has at
 * least one applicable component, so an inapplicable Reference Data never
 * renders an empty group.
 */
export function groupedComponents(badge: DQBadge | null | undefined): DQComponentGroup[] {
  const comps = scaledBreakdown(badge);
  if (!comps.length) return [];
  const sum = (arr: DQScaledComponent[], key: 'earned' | 'max') =>
    round2(arr.reduce((s, c) => s + c[key], 0));
  const groups: DQComponentGroup[] = [];
  const dataComps = comps.filter((c) => c.name === 'profile');
  const govComps = comps.filter((c) => c.name !== 'profile');
  if (dataComps.length) {
    groups.push({
      key: 'data',
      label: 'Data',
      pct: badge?.data_score ?? null,
      earned: sum(dataComps, 'earned'),
      max: sum(dataComps, 'max'),
      components: dataComps,
    });
  }
  if (govComps.length) {
    groups.push({
      key: 'governance',
      label: 'Governance',
      pct: badge?.governance_score ?? null,
      earned: sum(govComps, 'earned'),
      max: sum(govComps, 'max'),
      components: govComps,
    });
  }
  return groups;
}

// ── U4b-fix — observations folded into actions (Task 5) ──────────────────────

/** A data-quality observation (assessment finding) shown as an action's "why". */
export interface DQObservation {
  title?: string | null;
  rationale?: string | null;
  severity?: string | null;
  category?: string | null;
  regulatory_note?: string | null;
  source?: string | null;
}

/**
 * Finding category → the line-item its evidence belongs to. Completeness /
 * validity / uniqueness / consistency findings attach to the matching action;
 * everything else (regulatory, metadata) has no scored line-item and stays a
 * standalone observation.
 */
const FINDING_CATEGORY_TO_LINE_ITEM: Record<string, string> = {
  completeness: 'Completeness',
  validity: 'Validity',
  uniqueness: 'Uniqueness',
  consistency: 'Consistency',
};

export function lineItemForFindingCategory(category?: string | null): string | null {
  if (!category) return null;
  return FINDING_CATEGORY_TO_LINE_ITEM[category] ?? null;
}

/** Observations (findings) whose category maps to this action's line-item. */
export function observationsForAction(
  action: DQAction,
  findings: readonly DQObservation[] | null | undefined,
): DQObservation[] {
  if (!findings?.length) return [];
  return findings.filter(
    (f) => lineItemForFindingCategory(f.category) === action.line_item,
  );
}

/**
 * Observations that don't map to any action's line-item — kept as standalone,
 * humanised cards (no raw JSON). A finding is "unmatched" when its category has
 * no scored line-item, or when the matching line-item is already full (so it
 * produced no action to attach to).
 */
export function unmatchedObservations(
  actions: readonly DQAction[] | null | undefined,
  findings: readonly DQObservation[] | null | undefined,
): DQObservation[] {
  if (!findings?.length) return [];
  const actionLineItems = new Set((actions ?? []).map((a) => a.line_item));
  return findings.filter((f) => {
    const li = lineItemForFindingCategory(f.category);
    return !li || !actionLineItems.has(li);
  });
}

// ── Polish Batch Task 9 — DQ grade distribution (source/table overview) ─────

/** Grade bands in worst-to-best order (DQ §7), for a stable chart order. */
export const DQ_GRADE_ORDER = ['Critical', 'Weak', 'Adequate', 'Good', 'Excellent'] as const;

/** Band label → colour-intent class suffix, reusing the same palette as the badge. */
export const DQ_GRADE_COLOR_INTENT: Record<string, string> = {
  Critical: 'negative',
  Weak: 'warning-strong',
  Adequate: 'warning',
  Good: 'positive',
  Excellent: 'positive-strong',
};

export interface DQGradeDistributionEntry {
  grade: string;
  count: number;
  colorIntent: string;
  /** 0–100 share of the scored (non-excluded) columns, for the bar height. */
  pct: number;
}

/**
 * Distribution of column DQ grades for a source/table overview (Task 9) —
 * pure aggregation over the already-persisted per-column badges (no scoring).
 * Unscored/excluded columns are not counted (nothing to grade yet). Bands with
 * zero columns are omitted so the chart never shows an empty band.
 */
export function dqGradeDistribution(
  columns: readonly { dq?: DQBadge | null }[] | null | undefined,
): DQGradeDistributionEntry[] {
  if (!columns?.length) return [];
  const counts: Record<string, number> = {};
  let scoredTotal = 0;
  for (const c of columns) {
    if (!isScored(c.dq)) continue;
    const grade = c.dq!.grade_label || 'Unknown';
    counts[grade] = (counts[grade] ?? 0) + 1;
    scoredTotal += 1;
  }
  if (!scoredTotal) return [];
  return DQ_GRADE_ORDER.filter((g) => counts[g] > 0).map((g) => ({
    grade: g,
    count: counts[g],
    colorIntent: DQ_GRADE_COLOR_INTENT[g] ?? 'neutral',
    pct: Math.round((100 * counts[g]) / scoredTotal),
  }));
}

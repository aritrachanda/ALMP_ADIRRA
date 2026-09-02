/**
 * Dashboard presets — the "by design" configuration model.
 *
 * A CARD is one chart/panel. A PRESET is a curated bundle of cards. Users pick
 * a preset, not individual cards; hand-picking individual cards ("by elements")
 * is deliberately deferred until RBAC exists, at which point roles map onto
 * these same preset ids.
 */

export type CardId =
  | 'kpis'
  | 'governance-pipeline'
  | 'source-league'
  | 'avg-dq-by-source'
  | 'semantic-heatmap'
  | 'semantic-resolution'
  | 'governance-by-source'
  | 'quality-map'
  | 'dq-distribution'
  | 'ai-assistance'
  | 'ai-by-source'
  | 'mapping-coverage'
  | 'mapping-confidence'
  | 'glossary-status';

export interface DashboardPreset {
  id: string;
  label: string;
  /** Shown under the picker so the preset's purpose is obvious. */
  question: string;
  cards: CardId[];
}

export const DASHBOARD_PRESETS: DashboardPreset[] = [
  {
    id: 'executive',
    label: 'Executive Summary',
    question: 'How are we doing overall?',
    cards: ['kpis', 'source-league', 'governance-pipeline', 'avg-dq-by-source'],
  },
  {
    id: 'governance',
    label: 'Governance Progress',
    question: "What's stuck, and where?",
    cards: ['kpis', 'governance-pipeline', 'governance-by-source', 'semantic-resolution', 'semantic-heatmap'],
  },
  {
    id: 'quality',
    label: 'Data Quality',
    question: "Where's the risk?",
    cards: ['kpis', 'quality-map', 'dq-distribution', 'avg-dq-by-source'],
  },
  {
    id: 'ai-value',
    label: 'AI Value',
    question: 'What has AI actually contributed?',
    cards: ['ai-assistance', 'ai-by-source', 'glossary-status'],
  },
  {
    id: 'mapping',
    label: 'Mapping & Regulatory',
    question: 'How close are we to submission?',
    cards: ['mapping-coverage', 'mapping-confidence', 'glossary-status'],
  },
];

export const DEFAULT_PRESET_ID = 'executive';

export function presetById(id: string): DashboardPreset {
  return DASHBOARD_PRESETS.find((p) => p.id === id) ?? DASHBOARD_PRESETS[0];
}

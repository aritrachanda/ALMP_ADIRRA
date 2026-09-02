import { describe, it, expect } from 'vitest';
import {
  policyLabel,
  providerModelLabel,
  isActivePolicy,
  type AiGovernance,
} from '../src/pages/aiGovernanceDisplay';

function gov(overrides: Partial<AiGovernance> = {}): AiGovernance {
  return {
    ai_sample_policy: 'masked',
    ai_sample_policy_meaning: 'Raw sample values are redacted before leaving for the LLM.',
    ai_sample_policy_options: [
      { value: 'full', meaning: 'Everything is sent.' },
      { value: 'masked', meaning: 'Samples redacted.' },
      { value: 'stats_only', meaning: 'Samples dropped.' },
    ],
    provider: 'azure',
    model: 'gpt-5.4-mini',
    rules: ['AI proposes, the steward decides — an AI draft never auto-approves.'],
    read_only: true,
    edit_seam: 'editable by [role] — coming with roles',
    ...overrides,
  };
}

describe('AI-governance panel display', () => {
  it('title-cases the policy label', () => {
    expect(policyLabel('stats_only')).toBe('Stats Only');
    expect(policyLabel('masked')).toBe('Masked');
    expect(policyLabel(null)).toBe('—');
  });

  it('renders provider · model', () => {
    expect(providerModelLabel(gov())).toBe('azure · gpt-5.4-mini');
    expect(providerModelLabel(gov({ provider: null, model: null }))).toBe('Not configured');
  });

  it('flags the active policy option', () => {
    const g = gov();
    expect(isActivePolicy(g, { value: 'masked' })).toBe(true);
    expect(isActivePolicy(g, { value: 'full' })).toBe(false);
  });

  it('exposes the read-only role-editing seam', () => {
    expect(gov().read_only).toBe(true);
    expect(gov().edit_seam.toLowerCase()).toContain('role');
  });
});

/**
 * Pure helpers for the read-only AI-governance panel (U5c / decision D5).
 *
 * The panel makes the active AI policy legible for client-facing transparency:
 * the sample policy and what it means, the provider/model, and the standing
 * propose-only rules. Read-only this phase — role-gated editing is deferred until
 * ADIRRA has an auth/role model (the seam is only labelled).
 *
 * All functions are pure: no store access, no side effects.
 */

export interface AiSamplePolicyOption {
  value: string;
  meaning: string;
}

export interface AiGovernance {
  ai_sample_policy: string;
  ai_sample_policy_meaning: string;
  ai_sample_policy_options: AiSamplePolicyOption[];
  provider?: string | null;
  model?: string | null;
  rules: string[];
  read_only: boolean;
  edit_seam: string;
}

/** Title-case a policy id for display, e.g. `stats_only` → "Stats Only". */
export function policyLabel(policy: string | null | undefined): string {
  if (!policy) return '—';
  return policy.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

/** Provider · model attribution line, e.g. "azure · gpt-5.4-mini". */
export function providerModelLabel(g: Pick<AiGovernance, 'provider' | 'model'>): string {
  const parts = [g.provider, g.model].filter((x): x is string => !!x);
  return parts.length ? parts.join(' · ') : 'Not configured';
}

/** True when a given policy option is the active one (for highlighting). */
export function isActivePolicy(
  g: Pick<AiGovernance, 'ai_sample_policy'>,
  option: Pick<AiSamplePolicyOption, 'value'>,
): boolean {
  return g.ai_sample_policy === option.value;
}

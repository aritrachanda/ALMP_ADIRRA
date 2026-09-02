/**
 * Pure display helpers for the assessment scoping panel (U2c, decision D1).
 *
 * Extracted so the scope toggle state and the SD "technical → descope"
 * suggestion logic are unit-testable without mounting AssetWorkspace. Nothing
 * here mutates state: descoping is always an explicit steward act performed via
 * the API. A confirmed `technical` type *suggests* a descope; it never applies
 * one automatically.
 */
import type { DQBadge } from './dqBadgeDisplay';

export type AssessmentScope = 'in_scope' | 'out_of_scope';

/** A column absent the scope fact defaults to in-scope. */
export function isOutOfScope(scope?: string | null): boolean {
  return scope === 'out_of_scope';
}

export function scopeLabel(scope?: string | null): string {
  return isOutOfScope(scope) ? 'Out of scope' : 'In scope';
}

/** Minimal column shape the panel and suggestion logic consume. */
export interface ScopableColumn {
  name: string;
  /** Semantic ``type_id`` (e.g. ``technical``), or ``unresolved``. */
  semantic_type?: string | null;
  /** Derived semantic-type disposition: ``accepted`` | ``pending`` | ``unresolved``. */
  semantic_state?: string | null;
  assessment_scope?: string | null;
  dq?: DQBadge | null;
}

/** An accepted technical type is a strong suggestion; a pending one is a weak hint. */
export type DescopeStrength = 'accepted' | 'hint';

export interface DescopeSuggestion {
  strength: DescopeStrength;
  /** Human-readable provenance: *why* this column is suggested for descoping. */
  reason: string;
}

const TECHNICAL_TYPE = 'technical';

/**
 * SD `technical` → descope suggestion (D1). Returns a one-click suggestion when
 * a column's semantic type is `technical`:
 *   - an **accepted** technical type surfaces prominently (`strength: accepted`);
 *   - a **pending** (not yet accepted) technical type is a weaker hint (`strength: hint`).
 *
 * Never suggests for a column that is already out of scope, and NEVER applies
 * the descope itself — the steward always clicks.
 */
export function descopeSuggestion(col: ScopableColumn): DescopeSuggestion | null {
  if (isOutOfScope(col.assessment_scope)) return null; // already descoped — nothing to suggest
  if ((col.semantic_type || '') !== TECHNICAL_TYPE) return null;
  const state = col.semantic_state || '';
  if (state === 'accepted') {
    return { strength: 'accepted', reason: 'Accepted as a technical / platform field' };
  }
  if (state === 'pending') {
    return { strength: 'hint', reason: 'Detected as a technical / platform field, not yet accepted' };
  }
  return null;
}

/** True when the column carries any descope suggestion (strong or hint). */
export function hasDescopeSuggestion(col: ScopableColumn): boolean {
  return descopeSuggestion(col) !== null;
}

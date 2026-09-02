/**
 * U2c — Assessment scoping display helpers (assessmentScopeDisplay.ts).
 *
 * Covers the pure logic behind the scoping panel:
 *  - the in-scope default / fallback (absent scope fact = in-scope)
 *  - the SD `technical` → descope suggestion, and that it appears ONLY for
 *    `technical` types (accepted = strong, pending = hint)
 *  - that a suggestion never appears for an already-descoped column
 */

import { describe, it, expect } from 'vitest';
import {
  isOutOfScope,
  scopeLabel,
  descopeSuggestion,
  hasDescopeSuggestion,
  type ScopableColumn,
} from '../src/pages/assessmentScopeDisplay';

describe('in-scope default / fallback', () => {
  it('treats an absent scope fact as in-scope', () => {
    expect(isOutOfScope(undefined)).toBe(false);
    expect(isOutOfScope(null)).toBe(false);
    expect(isOutOfScope('in_scope')).toBe(false);
    expect(scopeLabel(undefined)).toBe('In scope');
  });

  it('recognises an explicit out-of-scope fact', () => {
    expect(isOutOfScope('out_of_scope')).toBe(true);
    expect(scopeLabel('out_of_scope')).toBe('Out of scope');
  });
});

describe('technical → descope suggestion', () => {
  it('surfaces a strong suggestion for an accepted technical type', () => {
    const col: ScopableColumn = {
      name: 'load_ts', semantic_type: 'technical', semantic_state: 'accepted',
      assessment_scope: 'in_scope',
    };
    const s = descopeSuggestion(col);
    expect(s).not.toBeNull();
    expect(s!.strength).toBe('accepted');
    expect(hasDescopeSuggestion(col)).toBe(true);
  });

  it('surfaces a weak hint for a pending (not yet accepted) technical type', () => {
    const pending: ScopableColumn = {
      name: 'batch_id', semantic_type: 'technical', semantic_state: 'pending',
    };
    expect(descopeSuggestion(pending)!.strength).toBe('hint');
  });

  it('never suggests for a non-technical type', () => {
    const monetary: ScopableColumn = {
      name: 'exposure_amount', semantic_type: 'monetary_amount', semantic_state: 'accepted',
    };
    const unresolved: ScopableColumn = { name: 'foo', semantic_type: 'unresolved' };
    expect(descopeSuggestion(monetary)).toBeNull();
    expect(descopeSuggestion(unresolved)).toBeNull();
    expect(hasDescopeSuggestion(monetary)).toBe(false);
  });

  it('never suggests for an already out-of-scope column', () => {
    const col: ScopableColumn = {
      name: 'load_ts', semantic_type: 'technical', semantic_state: 'accepted',
      assessment_scope: 'out_of_scope',
    };
    expect(descopeSuggestion(col)).toBeNull();
  });

  it('ignores a technical type with no disposition yet (unresolved)', () => {
    const col: ScopableColumn = {
      name: 'load_ts', semantic_type: 'technical', semantic_state: 'unresolved',
    };
    expect(descopeSuggestion(col)).toBeNull();
  });
});

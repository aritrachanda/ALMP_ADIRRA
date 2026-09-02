/**
 * Phase 5b.2 — per-code Reference Data store actions.
 *
 * saveReferenceCodes / submitReferenceCodes must call the API and fold the returned
 * codes + set_badge back onto store.referenceData so the tab reflects the change live.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { setActivePinia, createPinia } from 'pinia';
import type { ReferenceData } from '../src/api/element';

vi.mock('../src/api/element', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/api/element')>();
  return {
    ...actual,
    saveReferenceCodes: vi.fn(async () => ({
      codes: [{ code: 'A', value: null, meaning: 'Active', share_pct: 50, origin: 'profiled', status: 'draft', in_source: true }],
      set_badge: 'draft',
    })),
    submitReferenceCodes: vi.fn(async () => ({
      submitted: 1,
      codes: [{ code: 'A', value: null, meaning: 'Active', share_pct: 50, origin: 'profiled', status: 'in_review', in_source: true }],
      set_badge: 'in_review',
    })),
    withdrawReferenceCodes: vi.fn(async () => ({
      withdrawn: 1,
      codes: [{ code: 'A', value: null, meaning: 'Active', share_pct: 50, origin: 'profiled', status: 'draft', in_source: true }],
      set_badge: 'draft',
    })),
    revokeReferenceCodes: vi.fn(async () => ({
      revoked: 1,
      codes: [{ code: 'A', value: null, meaning: 'Active', share_pct: 50, origin: 'profiled', status: 'draft', in_source: true }],
      set_badge: 'draft',
    })),
    removeReferenceCodes: vi.fn(async () => ({
      removed: 1,
      codes: [],
      set_badge: 'empty',
    })),
  };
});

import * as api from '../src/api/element';
import { useElementStore } from '../src/stores/elementStore';

function seededRefData(): ReferenceData {
  return {
    source: 's', schema: 'sc', table: 't', column: 'c',
    is_coded: true, status: 'candidate',
    codes: [{ code: 'A', value: null, meaning: null, share_pct: 50, origin: 'profiled', status: 'empty', in_source: true }],
    bound_set_id: null, set_kind: 'local',
    backend: 'postgres', semantic_accepted: true, set_badge: 'empty',
  };
}

describe('elementStore — per-code Reference Data actions', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  it('saveReferenceCodes folds returned codes + badge onto referenceData', async () => {
    const store = useElementStore();
    store.referenceData = seededRefData();
    await store.saveReferenceCodes('s', 't', 'c', [{ code: 'A', meaning: 'Active' }], 'sc');
    expect(api.saveReferenceCodes).toHaveBeenCalledTimes(1);
    expect(store.referenceData?.codes[0].status).toBe('draft');
    expect(store.referenceData?.set_badge).toBe('draft');
  });

  it('submitReferenceCodes moves the code to in_review and updates the badge', async () => {
    const store = useElementStore();
    store.referenceData = seededRefData();
    const res = await store.submitReferenceCodes('s', 't', 'c', null, 'sc');
    expect(api.submitReferenceCodes).toHaveBeenCalledTimes(1);
    expect(res.submitted).toBe(1);
    expect(store.referenceData?.codes[0].status).toBe('in_review');
    expect(store.referenceData?.set_badge).toBe('in_review');
  });

  it('withdrawReferenceCodes returns the code to draft and updates the badge', async () => {
    const store = useElementStore();
    store.referenceData = seededRefData();
    const res = await store.withdrawReferenceCodes('s', 't', 'c', ['A'], 'sc');
    expect(api.withdrawReferenceCodes).toHaveBeenCalledTimes(1);
    expect(res.withdrawn).toBe(1);
    expect(store.referenceData?.codes[0].status).toBe('draft');
    expect(store.referenceData?.set_badge).toBe('draft');
  });

  it('revokeReferenceCodes returns the code to draft and updates the badge', async () => {
    const store = useElementStore();
    store.referenceData = seededRefData();
    const res = await store.revokeReferenceCodes('s', 't', 'c', ['A'], 'sc');
    expect(api.revokeReferenceCodes).toHaveBeenCalledTimes(1);
    expect(res.revoked).toBe(1);
    expect(store.referenceData?.codes[0].status).toBe('draft');
    expect(store.referenceData?.set_badge).toBe('draft');
  });

  it('removeReferenceCodes drops the code and updates the badge', async () => {
    const store = useElementStore();
    store.referenceData = seededRefData();
    const res = await store.removeReferenceCodes('s', 't', 'c', ['A'], 'sc');
    expect(api.removeReferenceCodes).toHaveBeenCalledTimes(1);
    expect(res.removed).toBe(1);
    expect(store.referenceData?.codes).toHaveLength(0);
    expect(store.referenceData?.set_badge).toBe('empty');
  });
});
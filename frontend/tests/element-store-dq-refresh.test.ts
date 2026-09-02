/**
 * Phase 5a — the DQ score auto-refreshes after interpretation-set commits.
 *
 * Regression cover for the "score went stale until a manual refresh / reload" fix.
 * Per-field saves (Description / Business Name) persist text only and do NOT
 * re-score — re-scoring is deferred to the tab-level 'Save as Draft'
 * (`saveInterpretation`) and to lifecycle changes, which still trigger a fresh
 * DQ re-score (`api.refreshElementDq`) and surface the new badge on `element.dq`.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { setActivePinia, createPinia } from 'pinia';
import type { ElementDetail } from '../src/api/element';

vi.mock('../src/api/element', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/api/element')>();
  return {
    ...actual,
    getElement: vi.fn(async (source: string, table: string, column: string, schema?: string) =>
      ({ source, table, column, schema: schema ?? null, lifecycle_state: 'draft',
         dq: { state: 'scored', dq_score: 63 } } as unknown as ElementDetail)),
    streamElement: vi.fn(async (source: string, table: string, column: string, schema?: string) =>
      ({ source, table, column, schema: schema ?? null, lifecycle_state: 'draft',
         dq: { state: 'scored', dq_score: 63 } } as unknown as ElementDetail)),
    updateBusinessName: vi.fn(async () =>
      ({ business_name: 'New Name', business_name_state: 'draft', business_name_is_ai: false })),
    updateDescription: vi.fn(async () =>
      ({ column_description: 'A description', lifecycle_state: 'defined' })),
    updateLifecycleState: vi.fn(async () => ({ lifecycle_state: 'approved' })),
    saveInterpretation: vi.fn(async () =>
      ({ lifecycle_state: 'draft', submission: null })),
    refreshElementDq: vi.fn(async () => ({ state: 'scored', dq_score: 88 })),
  };
});

import * as api from '../src/api/element';
import { useElementStore } from '../src/stores/elementStore';

describe('elementStore — DQ score auto-refreshes after interpretation-set commits', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  async function loadedStore() {
    const store = useElementStore();
    await store.loadElement('ALM Bank', 'sourcesystem', 'id', 'raw_almp');
    vi.mocked(api.refreshElementDq).mockClear();  // ignore any load-time scoring
    return store;
  }

  it('does NOT re-score after a per-field Business Name save (persists text only)', async () => {
    const store = await loadedStore();
    await store.updateBusinessName('New Name');
    expect(api.refreshElementDq).not.toHaveBeenCalled();
  });

  it('does NOT re-score after a per-field Description save (persists text only)', async () => {
    const store = await loadedStore();
    await store.updateDescription('A description');
    expect(api.refreshElementDq).not.toHaveBeenCalled();
  });

  it('re-scores after the tab-level Save as Draft (saveInterpretation)', async () => {
    const store = await loadedStore();
    await store.saveInterpretation({ description: 'A description', businessName: 'New Name' });
    expect(api.refreshElementDq).toHaveBeenCalledTimes(1);
    expect(store.element?.dq?.dq_score).toBe(88);
  });

  it('re-scores after a Lifecycle change', async () => {
    const store = await loadedStore();
    await store.setLifecycleState('approved');
    expect(api.refreshElementDq).toHaveBeenCalledTimes(1);
    expect(store.element?.dq?.dq_score).toBe(88);
  });
});


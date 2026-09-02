import { describe, it, expect, beforeEach, vi } from 'vitest';
import type { Mock } from 'vitest';
import { setActivePinia, createPinia } from 'pinia';
import { useGlossaryV2Store } from '../src/stores/glossaryV2Store';
import type { GlossaryV2Summary, GlossaryV2QueueItem, GlossaryTerm } from '../src/types';

vi.mock('../src/api/glossaryV2', () => ({
  getTree: vi.fn(), getFacets: vi.fn(), getCoverage: vi.fn(), streamCoverage: vi.fn(), getAttributesConfig: vi.fn(),
  search: vi.fn(), getTerm: vi.fn(), getHistory: vi.fn(), reparent: vi.fn(),
  getReviewQueue: vi.fn(), assignReview: vi.fn(), confirmTerm: vi.fn(), rejectTerm: vi.fn(),
  updateTerm: vi.fn(), generateField: vi.fn(),
}));
import * as api from '../src/api/glossaryV2';

function summary(over: Partial<GlossaryV2Summary> & { id: string }): GlossaryV2Summary {
  return {
    parent: null, title: over.id, domain: 'D', category: 'Cat1', status: 'draft',
    is_cde: null, has_linkage: false, ai_generated: false, has_children: false, ...over,
  };
}

function queueItem(id: string, assigned_to: string | null = null): GlossaryV2QueueItem {
  return { ...summary({ id, ai_generated: true }), assigned_to };
}

describe('glossaryV2Store.treeRows', () => {
  beforeEach(() => setActivePinia(createPinia()));

  it('groups by category and nests parent → child with depth', () => {
    const store = useGlossaryV2Store();
    store.summaries = [
      summary({ id: 'alpha', title: 'Alpha', category: 'Cat1', has_children: true }),
      summary({ id: 'beta', title: 'Beta', category: 'Cat1', parent: 'alpha' }),
      summary({ id: 'gamma', title: 'Gamma', category: 'Cat2' }),
    ];
    const rows = store.treeRows;
    // Cat1 header, Alpha (depth 1), Beta (depth 2), Cat2 header, Gamma (depth 1)
    expect(rows.map((r) => `${r.kind}:${r.label}:${r.depth ?? ''}`)).toEqual([
      'category:Cat1:',
      'term:Alpha:1',
      'term:Beta:2',
      'category:Cat2:',
      'term:Gamma:1',
    ]);
  });

  it('renders an orphaned child (parent filtered out) at category root', () => {
    const store = useGlossaryV2Store();
    // 'beta' points at 'alpha' which is NOT in the set (e.g. filtered away by search)
    store.summaries = [summary({ id: 'beta', title: 'Beta', category: 'Cat1', parent: 'alpha' })];
    const rows = store.treeRows;
    expect(rows.map((r) => `${r.kind}:${r.label}:${r.depth ?? ''}`)).toEqual([
      'category:Cat1:',
      'term:Beta:1',
    ]);
  });

  it('caps rendering at 3 levels of depth', () => {
    const store = useGlossaryV2Store();
    store.summaries = [
      summary({ id: 'l1', title: 'L1', category: 'C' }),
      summary({ id: 'l2', title: 'L2', category: 'C', parent: 'l1' }),
      summary({ id: 'l3', title: 'L3', category: 'C', parent: 'l2' }),
      summary({ id: 'l4', title: 'L4', category: 'C', parent: 'l3' }),
    ];
    const depths = store.treeRows.filter((r) => r.kind === 'term').map((r) => r.depth);
    expect(Math.max(...(depths as number[]))).toBe(3); // L4 (depth 4) is not walked
  });
});

describe('glossaryV2Store review-queue actions', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
    (api.streamCoverage as Mock).mockResolvedValue({});
  });

  it('loadReviewQueue populates the queue', async () => {
    const store = useGlossaryV2Store();
    (api.getReviewQueue as Mock).mockResolvedValue([queueItem('a'), queueItem('b')]);
    await store.loadReviewQueue();
    expect(store.reviewQueue.map((q) => q.id)).toEqual(['a', 'b']);
  });

  it('confirmTerm removes the term from the local queue and refreshes coverage', async () => {
    const store = useGlossaryV2Store();
    store.reviewQueue = [queueItem('a'), queueItem('b')];
    (api.confirmTerm as Mock).mockResolvedValue({});
    await store.confirmTerm('a', { decided_by: 'me' });
    expect(api.confirmTerm).toHaveBeenCalledWith('a', { decided_by: 'me' });
    expect(store.reviewQueue.map((q) => q.id)).toEqual(['b']);
    expect(api.streamCoverage).toHaveBeenCalled();
  });

  it('rejectTerm removes the term from the local queue', async () => {
    const store = useGlossaryV2Store();
    store.reviewQueue = [queueItem('a'), queueItem('b')];
    (api.rejectTerm as Mock).mockResolvedValue({});
    await store.rejectTerm('b');
    expect(store.reviewQueue.map((q) => q.id)).toEqual(['a']);
  });

  it('assignReview updates assigned_to on the local row', async () => {
    const store = useGlossaryV2Store();
    store.reviewQueue = [queueItem('a')];
    (api.assignReview as Mock).mockResolvedValue({});
    await store.assignReview('a', 'Bob');
    expect(api.assignReview).toHaveBeenCalledWith('a', 'Bob');
    expect(store.reviewQueue[0]!.assigned_to).toBe('Bob');
  });

  it('saveTerm returns the persisted term and syncs selectedTerm when it matches', async () => {
    const store = useGlossaryV2Store();
    store.selectedSlug = 'a';
    const persisted = { id: 'a', title: 'Alpha (edited)' } as GlossaryTerm;
    (api.updateTerm as Mock).mockResolvedValue(persisted);
    const result = await store.saveTerm('a', { title: 'Alpha (edited)' });
    expect(result).toEqual(persisted);
    expect(store.selectedTerm).toEqual(persisted);
  });

  it('generateField proxies the api and clears the generating flag', async () => {
    const store = useGlossaryV2Store();
    (api.generateField as Mock).mockResolvedValue({
      field: 'business_description', value: 'AI text', provenance: { model: 'm', prompt_id: 'p' },
    });
    const res = await store.generateField('a', 'business_description');
    expect(res.value).toBe('AI text');
    expect(store.generating).toBeNull();
  });
});

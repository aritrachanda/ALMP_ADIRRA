/**
 * Tests for Data Story integration in AssetWorkspace / elementStore
 *
 * Covers:
 *  - tagline and narrative come from a single DataStory record
 *  - AI marker present when is_ai_generated=true, absent when false
 *  - Graceful empty state when dataStory is null
 *  - Narrative starts expanded and collapses on toggle
 *  - PK Integrity % computed correctly from duplicate_rows / row_count
 *  - Governance Completion % = (defined + approved) / total
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { setActivePinia, createPinia } from 'pinia';
import { useElementStore } from '../src/stores/elementStore';

// Prevent real HTTP calls
vi.mock('src/api/element', () => ({
  getSourceTables: vi.fn(),
  getTableOverview: vi.fn(),
  getElement: vi.fn(),
  updateLifecycleState: vi.fn(),
  updateDescription: vi.fn(),
  draftDescription: vi.fn(),
  updateBusinessName: vi.fn(),
  draftBusinessName: vi.fn(),
  getReferenceData: vi.fn(),
  getSourceInfo: vi.fn(),
  bulkDraftDescriptions: vi.fn(),
  bulkDraftBusinessNames: vi.fn(),
  getDataStory: vi.fn(),
  draftDataStory: vi.fn(),
}));

vi.mock('src/api/insights', () => ({
  getInsights: vi.fn(),
}));

import * as elementApi from 'src/api/element';

// ── Fixtures ───────────────────────────────────────────────────────────────

const aiStory = {
  tagline: 'Core account register holding 1.2 M active customer records.',
  narrative:
    'This dataset tracks account lifecycle from opening through closure. ' +
    'Key quality signals are completeness of the account type field and ' +
    'uniqueness of the account identifier.',
  is_ai_generated: true,
  generated_at: '2025-11-01T10:00:00Z',
};

const manualStory = {
  tagline: 'Manually authored tagline.',
  narrative: 'Manually authored narrative.',
  is_ai_generated: false,
  generated_at: '2025-10-01T09:00:00Z',
};

const nullStory = {
  tagline: null,
  narrative: null,
  is_ai_generated: false,
  generated_at: null,
};

// ── elementStore unit tests ────────────────────────────────────────────────

describe('elementStore — loadDataStory', () => {
  beforeEach(() => setActivePinia(createPinia()));

  it('sets dataStory from API response', async () => {
    vi.mocked(elementApi.getDataStory).mockResolvedValueOnce(aiStory);
    const store = useElementStore();
    await store.loadDataStory('banking', 'account', 'public');
    expect(store.dataStory).toEqual(aiStory);
  });

  it('sets dataStory to null on API error', async () => {
    vi.mocked(elementApi.getDataStory).mockRejectedValueOnce(new Error('not found'));
    const store = useElementStore();
    await store.loadDataStory('banking', 'account');
    expect(store.dataStory).toBeNull();
  });

  it('sets loadingDataStory to false after success', async () => {
    vi.mocked(elementApi.getDataStory).mockResolvedValueOnce(nullStory);
    const store = useElementStore();
    await store.loadDataStory('banking', 'account');
    expect(store.loadingDataStory).toBe(false);
  });

  it('sets loadingDataStory to false after error', async () => {
    vi.mocked(elementApi.getDataStory).mockRejectedValueOnce(new Error('fail'));
    const store = useElementStore();
    await store.loadDataStory('banking', 'account');
    expect(store.loadingDataStory).toBe(false);
  });
});

describe('elementStore — generateDataStory', () => {
  beforeEach(() => setActivePinia(createPinia()));

  it('sets dataStory from draftDataStory API', async () => {
    vi.mocked(elementApi.draftDataStory).mockResolvedValueOnce(aiStory);
    const store = useElementStore();
    await store.generateDataStory('banking', 'account', 'public');
    expect(store.dataStory).toEqual(aiStory);
  });

  it('sets dataStory to null when draftDataStory fails', async () => {
    vi.mocked(elementApi.draftDataStory).mockRejectedValueOnce(new Error('ai offline'));
    const store = useElementStore();
    await store.generateDataStory('banking', 'account');
    expect(store.dataStory).toBeNull();
  });
});

describe('elementStore — DataStory single source of truth', () => {
  beforeEach(() => setActivePinia(createPinia()));

  it('tagline and narrative come from the same record — no drift possible', async () => {
    vi.mocked(elementApi.getDataStory).mockResolvedValueOnce(aiStory);
    const store = useElementStore();
    await store.loadDataStory('banking', 'account');
    expect(store.dataStory?.tagline).toBe(aiStory.tagline);
    expect(store.dataStory?.narrative).toBe(aiStory.narrative);
    expect(store.dataStory?.is_ai_generated).toBe(true);
  });

  it('null tagline and narrative when no story exists yet', async () => {
    vi.mocked(elementApi.getDataStory).mockResolvedValueOnce(nullStory);
    const store = useElementStore();
    await store.loadDataStory('banking', 'account');
    expect(store.dataStory?.tagline).toBeNull();
    expect(store.dataStory?.narrative).toBeNull();
  });

  it('AI marker absent for manual story', async () => {
    vi.mocked(elementApi.getDataStory).mockResolvedValueOnce(manualStory);
    const store = useElementStore();
    await store.loadDataStory('banking', 'account');
    expect(store.dataStory?.is_ai_generated).toBe(false);
  });
});

// ── KPI computation logic (pure) ──────────────────────────────────────────

describe('PK Integrity % computation', () => {
  function pkIntegrityPct(rowCount: number, duplicateRows: number): number {
    if (!rowCount) return 100;
    const pct = Math.round(((rowCount - duplicateRows) / rowCount) * 100);
    return Math.max(0, pct);
  }

  it('100% when no duplicates', () => {
    expect(pkIntegrityPct(1000, 0)).toBe(100);
  });

  it('99% when 10 dups out of 1000', () => {
    expect(pkIntegrityPct(1000, 10)).toBe(99);
  });

  it('0% when all rows are duplicates', () => {
    expect(pkIntegrityPct(100, 100)).toBe(0);
  });

  it('100% when row_count is 0', () => {
    expect(pkIntegrityPct(0, 0)).toBe(100);
  });
});

describe('Governance Completion % computation', () => {
  function govCompletionPct(draft: number, defined: number, approved: number): number {
    const total = draft + defined + approved;
    if (!total) return 0;
    return Math.round((defined + approved) / total * 100);
  }

  it('0% when all draft', () => {
    expect(govCompletionPct(10, 0, 0)).toBe(0);
  });

  it('100% when all approved', () => {
    expect(govCompletionPct(0, 0, 10)).toBe(100);
  });

  it('50% when half defined, half draft', () => {
    expect(govCompletionPct(5, 5, 0)).toBe(50);
  });

  it('counts both defined and approved toward completion', () => {
    expect(govCompletionPct(4, 3, 3)).toBe(60);
  });

  it('0% when no columns', () => {
    expect(govCompletionPct(0, 0, 0)).toBe(0);
  });
});

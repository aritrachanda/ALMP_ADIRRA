import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { setActivePinia, createPinia } from 'pinia';
import { useReferenceDataStore } from '../src/stores/referenceDataStore';

const REGISTER = {
  summary: { total_fields: 1, status_counts: { approved: 0, in_review: 1 }, gaps: 0, codes_of_record: 0 },
  sources: [{ source: 'banking', schemas: [{ schema: 'src', tables: [{ table: 'accounts', fields: [] }] }] }],
};

const VOCABULARY = {
  roles: [{ id: 'code', label: 'Code' }],
  types_by_role: {
    code: [{ id: 'currency_code', label: 'Currency Code' }, { id: 'country_code', label: 'Country Code' }],
    text: [{ id: 'currency_code', label: 'Currency Code' }],
  },
  scopes: [],
};

function jsonResponse(body: unknown, ok = true, status = 200) {
  return Promise.resolve({ ok, status, json: () => Promise.resolve(body) } as Response);
}

describe('referenceDataStore', () => {
  beforeEach(() => setActivePinia(createPinia()));
  afterEach(() => vi.restoreAllMocks());

  it('flattens, de-duplicates and sorts the governed vocabulary', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) =>
      url.includes('vocabulary') ? jsonResponse(VOCABULARY) : jsonResponse(REGISTER)));
    const store = useReferenceDataStore();

    await store.load();

    expect(store.data?.summary.total_fields).toBe(1);
    expect(store.vocabulary).toEqual([
      { id: 'country_code', label: 'Country Code' },
      { id: 'currency_code', label: 'Currency Code' },
    ]);
    expect(store.error).toBe('');
  });

  it('surfaces an error when the register request fails', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) =>
      url.includes('vocabulary') ? jsonResponse(VOCABULARY) : jsonResponse({}, false, 500)));
    const store = useReferenceDataStore();

    await store.load();

    expect(store.data).toBeNull();
    expect(store.error).toContain('500');
  });

  it('still loads the register when the vocabulary request fails', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) =>
      url.includes('vocabulary') ? jsonResponse({}, false, 404) : jsonResponse(REGISTER)));
    const store = useReferenceDataStore();

    await store.load();

    expect(store.data?.summary.total_fields).toBe(1);
    expect(store.vocabulary).toEqual([]);
    expect(store.error).toBe('');
  });

  it('loads reference sets alongside the register', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) =>
      url.includes('vocabulary') ? jsonResponse(VOCABULARY)
        : url.includes('reference-sets')
          ? jsonResponse({ sets: [{ id: 'iso_4217_currency', name: 'ISO 4217', kind: 'standard', standard_ref: 'ISO 4217', status: 'approved', entry_count: 12 }] })
          : jsonResponse(REGISTER)));
    const store = useReferenceDataStore();

    await store.load();

    expect(store.sets.map(s => s.id)).toEqual(['iso_4217_currency']);
  });
});

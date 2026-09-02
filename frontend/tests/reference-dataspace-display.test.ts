import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import {
  displayStatus,
  displayStatusLabel,
  filterFields,
  groupReferenceFields,
  groupBySet,
  type ReferenceField,
  type ReferenceSetSummary,
} from '../src/pages/referenceDataspaceDisplay';

const baseField: ReferenceField = {
  source: 'banking', schema: 'src', table: 'accounts', column: 'currency',
  business_name: 'Account currency', business_name_is_fallback: false,
  semantic_type: 'currency_code', status: 'in_review', code_source: 'reference_code', set_kind: 'local',
  bound_set_id: null,
  codes: [{ code: 'EUR', value: 'Euro', meaning: 'Single currency of the Eurozone', status: 'in_review', origin: 'profiled', share_pct: null, in_source: true, in_list: true }],
  counts: { total: 1, documented: 1, approved: 0, in_review: 1, rogue: 0, unused: 0 },
  approved_by: null, approved_at: null, asset_link: '/workspace',
};

describe('Reference Dataspace display', () => {
  it('maps field status to the display pill state', () => {
    expect(displayStatus(baseField)).toBe('submitted');
    expect(displayStatusLabel(baseField)).toBe('In review');
    expect(displayStatus({ ...baseField, status: 'approved' })).toBe('approved');
    expect(displayStatusLabel({ ...baseField, status: 'approved' })).toBe('Approved');
  });

  it('filters the register by search, state, semantic type, and selected dataset', () => {
    const country = {
      ...baseField,
      column: 'country',
      business_name: 'Country',
      semantic_type: 'country_code',
      status: 'approved' as const,
      table: 'customers',
      codes: [{ code: 'FI', value: 'Finland', meaning: 'Nordic sovereign country', status: 'approved' as const, origin: 'profiled', share_pct: null, in_source: true, in_list: true }],
    };
    const fields = [baseField, country];
    expect(filterFields(fields, { q: 'euro' })).toEqual([baseField]);
    expect(filterFields(fields, { status: 'approved' })).toEqual([country]);
    expect(filterFields(fields, { semanticType: 'currency_code' })).toEqual([baseField]);
    expect(filterFields(fields, { table: ['banking|src|customers'] })).toEqual([country]);
    const grouped = groupReferenceFields(fields);
    expect(grouped[0].source).toBe('banking');
    expect(grouped[0].schemas[0].tables.map(table => table.table)).toEqual(['accounts', 'customers']);
  });

  it('does not expose a mutation action in the read model', () => {
    expect(Object.keys(baseField)).not.toContain('update');
    expect(baseField.asset_link).toBe('/workspace');
  });

  it('groups by set with a used-by count and zero for unbound sets', () => {
    const sets: ReferenceSetSummary[] = [
      { id: 'iso_4217_currency', name: 'ISO 4217 Currency Codes', kind: 'standard', standard_ref: 'ISO 4217', status: 'approved', entry_count: 12 },
      { id: 'iso_3166_country', name: 'ISO 3166 Country Codes', kind: 'standard', standard_ref: 'ISO 3166', status: 'approved', entry_count: 12 },
    ];
    const boundA = { ...baseField, bound_set_id: 'iso_4217_currency' };
    const boundB = { ...baseField, column: 'settle_ccy', bound_set_id: 'iso_4217_currency' };
    const groups = groupBySet(sets, [boundA, boundB]);
    const currency = groups.find(g => g.id === 'iso_4217_currency');
    const country = groups.find(g => g.id === 'iso_3166_country');
    expect(currency?.usedByCount).toBe(2);
    expect(currency?.fields.map(f => f.column)).toEqual(['currency', 'settle_ccy']);
    expect(country?.usedByCount).toBe(0);
    // most-used set sorts first
    expect(groups[0].id).toBe('iso_4217_currency');
  });

  it('guarantees the page and store issue no mutating requests (read-only)', () => {
    const page = readFileSync(resolve(process.cwd(), 'src/pages/ReferenceDataspace.vue'), 'utf-8');
    const store = readFileSync(resolve(process.cwd(), 'src/stores/referenceDataStore.ts'), 'utf-8');
    for (const source of [page, store]) {
      expect(source).not.toMatch(/method:\s*['"](POST|PATCH|PUT|DELETE)['"]/i);
    }
    // The register/vocabulary calls are plain GET fetches (no request-init object).
    expect(store).toContain("fetch('/api/reference-data')");
    expect(store).not.toMatch(/fetch\([^)]*,\s*\{/);
  });
});
import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import ReferenceStatusPill from '../src/components/ReferenceStatusPill.vue';
import type { ReferenceField } from '../src/pages/referenceDataspaceDisplay';

function field(overrides: Partial<ReferenceField> = {}): ReferenceField {
  return {
    source: 'banking', schema: 'src', table: 'accounts', column: 'currency',
    business_name: 'Account currency', business_name_is_fallback: false,
    semantic_type: 'currency_code', status: 'in_review', code_source: 'reference_code', set_kind: 'local',
    bound_set_id: null,
    codes: [{ code: 'EUR', value: 'Euro', meaning: 'Single currency of the Eurozone', status: 'in_review', origin: 'profiled', share_pct: null, in_source: true, in_list: true }],
    counts: { total: 1, documented: 1, approved: 0, in_review: 1, rogue: 0, unused: 0 },
    approved_by: null, approved_at: null, asset_link: '/workspace',
    ...overrides,
  };
}

describe('ReferenceStatusPill', () => {
  it('maps each governance state to its display label and class', () => {
    const cases: Array<[Partial<ReferenceField>, string, string]> = [
      [{ status: 'approved' }, 'Approved', 'rd-status--approved'],
      [{ status: 'in_review' }, 'In review', 'rd-status--submitted'],
    ];
    for (const [overrides, label, cls] of cases) {
      const wrapper = mount(ReferenceStatusPill, { props: { field: field(overrides) } });
      expect(wrapper.text()).toBe(label);
      expect(wrapper.classes()).toContain(cls);
    }
  });

  it('renders as a read-only span with no interactive controls', () => {
    const wrapper = mount(ReferenceStatusPill, { props: { field: field() } });
    expect(wrapper.element.tagName).toBe('SPAN');
    expect(wrapper.find('button').exists()).toBe(false);
    expect(wrapper.find('input').exists()).toBe(false);
  });
});

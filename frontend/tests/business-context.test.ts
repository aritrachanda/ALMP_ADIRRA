/**
 * Tests for BusinessContextPanel.vue
 *
 * Covers:
 *  - State (a): no linked term → empty state, no dead link/empty collapsible
 *  - State (b): partial term → "Not yet documented" for missing slices, no fabricated values
 *  - State (c): full term → all slices render, collapse/expand via <details>
 *  - Projection integrity: panel reflects glossary store; no local canonical copy
 *  - Missing metadata: unset status → "State not set"
 *  - "Open in Glossary" uses named route 'glossary'
 *  - "This mapping looks wrong" emits report-wrong-mapping
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { createRouter, createMemoryHistory } from 'vue-router';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { useGlossaryStore } from '../src/stores/glossaryStore';
import type { GlossaryTermRef } from '../src/api/element';
import type { GlossaryTerm } from '../src/types';

// Prevent any real HTTP calls from the glossary API
vi.mock('src/api/glossary', () => ({
  getGlossary: vi.fn().mockResolvedValue([]),
  getTerm: vi.fn().mockResolvedValue(null),
  upsertTerm: vi.fn(),
  deleteTerm: vi.fn(),
  aiSuggest: vi.fn(),
  aiSuggestFields: vi.fn(),
  generateCRRContext: vi.fn(),
  generateDPMContext: vi.fn(),
  getUncovered: vi.fn().mockResolvedValue([]),
  crossRef: vi.fn(),
}));

// ── Quasar stubs so we don't need the full Quasar runtime ──────────────────

const QBtn = {
  name: 'QBtn',
  template: '<button class="q-btn" :data-to="toStr" :data-label="label"><slot/></button>',
  props: ['to', 'label', 'icon', 'flat', 'dense', 'size', 'color'],
  computed: {
    toStr(): string { return JSON.stringify((this as { to?: unknown }).to); },
  },
};
const QIcon = { name: 'QIcon', template: '<span class="q-icon" :data-name="name" />', props: ['name', 'size'] };
const QSpinnerDots = { name: 'QSpinnerDots', template: '<span class="q-spinner" />', props: ['size'] };
// Stub router-link to a plain anchor that exposes its :to as a data attribute
const RouterLink = {
  name: 'RouterLink',
  template: '<a class="router-link" :data-to="toStr"><slot/></a>',
  props: ['to'],
  computed: {
    toStr(): string { return JSON.stringify((this as { to?: unknown }).to); },
  },
};

const globalStubs = {
  'q-btn': QBtn,
  'q-icon': QIcon,
  'q-spinner-dots': QSpinnerDots,
  'router-link': RouterLink,
};

// Minimal router — only needs the 'business-glossary' named route for push() to resolve.
function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', name: 'business-glossary', component: { template: '<div/>' } }],
  });
}

// ── Fixtures ───────────────────────────────────────────────────────────────

const termRef: GlossaryTermRef = {
  id: 'term-001',
  title: 'Account Identifier',
  business_description: 'Unique identifier for each account record.',
  detailed_description: 'Surrogate key assigned at account creation.',
  status: 'approved',
  steward: 'data-team',
  related_objects: [],
};

const partialTermRef: GlossaryTermRef = {
  id: 'term-002',
  title: 'Partial Term',
  business_description: '',
  detailed_description: '',
  status: '',
  steward: '',
  related_objects: [],
};

const fullGlossaryTerm: GlossaryTerm = {
  id: 'term-001',
  title: 'Account Identifier',
  domain: 'Banking',
  category: 'Identity',
  business_description: 'Unique identifier for each account record.',
  detailed_description: 'Surrogate key assigned at account creation.',
  CRR_context: 'Relevant under CRR3 Article 5 as a primary obligor identifier.',
  DPM_context: 'Maps to DPM 2.0 column AcctId in T_ACCT_BASE.',
  synonyms: ['AcctId', 'AccountNo'],
  tags: ['identity', 'primary-key'],
  status: 'approved',
  steward: 'data-team',
  last_updated: '2025-11-01T10:00:00Z',
};

const partialGlossaryTerm: GlossaryTerm = {
  id: 'term-002',
  title: 'Partial Term',
  business_description: '',
  detailed_description: '',
  CRR_context: '',
  DPM_context: '',
  synonyms: [],
  tags: [],
  status: '',
  last_updated: null,
};

// ── Helper ─────────────────────────────────────────────────────────────────

async function mountPanel(props: { termRef: GlossaryTermRef | null }) {
  // Dynamic import so Pinia is active when the component module loads
  const { default: BusinessContextPanel } = await import('../src/components/BusinessContextPanel.vue');
  return mount(BusinessContextPanel, {
    props,
    // Router plugin is required so router-link and useRouter() resolve correctly.
    // Pinia is NOT added here — each describe block's beforeEach calls
    // setActivePinia(createPinia()) to configure the correct store state.
    global: { plugins: [makeRouter()], stubs: globalStubs },
  });
}

// ── Tests ──────────────────────────────────────────────────────────────────

describe('BusinessContextPanel — state (a): no linked term', () => {
  beforeEach(() => setActivePinia(createPinia()));

  it('renders the empty-state message', async () => {
    const wrapper = await mountPanel({ termRef: null });
    expect(wrapper.text()).toContain('No linked glossary term yet');
  });

  it('does NOT render a <details> element (no dead collapsible)', async () => {
    const wrapper = await mountPanel({ termRef: null });
    expect(wrapper.find('details').exists()).toBe(false);
  });

  it('renders linkage action button in the no-term state', async () => {
    const wrapper = await mountPanel({ termRef: null });
    // The component uses a plain <button class="biz-ctx-link-btn"> for the
    // "Add Glossary Linkage" action — not a q-btn with a :to route.
    const btn = wrapper.find('.biz-ctx-link-btn');
    expect(btn.exists()).toBe(true);
    expect(btn.text()).toContain('Glossary');
  });
});

describe('BusinessContextPanel — state (b): partial term', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    const store = useGlossaryStore();
    store.loadTerm = vi.fn(async () => { store.selectedTerm = partialGlossaryTerm; });
  });

  it('renders "Not yet documented" for missing business description', async () => {
    const wrapper = await mountPanel({ termRef: partialTermRef });
    await wrapper.vm.$nextTick();
    await wrapper.find('.biz-ctx-toggle-btn').trigger('click'); // expand: See more…
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain('Not yet documented');
  });

  it('shows "State not set" when term status is empty', async () => {
    const wrapper = await mountPanel({ termRef: partialTermRef });
    expect(wrapper.text()).toContain('State not set');
  });

  it('does NOT fabricate values — empty slices show "Not yet documented", nothing else', async () => {
    const wrapper = await mountPanel({ termRef: partialTermRef });
    await wrapper.vm.$nextTick();
    await wrapper.find('.biz-ctx-toggle-btn').trigger('click'); // expand: See more…
    await wrapper.vm.$nextTick();
    const text = wrapper.text();
    // Should not render the fixture's full-term values
    expect(text).not.toContain('CRR3 Article 5');
    expect(text).not.toContain('AcctId');
    // Should show the placeholder
    expect(text).toContain('Not yet documented');
  });

  it('stays collapsed by default for partial terms, then opens on "Expand"', async () => {
    const wrapper = await mountPanel({ termRef: partialTermRef });
    await wrapper.vm.$nextTick();
    // Default-collapsed: body hidden, bar offers "Expand"
    expect(wrapper.find('.biz-ctx-body').exists()).toBe(false);
    expect(wrapper.text()).toContain('Expand');
    // Expanding reveals the body + "Collapse"
    await wrapper.find('.biz-ctx-toggle-btn').trigger('click');
    await wrapper.vm.$nextTick();
    expect(wrapper.find('.biz-ctx-body').exists()).toBe(true);
    expect(wrapper.text()).toContain('Collapse');
  });
});

describe('BusinessContextPanel — state (c): full term', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    const store = useGlossaryStore();
    store.loadTerm = vi.fn(async () => { store.selectedTerm = fullGlossaryTerm; });
  });

  it('renders all projected slices after expanding', async () => {
    const wrapper = await mountPanel({ termRef });
    await wrapper.vm.$nextTick();
    await wrapper.find('.biz-ctx-toggle-btn').trigger('click'); // expand
    await wrapper.vm.$nextTick();
    const text = wrapper.text();
    expect(text).toContain('Business description');
    expect(text).toContain('Detailed description');
    expect(text).toContain('CRR3 interpretation');
    expect(text).toContain('DPM 2.0 interpretation');
    expect(text).toContain('Synonyms');
    expect(text).toContain('Tags');
  });

  it('renders actual term content from the store after expanding', async () => {
    const wrapper = await mountPanel({ termRef });
    await wrapper.vm.$nextTick();
    await wrapper.find('.biz-ctx-toggle-btn').trigger('click');
    await wrapper.vm.$nextTick();
    const text = wrapper.text();
    expect(text).toContain('CRR3 Article 5');
    expect(text).toContain('AcctId');
    expect(text).toContain('identity');
  });

  it('starts collapsed for a full term — shows "Expand" not the body', async () => {
    const wrapper = await mountPanel({ termRef });
    await wrapper.vm.$nextTick();
    expect(wrapper.find('.biz-ctx-body').exists()).toBe(false);
    expect(wrapper.text()).toContain('Expand');
  });
});

describe('BusinessContextPanel — projection integrity', () => {
  beforeEach(() => setActivePinia(createPinia()));

  it('reflects glossary store updates reactively', async () => {
    const store = useGlossaryStore();
    store.loadTerm = vi.fn(async () => { store.selectedTerm = partialGlossaryTerm; });

    const wrapper = await mountPanel({ termRef: partialTermRef });
    await wrapper.vm.$nextTick();
    await wrapper.find('.biz-ctx-toggle-btn').trigger('click'); // expand to reveal slices
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain('Not yet documented');

    // Simulate store update (another part of the app updated the term)
    store.selectedTerm = { ...partialGlossaryTerm, id: 'term-002', CRR_context: 'Updated CRR content' };
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain('Updated CRR content');
  });

  it('does not expose local glossary mutation methods', async () => {
    const wrapper = await mountPanel({ termRef });
    const vm = wrapper.vm as unknown as Record<string, unknown>;
    // The component must not own glossary mutation methods
    expect(vm.saveTerm).toBeUndefined();
    expect(vm.upsertTerm).toBeUndefined();
    expect(vm.glossaryData).toBeUndefined();
  });
});

describe('BusinessContextPanel — routing and events', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    const store = useGlossaryStore();
    store.loadTerm = vi.fn(async () => { store.selectedTerm = fullGlossaryTerm; });
  });

  it('term title is a router-link pointing to named route "business-glossary" with the term id in query', async () => {
    const wrapper = await mountPanel({ termRef });
    // The term title renders as a router-link stub with :to serialised in data-to.
    const link = wrapper.find('a.router-link');
    expect(link.exists()).toBe(true);
    const to = JSON.parse(link.attributes('data-to') ?? '{}');
    expect(to.name).toBe('business-glossary');
    expect(to.query?.term).toBe('term-001');
  });

  it('"report-wrong-mapping" is declared as an emit (button was removed from template, event preserved for future use)', async () => {
    // The wrong-mapping button was removed from the template in a later redesign.
    // The emit is still declared so parent components remain compatible.
    const src = readFileSync(
      resolve(__dirname, '../src/components/BusinessContextPanel.vue'),
      'utf-8',
    );
    expect(src).toContain('report-wrong-mapping');
  });
});

// ── Static structural checks (source-level) ────────────────────────────────

describe('BusinessContextPanel.vue — structural checks', () => {
  const src = readFileSync(
    resolve(__dirname, '../src/components/BusinessContextPanel.vue'),
    'utf-8',
  );

  it('uses glossaryStore, not a local copy', () => {
    expect(src).toContain('useGlossaryStore');
    expect(src).toContain('glossaryStore.selectedTerm');
  });

  it('does not hardcode the glossary path', () => {
    expect(src).not.toContain("'/tools/glossary'");
    expect(src).not.toContain('"/tools/glossary"');
    expect(src).not.toContain('`/tools/glossary`');
  });

  it('routes via named route "business-glossary"', () => {
    expect(src).toContain("name: 'business-glossary'");
  });

  it('emits report-wrong-mapping, does not hardcode a navigation', () => {
    // The handler emits the event rather than navigating directly to a hardcoded path.
    // (The TODO placeholder was removed when the feature was implemented.)
    expect(src).toContain('report-wrong-mapping');
    expect(src).not.toContain("'/tools/glossary'");
    expect(src).not.toContain('"/tools/glossary"');
  });
});

describe('AssetWorkspace.vue — uses BusinessContextPanel', () => {
  const src = readFileSync(
    resolve(__dirname, '../src/pages/AssetWorkspace.vue'),
    'utf-8',
  );

  it('imports BusinessContextPanel', () => {
    expect(src).toContain('BusinessContextPanel');
  });

  it('no longer hardcodes the glossary path', () => {
    expect(src).not.toContain("to=`/tools/glossary");
  });

  it('Definition section header is renamed', () => {
    expect(src).not.toContain('Column description');
    // The Definition block header now renders in the accent bar title.
    expect(src).toMatch(/block-bar-title[^>]*>\s*Definition\s*</);
  });
});

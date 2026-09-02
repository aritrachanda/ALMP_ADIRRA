import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type {
  GlossaryV2Summary, GlossaryTerm, GlossaryV2History, GlossaryV2Coverage, AttributeConfig,
  GlossaryV2QueueItem, GlossaryV2GenerateResult,
} from 'src/types';
import * as api from 'src/api/glossaryV2';
import type { ReviewDecision } from 'src/api/glossaryV2';

/** A row in the flattened, category-grouped, hierarchical browse list. */
export interface TreeRow {
  kind: 'category' | 'term';
  key: string;
  label: string;
  count?: number;         // category: number of terms
  term?: GlossaryV2Summary;
  depth?: number;         // term nesting depth within its category (1..3)
}

/** Category → hierarchical term rows, flattened for template rendering. Pure function so
 * pages can build rows from an arbitrary (e.g. client-filtered) subset, not just the
 * store's full `summaries` list. */
export function buildTreeRows(summaries: GlossaryV2Summary[]): TreeRow[] {
  const byId = new Map(summaries.map((s) => [s.id, s]));
  const byCategory = new Map<string, GlossaryV2Summary[]>();
  for (const s of summaries) {
    const cat = s.category || 'Uncategorized';
    const bucket = byCategory.get(cat) ?? [];
    bucket.push(s);
    byCategory.set(cat, bucket);
  }
  const rows: TreeRow[] = [];
  for (const cat of [...byCategory.keys()].sort((a, b) => a.localeCompare(b))) {
    const items = byCategory.get(cat)!;
    const inSet = new Set(items.map((i) => i.id));
    const childrenOf = new Map<string, GlossaryV2Summary[]>();
    const roots: GlossaryV2Summary[] = [];
    for (const it of items) {
      // a term is a "root" in this view if it has no parent, or its parent is not in the
      // current (possibly filtered) set / different category
      const parentInSet = it.parent && inSet.has(it.parent) && byId.get(it.parent)?.category === cat;
      if (parentInSet) {
        const arr = childrenOf.get(it.parent!) ?? [];
        arr.push(it);
        childrenOf.set(it.parent!, arr);
      } else {
        roots.push(it);
      }
    }
    rows.push({ kind: 'category', key: `cat:${cat}`, label: cat, count: items.length });
    const walk = (node: GlossaryV2Summary, depth: number) => {
      rows.push({ kind: 'term', key: `term:${node.id}`, label: node.title, term: node, depth });
      if (depth < 3) {
        for (const child of (childrenOf.get(node.id) ?? []).sort((a, b) => a.title.localeCompare(b.title))) {
          walk(child, depth + 1);
        }
      }
    };
    for (const root of roots.sort((a, b) => a.title.localeCompare(b.title))) walk(root, 1);
  }
  return rows;
}

export const useGlossaryV2Store = defineStore('glossaryV2', () => {
  const summaries = ref<GlossaryV2Summary[]>([]);   // current display set (all or search result)
  const facets = ref<Record<string, Record<string, number>>>({});
  const coverage = ref<GlossaryV2Coverage | null>(null);
  // Real (non-fabricated) staged-loading progress for the coverage loader — see
  // StagedLoader.vue's `completed`/`activeDetail` props.
  const coverageProgress = ref({ completed: 0, detail: '' });
  const attributesConfig = ref<AttributeConfig[]>([]);
  const selectedSlug = ref<string | null>(null);
  const selectedTerm = ref<GlossaryTerm | null>(null);
  const history = ref<GlossaryV2History | null>(null);
  const filters = ref<api.SearchParams>({});
  const loading = ref(false);
  const detailLoading = ref(false);

  // ── Review queue (Phase 4c) ────────────────────────────────────────────────
  const reviewQueue = ref<GlossaryV2QueueItem[]>([]);
  const reviewLoading = ref(false);
  const savingTerm = ref(false);
  const generating = ref<string | null>(null);   // field key currently being generated, if any

  /** Category → hierarchical term rows, flattened for template rendering. */
  const treeRows = computed<TreeRow[]>(() => buildTreeRows(summaries.value));

  async function loadTree() {
    loading.value = true;
    try {
      summaries.value = await api.getTree();
    } finally {
      loading.value = false;
    }
  }

  async function loadFacets() {
    facets.value = await api.getFacets();
  }

  async function loadCoverage() {
    coverageProgress.value = { completed: 0, detail: '' };
    coverage.value = await api.streamCoverage(
      (completed) => { coverageProgress.value = { ...coverageProgress.value, completed }; },
      (detail) => { coverageProgress.value = { ...coverageProgress.value, detail }; },
    );
  }

  async function loadAttributesConfig() {
    attributesConfig.value = await api.getAttributesConfig();
  }

  async function applyFilters(next: api.SearchParams) {
    filters.value = next;
    loading.value = true;
    try {
      const hasFilter = Object.values(next).some((v) => v !== undefined && v !== null && v !== '');
      summaries.value = hasFilter ? await api.search(next) : await api.getTree();
    } finally {
      loading.value = false;
    }
  }

  async function selectTerm(slug: string) {
    selectedSlug.value = slug;
    detailLoading.value = true;
    try {
      const [term, hist] = await Promise.all([api.getTerm(slug), api.getHistory(slug)]);
      selectedTerm.value = term;
      history.value = hist;
    } finally {
      detailLoading.value = false;
    }
  }

  async function reparentTerm(slug: string, parent: string | null) {
    await api.reparent(slug, parent);
    await loadTree();
  }

  // ── Review queue actions ────────────────────────────────────────────────────

  async function loadReviewQueue() {
    reviewLoading.value = true;
    try {
      reviewQueue.value = await api.getReviewQueue();
    } finally {
      reviewLoading.value = false;
    }
  }

  /** Drop a term from the local queue after a decision (server state already changed). */
  function dropFromQueue(slug: string) {
    reviewQueue.value = reviewQueue.value.filter((q) => q.id !== slug);
  }

  async function confirmTerm(slug: string, decision: ReviewDecision = {}) {
    await api.confirmTerm(slug, decision);
    dropFromQueue(slug);
    await loadCoverage();
  }

  async function rejectTerm(slug: string, decision: ReviewDecision = {}) {
    await api.rejectTerm(slug, decision);
    dropFromQueue(slug);
    await loadCoverage();
  }

  async function assignReview(slug: string, assignee: string | null) {
    await api.assignReview(slug, assignee);
    const row = reviewQueue.value.find((q) => q.id === slug);
    if (row) row.assigned_to = assignee;
  }

  /** Persist edits to a term (definition, descriptions, synonyms, tags, provenance…). */
  async function saveTerm(slug: string, patch: Partial<GlossaryTerm>): Promise<GlossaryTerm> {
    savingTerm.value = true;
    try {
      const updated = await api.updateTerm(slug, patch);
      if (selectedSlug.value === slug) selectedTerm.value = updated;
      return updated;
    } finally {
      savingTerm.value = false;
    }
  }

  /** Ask the backend to draft a single field; returns value + provenance. */
  async function generateField(slug: string, field: string): Promise<GlossaryV2GenerateResult> {
    generating.value = field;
    try {
      return await api.generateField(slug, field);
    } finally {
      generating.value = null;
    }
  }

  return {
    summaries, facets, coverage, coverageProgress, attributesConfig, selectedSlug, selectedTerm, history,
    filters, loading, detailLoading, treeRows,
    reviewQueue, reviewLoading, savingTerm, generating,
    loadTree, loadFacets, loadCoverage, loadAttributesConfig, applyFilters, selectTerm, reparentTerm,
    loadReviewQueue, confirmTerm, rejectTerm, assignReview, saveTerm, generateField,
  };
});

import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { GlossaryTerm, UncoveredConcept } from 'src/types';
import * as api from 'src/api/glossary';

export const useGlossaryStore = defineStore('glossary', () => {
  const terms = ref<GlossaryTerm[]>([]);
  const selectedTerm = ref<GlossaryTerm | null>(null);
  const uncoveredConcepts = ref<UncoveredConcept[]>([]);
  const prefill = ref<Partial<GlossaryTerm> | null>(null);
  const loading = ref(false);

  const byDomainCategory = computed(() => {
    const tree: Record<string, Record<string, GlossaryTerm[]>> = {};
    for (const t of terms.value) {
      const domain = t.domain ?? 'Uncategorized';
      const category = t.category ?? 'Uncategorized';
      if (!tree[domain]) tree[domain] = {};
      if (!tree[domain][category]) tree[domain][category] = [];
      tree[domain][category].push(t);
    }
    return tree;
  });

  async function loadGlossary() {
    loading.value = true;
    try {
      terms.value = await api.getGlossary();
    } finally {
      loading.value = false;
    }
  }

  async function loadTerm(id: string) {
    loading.value = true;
    try {
      selectedTerm.value = await api.getTerm(id);
    } finally {
      loading.value = false;
    }
  }

  async function saveTerm(term: Partial<GlossaryTerm>) {
    const saved = await api.upsertTerm(term);
    await loadGlossary();
    selectedTerm.value = saved;
    return saved;
  }

  async function removeTerm(id: string) {
    await api.deleteTerm(id);
    if (selectedTerm.value?.id === id) selectedTerm.value = null;
    await loadGlossary();
  }

  async function suggestAI(id: string) {
    return api.aiSuggest(id);
  }

  async function suggestFieldsAI(id: string, fields: string[]) {
    return api.aiSuggestFields(id, fields);
  }

  async function generateCRR(id: string) {
    return api.generateCRRContext(id);
  }

  async function generateDPM(id: string) {
    return api.generateDPMContext(id);
  }

  async function loadUncovered() {
    uncoveredConcepts.value = await api.getUncovered();
  }

  function setPrefill(data: Partial<GlossaryTerm>) {
    prefill.value = data;
  }

  function clearPrefill() {
    prefill.value = null;
  }

  return {
    terms, selectedTerm, uncoveredConcepts, prefill, byDomainCategory, loading,
    loadGlossary, loadTerm, saveTerm, removeTerm,
    suggestAI, suggestFieldsAI, generateCRR, generateDPM,
    loadUncovered, setPrefill, clearPrefill,
  };
});

import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { ReferenceDataspaceResponse, ReferenceSetSummary } from 'src/pages/referenceDataspaceDisplay';

export const useReferenceDataStore = defineStore('referenceData', () => {
  const data = ref<ReferenceDataspaceResponse | null>(null);
  const vocabulary = ref<Array<{ id: string; label: string }>>([]);
  const sets = ref<ReferenceSetSummary[]>([]);
  const loading = ref(false);
  const error = ref('');

  async function load(): Promise<void> {
    loading.value = true;
    error.value = '';
    try {
      const [registerResponse, vocabularyResponse, setsResponse] = await Promise.all([
        fetch('/api/reference-data'),
        fetch('/api/semantic-types/vocabulary'),
        fetch('/api/reference-sets'),
      ]);
      if (!registerResponse.ok) throw new Error(`Reference Dataspace request failed (${registerResponse.status})`);
      data.value = await registerResponse.json() as ReferenceDataspaceResponse;
      if (vocabularyResponse.ok) {
        const raw = await vocabularyResponse.json() as { types_by_role?: Record<string, Array<{ id: string; label?: string }>> };
        const entries = Object.values(raw.types_by_role ?? {}).flat();
        const seen = new Set<string>();
        vocabulary.value = entries
          .filter(item => item?.id && !seen.has(item.id) && seen.add(item.id))
          .map(item => ({ id: item.id, label: item.label ?? item.id }))
          .sort((a, b) => a.label.localeCompare(b.label));
      }
      if (setsResponse.ok) {
        const rawSets = await setsResponse.json() as { sets?: ReferenceSetSummary[] };
        const summaries = rawSets.sets ?? [];
        // Fetch each set's full entries so "Browse by set" can show the codes,
        // not just the count. Sets are few and small at prototype scale.
        sets.value = await Promise.all(summaries.map(async (summary) => {
          const detailResponse = await fetch(`/api/reference-sets/${encodeURIComponent(summary.id)}`);
          if (!detailResponse.ok) return summary;
          const detail = await detailResponse.json() as { entries?: ReferenceSetSummary['entries'] };
          return { ...summary, entries: detail.entries ?? [] };
        }));
      }
    } catch (caught) {
      error.value = caught instanceof Error ? caught.message : 'Unable to load Reference Dataspace.';
    } finally {
      loading.value = false;
    }
  }

  return { data, vocabulary, sets, loading, error, load };
});
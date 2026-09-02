import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import { apiFetch } from 'src/api/client';
import { getSourceInfo, type SourceInfo } from 'src/api/element';
import { getDashboardSummary, type DashboardSummary } from 'src/api/dashboard';

/** What the dashboard is currently reporting on. */
export type DashboardScope =
  | { kind: 'all' }
  | { kind: 'source'; source: string };

/**
 * Cross-source dashboard data.
 *
 * Aggregation happens here rather than in a new backend endpoint: the existing
 * per-source `/info` calls are already fast when warm (measured: 99ms–1.1s each,
 * run in parallel), and reusing them keeps one source of truth for every
 * governance/quality number the app shows.
 */
export const useDashboardStore = defineStore('dashboard', () => {
  const sources = ref<string[]>([]);
  const infoBySource = ref<Record<string, SourceInfo>>({});
  const legacy = ref<DashboardSummary | null>(null);

  const loading = ref(false);
  const error = ref<string | null>(null);
  const loadedCount = ref(0);
  const loadedSourceNames = ref<string[]>([]);
  const lastUpdatedAt = ref<Date | null>(null);

  const scope = ref<DashboardScope>({ kind: 'all' });

  /** Source infos in the current scope. */
  const scoped = computed<SourceInfo[]>(() => {
    const all = sources.value
      .map((s) => infoBySource.value[s])
      .filter((i): i is SourceInfo => !!i);
    if (scope.value.kind === 'source') {
      const one = infoBySource.value[scope.value.source];
      return one ? [one] : [];
    }
    return all;
  });

  const scopeLabel = computed(() => (scope.value.kind === 'source' ? scope.value.source : 'All sources'));

  function setScope(next: DashboardScope) {
    scope.value = next;
  }

  async function load(force = false) {
    if (loading.value) return;
    if (!force && sources.value.length && Object.keys(infoBySource.value).length) return;
    loading.value = true;
    error.value = null;
    loadedCount.value = 0;
    loadedSourceNames.value = [];
    try {
      const list = await apiFetch<{ catalogs: { name: string }[] }>('/api/catalogs/sources');
      sources.value = list.catalogs.map((c) => c.name);

      const results = await Promise.all(
        sources.value.map(async (name) => {
          const info = await getSourceInfo(name);
          loadedCount.value += 1;
          loadedSourceNames.value.push(name);
          return [name, info] as const;
        }),
      );
      infoBySource.value = Object.fromEntries(results);

      // Mapping/glossary aggregates still come from the original endpoint.
      legacy.value = await getDashboardSummary();
      lastUpdatedAt.value = new Date();
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to load dashboard data';
    } finally {
      loading.value = false;
    }
  }

  return {
    sources,
    infoBySource,
    legacy,
    loading,
    error,
    loadedCount,
    loadedSourceNames,
    lastUpdatedAt,
    scope,
    scoped,
    scopeLabel,
    setScope,
    load,
  };
});

import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { CatalogListItem, Catalog, Table } from 'src/types';
import * as api from 'src/api/catalogs';

export const useCatalogStore = defineStore('catalog', () => {
  const sources = ref<CatalogListItem[]>([]);
  const targets = ref<CatalogListItem[]>([]);
  const activeCatalog = ref<Catalog | null>(null);
  const activeTable = ref<Table | null>(null);
  const selectedDataset = ref('');
  const selectedTable = ref('');
  const selectedType = ref<'sources' | 'targets'>('sources');

  async function loadSources() {
    const res = await api.listCatalogs('sources');
    sources.value = res.catalogs;
    try {
      // eslint-disable-next-line no-console
      console.debug('catalogStore: sources loaded', sources.value);
    } catch { /* ignore */ }
  }

  async function loadTargets() {
    const res = await api.listCatalogs('targets');
    targets.value = res.catalogs;
    try {
      // eslint-disable-next-line no-console
      console.debug('catalogStore: targets loaded', targets.value);
    } catch { /* ignore */ }
  }

  async function loadCatalog(type: 'sources' | 'targets', name: string) {
    selectedType.value = type;
    selectedDataset.value = name;
    activeCatalog.value = await api.getCatalog(type, name);
    try {
      // eslint-disable-next-line no-console
      console.debug('catalogStore: loaded activeCatalog', activeCatalog.value);
    } catch {
      // ignore
    }
  }

  async function loadTable(type: 'sources' | 'targets', name: string, table: string) {
    selectedTable.value = table;
    activeTable.value = await api.getTable(type, name, table);
  }

  async function aiGenerate(field: string, columnName?: string | null) {
    return api.aiGenerate(
      selectedType.value,
      selectedDataset.value,
      selectedTable.value,
      field,
      columnName,
    );
  }

  return {
    sources, targets, activeCatalog, activeTable,
    selectedDataset, selectedTable, selectedType,
    loadSources, loadTargets, loadCatalog, loadTable, aiGenerate,
  };
});

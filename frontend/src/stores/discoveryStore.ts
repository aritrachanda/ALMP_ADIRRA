import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { Table } from 'src/types';
import * as api from 'src/api/discovery';
import type { DatasetItem, ChatVisual, AssessmentResult, TableProfile } from 'src/api/discovery';

export interface ChatMessage {
  role: string;
  content: string;
  visuals?: ChatVisual[];
}

export const useDiscoveryStore = defineStore('discovery', () => {
  const datasets = ref<DatasetItem[]>([]);
  const tableStats = ref<Table | null>(null);
  const tableProfile = ref<TableProfile | null>(null);
  const tableAssessment = ref<AssessmentResult | null>(null);
  const queryColumns = ref<string[]>([]);
  const queryRows = ref<Record<string, unknown>[]>([]);

  // Persisted UI state
  const selectedDataset = ref<string | null>(null);
  const selectedTable = ref<string | null>(null);
  const selectedColumn = ref<string | null>(null);
  const chatInput = ref('');
  const chatMessages = ref<ChatMessage[]>([]);

  async function loadDatasets() {
    datasets.value = await api.listDatasets();
  }

  async function loadStats(dataset: string, table: string) {
    tableStats.value = await api.getTableStats(dataset, table);
  }

  async function loadProfile(dataset: string, table: string) {
    tableProfile.value = await api.getTableProfile(dataset, table);
  }

  async function loadAssessment(
    dataset: string,
    table: string,
    opts: { includeAi?: boolean; refresh?: boolean } = {},
  ) {
    tableAssessment.value = await api.getTableAssessment(dataset, table, opts);
    return tableAssessment.value;
  }

  async function runQuery(dataset: string, table: string, sql: string, limit = 100) {
    const result = await api.executeQuery(dataset, table, sql, limit);
    queryColumns.value = result.columns;
    queryRows.value = result.rows;
    return result;
  }

  async function chat(dataset: string, table: string, messages: { role: string; content: string }[]) {
    return api.discoveryChat(dataset, table, messages);
  }

  return {
    datasets, tableStats, queryColumns, queryRows,
    tableProfile, tableAssessment,
    selectedDataset, selectedTable, selectedColumn, chatInput, chatMessages,
    loadDatasets, loadStats, runQuery, chat,
    loadProfile, loadAssessment,
  };
});

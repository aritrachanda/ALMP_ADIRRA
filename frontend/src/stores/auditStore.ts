import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { AuditEvent, AuditSummaryRow, ListEventsParams } from 'src/api/audit';
import * as api from 'src/api/audit';

export const useAuditStore = defineStore('audit', () => {
  const events = ref<AuditEvent[]>([]);
  const summary = ref<AuditSummaryRow[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);
  const total = ref(0);

  async function loadEvents(params: ListEventsParams = {}) {
    loading.value = true;
    error.value = null;
    try {
      events.value = await api.listEvents({ limit: 50, ...params });
      total.value = events.value.length;
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to load audit events';
    } finally {
      loading.value = false;
    }
  }

  async function loadSummary(days = 30) {
    try {
      summary.value = await api.getSummary(days);
    } catch {
      // non-critical; silently skip
    }
  }

  return { events, summary, loading, error, total, loadEvents, loadSummary };
});

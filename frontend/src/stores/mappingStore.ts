import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { MappingResult, MappingListItem, SSEEvent } from 'src/types';
import * as api from 'src/api/mappings';
import { readSSE } from 'src/api/sse';

export const useMappingStore = defineStore('mapping', () => {
  const mappings = ref<MappingListItem[]>([]);
  const activeMapping = ref<MappingResult | null>(null);
  const streamStatus = ref<string>('idle');
  const streamEvents = ref<SSEEvent[]>([]);
  let _abortController: AbortController | null = null;

  async function loadMappings() {
    mappings.value = await api.listMappings();
  }

  async function loadMapping(source: string, target: string) {
    activeMapping.value = await api.getMapping(source, target);
  }

  async function runStream(source: string, target: string, body: {
    dataset_context?: string;
    agent_choice?: string;
    selected_tables?: string[] | null;
  }) {
    streamStatus.value = 'running';
    streamEvents.value = [];
    // Drop any previous in-flight stream before opening a new one (avoids orphaning
    // a still-open fetch/ReadableStream connection on re-run).
    if (_abortController) _abortController.abort();
    _abortController = new AbortController();

    try {
      for await (const event of readSSE(`/api/mappings/${source}/${target}/run-stream`, body, _abortController.signal)) {
        streamEvents.value = [...streamEvents.value, event];
        if (event.event === 'done') {
          streamStatus.value = 'done';
          // Mapping was saved on the backend; fetch it
          await loadMapping(source, target);
        } else if (event.event === 'error') {
          streamStatus.value = 'error';
        }
      }
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === 'AbortError') {
        streamStatus.value = 'cancelled';
      } else {
        console.error('SSE stream error:', e);
        streamStatus.value = 'error';
      }
    } finally {
      _abortController = null;
    }

    if (streamStatus.value === 'running') {
      // Stream ended without explicit done event — try loading anyway
      streamStatus.value = 'done';
      try {
        await loadMapping(source, target);
      } catch {
        // No mapping saved
      }
    }
  }

  function cancelStream() {
    if (_abortController) {
      _abortController.abort();
    }
  }

  async function acceptDiscardCandidates(source: string, target: string, updates: {
    target_schema: string;
    target_table: string;
    target_column: string;
    status: string;
  }[]) {
    activeMapping.value = await api.updateCandidates(source, target, updates);
  }

  async function save(source: string, target: string) {
    if (activeMapping.value) {
      await api.saveMapping(source, target, activeMapping.value);
    }
  }

  return {
    mappings, activeMapping, streamStatus, streamEvents,
    loadMappings, loadMapping, runStream, cancelStream, acceptDiscardCandidates, save,
  };
});

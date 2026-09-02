import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { AnnotationOverlay, TableAnnotation } from 'src/types';
import * as api from 'src/api/annotations';

export const useAnnotationStore = defineStore('annotation', () => {
  const overlay = ref<AnnotationOverlay | null>(null);

  async function loadAnnotations(dataset: string) {
    overlay.value = await api.getAnnotations(dataset);
  }

  async function saveAnnotations(dataset: string, table: string, body: TableAnnotation) {
    await api.setAnnotations(dataset, table, body);
    await loadAnnotations(dataset);
  }

  return { overlay, loadAnnotations, saveAnnotations };
});

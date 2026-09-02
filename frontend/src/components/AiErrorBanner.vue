<template>
  <div v-if="error" class="ai-err-banner" role="alert">
    <q-icon name="error_outline" size="18px" class="ai-err-icon" />
    <div class="ai-err-body">
      <span class="ai-err-summary">{{ error.summary }}</span>
      <details v-if="error.detail" class="ai-err-details">
        <summary>Technical details</summary>
        <pre class="ai-err-pre">{{ (error.status ? '[' + error.status + '] ' : '') + error.detail }}</pre>
      </details>
    </div>
    <button class="ai-err-dismiss" title="Dismiss" aria-label="Dismiss" @click="$emit('dismiss')">
      <q-icon name="close" size="15px" />
    </button>
  </div>
</template>

<script setup lang="ts">
import type { AiError } from 'src/composables/useAiError';

defineProps<{ error: AiError | null }>();
defineEmits<{ (e: 'dismiss'): void }>();
</script>

<style scoped>
.ai-err-banner {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  margin-bottom: 10px;
  border: 1px solid var(--adirra-danger);
  border-radius: 8px;
  background: var(--adirra-danger-soft);
  color: var(--adirra-ink);
  font-size: 12.5px;
  line-height: 1.35;
}
.ai-err-icon {
  color: var(--adirra-danger);
  flex: 0 0 auto;
  margin-top: 1px;
}
.ai-err-body {
  flex: 1 1 auto;
  min-width: 0;
}
.ai-err-summary {
  font-weight: 600;
}
.ai-err-details {
  margin-top: 4px;
}
.ai-err-details > summary {
  cursor: pointer;
  color: var(--adirra-ink-2);
  font-size: 11.5px;
  user-select: none;
}
.ai-err-pre {
  margin: 4px 0 0;
  padding: 6px 8px;
  border-radius: 6px;
  background: var(--adirra-paper-2);
  color: var(--adirra-ink-2);
  font-size: 11px;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 140px;
  overflow: auto;
}
.ai-err-dismiss {
  flex: 0 0 auto;
  border: none;
  background: transparent;
  color: var(--adirra-ink-3);
  cursor: pointer;
  padding: 2px;
  border-radius: 4px;
  line-height: 0;
}
.ai-err-dismiss:hover {
  color: var(--adirra-ink);
  background: var(--adirra-paper-2);
}
</style>

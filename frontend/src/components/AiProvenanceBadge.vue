<template>
  <q-chip
    v-if="isAI"
    dense square size="sm"
    color="orange-1" text-color="orange-9"
    icon="auto_awesome"
    class="ai-prov-chip"
  >
    AI
    <q-tooltip anchor="bottom start" self="top start" class="ai-prov-tip">
      <template v-if="prov && (prov.model || prov.prompt_id)">
        <div>model: {{ prov.model || '—' }}</div>
        <div>prompt: {{ prov.prompt_id || '—' }}</div>
        <div v-if="prov.generated_at">generated: {{ prov.generated_at }}</div>
      </template>
      <template v-else>AI-generated · provenance not recorded</template>
    </q-tooltip>
  </q-chip>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { GlossaryTerm, AIProvenance } from 'src/types';

// Per-field AI badge. Provenance (model + prompt id, no confidence) shows when recorded;
// otherwise "provenance not recorded" — the majority state at launch, by design.
const props = defineProps<{ field: string; term: GlossaryTerm }>();

const isAI = computed(() => (props.term.ai_generated_fields || []).includes(props.field));
const prov = computed<AIProvenance | undefined>(() => props.term.ai_provenance?.[props.field]);
</script>

<style scoped>
.ai-prov-chip { font-weight: 600; }
.ai-prov-tip { font-family: monospace; font-size: 11px; }
</style>

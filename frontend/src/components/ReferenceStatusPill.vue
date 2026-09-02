<template>
  <span class="rd-status" :class="`rd-status--${state}`">{{ label }}</span>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { displayStatus, displayStatusLabel, type ReferenceField } from 'src/pages/referenceDataspaceDisplay';

const props = defineProps<{ field: ReferenceField }>();

const state = computed(() => displayStatus(props.field));
const label = computed(() => displayStatusLabel(props.field));
</script>

<style scoped>
.rd-status {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: max-content;
  padding: 3px 8px;
  border: 1px solid;
  border-radius: 999px;
  font-weight: 700;
  font-size: 11px;
}
.rd-status--approved { color: var(--adirra-released); background: var(--adirra-released-soft); border-color: var(--adirra-released); }
.rd-status--submitted { color: var(--adirra-reviewed); background: var(--adirra-reviewed-soft); border-color: var(--adirra-reviewed); }
.rd-status--draft { color: var(--adirra-draft); background: var(--adirra-draft-soft); border-color: var(--adirra-draft); }
.rd-status--undefined { color: var(--adirra-danger); background: var(--adirra-danger-soft); border-color: var(--adirra-danger); }
</style>

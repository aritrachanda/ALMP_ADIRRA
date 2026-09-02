<template>
  <span class="status-pill" :class="{ 'status-pill--compact': compact }" :style="pillStyle">
    {{ tone.label }}
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { getStatusTone } from 'src/utils/statusDisplay';

const props = withDefaults(defineProps<{
  status: string;
  compact?: boolean;
}>(), {
  compact: false,
});

const tone = computed(() => getStatusTone(props.status));
const pillStyle = computed(() => ({
  color: tone.value.textColor,
  background: tone.value.bgColor,
  borderColor: tone.value.borderColor,
}));
</script>

<style scoped>
.status-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 24px;
  padding: 0.18rem 0.62rem;
  border-radius: 999px;
  border: 1px solid;
  font-size: 0.74rem;
  font-weight: 700;
  letter-spacing: 0.02em;
  text-transform: capitalize;
  line-height: 1.1;
}

.status-pill--compact {
  min-height: 20px;
  padding: 0.14rem 0.52rem;
  font-size: 0.7rem;
}
</style>
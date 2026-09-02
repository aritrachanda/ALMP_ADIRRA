<template>
  <span class="governance-logo" :style="logoStyle" :aria-label="`${label} logo`" role="img">
    <svg v-if="system === 'collibra'" :width="size" :height="size" viewBox="0 0 14 14" xmlns="http://www.w3.org/2000/svg">
      <circle cx="7" cy="1.3" r="1.05" fill="#6DC130" />
      <circle cx="10.8" cy="3.2" r="1.05" fill="#6DC130" />
      <circle cx="12.7" cy="7" r="1.05" fill="#6DC130" />
      <circle cx="10.8" cy="10.8" r="1.05" fill="#6DC130" />
      <circle cx="7" cy="12.7" r="1.05" fill="#6DC130" />
      <circle cx="3.2" cy="10.8" r="1.05" fill="#6DC130" />
      <circle cx="1.3" cy="7" r="1.05" fill="#6DC130" />
      <circle cx="3.2" cy="3.2" r="1.05" fill="#6DC130" />
      <circle cx="7" cy="4.1" r="0.85" fill="#6DC130" />
      <circle cx="9.9" cy="7" r="0.85" fill="#6DC130" />
      <circle cx="7" cy="9.9" r="0.85" fill="#6DC130" />
      <circle cx="4.1" cy="7" r="0.85" fill="#6DC130" />
      <circle cx="7" cy="7" r="1.15" fill="#6DC130" />
    </svg>

    <svg v-else :width="size" :height="size" viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg">
      <rect x="1" y="1" width="6" height="6" fill="#F25022" />
      <rect x="9" y="1" width="6" height="6" fill="#7FBA00" />
      <rect x="1" y="9" width="6" height="6" fill="#00A4EF" />
      <rect x="9" y="9" width="6" height="6" fill="#FFB900" />
    </svg>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = withDefaults(defineProps<{
  system: 'collibra' | 'purview';
  size?: number;
}>(), {
  size: 18,
});

const label = computed(() => props.system === 'collibra' ? 'Collibra' : 'Microsoft Purview');
const logoStyle = computed(() => ({
  width: `${props.size}px`,
  height: `${props.size}px`,
}));
</script>

<style scoped>
.governance-logo {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.governance-logo svg {
  display: block;
}
</style>
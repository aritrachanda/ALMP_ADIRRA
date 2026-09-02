<template>
  <q-btn
    flat
    round
    dense
    :icon="dark ? 'dark_mode' : 'light_mode'"
    class="theme-toggle-btn"
    aria-label="Toggle theme"
    @click="toggleTheme"
  />
</template>

<script setup lang="ts">
import { useTheme } from 'src/composables/useTheme';

const { dark, toggleTheme } = useTheme();
</script>

<style scoped lang="scss">
.theme-toggle-btn {
  width: 36px;
  min-width: 36px;
  height: 36px;
  border-radius: 9px;
  border: 1px solid var(--adirra-line);
  background: var(--adirra-card);
  color: var(--adirra-ink-2);
}

.theme-toggle-btn:hover {
  border-color: var(--adirra-accent);
  color: var(--adirra-accent);
  background: var(--adirra-accent-soft);
}
</style>

<template>
  <q-item
    clickable
    :to="to"
    exact
    active-class="side-nav-active"
    class="side-nav-item q-pl-lg"
  >
    <q-item-section avatar>
      <q-icon :name="icon" size="20px" />
    </q-item-section>
    <q-item-section v-if="!mini" no-wrap>{{ label }}</q-item-section>
    <q-tooltip v-if="mini" anchor="center right" self="center left">{{ label }}</q-tooltip>
  </q-item>
</template>

<script setup lang="ts">
defineProps<{
  to: string;
  icon: string;
  label: string;
  mini: boolean;
}>();
</script>

<style scoped>
.side-nav-item {
  border-radius: 14px;
  margin: 0.15rem 0.45rem;
  color: rgba(230, 237, 245, 0.9);
  transition: background-color 0.16s ease, box-shadow 0.16s ease, color 0.16s ease;
}

.side-nav-item :deep(.q-icon) {
  color: rgba(230, 237, 245, 0.82);
}

.side-nav-item:hover {
  background: rgba(255,255,255,0.08);
}

.side-nav-active {
  background: linear-gradient(90deg, rgba(147, 197, 253, 0.28) 0%, rgba(255,255,255,0.12) 100%);
  box-shadow: inset 3px 0 0 #7dd3fc;
  color: #ffffff;
  font-weight: 700;
}

.side-nav-active :deep(.q-icon) {
  color: #9fd1ff;
}
</style>

<template>
  <div class="viz-card">
    <div class="viz-card-head">
      <span class="viz-card-title">{{ title }}</span>
      <span v-if="caption" class="viz-card-caption">{{ caption }}</span>
    </div>

    <template v-if="ranked.length">
      <div class="rank-rows">
        <div
          v-for="item in ranked" :key="item.label"
          class="rank-row"
          :class="{ 'rank-row--click': clickable }"
          @click="clickable && $emit('select', item.label)"
        >
          <span class="rank-lbl" :title="item.label">{{ item.label }}</span>
          <div class="rank-track">
            <div class="rank-fill" :style="{ width: item.pct + '%', background: item.color }" />
          </div>
          <span class="rank-val mono">{{ item.display }}</span>
        </div>
      </div>
    </template>
    <div v-else class="viz-empty">Nothing to rank yet.</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

export interface RankedItem {
  label: string;
  value: number;
  /** Pre-formatted value shown at the row's right edge. */
  display?: string;
  color?: string;
}

const props = defineProps<{
  title: string;
  caption?: string | null;
  items: RankedItem[];
  clickable?: boolean;
}>();

defineEmits<{ select: [label: string] }>();

const ranked = computed(() => {
  const max = Math.max(...props.items.map((i) => i.value), 1);
  return [...props.items]
    .sort((a, b) => b.value - a.value)
    .map((i) => ({
      ...i,
      pct: (i.value / max) * 100,
      display: i.display ?? i.value.toLocaleString(),
      color: i.color ?? 'var(--adirra-accent)',
    }));
});
</script>

<style scoped>
.viz-card {
  background: var(--adirra-card);
  border: 1px solid var(--adirra-line);
  border-radius: 10px;
  padding: 14px 16px;
  box-shadow: var(--adirra-shadow);
}

.viz-card-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 14px;
}

.viz-card-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--adirra-ink);
}

.viz-card-caption {
  font-size: 9.5px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--adirra-ink-3);
  white-space: nowrap;
}

.rank-rows {
  display: flex;
  flex-direction: column;
  gap: 9px;
}

.rank-row {
  display: grid;
  grid-template-columns: minmax(80px, 150px) 1fr 58px;
  align-items: center;
  gap: 10px;
}

.rank-row--click { cursor: pointer; }
.rank-row--click:hover .rank-lbl { color: var(--adirra-accent); }

.rank-lbl {
  font-size: 11.5px;
  color: var(--adirra-ink-2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rank-track {
  height: 12px;
  border-radius: 6px;
  background: var(--adirra-paper-2);
  overflow: hidden;
}

.rank-fill {
  height: 100%;
  border-radius: 6px;
  animation: viz-bar-grow 0.5s cubic-bezier(0.22, 1, 0.36, 1) both;
}

.rank-val {
  font-size: 11px;
  font-weight: 700;
  color: var(--adirra-ink);
  text-align: right;
  font-variant-numeric: tabular-nums;
}

@keyframes viz-bar-grow {
  from { transform: scaleX(0); transform-origin: left; }
  to { transform: scaleX(1); transform-origin: left; }
}

.viz-empty {
  font-size: 12px;
  color: var(--adirra-ink-3);
  padding: 6px 0;
}

@media (prefers-reduced-motion: reduce) {
  .rank-fill { animation: none; }
}
</style>

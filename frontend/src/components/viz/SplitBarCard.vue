<template>
  <div class="viz-card">
    <div class="viz-card-head">
      <span class="viz-card-title">{{ title }}</span>
      <span v-if="caption" class="viz-card-caption">{{ caption }}</span>
    </div>

    <template v-if="rows.length">
      <div class="split-rows">
        <div v-for="row in rows" :key="row.label" class="split-row">
          <span class="split-lbl" :title="row.label">{{ row.label }}</span>
          <div class="split-track">
            <div
              v-for="(seg, i) in row.segments"
              :key="row.label + i"
              class="split-seg"
              :style="{ width: widthPct(seg.count, row) + '%', background: seg.color }"
            >
              <q-tooltip>{{ seg.label }}: {{ seg.count.toLocaleString() }}</q-tooltip>
            </div>
          </div>
          <span class="split-val mono">{{ rowTotal(row).toLocaleString() }}</span>
        </div>
      </div>
      <div class="viz-legend">
        <span v-for="key in legendKeys" :key="key.label" class="viz-legend-item">
          <span class="viz-legend-dot" :style="{ background: key.color }" />
          <span class="viz-legend-label">{{ key.label }}</span>
          <span class="viz-legend-count mono">{{ key.total.toLocaleString() }}</span>
        </span>
      </div>
    </template>
    <div v-else class="viz-empty">Nothing to show yet.</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

export interface SplitSegment {
  label: string;
  count: number;
  color: string;
}

export interface SplitRow {
  label: string;
  segments: SplitSegment[];
}

const props = defineProps<{
  title: string;
  caption?: string | null;
  rows: SplitRow[];
}>();

function rowTotal(row: SplitRow): number {
  return row.segments.reduce((s, seg) => s + seg.count, 0);
}

/** Each row fills its own width, so rows read as proportions not magnitudes. */
function widthPct(count: number, row: SplitRow): number {
  const total = rowTotal(row) || 1;
  return (count / total) * 100;
}

const legendKeys = computed(() => {
  const totals = new Map<string, { label: string; color: string; total: number }>();
  for (const row of props.rows) {
    for (const seg of row.segments) {
      const entry = totals.get(seg.label) ?? { label: seg.label, color: seg.color, total: 0 };
      entry.total += seg.count;
      totals.set(seg.label, entry);
    }
  }
  return [...totals.values()];
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

.split-rows {
  display: flex;
  flex-direction: column;
  gap: 9px;
}

.split-row {
  display: grid;
  grid-template-columns: minmax(80px, 118px) 1fr 40px;
  align-items: center;
  gap: 10px;
}

.split-lbl {
  font-size: 11.5px;
  color: var(--adirra-ink-2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.split-track {
  display: flex;
  height: 12px;
  border-radius: 6px;
  overflow: hidden;
  background: var(--adirra-paper-2);
}

.split-seg {
  height: 100%;
  animation: viz-bar-grow 0.5s cubic-bezier(0.22, 1, 0.36, 1) both;
}

.split-seg + .split-seg {
  box-shadow: inset 1px 0 0 #ffffff40;
}

.split-val {
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

.viz-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 14px;
  margin-top: 12px;
}

.viz-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
}

.viz-legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.viz-legend-label { color: var(--adirra-ink-2); }
.viz-legend-count { font-weight: 700; color: var(--adirra-ink); }

.viz-empty {
  font-size: 12px;
  color: var(--adirra-ink-3);
  padding: 6px 0;
}

@media (prefers-reduced-motion: reduce) {
  .split-seg { animation: none; }
}
</style>

<template>
  <div class="viz-card">
    <div class="viz-card-head">
      <span class="viz-card-title">{{ title }}</span>
      <span v-if="caption" class="viz-card-caption">{{ caption }}</span>
    </div>

    <template v-if="segments.length">
      <div class="viz-bar">
        <div
          v-for="seg in segments"
          :key="seg.label"
          class="viz-bar-seg"
          :style="{ width: seg.pct + '%', background: seg.color }"
        >
          <q-tooltip>{{ seg.label }}: {{ seg.count.toLocaleString() }} ({{ seg.pct.toFixed(1) }}%)</q-tooltip>
        </div>
      </div>
      <div class="viz-legend">
        <span v-for="seg in segments" :key="seg.label" class="viz-legend-item">
          <span class="viz-legend-dot" :style="{ background: seg.color }" />
          <span class="viz-legend-label">{{ seg.label }}</span>
          <span class="viz-legend-count mono">{{ seg.count.toLocaleString() }}</span>
          <q-tooltip v-if="hints?.[seg.label]">{{ hints[seg.label] }}</q-tooltip>
        </span>
      </div>
    </template>
    <div v-else class="viz-empty">Nothing to show yet.</div>
  </div>
</template>

<script setup lang="ts">
import type { VizSegment } from './vizTypes';

defineProps<{
  title: string;
  caption?: string | null;
  segments: VizSegment[];
  /** Optional legend tooltips, keyed by segment label. */
  hints?: Record<string, string>;
}>();
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

.viz-bar {
  display: flex;
  height: 14px;
  border-radius: 7px;
  overflow: hidden;
  background: var(--adirra-paper-2);
}

.viz-bar-seg {
  height: 100%;
  cursor: default;
  /* Grow in from zero on first paint — cheap perceived-quality lift. */
  animation: viz-bar-grow 0.5s cubic-bezier(0.22, 1, 0.36, 1) both;
}

.viz-bar-seg + .viz-bar-seg {
  box-shadow: inset 1px 0 0 #ffffff40;
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

.viz-legend-label {
  color: var(--adirra-ink-2);
}

.viz-legend-count {
  font-weight: 700;
  color: var(--adirra-ink);
}

.viz-empty {
  font-size: 12px;
  color: var(--adirra-ink-3);
  padding: 6px 0;
}

@media (prefers-reduced-motion: reduce) {
  .viz-bar-seg { animation: none; }
}
</style>

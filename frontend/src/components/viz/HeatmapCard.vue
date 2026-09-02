<template>
  <div class="viz-card">
    <div class="viz-card-head">
      <span class="viz-card-title">{{ title }}</span>
      <span v-if="caption" class="viz-card-caption">{{ caption }}</span>
    </div>

    <template v-if="rows.length">
      <div class="hm" :style="{ gridTemplateColumns: `minmax(90px, 1fr) repeat(${cols.length}, minmax(58px, 0.7fr))` }">
        <span class="hm-corner" />
        <span v-for="c in cols" :key="'h' + c.key" class="hm-col-head">{{ c.label }}</span>

        <template v-for="row in rows" :key="row.type">
          <span class="hm-row-head" :title="row.label || row.type">{{ row.label || row.type }}</span>
          <span
            v-for="c in cols" :key="row.type + c.key"
            class="hm-cell"
            :style="cellStyle(row[c.key] ?? 0, c.color)"
          >
            {{ (row[c.key] ?? 0) || '' }}
            <q-tooltip>{{ row.label || row.type }} · {{ c.label }}: {{ row[c.key] ?? 0 }}</q-tooltip>
          </span>
        </template>
      </div>
      <div class="hm-scale">
        <span class="hm-scale-lbl">Fewer</span>
        <span class="hm-scale-ramp" />
        <span class="hm-scale-lbl">More ({{ max.toLocaleString() }})</span>
      </div>
    </template>
    <div v-else class="viz-empty">No cross-tab data available.</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { GOV_SEGMENT_COLOR, GOV_SEGMENT_LABEL, GOV_SEGMENT_ORDER, type GovSegmentKey } from './vizTypes';

interface HeatmapRow {
  type: string;
  label?: string | null;
  empty?: number;
  draft?: number;
  in_review?: number;
  approved?: number;
  bounced?: number;
  [key: string]: unknown;
}

const props = defineProps<{
  title: string;
  caption?: string | null;
  rows: HeatmapRow[];
}>();

const cols = GOV_SEGMENT_ORDER.map((key) => ({
  key: key as GovSegmentKey,
  label: GOV_SEGMENT_LABEL[key],
  color: GOV_SEGMENT_COLOR[key],
}));

const max = computed(() => {
  let m = 0;
  for (const r of props.rows) {
    for (const c of cols) m = Math.max(m, (r[c.key] as number) ?? 0);
  }
  return Math.max(m, 1);
});

/** Intensity encodes count; hue stays the column's own governance colour. */
function cellStyle(count: number, color: string) {
  if (!count) return { background: 'var(--adirra-paper-2)', color: 'transparent' };
  const intensity = Math.min(1, 0.12 + (count / max.value) * 0.88);
  return {
    background: color,
    opacity: String(intensity),
    color: intensity > 0.55 ? '#fff' : 'var(--adirra-ink)',
  };
}
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

.hm {
  display: grid;
  gap: 3px;
  align-items: stretch;
}

.hm-col-head,
.hm-row-head {
  font-size: 9.5px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--adirra-ink-3);
  display: flex;
  align-items: center;
}

.hm-col-head { justify-content: center; text-align: center; }

.hm-row-head {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding-right: 6px;
}

.hm-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 30px;
  border-radius: 5px;
  font-size: 11px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  cursor: default;
}

.hm-scale {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
}

.hm-scale-lbl {
  font-size: 10px;
  color: var(--adirra-ink-3);
}

.hm-scale-ramp {
  flex: 0 0 90px;
  height: 7px;
  border-radius: 4px;
  background: linear-gradient(90deg, var(--adirra-paper-2), var(--gov-in-review-vivid));
}

.viz-empty {
  font-size: 12px;
  color: var(--adirra-ink-3);
  padding: 6px 0;
}
</style>

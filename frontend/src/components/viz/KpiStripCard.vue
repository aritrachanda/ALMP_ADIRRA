<template>
  <div class="viz-kpi-strip">
    <div v-for="kpi in kpis" :key="kpi.label" class="viz-kpi">
      <div class="viz-kpi-val" :style="kpi.color ? { color: kpi.color } : undefined">{{ kpi.value }}</div>
      <div class="viz-kpi-lbl">{{ kpi.label }}</div>
      <div v-if="kpi.meterPct != null" class="viz-kpi-meter">
        <div
          class="viz-kpi-meter-fill"
          :style="{ width: Math.max(0, Math.min(100, kpi.meterPct)) + '%', background: kpi.color || 'var(--adirra-accent)' }"
        />
      </div>
      <q-tooltip v-if="kpi.hint">{{ kpi.hint }}</q-tooltip>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { VizKpi } from './vizTypes';

defineProps<{ kpis: VizKpi[] }>();
</script>

<style scoped>
.viz-kpi-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
}

.viz-kpi {
  background: var(--adirra-card);
  border: 1px solid var(--adirra-line);
  border-radius: 10px;
  padding: 14px 16px;
  box-shadow: var(--adirra-shadow);
}

.viz-kpi-val {
  font-size: 26px;
  font-weight: 700;
  line-height: 1.1;
  color: var(--adirra-ink);
  font-variant-numeric: tabular-nums;
}

.viz-kpi-lbl {
  margin-top: 3px;
  font-size: 9.5px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--adirra-ink-3);
}

.viz-kpi-meter {
  margin-top: 8px;
  height: 4px;
  border-radius: 2px;
  background: var(--adirra-paper-2);
  overflow: hidden;
}

.viz-kpi-meter-fill {
  height: 100%;
  border-radius: 2px;
  animation: viz-meter-grow 0.6s cubic-bezier(0.22, 1, 0.36, 1) both;
}

@keyframes viz-meter-grow {
  from { transform: scaleX(0); transform-origin: left; }
  to { transform: scaleX(1); transform-origin: left; }
}

@media (prefers-reduced-motion: reduce) {
  .viz-kpi-meter-fill { animation: none; }
}
</style>

<template>
  <div class="viz-card">
    <div class="viz-card-head">
      <span class="viz-card-title">{{ title }}</span>
      <span v-if="caption" class="viz-card-caption">{{ caption }}</span>
    </div>

    <template v-if="plotted.length">
      <svg class="qmap" :viewBox="`0 0 ${W} ${H}`" preserveAspectRatio="xMidYMid meet">
        <!-- DQ grade bands as soft zones, each labelled with its score range so
             a bubble's height reads as a grade without consulting a legend. -->
        <g v-for="band in bands" :key="band.label">
          <rect
            :x="PAD_L" :width="PLOT_W"
            :y="yFor(band.max)" :height="Math.max(0, yFor(band.min) - yFor(band.max))"
            :fill="band.color" opacity="0.08"
          />
          <text
            :x="W - PAD_R + 8"
            :y="(yFor(band.max) + yFor(band.min)) / 2 + 1"
            class="qmap-band-lbl" :fill="band.color"
          >{{ band.label }}</text>
          <text
            :x="W - PAD_R + 8"
            :y="(yFor(band.max) + yFor(band.min)) / 2 + 10"
            class="qmap-band-range"
          >{{ band.min }}–{{ band.max }}</text>
        </g>

        <line :x1="PAD_L" :y1="PAD_T" :x2="PAD_L" :y2="H - PAD_B" class="qmap-axis" />
        <line :x1="PAD_L" :y1="H - PAD_B" :x2="W - PAD_R" :y2="H - PAD_B" class="qmap-axis" />

        <!-- Midline splits the plot into four priority quadrants: position now
             answers "what do I do about this dataset?", not just "how big is it". -->
        <line
          :x1="xFor(50)" :y1="PAD_T" :x2="xFor(50)" :y2="H - PAD_B"
          class="qmap-midline"
        />
        <text :x="xFor(50) - 6" :y="PAD_T + 11" text-anchor="end" class="qmap-quad">Quick wins</text>
        <text :x="xFor(50) + 6" :y="PAD_T + 11" text-anchor="start" class="qmap-quad">Healthy</text>
        <text :x="xFor(50) - 6" :y="H - PAD_B - 5" text-anchor="end" class="qmap-quad">Biggest effort</text>
        <text :x="xFor(50) + 6" :y="H - PAD_B - 5" text-anchor="start" class="qmap-quad">Fix the data</text>

        <text v-for="t in [0, 50, 100]" :key="'y' + t" :x="PAD_L - 6" :y="yFor(t) + 3" text-anchor="end" class="qmap-tick">{{ t }}</text>
        <text
          :x="10" :y="(PAD_T + H - PAD_B) / 2" class="qmap-axis-lbl"
          :transform="`rotate(-90, 10, ${(PAD_T + H - PAD_B) / 2})`" text-anchor="middle"
        >DQ score</text>

        <text
          v-for="tick in xTicks" :key="'x' + tick.value"
          :x="tick.x" :y="H - PAD_B + 12" text-anchor="middle" class="qmap-tick"
        >{{ tick.value }}%</text>
        <text :x="PAD_L + PLOT_W / 2" :y="H - 2" text-anchor="middle" class="qmap-axis-lbl">Governance progress</text>

        <g
          v-for="p in plotted" :key="p.schema + '.' + p.label"
          class="qmap-pt"
          @click="$emit('select', p)"
        >
          <circle :cx="p.cx" :cy="p.cy" :r="p.r" :fill="p.color" opacity="0.5" />
          <circle :cx="p.cx" :cy="p.cy" :r="p.r" fill="none" :stroke="p.color" stroke-width="1.3" />
          <title>{{ p.label }} — DQ {{ p.score ?? 'not scored' }}, {{ p.governancePct }}% governed, {{ p.columns }} columns, {{ p.rows.toLocaleString() }} rows</title>
        </g>
      </svg>
      <div class="qmap-hint">
        Bubble size = row count · click a bubble to open that dataset
        <template v-if="unscored"> · {{ unscored }} not yet scored</template>
      </div>
    </template>
    <div v-else class="viz-empty">No scored datasets to plot yet.</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { VizQualityPoint } from './vizTypes';

const props = defineProps<{
  title: string;
  caption?: string | null;
  points: VizQualityPoint[];
}>();

defineEmits<{ select: [point: VizQualityPoint] }>();

const W = 720;
const H = 206;
const PAD_L = 32;
const PAD_R = 76;
const PAD_T = 8;
const PAD_B = 28;
const PLOT_W = W - PAD_L - PAD_R;

const bands = [
  { label: 'Excellent', min: 90, max: 100, color: 'var(--dq-excellent)' },
  { label: 'Good', min: 75, max: 89, color: 'var(--dq-good)' },
  { label: 'Adequate', min: 60, max: 74, color: 'var(--dq-adequate)' },
  { label: 'Weak', min: 40, max: 59, color: 'var(--dq-weak)' },
  { label: 'Critical', min: 0, max: 39, color: 'var(--dq-critical)' },
];

function yFor(score: number): number {
  return PAD_T + (1 - score / 100) * (H - PAD_T - PAD_B);
}

const scored = computed(() => props.points.filter((p) => p.score != null));
const unscored = computed(() => props.points.length - scored.value.length);

/** Both axes are fixed 0–100, so the plot reads the same in every source. */
function xFor(pct: number): number {
  return PAD_L + (pct / 100) * PLOT_W;
}

const xTicks = [0, 50, 100].map((value) => ({ value, x: PAD_L + (value / 100) * PLOT_W }));

const plotted = computed(() => {
  const pts = scored.value;
  if (!pts.length) return [];
  const maxRows = Math.max(...pts.map((p) => p.rows), 1);
  return pts.map((p) => ({
    ...p,
    cx: xFor(p.governancePct),
    cy: yFor(p.score as number),
    // Area-proportional so a 10x bigger table doesn't render 10x wider.
    r: 4 + Math.sqrt(p.rows / maxRows) * 12,
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
  margin-bottom: 8px;
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

.qmap {
  width: 100%;
  height: auto;
  display: block;
}

.qmap-axis {
  stroke: var(--adirra-line);
  stroke-width: 1;
}

.qmap-tick {
  font-size: 8.5px;
  fill: var(--adirra-ink-3);
  font-variant-numeric: tabular-nums;
}

.qmap-axis-lbl {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  fill: var(--adirra-ink-3);
}

.qmap-band-lbl {
  font-size: 9px;
  font-weight: 700;
}

.qmap-band-range {
  font-size: 8px;
  fill: var(--adirra-ink-3);
  font-variant-numeric: tabular-nums;
}

.qmap-size-lbl {
  font-size: 8px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  fill: var(--adirra-ink-3);
  opacity: 0.75;
}

.qmap-midline {
  stroke: var(--adirra-line);
  stroke-width: 1;
  stroke-dasharray: 3 3;
}

.qmap-quad {
  font-size: 8px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  fill: var(--adirra-ink-3);
  opacity: 0.55;
}

.qmap-pt {
  cursor: pointer;
}

.qmap-pt:hover circle {
  opacity: 0.85;
}

.qmap-hint {
  margin-top: 6px;
  font-size: 10.5px;
  color: var(--adirra-ink-3);
}

.viz-empty {
  font-size: 12px;
  color: var(--adirra-ink-3);
  padding: 6px 0;
}
</style>

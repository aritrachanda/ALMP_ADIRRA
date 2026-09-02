<template>
  <div class="staged-loader" role="status" aria-live="polite">
    <ul class="sl-list">
      <li
        v-for="(row, i) in rows"
        :key="i"
        class="sl-row"
        :class="{ 'sl-row--done': row.done, 'sl-row--active': !row.done }"
      >
        <span class="sl-mark">
          <q-icon v-if="row.done" name="check" size="13px" />
          <span v-else class="sl-dot" />
        </span>
        <span class="sl-text">{{ row.text }}</span>
      </li>
    </ul>
    <div class="sl-bar-row">
      <div class="sl-bar">
        <span
          class="sl-bar-fill"
          :class="{ 'sl-bar-fill--real': controlled }"
          :style="controlled ? { width: `${barPercent}%` } : undefined"
        />
      </div>
      <span v-if="controlled" class="sl-bar-pct">{{ barPercent }}%</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue';

const props = withDefaults(defineProps<{
  /** Ordered, plain-language stage lines. Each is revealed then ticked off in turn. */
  stages: string[];
  /**
   * Real number of stages that have genuinely finished (0..stages.length), reported by
   * the caller from actual backend progress events. When provided, ticks are 100% honest
   * — a stage is only ever checked off once its real work has completed — and the legacy
   * simulated timer below is disabled entirely.
   */
  completed?: number;
  /** Extra live detail appended to the active stage's text, e.g. "(23/80 columns)". */
  activeDetail?: string;
  /**
   * Real fraction (0..1) of progress WITHIN the currently active stage, e.g. 23/80 columns
   * processed so far. Lets the bar move smoothly as real sub-steps complete instead of only
   * jumping at whole-stage boundaries. Omit (or 0) when no such sub-progress is available —
   * the bar then simply advances a whole stage at a time, still 100% honest either way.
   */
  activeFraction?: number;
  /** Reassurance lines cycled once the stages are exhausted but work is still ongoing.
   *  Only used in legacy (uncontrolled) mode — see `completed`. */
  holdMessages?: string[];
  /** Milliseconds each stage is shown before advancing. Legacy (uncontrolled) mode only. */
  stepMs?: number;
  /** Milliseconds each reassurance (hold) line is shown before rotating. Legacy mode only. */
  holdMs?: number;
}>(), {
  completed: undefined,
  activeDetail: '',
  activeFraction: 0,
  holdMessages: () => [
    'Almost there…',
    'Just a few more moments…',
    'We\u2019re making everything ready…',
    'Nearly done…',
  ],
  stepMs: 1400,
  holdMs: 5000,
});

const controlled = computed(() => props.completed !== undefined);

// ── Legacy simulated mode (unconverted pages) ───────────────────────────────
const activeStage = ref(0);   // index of the stage currently being worked
const inHold = ref(false);    // stages exhausted; cycling reassurance lines
const holdIndex = ref(0);
let timer: ReturnType<typeof setTimeout> | undefined;

function tick() {
  if (!inHold.value) {
    if (activeStage.value < props.stages.length - 1) {
      activeStage.value += 1;
    } else {
      inHold.value = true;
      holdIndex.value = 0;
    }
  } else {
    holdIndex.value = (holdIndex.value + 1) % props.holdMessages.length;
  }
}

// Self-scheduling so stage steps and (slower) hold lines can use different delays.
function schedule() {
  const delay = inHold.value ? props.holdMs : props.stepMs;
  timer = setTimeout(() => { tick(); schedule(); }, delay);
}

onMounted(() => { if (!controlled.value) schedule(); });
onBeforeUnmount(() => { if (timer) clearTimeout(timer); });

// ── Shared display logic ────────────────────────────────────────────────────
const doneCount = computed(() => {
  if (controlled.value) return Math.max(0, Math.min(props.completed ?? 0, props.stages.length));
  return inHold.value ? props.stages.length : activeStage.value;
});
const activeText = computed(() => {
  if (controlled.value) {
    const base = props.stages[doneCount.value] ?? props.stages[props.stages.length - 1] ?? '';
    return (props.activeDetail ? `${base} ${props.activeDetail}` : base).trim();
  }
  return inHold.value
    ? (props.holdMessages[holdIndex.value] ?? '')
    : (props.stages[activeStage.value] ?? '');
});

// Completed stages (ticked) followed by the single active line (omitted once every
// real stage is done — the caller swaps the loader out for real content at that point).
const rows = computed(() => {
  const done = props.stages
    .slice(0, doneCount.value)
    .map((text) => ({ text, done: true }));
  if (controlled.value && doneCount.value >= props.stages.length) return done;
  return [...done, { text: activeText.value, done: false }];
});

// Real, non-fabricated percentage: whole stages done + how far through the CURRENT
// stage's real sub-progress (when the caller has one to report; 0 otherwise).
const barPercent = computed(() => {
  const total = Math.max(props.stages.length, 1);
  const stageFraction = Math.max(0, Math.min(props.activeFraction ?? 0, 1));
  const fraction = Math.min((doneCount.value + stageFraction) / total, 1);
  return Math.round(fraction * 100);
});
</script>

<style scoped>
.staged-loader {
  display: flex;
  flex-direction: column;
  gap: 16px;
  width: 100%;
  max-width: 340px;
}

.sl-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 9px;
}

.sl-row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  line-height: 1.3;
  animation: sl-row-in 0.28s ease both;
}
.sl-row--done { color: var(--adirra-ink-3); }
.sl-row--active { color: var(--adirra-ink); font-weight: 600; }

.sl-mark {
  width: 18px;
  height: 18px;
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
}
.sl-row--done .sl-mark {
  color: var(--adirra-accent);
  background: var(--adirra-accent-soft);
}

.sl-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--adirra-accent);
  animation: sl-pulse 1s ease-in-out infinite;
}

.sl-bar-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.sl-bar-pct {
  flex: none;
  font-size: 11px;
  font-weight: 600;
  color: var(--adirra-ink-3);
  font-variant-numeric: tabular-nums;
  min-width: 2.4em;
  text-align: right;
}

.sl-bar {
  position: relative;
  height: 4px;
  border-radius: 4px;
  background: var(--adirra-line);
  overflow: hidden;
  flex: 1;
}
.sl-bar-fill {
  position: absolute;
  inset: 0;
  border-radius: 4px;
  background: linear-gradient(
    90deg,
    var(--adirra-accent),
    var(--dq-profile),
    var(--adirra-reviewed),
    var(--adirra-released),
    var(--adirra-accent)
  );
  background-size: 200% 100%;
  animation: sl-sweep 1.4s linear infinite;
}

/* Real mode: width reflects genuine completion, so the sweep would misrepresent
   progress as further along/behind than reality — a plain filled bar instead. */
.sl-bar-fill--real {
  background: var(--adirra-accent);
  background-size: auto;
  animation: none;
  transition: width 0.35s ease;
}

@keyframes sl-sweep {
  from { background-position: 0% 0; }
  to { background-position: -200% 0; }
}
@keyframes sl-pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(0.55); opacity: 0.5; }
}
@keyframes sl-row-in {
  from { opacity: 0; transform: translateY(3px); }
  to { opacity: 1; transform: translateY(0); }
}

@media (prefers-reduced-motion: reduce) {
  .sl-bar-fill,
  .sl-dot,
  .sl-row { animation: none; }
}
</style>

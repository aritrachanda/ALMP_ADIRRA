<template>
  <q-page class="dash">
    <div class="dash-head">
      <div class="dash-title-row">
        <div>
          <h1 class="dash-title">Dashboard</h1>
          <div class="dash-sub">{{ activePreset.question }} · {{ store.scopeLabel }}</div>
        </div>
        <div class="dash-refresh-wrap">
          <button class="dash-refresh" :disabled="store.loading" @click="store.load(true)">
            <q-icon name="refresh" size="14px" class="q-mr-xs" />Refresh
          </button>
          <span v-if="lastUpdatedLabel" class="dash-updated">Updated {{ lastUpdatedLabel }}</span>
        </div>
      </div>

      <div class="dash-controls">
        <div class="dash-seg" role="tablist" aria-label="Dashboard preset">
          <button
            v-for="p in presets" :key="p.id"
            class="dash-seg-btn" :class="{ 'dash-seg-btn--active': p.id === presetId }"
            role="tab" :aria-selected="p.id === presetId"
            @click="selectPreset(p.id)"
          >{{ p.label }}</button>
        </div>

        <div class="dash-scope">
          <span class="dash-scope-lbl">Scope</span>
          <select class="dash-scope-select" :value="scopeValue" @change="onScopeChange">
            <option value="__all__">All sources</option>
            <option v-for="s in store.sources" :key="s" :value="s">{{ s }}</option>
          </select>
        </div>
      </div>
    </div>

    <div v-if="store.loading" class="dash-loading">
      <StagedLoader
        :stages="loadStages"
        :completed="loadCompleted"
        :active-detail="loadDetail"
        class="q-mx-auto"
      />
    </div>

    <div v-else-if="store.error" class="dash-error">
      <q-icon name="error_outline" size="18px" class="q-mr-sm" />{{ store.error }}
    </div>

    <div v-else class="dash-grid">
      <template v-for="card in activePreset.cards" :key="card">
        <KpiStripCard v-if="card === 'kpis'" :kpis="kpis" class="dash-full" />

        <ProportionalBarCard
          v-else-if="card === 'governance-pipeline'"
          title="Governance Pipeline"
          :caption="`${totalElements.toLocaleString()} ELEMENTS`"
          :segments="governanceSegments"
          :hints="GOV_LEGEND_HINTS"
        />

        <ProportionalBarCard
          v-else-if="card === 'semantic-resolution'"
          title="Semantic Resolution"
          caption="BLOCKS SUBMISSION UNTIL ACCEPTED"
          :segments="semanticResolutionSegments"
          :hints="SEM_STATE_HINTS"
        />

        <ProportionalBarCard
          v-else-if="card === 'dq-distribution'"
          title="Dataset DQ Grades"
          :caption="`${scopedDatasets.length} DATASETS`"
          :segments="dqDistributionSegments"
        />

        <ProportionalBarCard
          v-else-if="card === 'mapping-confidence'"
          title="Mapping Confidence"
          caption="MAPPED COLUMNS"
          :segments="mappingConfidenceSegments"
        />

        <ProportionalBarCard
          v-else-if="card === 'glossary-status'"
          title="Glossary Terms by Status"
          :caption="`${store.legacy?.glossary.terms ?? 0} TERMS`"
          :segments="glossaryStatusSegments"
        />

        <RankedBarCard
          v-else-if="card === 'source-league'"
          title="Sources by size"
          caption="DATA ELEMENTS"
          :items="sourceLeagueItems"
          clickable
          @select="scopeToSource"
        />

        <RankedBarCard
          v-else-if="card === 'governance-by-source'"
          title="Governance progress by source"
          caption="% PAST DRAFT"
          :items="governanceBySourceItems"
          clickable
          @select="scopeToSource"
        />

        <RankedBarCard
          v-else-if="card === 'avg-dq-by-source'"
          title="Average DQ by source"
          caption="0–100"
          :items="avgDqBySourceItems"
          clickable
          @select="scopeToSource"
        />

        <RankedBarCard
          v-else-if="card === 'ai-by-source'"
          title="AI-written data stories by source"
          caption="DATASETS"
          :items="aiBySourceItems"
          clickable
          @select="scopeToSource"
        />

        <RankedBarCard
          v-else-if="card === 'mapping-coverage'"
          title="Mapping coverage by source table"
          caption="MAPPED COLUMNS"
          :items="mappingCoverageItems"
          class="dash-full"
        />

        <SplitBarCard
          v-else-if="card === 'ai-assistance'"
          title="AI Assistance"
          caption="WHO AUTHORED IT"
          :rows="aiAssistanceRows"
          class="dash-full"
        />

        <HeatmapCard
          v-else-if="card === 'semantic-heatmap'"
          title="Semantic type × Governance state"
          :caption="`${totalElements.toLocaleString()} ELEMENTS`"
          :rows="heatmapRows"
          class="dash-full"
        />

        <QualityMapCard
          v-else-if="card === 'quality-map'"
          title="Dataset Quality Map"
          :caption="`${scopedDatasets.length} DATASETS`"
          :points="qualityPoints"
          class="dash-full"
          @select="openDataset"
        />
      </template>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import StagedLoader from 'src/components/StagedLoader.vue';
import KpiStripCard from 'src/components/viz/KpiStripCard.vue';
import ProportionalBarCard from 'src/components/viz/ProportionalBarCard.vue';
import RankedBarCard, { type RankedItem } from 'src/components/viz/RankedBarCard.vue';
import SplitBarCard from 'src/components/viz/SplitBarCard.vue';
import HeatmapCard from 'src/components/viz/HeatmapCard.vue';
import QualityMapCard from 'src/components/viz/QualityMapCard.vue';
import {
  govSegments,
  dqIntentColor,
  GOV_SEGMENT_HINT,
  GOV_SEGMENT_LABEL,
  type VizSegment,
  type VizKpi,
  type VizQualityPoint,
} from 'src/components/viz/vizTypes';
import { useDashboardStore } from 'src/stores/dashboardStore';
import { DASHBOARD_PRESETS, DEFAULT_PRESET_ID, presetById } from './dashboardPresets';
import { getPreference, setPreference } from 'src/utils/preferences';

const router = useRouter();
const store = useDashboardStore();
const presets = DASHBOARD_PRESETS;

const presetId = ref(getPreference('dashboard.preset', DEFAULT_PRESET_ID));
const activePreset = computed(() => presetById(presetId.value));

function selectPreset(id: string) {
  presetId.value = id;
  setPreference('dashboard.preset', id);
}

const scopeValue = computed(() => (store.scope.kind === 'source' ? store.scope.source : '__all__'));

function onScopeChange(evt: Event) {
  const value = (evt.target as HTMLSelectElement).value;
  const next = value === '__all__' ? { kind: 'all' as const } : { kind: 'source' as const, source: value };
  store.setScope(next);
  setPreference('dashboard.scope', value);
}

function scopeToSource(source: string) {
  store.setScope({ kind: 'source', source });
  setPreference('dashboard.scope', source);
}

function openDataset(point: VizQualityPoint) {
  const source = datasetSource.value[`${point.schema}.${point.label}`];
  if (!source) return;
  void router.push({
    path: '/workspace',
    query: { source, schema: point.schema, table: point.label },
  });
}

// ── Loading progress ──────────────────────────────────────────────────────
// Real, not simulated: the store reports how many sources have actually
// finished loading (tech-debt #22 — this loader no longer fakes its ticks).
const loadStages = ['Finding your sources…', 'Reading each source…', 'Building the dashboard…'];
const loadCompleted = computed(() => {
  if (!store.sources.length) return 0;
  return store.loadedCount >= store.sources.length ? 2 : 1;
});
const loadDetail = computed(() => {
  if (!store.sources.length) return '';
  const total = store.sources.length;
  const count = store.loadedCount;
  // Once every source is in, drop the name(s) entirely rather than listing all of
  // them — that list only grows as more sources are onboarded and would eventually
  // overflow. While still in progress, name only the source that JUST finished.
  if (count >= total) return `(${count}/${total} sources)`;
  const latest = store.loadedSourceNames[store.loadedSourceNames.length - 1];
  return latest ? `(${count}/${total} sources — ${latest})` : `(${count}/${total} sources)`;
});

const lastUpdatedLabel = computed(() => {
  const d = store.lastUpdatedAt;
  return d ? d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' }) : '';
});

const GOV_LEGEND_HINTS: Record<string, string> = Object.fromEntries(
  Object.entries(GOV_SEGMENT_HINT).map(([key, hint]) => [GOV_SEGMENT_LABEL[key as keyof typeof GOV_SEGMENT_LABEL], hint]),
);

const SEM_STATE_HINTS: Record<string, string> = {
  Accepted: 'An analyst has accepted the semantic type — submission is unblocked',
  Pending: 'A type was deduced but nobody has accepted it yet — still blocks submission',
  Unresolved: 'No semantic type could be deduced — blocks submission',
};

// ── Aggregates over the current scope ─────────────────────────────────────

const totalElements = computed(() => store.scoped.reduce((s, i) => s + (i.column_count ?? 0), 0));

const governanceCounts = computed(() => {
  const acc = { empty: 0, draft: 0, in_review: 0, approved: 0, bounced: 0 };
  for (const info of store.scoped) {
    const g = info.governance_state ?? {};
    acc.empty += g.empty ?? 0;
    acc.draft += g.draft ?? 0;
    acc.in_review += g.in_review ?? 0;
    acc.approved += g.approved ?? 0;
    acc.bounced += g.bounced ?? 0;
  }
  return acc;
});

const governanceSegments = computed<VizSegment[]>(() => govSegments(governanceCounts.value));

const scopedDatasets = computed(() =>
  store.scoped.flatMap((info) => info.datasets.map((d) => ({ ...d, source: info.source }))),
);

/** Dataset name -> owning source, so a bubble click can deep-link correctly. */
const datasetSource = computed(() => {
  const map: Record<string, string> = {};
  for (const d of scopedDatasets.value) map[`${d.schema}.${d.table_name}`] = d.source;
  return map;
});

const avgDq = computed<number | null>(() => {
  const scores = scopedDatasets.value
    .map((d) => d.dataset_dq?.dq_score)
    .filter((s): s is number => typeof s === 'number');
  if (!scores.length) return null;
  return Math.round(scores.reduce((a, b) => a + b, 0) / scores.length);
});

function pctOf(part: number, total: number): number {
  return total ? Math.round((part / total) * 100) : 0;
}

/**
 * Progress and Approved are shown as SEPARATE metrics here (unlike the single
 * combined figure at dataset/source level) so "we've started" is never mistaken
 * for "we're done".
 */
const kpis = computed<VizKpi[]>(() => {
  const g = governanceCounts.value;
  const total = totalElements.value;
  const progress = pctOf(g.in_review + g.approved + g.bounced, total);
  const approved = pctOf(g.approved, total);
  const dq = avgDq.value;
  const dqColor = dq == null ? undefined
    : dq >= 90 ? 'var(--dq-excellent)' : dq >= 75 ? 'var(--dq-good)'
    : dq >= 60 ? 'var(--dq-adequate)' : dq >= 40 ? 'var(--dq-weak)' : 'var(--dq-critical)';
  const band = (p: number) => (p >= 60 ? 'var(--dq-excellent)' : p >= 25 ? 'var(--dq-adequate)' : 'var(--dq-critical)');
  return [
    { label: 'Sources', value: store.scoped.length },
    { label: 'Datasets', value: scopedDatasets.value.length.toLocaleString() },
    { label: 'Data Elements', value: total.toLocaleString() },
    {
      label: 'Governance Progress',
      value: `${progress}%`,
      meterPct: progress,
      color: band(progress),
      hint: 'What % of elements have moved past Draft',
    },
    {
      label: 'Approved',
      value: `${approved}%`,
      meterPct: approved,
      color: band(approved),
      hint: 'What % of elements a steward has actually approved',
    },
    {
      label: 'Avg DQ Score',
      value: dq == null ? '—' : dq,
      meterPct: dq,
      color: dqColor,
      hint: dq == null ? 'No datasets scored yet' : 'Average quality score across the datasets that have been scored',
    },
  ];
});

const semanticResolutionSegments = computed<VizSegment[]>(() => {
  const acc = { accepted: 0, pending: 0, unresolved: 0 };
  for (const info of store.scoped) {
    const s = info.semantic_state;
    if (!s) continue;
    acc.accepted += s.accepted;
    acc.pending += s.pending;
    acc.unresolved += s.unresolved;
  }
  const total = acc.accepted + acc.pending + acc.unresolved;
  if (!total) return [];
  const colors: Record<string, string> = {
    accepted: 'var(--gov-approved-vivid)',
    pending: 'var(--gov-draft-vivid)',
    unresolved: 'var(--gov-empty-vivid)',
  };
  return (['accepted', 'pending', 'unresolved'] as const)
    .filter((k) => acc[k] > 0)
    .map((k) => ({
      label: k.charAt(0).toUpperCase() + k.slice(1),
      count: acc[k],
      pct: (100 * acc[k]) / total,
      color: colors[k],
    }));
});

const dqDistributionSegments = computed<VizSegment[]>(() => {
  const counts = new Map<string, { count: number; intent: string }>();
  for (const d of scopedDatasets.value) {
    const label = d.dataset_dq?.grade_label;
    if (!label) continue;
    const entry = counts.get(label) ?? { count: 0, intent: d.dataset_dq?.grade_color_intent ?? '' };
    entry.count += 1;
    counts.set(label, entry);
  }
  const total = [...counts.values()].reduce((s, c) => s + c.count, 0);
  if (!total) return [];
  const order = ['Excellent', 'Good', 'Adequate', 'Weak', 'Critical'];
  return order
    .filter((g) => counts.has(g))
    .map((g) => ({
      label: g,
      count: counts.get(g)!.count,
      pct: (100 * counts.get(g)!.count) / total,
      color: dqIntentColor(counts.get(g)!.intent),
    }));
});

const heatmapRows = computed(() => {
  const byType = new Map<string, Record<string, number | string>>();
  for (const info of store.scoped) {
    for (const row of info.semantic_governance_matrix ?? []) {
      const existing = byType.get(row.type) ?? {
        type: row.type, label: row.label ?? row.type, color: row.color,
        empty: 0, draft: 0, in_review: 0, approved: 0, bounced: 0,
      };
      for (const k of ['empty', 'draft', 'in_review', 'approved', 'bounced'] as const) {
        existing[k] = (existing[k] as number) + (row[k] ?? 0);
      }
      byType.set(row.type, existing);
    }
  }
  return [...byType.values()] as never[];
});

const qualityPoints = computed<VizQualityPoint[]>(() =>
  scopedDatasets.value.map((d) => {
    const g = d.governance ?? {};
    const govTotal = Object.values(g).reduce((a, b) => a + b, 0);
    const govMoved = (g.in_review ?? 0) + (g.approved ?? 0) + (g.bounced ?? 0);
    return {
      label: d.table_name,
      schema: d.schema,
      governancePct: govTotal ? Math.round((govMoved / govTotal) * 100) : 0,
      score: d.dataset_dq?.dq_score ?? null,
      rows: d.row_count ?? 0,
      columns: d.column_count ?? 0,
      color: dqIntentColor(d.dataset_dq?.grade_color_intent),
    };
  }),
);

const aiAssistanceRows = computed(() => {
  let ai = 0; let manual = 0; let absent = 0;
  for (const d of scopedDatasets.value) {
    if (!d.has_story) absent += 1;
    else if (d.story_is_ai) ai += 1;
    else manual += 1;
  }
  const rows = [{
    label: 'Data stories',
    segments: [
      { label: 'AI-generated', count: ai, color: '#8b5cf6' },
      { label: 'Hand-written', count: manual, color: 'var(--gov-in-review-vivid)' },
      { label: 'Not yet written', count: absent, color: 'var(--adirra-paper-2)' },
    ],
  }];
  const gl = store.legacy?.glossary;
  if (gl?.terms) {
    rows.push({
      label: 'Glossary terms',
      segments: [
        { label: 'AI-generated', count: gl.ai_terms, color: '#8b5cf6' },
        { label: 'Hand-written', count: Math.max(0, gl.terms - gl.ai_terms), color: 'var(--gov-in-review-vivid)' },
        { label: 'Not yet written', count: 0, color: 'var(--adirra-paper-2)' },
      ],
    });
  }
  return rows;
});

// ── Per-source league tables ──────────────────────────────────────────────

const sourceLeagueItems = computed<RankedItem[]>(() =>
  store.scoped.map((i) => ({ label: i.source, value: i.column_count ?? 0 })),
);

const governanceBySourceItems = computed<RankedItem[]>(() =>
  store.scoped.map((i) => {
    const g = i.governance_state ?? {};
    const total = (g.empty ?? 0) + (g.draft ?? 0) + (g.in_review ?? 0) + (g.approved ?? 0) + (g.bounced ?? 0);
    const moved = (g.in_review ?? 0) + (g.approved ?? 0) + (g.bounced ?? 0);
    const pct = pctOf(moved, total);
    return { label: i.source, value: pct, display: `${pct}%`, color: 'var(--gov-in-review-vivid)' };
  }),
);

const avgDqBySourceItems = computed<RankedItem[]>(() =>
  store.scoped.flatMap((i) => {
    const scores = i.datasets
      .map((d) => d.dataset_dq?.dq_score)
      .filter((s): s is number => typeof s === 'number');
    if (!scores.length) return [];
    const avg = Math.round(scores.reduce((a, b) => a + b, 0) / scores.length);
    const color = avg >= 90 ? 'var(--dq-excellent)' : avg >= 75 ? 'var(--dq-good)'
      : avg >= 60 ? 'var(--dq-adequate)' : avg >= 40 ? 'var(--dq-weak)' : 'var(--dq-critical)';
    return [{ label: i.source, value: avg, display: String(avg), color }];
  }),
);

const aiBySourceItems = computed<RankedItem[]>(() =>
  store.scoped.map((i) => ({
    label: i.source,
    value: i.datasets.filter((d) => d.story_is_ai).length,
    color: '#8b5cf6',
  })),
);

// ── Mapping / glossary (from the original dashboard endpoint) ─────────────

const mappingCoverageItems = computed<RankedItem[]>(() =>
  (store.legacy?.mappings.by_source_table ?? []).map((t) => ({
    label: t.source_table,
    value: t.mapped,
    display: `${t.mapped}/${t.mapped + t.unmapped}`,
    color: 'var(--gov-approved-vivid)',
  })),
);

const mappingConfidenceSegments = computed<VizSegment[]>(() => {
  const bands = store.legacy?.mappings.confidence_bands ?? [];
  const total = bands.reduce((s, b) => s + b.columns, 0);
  if (!total) return [];
  const colors = ['var(--dq-excellent)', 'var(--dq-good)', 'var(--dq-adequate)', 'var(--dq-critical)'];
  return bands
    .filter((b) => b.columns > 0)
    .map((b, i) => ({
      label: b.band,
      count: b.columns,
      pct: (100 * b.columns) / total,
      color: colors[i] ?? 'var(--adirra-ink-3)',
    }));
});

const glossaryStatusSegments = computed<VizSegment[]>(() => {
  const rows = store.legacy?.glossary.by_status ?? [];
  const total = rows.reduce((s, r) => s + r.count, 0);
  if (!total) return [];
  const colors: Record<string, string> = {
    approved: 'var(--gov-approved-vivid)',
    draft: 'var(--gov-draft-vivid)',
    in_review: 'var(--gov-in-review-vivid)',
    retired: 'var(--gov-empty-vivid)',
  };
  return rows.map((r) => ({
    label: r.status.charAt(0).toUpperCase() + r.status.slice(1).replace('_', ' '),
    count: r.count,
    pct: (100 * r.count) / total,
    color: colors[r.status] ?? 'var(--adirra-ink-3)',
  }));
});

onMounted(async () => {
  await store.load();
  const saved = getPreference<string>('dashboard.scope', '__all__');
  if (saved !== '__all__' && store.sources.includes(saved)) {
    store.setScope({ kind: 'source', source: saved });
  }
});
</script>

<style scoped>
.dash {
  /* Content-flow page: scrolled by the shared `.page-content-wrapper`
     ancestor (app.scss), which is a column flex container. QPage sets its own
     inline min-height equal to the viewport, so a shrinkable flex item gets
     squashed to exactly that floor and the overflow is clipped rather than
     scrolled. flex-shrink: 0 lets the page keep its real content height. */
  flex-shrink: 0;
  padding: 20px 24px 48px;
  background: var(--adirra-paper);
  box-sizing: border-box;
}

.dash-head {
  margin-bottom: 18px;
}

.dash-title-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.dash-title {
  font-family: 'IBM Plex Serif', serif;
  font-size: 26px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--adirra-ink);
  margin: 0;
}

.dash-sub {
  font-size: 12.5px;
  color: var(--adirra-ink-2);
  margin-top: 3px;
}

.dash-refresh-wrap {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  flex: none;
}

.dash-refresh {
  display: inline-flex;
  align-items: center;
  border: 1px solid var(--adirra-line);
  background: var(--adirra-card);
  color: var(--adirra-ink-2);
  border-radius: 7px;
  padding: 5px 11px;
  font: inherit;
  font-size: 11.5px;
  cursor: pointer;
}

.dash-refresh:hover:not(:disabled) {
  border-color: var(--adirra-accent);
  color: var(--adirra-accent);
}

.dash-refresh:disabled {
  opacity: 0.5;
  cursor: default;
}

.dash-updated {
  font-size: 10.5px;
  color: var(--adirra-ink-3);
  white-space: nowrap;
}

.dash-controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 14px;
}

.dash-seg {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.dash-seg-btn {
  font-size: 12.5px;
  padding: 7px 14px;
  border: 1px solid rgba(13, 92, 84, 0.14);
  border-radius: 9px;
  background: linear-gradient(180deg, rgba(13, 92, 84, 0.09), rgba(13, 92, 84, 0.035));
  color: var(--adirra-ink);
  cursor: pointer;
  font-weight: 600;
  transition: color .15s, background .15s, border-color .15s, box-shadow .15s;
}

.dash-seg-btn:hover {
  border-color: var(--adirra-ink);
}

.dash-seg-btn--active {
  color: #fdfffe;
  background: linear-gradient(160deg, #16887c 0%, var(--adirra-accent) 55%, #0a4a43 100%);
  border-color: #0a4a43;
  font-weight: 700;
  box-shadow: 0 3px 10px -2px rgba(13, 92, 84, 0.45), inset 0 1px 0 rgba(255, 255, 255, 0.28);
}

.dash-seg-btn--active:hover {
  color: #fdfffe;
  border-color: #0a4a43;
}

.dash-scope {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}

.dash-scope-lbl {
  font-size: 9.5px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--adirra-ink-3);
}

.dash-scope-select {
  font: inherit;
  font-size: 12px;
  color: var(--adirra-ink);
  background: var(--adirra-card);
  border: 1px solid var(--adirra-line);
  border-radius: 7px;
  padding: 5px 9px;
  cursor: pointer;
}

.dash-loading {
  padding: 48px 0;
  text-align: center;
}

/* The shared loader's "real progress" mode deliberately renders a plain flat-accent
   bar (see StagedLoader.vue) so a genuine, width-accurate fill is never confused with
   the decorative animated sweep used elsewhere in the app. Overridden here, for this
   page only, to the same multi-colour palette as the rest of the app for visual
   consistency — kept STATIC (no sweep animation) so the bar still never implies more
   or less progress than what loadedCount actually reports. */
.dash-loading :deep(.sl-bar-fill--real) {
  background: linear-gradient(90deg, var(--adirra-accent), var(--dq-profile), var(--adirra-reviewed), var(--adirra-released));
  background-size: 100% 100%;
}

.dash-error {
  display: flex;
  align-items: center;
  padding: 12px 14px;
  border-radius: 9px;
  background: var(--adirra-danger-soft);
  color: var(--adirra-danger);
  font-size: 13px;
}

.dash-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  align-items: start;
}

.dash-full {
  grid-column: 1 / -1;
}

@media (max-width: 900px) {
  .dash-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>

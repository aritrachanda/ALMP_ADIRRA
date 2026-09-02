<template>
  <q-page class="mw">
    <!-- ── Page header ─────────────────────────────────────────────────── -->
    <div class="mw-head">
      <div class="mw-eyebrow">Workspace</div>
      <h1 class="mw-title">Mapping Workspace</h1>
      <p class="mw-sub">
        Align source data elements to a target data model. Every proposed mapping carries a
        confidence score and a rationale, so it can be reviewed rather than accepted blindly.
      </p>
    </div>

    <!-- ── Run controls ────────────────────────────────────────────────── -->
    <div class="panel-card q-mb-md">
      <div class="block-bar">
        <span class="block-bar-title">Mapping run</span>
        <span class="block-bar-actions">
          <button
            class="mw-btn mw-btn--primary"
            :disabled="runDisabled"
            @click="onRun"
          >
            <q-spinner v-if="isRunning" size="13px" class="q-mr-xs" />
            <q-icon v-else name="play_arrow" size="15px" class="q-mr-xs" />
            Run Mapping
          </button>
          <button v-if="isRunning" class="mw-btn mw-btn--danger" @click="mappingStore.cancelStream()">
            <q-icon name="stop_circle" size="14px" class="q-mr-xs" />Stop
          </button>
        </span>
      </div>

      <div class="mw-controls">
        <q-select
          v-model="selectedSource"
          :options="sourceOptions"
          label="Source dataset"
          outlined dense options-dense
          class="mw-field"
          @update:model-value="onSourceChange"
        />
        <q-icon name="east" size="17px" class="mw-arrow" />
        <q-select
          v-model="selectedTarget"
          :options="targetOptions"
          label="Target model"
          outlined dense options-dense
          class="mw-field"
          @update:model-value="onTargetChange"
        />
        <q-select
          v-model="agentChoice"
          :options="['generic', 'bird']"
          label="Agent"
          outlined dense options-dense
          class="mw-field mw-field--narrow"
        />
      </div>

      <!-- Target table scope -->
      <div v-if="selectedTarget" class="mw-scope">
        <button class="mw-collapse" @click="scopeOpen = !scopeOpen">
          <q-icon :name="scopeOpen ? 'expand_more' : 'chevron_right'" size="15px" />
          Target tables
          <span class="mw-scope-count">
            {{ selectedTables.length ? `${selectedTables.length} selected` : `all ${targetTables.length}` }}
          </span>
        </button>
        <div v-if="scopeOpen" class="mw-scope-body">
          <q-checkbox
            v-for="t in targetTables"
            :key="t"
            v-model="selectedTables"
            :val="t"
            :label="t"
            dense
            size="xs"
            class="mw-check"
          />
        </div>
      </div>
    </div>

    <!-- ── Live progress ───────────────────────────────────────────────── -->
    <div v-if="isRunning" class="panel-card q-mb-md">
      <div class="block-bar">
        <span class="block-bar-title">Progress</span>
        <span class="block-bar-actions">
          <span class="mw-pct mono">{{ progressPercentLabel }}</span>
          <span class="mw-chip mw-chip--running">Running</span>
        </span>
      </div>
      <div class="mw-body">
        <div class="mw-prog-meta">
          <span class="mw-prog-status">
            <q-spinner-hourglass size="15px" class="q-mr-xs" />{{ progressStatusText }}
          </span>
          <span class="mw-prog-stat">ETA <strong class="mono">{{ etaLabel }}</strong></span>
          <span class="mw-prog-stat">Elapsed <strong class="mono">{{ elapsedLabel }}</strong></span>
        </div>
        <div class="mw-bar">
          <div class="mw-bar-fill" :style="{ width: `${progress * 100}%` }" />
        </div>
        <div class="mw-prog-note">
          {{ completedTables }} of {{ totalTables }} target tables processed<template v-if="currentTargetTable"> · current: <span class="mono">{{ currentTargetTable }}</span></template>
        </div>
        <div class="mw-log">
          <div
            v-for="(entry, i) in streamLogEntries"
            :key="i"
            class="mw-log-row"
            :class="{ 'mw-log-row--err': entry.isError }"
          >
            <span class="mw-log-icon">{{ entry.icon }}</span><span>{{ entry.text }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Finished run log ────────────────────────────────────────────── -->
    <div v-else-if="streamLogEntries.length" class="panel-card q-mb-md">
      <div class="block-bar">
        <span class="block-bar-left">
          <button class="mw-collapse mw-collapse--bare" @click="logOpen = !logOpen">
            <q-icon :name="logOpen ? 'expand_more' : 'chevron_right'" size="15px" />
            Run log
            <span class="mw-scope-count">{{ streamLogEntries.length }} events</span>
          </button>
        </span>
        <span class="mw-chip" :class="`mw-chip--${mappingStore.streamStatus}`">{{ runStatusLabel }}</span>
      </div>
      <div v-if="logOpen" class="mw-body">
        <div class="mw-log">
          <div
            v-for="(entry, i) in streamLogEntries"
            :key="i"
            class="mw-log-row"
            :class="{ 'mw-log-row--err': entry.isError }"
          >
            <span class="mw-log-icon">{{ entry.icon }}</span><span>{{ entry.text }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Results ─────────────────────────────────────────────────────── -->
    <div v-if="mappingStore.activeMapping" class="panel-card">
      <div class="block-bar">
        <span class="block-bar-title">Results</span>
        <span class="block-bar-time">
          Generated {{ mappingStore.activeMapping.generated_at ?? '—' }} · model
          <span class="mono">{{ mappingStore.activeMapping.model ?? '—' }}</span>
        </span>
      </div>

      <div class="mw-body">
        <!-- Filters -->
        <div class="mw-filters">
          <q-select v-model="filterSrc" :options="['All', ...allSrcTables]" label="Source table" outlined dense options-dense class="mw-field" />
          <q-select v-model="filterTgt" :options="['All', ...allTgtTables]" label="Target table" outlined dense options-dense class="mw-field" />
          <q-select v-model="filterConf" :options="confLevels" label="Confidence" outlined dense options-dense class="mw-field" />
          <q-input v-model="tableSearch" label="Search" outlined dense clearable class="mw-field" />
        </div>

        <div class="mw-legend">
          <strong>{{ vizMappedCount }}</strong> column mappings
          <span class="mw-legend-sep">·</span>
          <span class="mw-dot mw-dot--high" />high ≥0.7
          <span class="mw-dot mw-dot--med" />medium 0.4–0.69
          <span class="mw-dot mw-dot--low" />low &lt;0.4
        </div>

        <!-- Tabs -->
        <div class="mw-tabs">
          <button
            v-for="t in resultTabs"
            :key="t.key"
            class="tab-btn"
            :class="{ 'tab-btn--active': tab === t.key }"
            @click="tab = t.key"
          >{{ t.label }}</button>
        </div>

        <!-- Visualization -->
        <div v-show="tab === 'visualization'" class="mw-panel">
          <MappingGraph :mapping="filteredMapping" />
        </div>

        <!-- Table -->
        <div v-show="tab === 'table'" class="mw-panel">
          <q-table
            v-if="filteredTableRows.length"
            :rows="filteredTableRows"
            :columns="tableColumns"
            row-key="id"
            flat dense
            :pagination="{ rowsPerPage: 50 }"
            class="mw-table"
          >
            <template #body-cell-confidence="cellProps">
              <q-td :props="cellProps" class="text-right">
                <span class="mw-conf" :class="`mw-conf--${confBucket(cellProps.row.confidence)}`">
                  {{ ((cellProps.row.confidence ?? 0) * 100).toFixed(0) }}%
                </span>
              </q-td>
            </template>
            <template #body-cell-status="cellProps">
              <q-td :props="cellProps">
                <StatusPill :status="cellProps.row.status ?? 'pending'" compact />
              </q-td>
            </template>
          </q-table>
          <div v-else class="mw-empty-inline">No mapping results match these filters.</div>

          <div v-if="sqlPreview" class="mw-sql-block">
            <button class="mw-collapse" @click="sqlOpen = !sqlOpen">
              <q-icon :name="sqlOpen ? 'expand_more' : 'chevron_right'" size="15px" />
              SQL query
            </button>
            <pre v-if="sqlOpen" class="mw-sql">{{ sqlPreview }}</pre>
          </div>
        </div>

        <!-- Raw -->
        <div v-show="tab === 'raw'" class="mw-panel">
          <div v-for="(mt, i) in filteredMapping.tables" :key="i" class="mw-raw-card">
            <div class="mw-raw-head">
              <StatusPill :status="mt.status ?? 'pending'" />
              <span class="mw-raw-name mono">{{ mt.target_schema }}.{{ mt.target_table }}</span>
              <span v-if="mt.target_framework" class="mw-chip mw-chip--info">{{ mt.target_framework }}</span>
              <span
                v-if="mt.table_confidence != null"
                class="mw-conf"
                :class="`mw-conf--${confBucket(mt.table_confidence)}`"
              >{{ (mt.table_confidence * 100).toFixed(0) }}%</span>
              <q-space />
              <button class="mw-btn mw-btn--ok" @click="onBulkStatus(mt, 'accepted')">Accept all</button>
              <button class="mw-btn mw-btn--danger" @click="onBulkStatus(mt, 'discarded')">Discard all</button>
              <button class="mw-btn" @click="onBulkStatus(mt, 'pending')">Reset</button>
            </div>
            <div v-if="mt.table_rationale" class="mw-raw-rationale">{{ mt.table_rationale }}</div>

            <div v-if="mt.sql_query" class="mw-sql-block mw-sql-block--inset">
              <button class="mw-collapse" @click="toggleRawSql(i)">
                <q-icon :name="rawSqlOpen[i] ? 'expand_more' : 'chevron_right'" size="15px" />
                SQL query
              </button>
              <pre v-if="rawSqlOpen[i]" class="mw-sql">{{ mt.sql_query }}</pre>
            </div>

            <q-table
              v-if="mt.columns?.length"
              :rows="mt.columns"
              :columns="rawColumns"
              row-key="target_column"
              flat dense
              :pagination="{ rowsPerPage: 50 }"
              class="mw-table mw-table--inset"
            >
              <template #body-cell-confidence="cellProps">
                <q-td :props="cellProps" class="text-right">
                  <span class="mw-conf" :class="`mw-conf--${confBucket(cellProps.row.confidence)}`">
                    {{ ((cellProps.row.confidence ?? 0) * 100).toFixed(0) }}%
                  </span>
                </q-td>
              </template>
              <template #body-cell-status="cellProps">
                <q-td :props="cellProps">
                  <StatusPill :status="cellProps.row.status ?? 'pending'" compact />
                </q-td>
              </template>
              <template #body-cell-actions="cellProps">
                <q-td :props="cellProps" class="text-center">
                  <button class="mw-icon-btn mw-icon-btn--ok" title="Accept" @click="onAccept(mt, cellProps.row)">
                    <q-icon name="check" size="14px" />
                  </button>
                  <button class="mw-icon-btn mw-icon-btn--danger" title="Discard" @click="onDiscard(mt, cellProps.row)">
                    <q-icon name="close" size="14px" />
                  </button>
                </q-td>
              </template>
            </q-table>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Empty state ─────────────────────────────────────────────────── -->
    <div v-else-if="!isRunning" class="panel-card mw-empty">
      <q-icon name="alt_route" size="30px" class="mw-empty-icon" />
      <div class="mw-empty-title">No mapping results yet</div>
      <div class="mw-empty-text">
        Pick a source dataset and a target model above, then run the mapping. If a mapping already
        exists for that pair, it loads here automatically.
      </div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue';
import { useCatalogStore } from 'src/stores/catalogStore';
import { useMappingStore } from 'src/stores/mappingStore';
import type { MappingResult, MappingTable, ColumnMapping, SSEEvent } from 'src/types';
import MappingGraph from 'src/components/MappingGraph.vue';
import StatusPill from 'src/components/StatusPill.vue';

const catalogStore = useCatalogStore();
const mappingStore = useMappingStore();

const selectedSource = ref<string | null>(null);
const selectedTarget = ref<string | null>(null);
const agentChoice = ref('generic');
const selectedTables = ref<string[]>([]);
const tab = ref('visualization');
const filterSrc = ref('All');
const filterTgt = ref('All');
const filterConf = ref('All');
const tableSearch = ref('');
const confLevels = ['All', 'high (≥0.7)', 'medium (0.4–0.69)', 'low (<0.4)'];
const nowMs = ref(Date.now());
let progressTimer: number | null = null;

// Presentation-only collapse state (replaces the old q-expansion-items so the
// disclosure controls can carry the app's own styling).
const scopeOpen = ref(false);
const logOpen = ref(false);
const sqlOpen = ref(false);
const rawSqlOpen = ref<Record<number, boolean>>({});
function toggleRawSql(i: number) {
  rawSqlOpen.value = { ...rawSqlOpen.value, [i]: !rawSqlOpen.value[i] };
}

const resultTabs = [
  { key: 'visualization', label: 'Visualisation' },
  { key: 'table', label: 'Table' },
  { key: 'raw', label: 'By target table' },
];

const isRunning = computed(() => mappingStore.streamStatus === 'running');
const runDisabled = computed(() => isRunning.value || !selectedSource.value || !selectedTarget.value);

const runStatusLabel = computed(() => {
  switch (mappingStore.streamStatus) {
    case 'done': return 'Complete';
    case 'cancelled': return 'Stopped';
    case 'error': return 'Error';
    default: return '';
  }
});

const sourceOptions = computed(() => catalogStore.sources.map(s => s.name));
const targetOptions = computed(() => catalogStore.targets.map(t => t.name));
const targetTables = computed(() => {
  if (!selectedTarget.value) return [];
  const cat = catalogStore.activeCatalog;
  if (!cat) return [];
  return (cat.schemas ?? []).flatMap((s: { tables: { table_name: string }[] }) => s.tables.map(t => t.table_name));
});

// region Stream log entries
interface StreamLogEntry {
  icon: string;
  text: string;
  isError: boolean;
}

const streamLogEntries = computed((): StreamLogEntry[] => {
  const entries: StreamLogEntry[] = [];
  for (const ev of mappingStore.streamEvents) {
    const d = ev.data;
    const table = d.target_table ?? '';
    const idx = d.index ?? 0;
    const total = d.total ?? 0;

    switch (d.type) {
      case 'analyzing':
        entries.push({ icon: '⚙️', text: `Table ${idx}/${total}: ${table} — Analyzing source schema (${d.data?.target_columns ?? '?'} columns)…`, isError: false });
        break;
      case 'candidates': {
        const cands = (d.data?.candidates as string[] | undefined) ?? [];
        const candStr = cands.slice(0, 3).map(c => c.split('.').pop()).join(', ') + (cands.length > 3 ? '…' : '');
        entries.push({ icon: '⚙️', text: `${table} — Found ${d.data?.source_tables ?? '?'} candidates: ${candStr}`, isError: false });
        break;
      }
      case 'scoring':
        entries.push({ icon: '⚙️', text: `${table} — Scoring table match…`, isError: false });
        break;
      case 'columns': {
        const cols = (d.data?.columns as Array<{ source_column?: string; target_column?: string; confidence?: number; transformation_type?: string }>) ?? [];
        entries.push({ icon: '⚙️', text: `${table} — Column-level mapping (${cols.length} columns)…`, isError: false });
        for (const col of cols.slice(0, 5)) {
          const conf = col.confidence ?? 0;
          const icon = conf >= 0.8 ? '✓' : conf >= 0.5 ? '⚠️' : '❌';
          entries.push({ icon, text: `  ${col.source_column ?? '—'} → ${col.target_column ?? '?'} (${conf.toFixed(2)}, ${col.transformation_type ?? 'unmapped'})`, isError: false });
        }
        if (cols.length > 5) entries.push({ icon: '…', text: `  and ${cols.length - 5} more columns`, isError: false });
        break;
      }
      case 'validating':
        entries.push({ icon: '⚙️', text: `${table} — Validating transformations…`, isError: false });
        break;
      case 'table_done': {
        const mapped = (d.data?.mapped as number) ?? 0;
        const unmapped = (d.data?.unmapped as number) ?? 0;
        const highConf = (d.data?.high_confidence as number) ?? 0;
        const tConf = d.data?.table_confidence as number | undefined;
        const confStr = tConf != null ? ` (table confidence: ${tConf.toFixed(2)})` : '';
        entries.push({ icon: '✅', text: `${table} — ${mapped}/${(mapped as number) + (unmapped as number)} mapped, ${highConf} at >0.8${confStr}`, isError: false });
        break;
      }
      case 'error':
        entries.push({ icon: '❌', text: d.message ?? 'Unknown error', isError: true });
        break;
      case 'done':
        entries.push({ icon: '🏁', text: 'Mapping complete', isError: false });
        break;
    }
  }
  return entries;
});
// endregion

function eventTimeMs(event: SSEEvent | null | undefined): number | null {
  const timestamp = event?.data.timestamp;
  if (!timestamp) return null;
  const parsed = Date.parse(timestamp);
  return Number.isNaN(parsed) ? null : parsed;
}

function formatDuration(totalSeconds: number | null): string {
  if (totalSeconds == null || !Number.isFinite(totalSeconds) || totalSeconds < 0) return 'Estimating…';
  const rounded = Math.max(0, Math.round(totalSeconds));
  const hours = Math.floor(rounded / 3600);
  const minutes = Math.floor((rounded % 3600) / 60);
  const seconds = rounded % 60;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${seconds}s`;
  return `${seconds}s`;
}

const stageWeights: Record<string, number> = {
  analyzing: 0.12,
  candidates: 0.28,
  scoring: 0.48,
  columns: 0.76,
  validating: 0.92,
  table_done: 1,
  done: 1,
  error: 1,
};

const latestProgressEvent = computed(() => {
  const events = mappingStore.streamEvents;
  return events.length ? events[events.length - 1] : null;
});

const totalTables = computed(() => selectedTables.value.length || latestProgressEvent.value?.data.total || 1);

const completedTables = computed(() =>
  mappingStore.streamEvents.filter(e => e.data.type === 'table_done').length,
);

const currentTargetTable = computed(() => latestProgressEvent.value?.data.target_table ?? '');

const progress = computed(() => {
  const total = totalTables.value;
  if (!total) return 0;
  const latest = latestProgressEvent.value;
  if (!latest) return 0;
  if (latest.data.type === 'done') return 1;

  const currentIndex = Math.max(latest.data.index ?? completedTables.value, completedTables.value);
  const completedBeforeCurrent = Math.max(0, Math.min(completedTables.value, currentIndex - 1));
  const stageProgress = stageWeights[latest.data.type] ?? (completedTables.value > 0 ? 1 : 0);
  return Math.min((completedBeforeCurrent + stageProgress) / total, 1);
});

const progressPercentLabel = computed(() => `${Math.round(progress.value * 100)}%`);

const progressStatusText = computed(() => {
  const latest = latestProgressEvent.value;
  if (!latest) return 'Preparing mapping run…';
  if (latest.data.message) return latest.data.message;
  if (currentTargetTable.value) return `Working on ${currentTargetTable.value}`;
  return 'Processing mapping tables…';
});

const runStartedAtMs = computed(() => eventTimeMs(mappingStore.streamEvents[0] ?? null));

const elapsedSeconds = computed(() => {
  const start = runStartedAtMs.value;
  if (start == null) return null;
  return Math.max(0, (nowMs.value - start) / 1000);
});

const elapsedLabel = computed(() => formatDuration(elapsedSeconds.value));

const etaSeconds = computed(() => {
  const fraction = progress.value;
  const elapsed = elapsedSeconds.value;
  if (fraction <= 0.01 || elapsed == null || elapsed <= 0) return null;
  const totalEstimate = elapsed / fraction;
  return Math.max(0, totalEstimate - elapsed);
});

const etaLabel = computed(() => formatDuration(etaSeconds.value));

// region Table tab
const CONF_HIGH = 0.7;
const CONF_MED = 0.4;

function confBucket(c: number | null | undefined): string {
  if (c == null) return 'low';
  if (c >= CONF_HIGH) return 'high';
  if (c >= CONF_MED) return 'medium';
  return 'low';
}

const tableColumns = [
  { name: 'source_table', label: 'Source Table', field: 'source_table', align: 'left' as const, sortable: true },
  { name: 'source_column', label: 'Source Column', field: 'source_column', align: 'left' as const, sortable: true },
  { name: 'target_table', label: 'Target Table', field: 'target_table', align: 'left' as const, sortable: true },
  { name: 'target_column', label: 'Target Column', field: 'target_column', align: 'left' as const, sortable: true },
  { name: 'confidence', label: 'Confidence', field: 'confidence', align: 'right' as const, sortable: true },
  { name: 'status', label: 'Status', field: 'status', align: 'left' as const, sortable: true },
  { name: 'rationale', label: 'Rationale', field: 'rationale', align: 'left' as const },
  { name: 'transformation_type', label: 'Type', field: 'transformation_type', align: 'left' as const },
];

const rawColumns = [
  { name: 'target_column', label: 'Target Column', field: 'target_column', align: 'left' as const, sortable: true },
  { name: 'source_table', label: 'Source Table', field: 'source_table', align: 'left' as const, sortable: true },
  { name: 'source_column', label: 'Source Column', field: 'source_column', align: 'left' as const, sortable: true },
  { name: 'confidence', label: 'Confidence', field: 'confidence', align: 'right' as const, sortable: true },
  { name: 'transformation_type', label: 'Type', field: 'transformation_type', align: 'left' as const, sortable: true },
  { name: 'rationale', label: 'Rationale', field: 'rationale', align: 'left' as const },
  { name: 'status', label: 'Status', field: 'status', align: 'left' as const, sortable: true },
  { name: 'actions', label: '', field: 'actions', align: 'center' as const },
];

interface FlatRow {
  id: string;
  source_table: string;
  source_column: string;
  target_table: string;
  target_column: string;
  confidence: number;
  status: string;
  rationale: string;
  transformation_type: string;
  _bucket: string;
}

const tableRows = computed((): FlatRow[] => {
  if (!mappingStore.activeMapping) return [];
  const rows: FlatRow[] = [];
  for (const mt of mappingStore.activeMapping.tables) {
    if (mt.status === 'discarded') continue;
    for (const col of mt.columns) {
      if (col.status === 'discarded') continue;
      const conf = col.confidence ?? 0;
      rows.push({
        id: `${mt.target_table}_${col.target_column}`,
        source_table: col.source_table ?? '',
        source_column: col.source_column ?? '',
        target_table: mt.target_table,
        target_column: col.target_column,
        confidence: conf,
        status: col.status ?? 'pending',
        rationale: col.rationale ?? '',
        transformation_type: col.transformation_type ?? '',
        _bucket: confBucket(conf),
      });
    }
  }
  return rows;
});

const filteredTableRows = computed(() => {
  let rows = tableRows.value;
  if (filterSrc.value !== 'All') {
    rows = rows.filter(r => r.source_table === filterSrc.value);
  }
  if (filterTgt.value !== 'All') {
    rows = rows.filter(r => r.target_table === filterTgt.value);
  }
  if (filterConf.value !== 'All') {
    rows = rows.filter(r => r._bucket === confBucketMap[filterConf.value]);
  }
  if (tableSearch.value) {
    const q = tableSearch.value.toLowerCase();
    rows = rows.filter(r =>
      Object.values(r).some(v => String(v).toLowerCase().includes(q))
    );
  }
  return rows;
});

const sqlPreview = computed(() => {
  if (!mappingStore.activeMapping) return '';
  const blocks: string[] = [];
  for (const t of mappingStore.activeMapping.tables) {
    if (t.status === 'discarded' || !t.sql_query) continue;
    blocks.push(`-- Target: ${t.target_schema}.${t.target_table}\n${t.sql_query.trim()}`);
  }
  return blocks.join('\n\n');
});
// endregion

// region Global filters
const allSrcTables = computed(() =>
  [...new Set(tableRows.value.map(r => r.source_table).filter(Boolean))].sort()
);
const allTgtTables = computed(() =>
  [...new Set(tableRows.value.map(r => r.target_table).filter(Boolean))].sort()
);

const confBucketMap: Record<string, string> = {
  'high (≥0.7)': 'high',
  'medium (0.4–0.69)': 'medium',
  'low (<0.4)': 'low',
};

const filteredMapping = computed((): MappingResult => {
  const m = mappingStore.activeMapping;
  if (!m) return { tables: [] };

  const tables: MappingTable[] = [];
  for (const mt of m.tables) {
    if (mt.status === 'discarded') continue;
    if (filterTgt.value !== 'All' && mt.target_table !== filterTgt.value) continue;

    const cols = mt.columns.filter(col => {
      if (col.status === 'discarded') return false;
      if (filterSrc.value !== 'All' && col.source_table !== filterSrc.value) return false;
      if (filterConf.value !== 'All') {
        const bucket = confBucket(col.confidence);
        if (bucket !== confBucketMap[filterConf.value]) return false;
      }
      return true;
    });

    if (cols.length > 0) {
      tables.push({ ...mt, columns: cols });
    }
  }
  return { ...m, tables };
});

const vizMappedCount = computed(() =>
  filteredMapping.value.tables.reduce((sum, t) => sum + t.columns.filter(c => c.source_column).length, 0)
);
// endregion

// region Actions
function onSourceChange() {
  if (selectedSource.value) catalogStore.loadCatalog('sources', selectedSource.value);
}

function onTargetChange() {
  if (selectedTarget.value) {
    catalogStore.loadCatalog('targets', selectedTarget.value);
    // Try loading existing mapping
    if (selectedSource.value) {
      mappingStore.loadMapping(selectedSource.value, selectedTarget.value).catch(() => { /* no mapping yet */ });
    }
  }
}

async function onRun() {
  if (!selectedSource.value || !selectedTarget.value) return;
  await mappingStore.runStream(selectedSource.value, selectedTarget.value, {
    agent_choice: agentChoice.value,
    selected_tables: selectedTables.value.length ? selectedTables.value : null,
  });
}

function onAccept(mt: MappingTable, col: ColumnMapping) {
  if (!selectedSource.value || !selectedTarget.value) return;
  mappingStore.acceptDiscardCandidates(selectedSource.value, selectedTarget.value, [{
    target_schema: mt.target_schema,
    target_table: mt.target_table,
    target_column: col.target_column,
    status: 'accepted',
  }]);
}

function onDiscard(mt: MappingTable, col: ColumnMapping) {
  if (!selectedSource.value || !selectedTarget.value) return;
  mappingStore.acceptDiscardCandidates(selectedSource.value, selectedTarget.value, [{
    target_schema: mt.target_schema,
    target_table: mt.target_table,
    target_column: col.target_column,
    status: 'discarded',
  }]);
}

function onBulkStatus(mt: MappingTable, status: string) {
  if (!selectedSource.value || !selectedTarget.value) return;
  const updates = mt.columns.map(col => ({
    target_schema: mt.target_schema,
    target_table: mt.target_table,
    target_column: col.target_column,
    status,
  }));
  mappingStore.acceptDiscardCandidates(selectedSource.value, selectedTarget.value, updates);
}

// Auto-load existing mapping when source+target change
watch([selectedSource, selectedTarget], ([src, tgt]) => {
  if (src && tgt) {
    mappingStore.loadMapping(src, tgt).catch(() => { /* no mapping */ });
  }
});

watch(() => mappingStore.streamStatus, (status) => {
  if (status === 'running') {
    nowMs.value = Date.now();
    if (progressTimer === null) {
      progressTimer = window.setInterval(() => {
        nowMs.value = Date.now();
      }, 1000);
    }
    return;
  }

  if (progressTimer !== null) {
    window.clearInterval(progressTimer);
    progressTimer = null;
  }
  nowMs.value = Date.now();
}, { immediate: true });

onMounted(async () => {
  await Promise.all([catalogStore.loadSources(), catalogStore.loadTargets()]);
  // Auto-select first source/target if available
  if (sourceOptions.value.length && !selectedSource.value) {
    selectedSource.value = sourceOptions.value[0];
    onSourceChange();
  }
  if (targetOptions.value.length && !selectedTarget.value) {
    selectedTarget.value = targetOptions.value[0];
    onTargetChange();
  }
});

onBeforeUnmount(() => {
  if (progressTimer !== null) {
    window.clearInterval(progressTimer);
  }
  // Abort any in-flight mapping SSE stream — a leaked long-lived stream keeps its
  // fetch connection open and eventually exhausts the browser's per-host slots.
  mappingStore.cancelStream();
});
// endregion
</script>

<style scoped>
/* Warm palette, matching Asset Workspace so the two read as one surface. */
.mw {
  --accent: #0d5c54;
  --paper: #f6f4f0;
  --card-bg: rgba(255, 253, 248, 0.62);
  --border: #ddd6c8;
  --text: #1c1b18;
  --text-2: #86827a;
  --ok-col: #2f6b3a;
  --warn-col: #a9651b;
  --danger-col: #9e3326;
  --info-col: #2f5d8a;

  background: var(--paper);
  color: var(--text);
  padding: 18px 20px 28px;
  /* .page-content-wrapper is a column flex container and QPage sets an inline
     viewport min-height — without this the page collapses to that floor and
     the bottom padding falls outside the box. */
  flex-shrink: 0;
}

.mono { font-family: 'IBM Plex Mono', monospace; }

/* ── Header ───────────────────────────────────────────────────────────── */
.mw-eyebrow {
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: .12em;
  text-transform: uppercase;
  color: var(--text-2);
}
.mw-title {
  font-size: 21px;
  font-weight: 700;
  letter-spacing: -.01em;
  margin: 2px 0 4px;
  line-height: 1.2;
}
.mw-sub {
  font-size: 12.5px;
  color: var(--text-2);
  max-width: 74ch;
  margin: 0 0 16px;
  line-height: 1.5;
}

/* ── Shared card / bar ────────────────────────────────────────────────── */
.panel-card {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  overflow: hidden;
}
.block-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 34px;
  padding: 0 14px;
  border-bottom: 1px solid var(--border);
  background: linear-gradient(180deg, rgba(13, 92, 84, 0.07), rgba(13, 92, 84, 0.02));
}
.block-bar-left { display: flex; align-items: center; gap: 8px; min-width: 0; flex: 1; }
.block-bar-title { font-size: 13px; font-weight: 700; letter-spacing: .01em; }
.block-bar-actions { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.block-bar-time { font-size: 10.5px; color: var(--text-2); white-space: nowrap; }
.mw-body { padding: 14px; }

/* ── Buttons ──────────────────────────────────────────────────────────── */
.mw-btn {
  display: inline-flex;
  align-items: center;
  font-size: 11.5px;
  font-weight: 600;
  padding: 4px 11px;
  border-radius: 7px;
  border: 1px solid var(--border);
  background: #fffdf8;
  color: var(--text);
  cursor: pointer;
  transition: filter .12s, background .12s;
}
.mw-btn:hover:not(:disabled) { filter: brightness(.96); }
.mw-btn:disabled { opacity: .45; cursor: not-allowed; }
.mw-btn--primary {
  background: linear-gradient(160deg, #16887c 0%, var(--accent) 55%, #0a4a43 100%);
  border-color: #0a4a43;
  color: #fdfffe;
  box-shadow: 0 3px 10px -2px rgba(13, 92, 84, .45), inset 0 1px 0 rgba(255, 255, 255, .28);
}
.mw-btn--danger { color: var(--danger-col); border-color: #9e332644; }
.mw-btn--ok { color: var(--ok-col); border-color: #2f6b3a44; }

.mw-icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  margin: 0 1px;
  border-radius: 5px;
  border: 1px solid transparent;
  background: transparent;
  cursor: pointer;
  color: var(--text-2);
}
.mw-icon-btn--ok:hover { background: #2f6b3a18; color: var(--ok-col); }
.mw-icon-btn--danger:hover { background: #9e332615; color: var(--danger-col); }

/* ── Controls ─────────────────────────────────────────────────────────── */
.mw-controls {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 14px 14px 4px;
}
.mw-field { width: 210px; }
.mw-field--narrow { width: 130px; }
.mw-arrow { color: var(--text-2); margin: 0 -2px; }

.mw-scope { padding: 4px 14px 12px; }
.mw-collapse {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
  background: transparent;
  border: none;
  padding: 4px 0;
  cursor: pointer;
}
.mw-collapse--bare { font-size: 13px; font-weight: 700; }
.mw-scope-count {
  font-size: 10.5px;
  font-weight: 600;
  color: var(--text-2);
  padding: 1px 7px;
  border-radius: 999px;
  background: #0d5c5410;
}
.mw-scope-body {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 16px;
  margin-top: 6px;
  max-height: 190px;
  overflow-y: auto;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #fffdf880;
}
.mw-check { font-size: 12px; }

/* ── Progress ─────────────────────────────────────────────────────────── */
.mw-prog-meta {
  display: flex;
  align-items: center;
  gap: 18px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--text-2);
  margin-bottom: 9px;
}
.mw-prog-status { display: inline-flex; align-items: center; color: var(--text); font-weight: 600; }
.mw-prog-stat strong { color: var(--text); }
.mw-pct { font-size: 12px; font-weight: 700; color: var(--accent); }

.mw-bar {
  height: 7px;
  border-radius: 999px;
  background: #0d5c5414;
  overflow: hidden;
}
.mw-bar-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #16887c, var(--accent));
  transition: width .3s ease;
}
.mw-prog-note { font-size: 11.5px; color: var(--text-2); margin: 7px 0 10px; }

.mw-log {
  max-height: 300px;
  overflow-y: auto;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11.5px;
  line-height: 1.65;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #fffdf880;
}
.mw-log-row { color: var(--text); white-space: pre-wrap; }
.mw-log-row--err { color: var(--danger-col); }
.mw-log-icon { margin-right: 6px; }

/* ── Chips ────────────────────────────────────────────────────────────── */
.mw-chip {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .04em;
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: 999px;
  background: #0d5c5412;
  color: var(--text-2);
  white-space: nowrap;
}
.mw-chip--running { background: var(--accent); color: #fff; }
.mw-chip--done { background: #2f6b3a18; color: var(--ok-col); }
.mw-chip--cancelled { background: #a9651b18; color: var(--warn-col); }
.mw-chip--error { background: #9e332615; color: var(--danger-col); }
.mw-chip--info { background: #2f5d8a18; color: var(--info-col); text-transform: none; }

/* ── Filters + legend ─────────────────────────────────────────────────── */
.mw-filters { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 10px; }
.mw-legend {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  font-size: 11.5px;
  color: var(--text-2);
  margin-bottom: 12px;
}
.mw-legend strong { color: var(--text); }
.mw-legend-sep { opacity: .5; }
.mw-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
  margin-left: 8px;
}
.mw-dot--high { background: var(--ok-col); }
.mw-dot--med { background: var(--warn-col); }
.mw-dot--low { background: var(--danger-col); }

/* ── Tabs ─────────────────────────────────────────────────────────────── */
.mw-tabs { display: flex; gap: 7px; flex-wrap: wrap; margin-bottom: 13px; }
.tab-btn {
  font-size: 12.5px;
  padding: 7px 14px;
  border: 1px solid rgba(13, 92, 84, .14);
  border-radius: 9px;
  background: linear-gradient(180deg, rgba(13, 92, 84, .09), rgba(13, 92, 84, .035));
  color: var(--text);
  cursor: pointer;
  transition: background .12s, border-color .12s;
}
.tab-btn:not(.tab-btn--active):hover { border-color: #1c1b18; }
.tab-btn--active {
  color: #fdfffe;
  background: linear-gradient(160deg, #16887c 0%, var(--accent) 55%, #0a4a43 100%);
  border-color: #0a4a43;
  font-weight: 700;
  box-shadow: 0 3px 10px -2px rgba(13, 92, 84, .45), inset 0 1px 0 rgba(255, 255, 255, .28);
}
.mw-panel { min-height: 60px; }

/* ── Confidence badge ─────────────────────────────────────────────────── */
.mw-conf {
  display: inline-block;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10.5px;
  font-weight: 700;
  padding: 1px 7px;
  border-radius: 999px;
}
.mw-conf--high { background: #2f6b3a18; color: var(--ok-col); }
.mw-conf--medium { background: #a9651b18; color: var(--warn-col); }
.mw-conf--low { background: #9e332615; color: var(--danger-col); }

/* ── Tables ───────────────────────────────────────────────────────────── */
.mw-table {
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 8px;
}
.mw-table :deep(thead th) {
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: .05em;
  text-transform: uppercase;
  color: var(--text-2);
  background: #0d5c5408;
}
.mw-table :deep(tbody td) { font-size: 12px; color: var(--text); }
.mw-table :deep(tbody tr:hover) { background: #0d5c5408; }
.mw-table :deep(.q-table__bottom) {
  font-size: 11.5px;
  color: var(--text-2);
  border-top: 1px solid var(--border);
}
.mw-table--inset { border: none; border-top: 1px solid var(--border); border-radius: 0; }

/* ── Raw / by-target-table cards ──────────────────────────────────────── */
.mw-raw-card {
  border: 1px solid var(--border);
  border-radius: 9px;
  overflow: hidden;
  margin-bottom: 12px;
  background: #fffdf866;
}
.mw-raw-head {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
  padding: 8px 12px;
  background: linear-gradient(180deg, rgba(13, 92, 84, .06), rgba(13, 92, 84, .02));
  border-bottom: 1px solid var(--border);
}
.mw-raw-name { font-size: 12.5px; font-weight: 700; }
.mw-raw-rationale {
  font-size: 11.5px;
  color: var(--text-2);
  padding: 7px 12px 0;
  line-height: 1.5;
}

/* ── SQL ──────────────────────────────────────────────────────────────── */
.mw-sql-block { margin-top: 12px; }
.mw-sql-block--inset { margin: 0; padding: 4px 12px 0; }
.mw-sql {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11.5px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-x: auto;
  margin: 6px 0 10px;
  padding: 11px 13px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #fffdf880;
  color: var(--text);
}

/* ── Empty states ─────────────────────────────────────────────────────── */
.mw-empty { padding: 44px 24px; text-align: center; }
.mw-empty-icon { color: var(--text-2); opacity: .55; }
.mw-empty-title { font-size: 14px; font-weight: 700; margin: 10px 0 4px; }
.mw-empty-text {
  font-size: 12.5px;
  color: var(--text-2);
  max-width: 52ch;
  margin: 0 auto;
  line-height: 1.55;
}
.mw-empty-inline {
  font-size: 12.5px;
  color: var(--text-2);
  text-align: center;
  padding: 34px 0;
}
</style>

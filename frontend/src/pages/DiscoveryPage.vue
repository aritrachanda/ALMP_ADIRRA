<template>
  <q-page class="discovery-page q-pa-md">
    <q-slide-transition>
      <q-banner v-if="tableListLoading" rounded class="bg-blue-1 text-primary q-mb-md">
        <StagedLoader :stages="tableLoadStages" />
      </q-banner>
    </q-slide-transition>

    <q-slide-transition>
      <q-banner v-if="loadSuccessMessage" rounded class="bg-positive text-white q-mb-md">
        <template #avatar>
          <q-icon name="check_circle" color="white" />
        </template>
        {{ loadSuccessMessage }}
      </q-banner>
    </q-slide-transition>

    <!-- Dataset / Table selectors -->
    <div class="panel-container q-pa-md q-mb-md">
      <div class="row q-gutter-md items-end">
        <q-select
          v-model="selectedDataset"
          :options="datasetOptions"
          option-label="label"
          option-value="name"
          emit-value map-options
          label="Dataset"
          :loading="tableListLoading"
          outlined dense
          style="width: 240px"
          @update:model-value="onDatasetChange"
        />
        <q-select
          v-model="selectedTable"
          :options="tableOptions"
          option-label="label"
          option-value="name"
          emit-value map-options
          label="Table"
          :loading="tableListLoading"
          :disable="tableListLoading"
          outlined dense
          style="width: 240px"
          @update:model-value="onTableChange"
        />
      </div>
    </div>

    <template v-if="discoveryStore.tableProfile || discoveryStore.tableStats">
      <!-- Table header + metrics -->
      <div class="panel-container q-pa-md q-mb-md">
        <div class="text-h6 text-grey-8 q-mb-xs">
          {{ activeProfile.schema_name || activeStats.schema_name }}.{{ activeProfile.table_name || activeStats.table_name }}
        </div>
        <div v-if="(activeProfile.description || activeStats.description)" class="text-caption text-grey-6 q-mb-sm">
          {{ activeProfile.description || activeStats.description }}
        </div>

        <!-- Metrics row -->
        <div class="row q-gutter-md q-mb-md">
          <div class="metric-card col">
            <div class="metric-value">{{ (activeProfile.row_count || activeStats.row_count)?.toLocaleString() ?? '—' }}</div>
            <div class="metric-label">Rows</div>
          </div>
          <div class="metric-card col">
            <div class="metric-value">{{ (activeProfile.columns ?? activeStats.columns)?.length ?? 0 }}</div>
            <div class="metric-label">Columns</div>
          </div>
          <div class="metric-card col">
            <div class="metric-value">{{ (activeProfile.primary_key || activeStats.primary_key)?.join?.(', ') || '—' }}</div>
            <div class="metric-label">Primary Key</div>
          </div>
          <div class="metric-card col">
            <div class="metric-value">{{ activeProfile.duplicate_count ?? '—' }}</div>
            <div class="metric-label">Duplicate Rows</div>
          </div>
          <div class="metric-card col">
            <div class="metric-value">{{ activeProfile.orphan_fk_count ?? '—' }}</div>
            <div class="metric-label">Orphan FK</div>
          </div>
          <div class="metric-card col">
            <div class="metric-value">{{ activeProfile.completeness_summary?.toFixed(2) ?? '—' }}%</div>
            <div class="metric-label">Completeness</div>
          </div>
          <div class="metric-card col">
            <div class="metric-value">{{ activeProfile.pct_columns_described ? (activeProfile.pct_columns_described * 100).toFixed(0) + '%' : '—' }}</div>
            <div class="metric-label">% Columns Described</div>
          </div>
        </div>

        <!-- Foreign keys / relations -->
        <template v-if="(activeProfile.relations || activeStats.relations)?.length">
          <div class="section-label q-mb-xs">Foreign Keys</div>
          <div v-for="(rel, i) in (activeProfile.relations || activeStats.relations)" :key="i" class="text-caption text-grey-7 q-mb-xs">
            <code>({{ (rel as Record<string, unknown>).columns }})</code> → <code>{{ (rel as Record<string, unknown>).reference_table }}({{ (rel as Record<string, unknown>).reference_table_columns }})</code>
          </div>
        </template>
        <template v-else-if="(activeProfile.foreign_keys || activeStats.foreign_keys)?.length">
          <div class="section-label q-mb-xs">Foreign Keys</div>
          <div class="text-caption text-grey-7">{{ (activeProfile.foreign_keys || activeStats.foreign_keys)?.join(', ') }}</div>
        </template>
      </div>

      <!-- Column statistics -->
      <div class="panel-container q-pa-md q-mb-md">
        <div class="text-subtitle2 text-grey-8 text-weight-bold q-mb-sm">Column Statistics</div>
        <q-markup-table flat dense separator="horizontal" class="stats-table">
          <thead>
            <tr>
              <th class="text-left">Column</th>
              <th class="text-left">Type</th>
              <th class="text-left">Description</th>
              <th class="text-right">Null %</th>
              <th class="text-right">Uniqueness %</th>
              <th class="text-right">Duplicate %</th>
              <th class="text-right">Empty</th>
              <th class="text-right">Placeholders</th>
              <th class="text-left">Top Values</th>
              <th class="text-left">Pattern</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(col, idx) in ((activeProfile.columns || activeStats.columns) as ProfileColumn[])" :key="col.name" :class="{'alt-row': idx % 2 === 0}">
              <td class="text-body2">
                <span v-if="pkSet.has(col.name)" class="q-mr-xs" title="Primary Key">🔑</span>
                <span v-else-if="fkSet.has(col.name)" class="q-mr-xs" title="Foreign Key">→</span>
                <strong>{{ col.name }}</strong>
              </td>
              <td class="text-caption text-grey-7">{{ col.data_type }}</td>
              <td class="text-caption text-grey-6">{{ col.description || '' }}</td>
              <td class="text-right text-caption">{{ fmtNullPct(col) }}</td>
              <td class="text-right text-caption">{{ col.uniqueness_pct != null ? (col.uniqueness_pct * 100).toFixed(1) + '%' : '—' }}</td>
              <td class="text-right text-caption">{{ fmtDuplicatePct(col) }}</td>
              <td class="text-right text-caption">{{ col.empty_string_count ?? '—' }}</td>
              <td class="text-right text-caption">{{ col.placeholder_count ?? '—' }}</td>
              <td class="text-caption">{{ (col.top_values ?? []).map((v: { value?: unknown }) => v.value).slice(0,2).join(', ') }}</td>
              <td class="text-caption">{{ col.inferred_pattern || '—' }}</td>
            </tr>
          </tbody>
        </q-markup-table>
      </div>
      <!-- Column detail removed: detailed stats shown inline in the column list -->

      <!-- Smart Data Assessment -->
      <div class="panel-container q-pa-md q-mb-md">
        <div class="row items-center justify-between q-mb-sm">
          <div class="row items-center">
            <q-icon name="fact_check" size="20px" color="primary" class="q-mr-sm" />
            <span class="text-subtitle2 text-grey-8 text-weight-bold">Smart Data Assessment</span>
            <q-badge
              v-if="assessment && assessment.summary.total"
              color="grey-7"
              class="q-ml-sm"
              :label="`${assessment.summary.total} findings`"
            />
          </div>
          <div class="row items-center q-gutter-sm">
            <q-toggle
              v-model="includeAi"
              label="Include AI suggestions"
              dense
              color="primary"
              @update:model-value="onToggleAi"
            />
            <q-btn
              flat dense no-caps
              icon="refresh"
              label="Refresh"
              color="primary"
              :loading="assessmentLoading"
              @click="loadAssessment(true)"
            />
          </div>
        </div>

        <div class="text-caption text-grey-6 q-mb-sm">
          Advisory observations from the data — not enforced rules. These never block onboarding.
        </div>

        <!-- Severity summary chips -->
        <div v-if="assessment && assessment.summary.total" class="row q-gutter-sm q-mb-sm">
          <q-chip v-if="assessment.summary.by_severity.high" dense square color="red-1" text-color="red-9" icon="error">
            {{ assessment.summary.by_severity.high }} high
          </q-chip>
          <q-chip v-if="assessment.summary.by_severity.attention" dense square color="orange-1" text-color="orange-9" icon="warning">
            {{ assessment.summary.by_severity.attention }} attention
          </q-chip>
          <q-chip v-if="assessment.summary.by_severity.info" dense square color="blue-1" text-color="blue-9" icon="info">
            {{ assessment.summary.by_severity.info }} info
          </q-chip>
          <q-chip v-if="assessment.ai_status === 'cached' || assessment.ai_status === 'generated'" dense square color="grey-2" text-color="grey-8" icon="auto_awesome">
            AI {{ assessment.ai_status }}
          </q-chip>
        </div>

        <div v-if="assessmentLoading" class="text-caption text-grey-6 q-pa-sm">
          <q-spinner-dots size="18px" color="primary" class="q-mr-xs" /> Assessing data…
        </div>

        <div v-else-if="assessment && !assessment.summary.total" class="text-caption text-grey-6 q-pa-sm">
          No notable findings — the data looks clean against the current checks.
        </div>

        <q-list v-else-if="assessment" separator>
          <q-item v-for="(f, i) in assessment.findings" :key="i" class="q-px-none">
            <q-item-section avatar top>
              <q-icon :name="severityIcon(f.severity)" :color="severityColor(f.severity)" />
            </q-item-section>
            <q-item-section>
              <q-item-label class="row items-center q-gutter-xs">
                <span class="text-weight-medium">{{ f.title }}</span>
                <q-badge :color="f.source === 'ai' ? 'deep-purple-1' : 'teal-1'" :text-color="f.source === 'ai' ? 'deep-purple-9' : 'teal-9'" :label="f.source === 'ai' ? 'AI' : 'Rule'" />
                <q-badge outline color="grey-7" :label="f.category" />
                <q-badge outline color="grey-6" :label="f.scope === 'dataset' ? 'table' : f.target" />
              </q-item-label>
              <q-item-label caption class="text-grey-7">{{ f.rationale }}</q-item-label>
              <q-item-label v-if="f.regulatory_note" caption class="text-indigo-8 q-mt-xs">
                <q-icon name="gavel" size="14px" class="q-mr-xs" />{{ f.regulatory_note }}
              </q-item-label>
            </q-item-section>
          </q-item>
        </q-list>

        <div v-else class="text-caption text-grey-6 q-pa-sm">
          Select a table to view its Smart Data Assessment.
        </div>
      </div>

      <!-- Chat panel -->
      <div class="panel-container q-pa-md">
        <div class="row items-center q-mb-sm">
          <q-icon name="chat" size="20px" color="primary" class="q-mr-sm" />
          <span class="text-subtitle2 text-grey-8 text-weight-bold">Ask about this table</span>
        </div>

        <div class="chat-messages q-mb-sm" ref="chatContainer">
          <div v-if="!chatMessages.length" class="text-caption text-grey-5 q-pa-md text-center">
            Ask the AI about this table's data — query rows, explore patterns, check data quality.
          </div>
          <template v-for="(msg, i) in chatMessages" :key="i">
            <!-- User message -->
            <div v-if="msg.role === 'user'" class="q-mb-sm">
              <q-chat-message sent :text="[msg.content]" bg-color="primary" text-color="white" />
            </div>
            <!-- Assistant message: rendered markdown + visuals -->
            <div v-else class="q-mb-sm">
              <div class="assistant-bubble q-pa-sm">
                <div class="assistant-md" v-html="renderMarkdown(msg.content)" />
                <!-- Charts -->
                <template v-for="(vis, vi) in (msg.visuals ?? [])" :key="vi">
                  <div v-if="vis.type === 'chart' && vis.spec && vis.data?.length" class="chart-wrapper q-mt-sm">
                    <Bar v-if="vis.spec.chart_type === 'bar'" :data="toChartData(vis)" :options="chartOptions(vis)" :style="{height: '260px'}" />
                    <Line v-else-if="vis.spec.chart_type === 'line'" :data="toChartData(vis)" :options="chartOptions(vis)" :style="{height: '260px'}" />
                    <Pie v-else-if="vis.spec.chart_type === 'pie'" :data="toPieData(vis)" :options="pieOptions(vis)" :style="{height: '260px'}" />
                    <Scatter v-else-if="vis.spec.chart_type === 'scatter'" :data="toChartData(vis)" :options="chartOptions(vis)" :style="{height: '260px'}" />
                    <Bar v-else-if="vis.spec.chart_type === 'histogram'" :data="toChartData(vis)" :options="chartOptions(vis)" :style="{height: '260px'}" />
                  </div>
                  <div v-else-if="vis.type === 'dataframe' && vis.data?.length" class="q-mt-sm">
                    <q-markup-table flat dense separator="horizontal" class="stats-table">
                      <thead><tr><th v-for="col in (vis.columns ?? Object.keys(vis.data[0]))" :key="col" class="text-left">{{ col }}</th></tr></thead>
                      <tbody>
                        <tr v-for="(row, ri) in vis.data.slice(0, 50)" :key="ri" :class="{'alt-row': ri % 2 === 0}">
                          <td v-for="col in (vis.columns ?? Object.keys(vis.data[0]))" :key="col" class="text-caption">{{ row[col] }}</td>
                        </tr>
                      </tbody>
                    </q-markup-table>
                  </div>
                  <div v-else-if="vis.type === 'error'" class="text-caption text-negative q-mt-xs">{{ vis.message }}</div>
                </template>
              </div>
            </div>
          </template>
        </div>

        <q-input
          v-model="chatInput"
          outlined dense
          placeholder="Ask a question about this table..."
          @keyup.enter="onChat"
        >
          <template #append>
            <q-btn flat round icon="send" color="primary" @click="onChat" :loading="chatLoading" :disable="!chatInput.trim()" />
          </template>
        </q-input>
      </div>
    </template>
  </q-page>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue';
import { useRoute } from 'vue-router';
import { storeToRefs } from 'pinia';
import { Notify } from 'quasar';
import { useCatalogStore } from 'src/stores/catalogStore';
import { useDiscoveryStore } from 'src/stores/discoveryStore';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { Bar, Line, Pie, Scatter } from 'vue-chartjs';
import StagedLoader from 'src/components/StagedLoader.vue';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  ArcElement,
  Tooltip,
  Legend,
} from 'chart.js';
import type { Column, Table, Schema } from 'src/types';
import type { ChatVisual, ProfileColumn, TableProfile } from 'src/api/discovery';

ChartJS.register(CategoryScale, LinearScale, BarElement, LineElement, PointElement, ArcElement, Tooltip, Legend);

const route = useRoute();
const catalogStore = useCatalogStore();
const discoveryStore = useDiscoveryStore();
const { selectedDataset, selectedTable, selectedColumn, chatInput, chatMessages } = storeToRefs(discoveryStore);

// region State
const chatLoading = ref(false);
const chatContainer = ref<HTMLElement | null>(null);
const assessmentLoading = ref(false);
const includeAi = ref(false);
const tableLoadStages = computed(() => [
  `Opening ${selectedDataset.value ?? 'the selected dataset'}\u2026`,
  'Profiling its columns\u2026',
  'Crunching statistics\u2026',
]);
const tableListLoading = ref(false);
const loadSuccessMessage = ref<string | null>(null);
let loadSuccessTimer: number | null = null;
// endregion

// region Computed
const datasetOptions = computed(() =>
  discoveryStore.datasets.map(d => ({
    label: `[${d.kind.toUpperCase()}] ${d.name}`,
    name: d.name,
    kind: d.kind,
  })),
);

const tableOptions = computed(() => {
  const ac = catalogStore.activeCatalog;
  if (!ac) return [];
  const schemas = ac.schemas ?? [];
  const opts: { label: string; name: string }[] = [];
  for (const s of schemas) {
    const sAny = s as Schema & { schema_name?: string };
    const tlist = s.tables ?? [];
    for (const t of tlist) {
      const tAny = t as Table & { table?: string; name?: string };
      const name = tAny.table_name ?? tAny.table ?? tAny.name;
      const schemaLabel = sAny.name ?? sAny.schema_name ?? '';
      // use schema-qualified name as the option value to disambiguate tables with the same name
      const qualified = schemaLabel ? `${schemaLabel}.${name}` : String(name);
      opts.push({ label: qualified, name: qualified });
    }
  }
  if (opts.length === 0) {
    try {
      // eslint-disable-next-line no-console
      console.debug('Discovery: tableOptions parsed empty from activeCatalog', ac);
    } catch { /* ignore */ }
  }
  return opts;
});

const activeProfile = computed<Partial<TableProfile>>(() => discoveryStore.tableProfile ?? {});
const activeStats = computed<Partial<Table>>(() => discoveryStore.tableStats ?? {});
const assessment = computed(() => discoveryStore.tableAssessment);

const pkSet = computed(() => new Set(activeProfile.value.primary_key || activeStats.value.primary_key || []));
const fkSet = computed(() => new Set(activeProfile.value.foreign_keys || activeStats.value.foreign_keys || []));
// endregion

// region Helpers
function fmtNullPct(col: Column): string {
  const v = col.null_pct;
  if (v == null) return '—';
  return v > 0 ? `${(v * 100).toFixed(0)}%` : '0%';
}
function fmtDuplicatePct(col: Column): string {
  if (col.duplicate_count == null || col.row_count == null || col.row_count <= 0) {
    return '—';
  }
  const pct = (col.duplicate_count / col.row_count) * 100;
  return `${pct.toFixed(1)}%`;
}

function catalogType(): 'sources' | 'targets' {
  const ds = discoveryStore.datasets.find(d => d.name === selectedDataset.value);
  return ds?.kind === 'target' ? 'targets' : 'sources';
}

function severityIcon(sev: string): string {
  if (sev === 'high') return 'error';
  if (sev === 'attention') return 'warning';
  return 'info';
}

function severityColor(sev: string): string {
  if (sev === 'high') return 'negative';
  if (sev === 'attention') return 'orange';
  return 'blue';
}

async function loadAssessment(refresh = false) {
  if (!selectedDataset.value || !selectedTable.value) return;
  assessmentLoading.value = true;
  try {
    await discoveryStore.loadAssessment(selectedDataset.value, selectedTable.value, {
      includeAi: includeAi.value,
      refresh,
    });
  } catch (e) {
    // eslint-disable-next-line no-console
    console.debug('Discovery: assessment load failed', e);
  } finally {
    assessmentLoading.value = false;
  }
}

function showLoadSuccess(message: string, timeout = 2200) {
  if (loadSuccessTimer !== null) {
    window.clearTimeout(loadSuccessTimer);
  }
  loadSuccessMessage.value = message;
  loadSuccessTimer = window.setTimeout(() => {
    loadSuccessMessage.value = null;
    loadSuccessTimer = null;
  }, timeout);
}

async function onToggleAi() {
  await loadAssessment(false);
}

function renderMarkdown(text: string): string {
  const html = marked.parse(text, { async: false }) as string;
  return DOMPurify.sanitize(html);
}

const PALETTE = ['#0d4da1', '#e07be0', '#4ecdc4', '#7c3aed', '#f59e0b', '#ef4444', '#10b981', '#6366f1'];

function toChartData(vis: ChatVisual) {
  const rows = vis.data ?? [];
  const x = vis.spec?.x ?? '';
  const y = vis.spec?.y ?? '';
  const labels = rows.map(r => String(r[x] ?? ''));
  const values = rows.map(r => Number(r[y]) || 0);
  return {
    labels,
    datasets: [{
      label: vis.spec?.title ?? y,
      data: values,
      backgroundColor: PALETTE.slice(0, values.length > PALETTE.length ? PALETTE.length : values.length),
      borderColor: '#0d4da1',
      borderWidth: vis.spec?.chart_type === 'line' ? 2 : 0,
      borderRadius: vis.spec?.chart_type === 'bar' || vis.spec?.chart_type === 'histogram' ? 3 : 0,
    }],
  };
}

function toPieData(vis: ChatVisual) {
  const rows = vis.data ?? [];
  const x = vis.spec?.x ?? '';
  const y = vis.spec?.y ?? '';
  return {
    labels: rows.map(r => String(r[x] ?? '')),
    datasets: [{
      data: rows.map(r => Number(r[y]) || 0),
      backgroundColor: PALETTE,
    }],
  };
}

function chartOptions(vis: ChatVisual) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: { enabled: true },
    },
    scales: {
      x: { grid: { display: false }, title: { display: true, text: vis.spec?.x ?? '' } },
      y: { beginAtZero: true, grid: { color: '#f0f0f0' }, title: { display: true, text: vis.spec?.y ?? '' } },
    },
  };
}

function pieOptions(_vis: ChatVisual) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { position: 'bottom' as const, labels: { boxWidth: 10 } },
      tooltip: { enabled: true },
    },
  };
}
// endregion

// region Navigation
async function onDatasetChange() {
  selectedTable.value = null;
  selectedColumn.value = null;
  chatMessages.value = [];
  if (selectedDataset.value) {
    tableListLoading.value = true;
    loadSuccessMessage.value = null;
    try {
      // eslint-disable-next-line no-console
      console.debug('Discovery: onDatasetChange selectedDataset', selectedDataset.value);
    } catch { /* ignore */ }

    try {
      await catalogStore.loadCatalog(catalogType(), selectedDataset.value);

      // debug: log loaded catalog and computed table options
      try {
        // eslint-disable-next-line no-console
        console.debug('Discovery: loaded activeCatalog', catalogStore.activeCatalog);
        // eslint-disable-next-line no-console
        console.debug('Discovery: computed tableOptions', tableOptions.value);
      } catch {
        // ignore
      }

      // If no table is selected, auto-select the first available table and load it
      try {
        if (!selectedTable.value && tableOptions.value && tableOptions.value.length) {
          selectedTable.value = tableOptions.value[0].name;
          // eslint-disable-next-line no-console
          console.debug('Discovery: auto-selected table', selectedTable.value);
          await onTableChange();
        }
      } catch {
        // ignore selection errors
      }

      showLoadSuccess(
        tableOptions.value.length
          ? `Discovery loaded ${tableOptions.value.length} tables for ${selectedDataset.value}.`
          : `Discovery loaded ${selectedDataset.value}, but no tables were found.`,
      );
    } catch (e) {
      Notify.create({
        message: `Failed to load Discovery tables: ${e}`,
        color: 'negative',
        position: 'top',
      });
    } finally {
      tableListLoading.value = false;
    }
  }
}

async function onTableChange() {
  // clear prior UI state
  chatMessages.value = [];
  if (selectedDataset.value && selectedTable.value) {
    // clear previous results to avoid showing stale data while loading
    discoveryStore.tableStats = null;
    discoveryStore.tableProfile = null;
    discoveryStore.tableAssessment = null;

    try {
      // eslint-disable-next-line no-console
      console.debug('Discovery: loading stats/profile for', selectedDataset.value, selectedTable.value);
    } catch { /* ignore */ }

    const [stats, profile] = await Promise.all([
      discoveryStore.loadStats(selectedDataset.value, selectedTable.value).then(() => discoveryStore.tableStats).catch(err => { return { _error: String(err) }; }),
      discoveryStore.loadProfile(selectedDataset.value, selectedTable.value).then(() => discoveryStore.tableProfile).catch(err => { return { _error: String(err) }; }),
    ]);

    try {
      // eslint-disable-next-line no-console
      console.debug('Discovery: stats result', stats);
      // eslint-disable-next-line no-console
      console.debug('Discovery: profile result', profile);
    } catch { /* ignore */ }

    // Load the rule-based Smart Data Assessment (AI is opt-in via the toggle).
    await loadAssessment(false);
  }
}
// endregion

// region Chat
async function onChat() {
  const text = chatInput.value.trim();
  if (!text || !selectedDataset.value || !selectedTable.value) return;
  chatInput.value = '';
  chatMessages.value.push({ role: 'user', content: text });
  chatLoading.value = true;
  await scrollChat();
  try {
    const result = await discoveryStore.chat(
      selectedDataset.value,
      selectedTable.value,
      chatMessages.value.map(m => ({ role: m.role, content: m.content })),
    );
    chatMessages.value.push({ role: 'assistant', content: result.reply, visuals: result.visuals ?? [] });
  } catch (e) {
    chatMessages.value.push({ role: 'assistant', content: `Error: ${e}` });
  } finally {
    chatLoading.value = false;
    await scrollChat();
  }
}

async function scrollChat() {
  await nextTick();
  if (chatContainer.value) {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight;
  }
}
// endregion

// region Init
onMounted(async () => {
  if (!discoveryStore.datasets.length) {
    await discoveryStore.loadDatasets();
  }
  await Promise.all([catalogStore.loadSources(), catalogStore.loadTargets()]);

  // Handle query params (deep-link) — takes precedence over persisted selection
  if (route.query.dataset) {
    selectedDataset.value = route.query.dataset as string;
    await onDatasetChange();
    if (route.query.table) {
      selectedTable.value = route.query.table as string;
      await onTableChange();
    }
  } else if (selectedDataset.value) {
    // Restore catalog + stats from persisted selection
    await catalogStore.loadCatalog(catalogType(), selectedDataset.value);
    if (selectedTable.value && !discoveryStore.tableStats) {
      await Promise.all([
        discoveryStore.loadStats(selectedDataset.value, selectedTable.value),
        discoveryStore.loadProfile(selectedDataset.value, selectedTable.value),
      ]);
      await loadAssessment(false);
    }
  }
  await scrollChat();
});

onBeforeUnmount(() => {
  if (loadSuccessTimer !== null) {
    window.clearTimeout(loadSuccessTimer);
  }
});
// endregion
</script>

<style scoped lang="scss">
.discovery-page {
  background: #f0f0f0;
}

.panel-container {
  background: #fdfdfd;
  border-radius: 10px;
}

.section-label {
  font-weight: 700;
  font-size: 13px;
  color: #2b2a31;
}

.metric-card {
  background: #f8f9fa;
  border: 1px solid #eee;
  border-radius: 8px;
  padding: 12px 16px;
  text-align: center;
}

.metric-value {
  font-size: 18px;
  font-weight: 700;
  color: #2b2a31;
  overflow: hidden;
  text-overflow: ellipsis;
}

.metric-label {
  font-size: 11px;
  font-weight: 600;
  color: #94a3b8;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-top: 2px;
}

.stats-table {
  width: 100%;

  th {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: #94a3b8;
    padding: 8px 10px;
    white-space: nowrap;
  }

  td {
    padding: 6px 10px;
    vertical-align: middle;
  }

  .alt-row {
    background: #fafafa;
  }
}

.chat-messages {
  max-height: 500px;
  overflow-y: auto;
  border: 1px solid #eee;
  border-radius: 8px;
  padding: 8px;
  background: #fafafa;
}

.assistant-bubble {
  background: #f0f0f0;
  border-radius: 10px;
  max-width: 85%;
}

.assistant-md {
  :deep(p) { margin: 0 0 6px; }
  :deep(pre) {
    background: #e8e8e8;
    border-radius: 6px;
    padding: 8px 12px;
    overflow-x: auto;
    font-size: 12px;
  }
  :deep(code) {
    font-size: 12px;
    background: #e8e8e8;
    padding: 1px 4px;
    border-radius: 3px;
  }
  :deep(pre code) {
    background: none;
    padding: 0;
  }
  :deep(table) {
    border-collapse: collapse;
    width: 100%;
    font-size: 12px;
    margin: 6px 0;
  }
  :deep(th), :deep(td) {
    border: 1px solid #ddd;
    padding: 4px 8px;
    text-align: left;
  }
  :deep(th) { background: #e8e8e8; font-weight: 600; }
  :deep(ul), :deep(ol) { padding-left: 20px; margin: 4px 0; }
}

.chart-wrapper {
  background: white;
  border: 1px solid #eee;
  border-radius: 8px;
  padding: 12px;
}
</style>

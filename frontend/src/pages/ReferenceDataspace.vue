<template>
  <q-page class="rds-page">
    <header class="rds-topbar">
      <div>
        <div class="rds-eyebrow">Data Marketspace</div>
        <div class="rds-title-row"><h1>Reference Dataspace</h1><q-chip dense icon="lock" class="rds-readonly-chip">Read-only register</q-chip></div>
        <p class="rds-subtitle">Observe governed local code lists, their coverage, and where the source needs definition work.</p>
      </div>
      <ExportSyncMenu :export-data="exportRows" :export-detail="exportDetail" export-filename="reference_dataspace" export-title="Reference Dataspace" api-path="/api/reference-data" />
    </header>

    <div v-if="store.loading && !store.data" class="rds-state-panel"><StagedLoader :stages="registerLoadStages" /></div>
    <div v-else-if="store.error" class="rds-state-panel rds-state-panel--error"><q-icon name="error_outline" size="28px" /><div>{{ store.error }}</div><q-btn flat color="primary" label="Try again" @click="store.load" /></div>

    <div v-else class="rds-layout">
      <!-- ── LEFT RAIL: collapsible source / schema / dataset scope ──────── -->
      <aside class="rds-rail" :class="{ 'rds-rail--collapsed': !scopeOpen }">
        <button
          class="rds-rail-toggle" :title="scopeOpen ? 'Hide scope filters' : 'Show scope filters'"
          @click="scopeOpen = !scopeOpen"
        >
          <q-icon v-if="scopeOpen" name="tune" size="16px" />
          <span v-if="scopeOpen" class="rds-rail-toggle-label">Scope</span>
          <span v-if="!scopeOpen && scopeActive" class="rds-rail-dot" />
          <q-icon :name="scopeOpen ? 'keyboard_double_arrow_left' : 'keyboard_double_arrow_right'" size="18px" class="rds-rail-caret" />
        </button>
        <div v-show="scopeOpen" class="rds-rail-scope">
          <div class="rds-rail-sub"><span class="rds-rail-label">Source</span></div>
          <div class="rds-rail-field-row">
            <q-select
              v-model="scopeSource" :options="sourceOptions" dense outlined clearable
              placeholder="All sources" class="rds-select rds-field--source"
            >
              <template #prepend><q-icon name="dns" size="15px" /></template>
            </q-select>
            <q-select
              v-if="scopeSource" v-model="scopeSchema" :options="schemasForSelectedSource" dense outlined clearable
              placeholder="All schemas" class="rds-select rds-field--schema"
            >
              <template #prepend><q-icon name="schema" size="15px" /></template>
            </q-select>
          </div>
          <template v-if="scopeSource">
            <div class="rds-rail-sub"><span class="rds-rail-label">Dataset</span></div>
            <div class="rds-rail-field-row">
              <q-select
                v-model="scopeTable" :options="tablesInScope" dense outlined clearable
                placeholder="All datasets" class="rds-select"
              >
                <template #prepend><q-icon name="table_chart" size="15px" /></template>
              </q-select>
            </div>
          </template>
        </div>
      </aside>

      <!-- ── MAIN: coverage stats + search/filters + register / set browser ─ -->
      <main class="rds-main">
        <section class="rds-stats">
          <button class="rds-stat-card rds-stat-card--neutral" @click="clearStatus">
            <span class="rds-stat-lbl">Reference coverage</span><strong class="rds-stat-val">{{ coveragePercent }}%</strong><small>{{ fields.length }} code sets</small>
          </button>
          <button class="rds-stat-card" :class="{ 'rds-stat-card--active': statusFilter === 'approved' }" @click="toggleStatus('approved')">
            <span class="rds-stat-lbl">Approved lists</span><strong class="rds-stat-val rds-stat-val--approved">{{ summary.status_counts.approved }}</strong><small>Click to filter</small>
          </button>
          <div class="rds-stat-card rds-stat-card--neutral">
            <span class="rds-stat-lbl">Codes of record</span><strong class="rds-stat-val">{{ summary.codes_of_record }}</strong><small>On approved lists</small>
          </div>
          <button class="rds-stat-card" :class="{ 'rds-stat-card--active': statusFilter === 'in_review' }" @click="toggleStatus('in_review')">
            <span class="rds-stat-lbl">Awaiting review</span><strong class="rds-stat-val rds-stat-val--review">{{ summary.status_counts.in_review }}</strong><small>Click to filter</small>
          </button>
        </section>

        <section class="rds-filterbar">
          <q-input v-model="search" dense outlined clearable placeholder="Search business name, column, code or meaning" class="rds-filter-search">
            <template #prepend><q-icon name="search" size="16px" /></template>
          </q-input>
          <div class="rds-filter-chips">
            <button
              v-for="chip in statusChips" :key="chip.value"
              class="rds-chip" :class="{ 'rds-chip--active': statusFilter === chip.value }"
              @click="statusFilter = chip.value"
            >{{ chip.label }}</button>
            <button v-if="hasActiveFilters" class="rds-chip rds-chip--clear" @click="clearFilters">
              <q-icon name="filter_alt_off" size="12px" class="q-mr-xs" />Clear all
            </button>
          </div>
        </section>

        <div class="rds-view-toggle">
          <button class="rds-tab-btn" :class="{ 'rds-tab-btn--active': viewMode === 'source' }" @click="viewMode = 'source'">
            <q-icon name="account_tree" size="14px" class="q-mr-xs" />By source
          </button>
          <button class="rds-tab-btn" :class="{ 'rds-tab-btn--active': viewMode === 'set' }" @click="viewMode = 'set'">
            <q-icon name="dataset" size="14px" class="q-mr-xs" />Browse by set
          </button>
        </div>

        <template v-if="viewMode === 'source'">
          <section v-if="flatTableGroups.length" class="rds-register">
            <div class="rds-register-heading">
              <span>Reference register</span>
              <small>{{ filteredFields.length }} of {{ fields.length }} code sets shown</small>
              <span v-if="expandableCount" class="rds-expand-count">{{ openCount }} of {{ expandableCount }} expanded</span>
              <button v-if="expandableCount" class="rds-expand-all" @click="allExpanded ? collapseAll() : expandAll()">
                <q-icon :name="allExpanded ? 'unfold_less' : 'unfold_more'" size="14px" class="q-mr-xs" />{{ allExpanded ? 'Collapse all' : 'Expand all' }}
              </button>
            </div>

            <div v-for="group in flatTableGroups" :key="`${group.source}|${group.schema}|${group.table}`" class="rds-table-group">
              <div class="rds-table-group-head">
                <q-icon name="table_chart" size="15px" />
                <strong>{{ group.table }}</strong>
                <span class="rds-table-group-path">{{ group.source }}.{{ group.schema }}</span>
                <span class="rds-table-group-rollup">{{ rollup(group.fields) }}</span>
              </div>
              <q-expansion-item
                v-for="field in group.fields" :key="fieldKey(field)" dense
                :model-value="openItems.has(fieldKey(field))"
                @update:model-value="val => toggleOpen(fieldKey(field), val)"
                header-class="rds-field-row"
                :expand-icon-class="field.counts.total === 0 ? 'rds-field-expand rds-field-expand--none' : 'rds-field-expand'"
                :disable="field.counts.total === 0"
              >
                <template #header>
                  <div class="rds-field-grid">
                    <div>
                      <div class="rds-business-name" :class="{ fallback: field.business_name_is_fallback }">{{ field.business_name }}</div>
                      <div class="rds-technical"><code>{{ field.column }}</code><span>{{ field.semantic_type }}</span></div>
                    </div>
                    <div class="rds-code-count">{{ field.counts.total }} <span>codes</span></div>
                    <ReferenceStatusPill :field="field" />
                    <q-chip dense square class="rds-kind-chip">{{ field.set_kind === 'standard' ? 'Standard' : 'Local' }}</q-chip>
                  </div>
                </template>
                <div class="rds-ledger">
                  <div class="rds-ledger-meta">
                    <a :href="field.asset_link" class="rds-asset-link">View in Asset Workspace <q-icon name="arrow_forward" size="15px" /></a>
                  </div>
                  <q-markup-table flat dense class="rds-ledger-table">
                    <thead><tr><th>Code</th><th>Value</th><th>Meaning</th></tr></thead>
                    <tbody>
                      <tr v-for="code in field.codes" :key="code.code">
                        <td><code>{{ code.code }}</code></td>
                        <td :class="{ muted: !code.value }">{{ code.value || 'Not defined' }}</td>
                        <td :class="{ muted: !code.meaning }">{{ code.meaning || 'Not defined' }}</td>
                      </tr>
                    </tbody>
                  </q-markup-table>
                  <div v-if="field.approved_by || field.approved_at" class="rds-approval-meta">Approved <span v-if="field.approved_by">by {{ field.approved_by }}</span><span v-if="field.approved_at"> on {{ field.approved_at }}</span></div>
                </div>
              </q-expansion-item>
            </div>
          </section>
          <div v-else class="rds-state-panel"><q-icon name="filter_alt_off" size="30px" /><div>No reference code sets match these filters.</div><q-btn flat color="primary" label="Clear filters" @click="clearFilters" /></div>
        </template>

        <template v-else>
          <section v-if="setGroups.length" class="rds-register">
            <div class="rds-register-heading"><span>Reference sets</span><small>{{ setGroups.length }} set{{ setGroups.length === 1 ? '' : 's' }}</small></div>
            <q-expansion-item v-for="set in setGroups" :key="set.id" dense header-class="rds-table-group-head rds-table-group-head--set">
              <template #header>
                <q-icon name="dataset" size="15px" />
                <strong>{{ set.name }}</strong>
                <q-chip dense square class="rds-kind-chip">{{ set.kind === 'standard' ? 'Standard' : 'Local' }}</q-chip>
                <span class="rds-table-group-rollup">used by {{ set.usedByCount }} field{{ set.usedByCount === 1 ? '' : 's' }}</span>
              </template>
              <div class="rds-set-detail">
                <div class="rds-set-meta">{{ set.entry_count }} code{{ set.entry_count === 1 ? '' : 's' }}<span v-if="set.standard_ref"> · {{ set.standard_ref }}</span></div>
                <q-markup-table v-if="set.entries?.length" flat dense class="rds-ledger-table rds-ledger-table--set">
                  <thead><tr><th>Code</th><th>Value</th><th>Meaning</th><th>Status</th></tr></thead>
                  <tbody>
                    <tr v-for="entry in set.entries" :key="entry.code">
                      <td><code>{{ entry.code }}</code></td>
                      <td :class="{ muted: !entry.value }">{{ entry.value || 'Not defined' }}</td>
                      <td :class="{ muted: !entry.meaning }">{{ entry.meaning || 'Not defined' }}</td>
                      <td :class="{ muted: entry.status !== 'active' }">{{ entry.status }}</td>
                    </tr>
                  </tbody>
                </q-markup-table>
                <div v-if="set.fields.length" class="rds-set-fields">
                  <div class="rds-set-fields-label">Used by</div>
                  <div v-for="field in set.fields" :key="fieldKey(field)" class="rds-set-field-row"><code>{{ field.source }}.{{ field.schema }}.{{ field.table }}.{{ field.column }}</code><span>{{ field.business_name }}</span></div>
                </div>
                <div v-else class="rds-set-fields-empty">No fields bound to this set yet.</div>
              </div>
            </q-expansion-item>
          </section>
          <div v-else class="rds-state-panel"><q-icon name="dataset" size="30px" /><div>No reference sets defined yet.</div></div>
        </template>
      </main>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import ExportSyncMenu from 'src/components/ExportSyncMenu.vue';
import ReferenceStatusPill from 'src/components/ReferenceStatusPill.vue';
import StagedLoader from 'src/components/StagedLoader.vue';
import { useReferenceDataStore } from 'src/stores/referenceDataStore';
import { displayStatusLabel, filterFields, flattenedFields, groupReferenceFields, groupBySet, type ReferenceField } from './referenceDataspaceDisplay';

const route = useRoute(); const router = useRouter(); const store = useReferenceDataStore();
const registerLoadStages = computed(() => [
  'Connecting to the reference register…',
  'Gathering coded columns…',
  'Building the register view…',
]);
const search = ref(String(route.query.q ?? ''));
const statusFilter = ref(String(route.query.status ?? ''));
// Scope selection — cascading single-select Source / Schema / Dataset
// dropdowns (mirrors the Asset Workspace rail) instead of a checkbox tree.
const scopeSource = ref<string | null>(typeof route.query.source === 'string' ? route.query.source : null);
const scopeSchema = ref<string | null>(typeof route.query.schema === 'string' ? route.query.schema : null);
const scopeTable = ref<string | null>(typeof route.query.table === 'string' ? route.query.table : null);
// Scope rail is collapsed by default; auto-opened when a source scope is active (e.g. deep link).
const scopeActive = computed(() => !!scopeSource.value);
const scopeOpen = ref(scopeActive.value);

const statusChips = [
  { label: 'All', value: '' },
  { label: 'In review', value: 'in_review' },
  { label: 'Approved', value: 'approved' },
];

const fields = computed(() => flattenedFields(store.data));
const summary = computed(() => store.data?.summary ?? { total_fields: 0, status_counts: { approved: 0, in_review: 0 }, gaps: 0, codes_of_record: 0 });
const coveragePercent = computed(() => summary.value.total_fields ? Math.round((summary.value.status_counts.approved / summary.value.total_fields) * 100) : 0);
const hasActiveFilters = computed(() => !!(search.value || statusFilter.value || scopeSource.value));
const filteredFields = computed(() => filterFields(fields.value, {
  q: search.value,
  status: statusFilter.value,
  source: scopeSource.value ? [scopeSource.value] : undefined,
  schema: scopeSource.value && scopeSchema.value ? [`${scopeSource.value}|${scopeSchema.value}`] : undefined,
  table: scopeSource.value && scopeSchema.value && scopeTable.value ? [`${scopeSource.value}|${scopeSchema.value}|${scopeTable.value}`] : undefined,
}));
const exportRows = computed(() => filteredFields.value.map(field => ({ source: field.source, schema: field.schema, table: field.table, column: field.column, business_name: field.business_name, semantic_type: field.semantic_type, status: displayStatusLabel(field), code_count: field.counts.total, documented_codes: field.counts.documented, code_source: field.code_source })));
// Structured per-codeset detail (codes included) for the PDF export.
const exportDetail = computed(() => filteredFields.value.map(field => ({
  business_name: field.business_name,
  path: `${field.source}.${field.schema}.${field.table}.${field.column}`,
  semantic_type: field.semantic_type,
  status: displayStatusLabel(field),
  codes: field.codes.map(code => ({ code: code.code, value: code.value ?? '', meaning: code.meaning ?? '', status: code.status })),
})));
const visibleGroups = computed(() => groupReferenceFields(filteredFields.value));

// Expand/collapse state for the register codesets (keyed by fieldKey).
const openItems = ref<Set<string>>(new Set());
function toggleOpen(key: string, val: boolean): void { if (val) openItems.value.add(key); else openItems.value.delete(key); }
const expandableCount = computed(() => filteredFields.value.filter(field => field.counts.total > 0).length);
const openCount = computed(() => filteredFields.value.filter(field => field.counts.total > 0 && openItems.value.has(fieldKey(field))).length);
const allExpanded = computed(() => expandableCount.value > 0 && filteredFields.value.every(field => field.counts.total === 0 || openItems.value.has(fieldKey(field))));
function expandAll(): void { for (const field of filteredFields.value) if (field.counts.total > 0) openItems.value.add(fieldKey(field)); }
function collapseAll(): void { openItems.value.clear(); }

// Flattened one-level-per-table view (source/schema/table headings collapsed
// into a single group heading) — the rail already scopes source/schema/table,
// so the register itself only needs to group by table, not re-nest all three.
interface FlatTableGroup { source: string; schema: string; table: string; fields: ReferenceField[] }
const flatTableGroups = computed<FlatTableGroup[]>(() => {
  const out: FlatTableGroup[] = [];
  for (const source of visibleGroups.value) {
    for (const schema of source.schemas) {
      for (const table of schema.tables) {
        out.push({ source: source.source, schema: schema.schema, table: table.table, fields: table.fields });
      }
    }
  }
  return out;
});

const viewMode = ref<'source' | 'set'>(route.query.view === 'set' ? 'set' : 'source');
const setGroups = computed(() => groupBySet(store.sets, filteredFields.value));
const availableTree = computed(() => buildTree(fields.value));
interface RdTreeTable { key: string; name: string }
interface RdTreeSchema { key: string; name: string; tables: RdTreeTable[] }
interface RdTreeSource { source: string; schemas: RdTreeSchema[] }
interface RdTreeSourceBuilding { source: string; schemas: Map<string, RdTreeSchema> }

function buildTree(input: ReferenceField[]): RdTreeSource[] {
  const map = new Map<string, RdTreeSourceBuilding>();
  for (const field of input) {
    const source = map.get(field.source) ?? { source: field.source, schemas: new Map<string, RdTreeSchema>() };
    map.set(field.source, source);
    const key = `${field.source}|${field.schema}`;
    const schema = source.schemas.get(key) ?? { key, name: field.schema, tables: [] };
    source.schemas.set(key, schema);
    const tableKey = `${key}|${field.table}`;
    if (!schema.tables.some((table) => table.key === tableKey)) schema.tables.push({ key: tableKey, name: field.table });
  }
  return [...map.values()].map(source => ({ source: source.source, schemas: [...source.schemas.values()] }));
}
function fieldKey(field: ReferenceField): string { return `${field.source}|${field.schema}|${field.table}|${field.column}`; }
function rollup(groupFields: ReferenceField[]): string { const approved = groupFields.filter(field => field.status === 'approved').length; return `${approved}/${groupFields.length} approved`; }

const sourceOptions = computed(() => availableTree.value.map(source => source.source));
const schemasForSelectedSource = computed(() => {
  const source = availableTree.value.find(item => item.source === scopeSource.value);
  return source ? source.schemas.map(schema => schema.name) : [];
});
const tablesInScope = computed(() => {
  const source = availableTree.value.find(item => item.source === scopeSource.value);
  if (!source) return [];
  const schemas = scopeSchema.value ? source.schemas.filter(schema => schema.name === scopeSchema.value) : source.schemas;
  return schemas.flatMap(schema => schema.tables.map((table) => table.name));
});

// Reset narrower selections when a broader one changes (source -> schema ->
// dataset), and auto-select a schema when the source only has one — same
// "always visible, auto-filled" treatment as the Asset Workspace rail.
watch(scopeSource, (_next, prev) => { if (prev !== undefined) { scopeSchema.value = null; scopeTable.value = null; } });
watch(scopeSchema, (_next, prev) => { if (prev !== undefined) scopeTable.value = null; });
watch(schemasForSelectedSource, (schemas) => { if (schemas.length === 1) scopeSchema.value = schemas[0]; });
function toggleStatus(status: string): void { statusFilter.value = statusFilter.value === status ? '' : status; } function clearStatus(): void { statusFilter.value = ''; } function clearFilters(): void { search.value = ''; statusFilter.value = ''; scopeSource.value = null; scopeSchema.value = null; scopeTable.value = null; }
watch([search, statusFilter, scopeSource, scopeSchema, scopeTable, viewMode], () => { void router.replace({ query: { ...route.query, q: search.value || undefined, status: statusFilter.value || undefined, source: scopeSource.value || undefined, schema: scopeSchema.value || undefined, table: scopeTable.value || undefined, view: viewMode.value === 'set' ? 'set' : undefined } }); }, { deep: true });
onMounted(async () => { await store.load(); });
</script>

<style scoped>
/* ── Shell — local token overrides mirror AssetWorkspace's `.wp` block so
   this page can reuse the exact same rail / stat-card / tab-btn visual
   language, without introducing a second competing token system. The
   underlying colour VALUES are already identical to the global --adirra-*
   tokens (e.g. --adirra-accent === AssetWorkspace's --accent, #0d5c54) — this
   block just renames them locally so the copied CSS patterns work verbatim. */
.rds-page {
  --accent: var(--adirra-accent);
  --accent-light: var(--adirra-accent-soft);
  --card-bg: rgba(255, 253, 248, .62);
  --border: var(--adirra-line);
  --text: var(--adirra-ink);
  --text-2: var(--adirra-ink-2);
  --text-3: var(--adirra-ink-3);
  /* This page is a normal flowing page, scrolled by the shared
     `.page-content-wrapper` ancestor (see app.scss — that's the documented
     mechanism for "content-flow" pages like Discovery/Catalog). It
     deliberately does NOT use the height:100%/overflow:hidden app-shell
     pattern that Asset Workspace uses for its own internally-scrolling
     dual-pane view — that pattern depends on a height chain propagating
     all the way from q-page-container, which content-flow pages don't get.
     Fighting that with height:100% here just clips content instead of
     scrolling it. */
  background: radial-gradient(ellipse 110% 55% at 50% 0%, #b8d4ec 0%, #d4e6f2 28%, #e8f0f7 50%, #f6f3ec 75%);
  color: var(--text);
  padding: 16px clamp(16px, 3vw, 32px) 32px;
  box-sizing: border-box;
}

.rds-topbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--border);
}
.rds-eyebrow { font-size: 11px; text-transform: uppercase; letter-spacing: .1em; color: var(--text-3); font-weight: 700; }
.rds-title-row { display: flex; align-items: center; gap: 12px; }
.rds-title-row h1 { font-family: 'IBM Plex Serif', serif; font-size: 26px; margin: 3px 0; }
.rds-subtitle { color: var(--text-2); margin: 0; font-size: 13px; }
.rds-readonly-chip { color: var(--text-2); background: var(--adirra-paper-2); border: 1px solid var(--border); }

.rds-state-panel {
  min-height: 300px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-top: 12px;
  background: var(--card-bg);
  backdrop-filter: blur(8px);
  border: 1px solid var(--border);
  border-radius: 10px;
  color: var(--text-2);
}
.rds-state-panel--error { color: var(--adirra-danger); }

/* ── Two-pane layout: rail sticks while main flows/scrolls with the page ── */
.rds-layout {
  display: flex;
  align-items: flex-start;
  margin-top: 14px;
  gap: 14px;
}

.rds-rail {
  flex: 0 0 280px;
  position: sticky;
  top: 12px;
  max-height: calc(100vh - 130px);
  overflow-y: auto;
  overflow-x: hidden;
  background: var(--card-bg);
  backdrop-filter: blur(8px);
  border: 1px solid var(--border);
  border-radius: 10px;
}

.rds-rail-label {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .10em;
  text-transform: uppercase;
  color: var(--text-3);
}

.rds-rail-toggle {
  display: flex; align-items: center; gap: 8px; width: 100%;
  padding: 12px; background: transparent; border: none; cursor: pointer;
  color: var(--text-2); font-weight: 700; font-size: 11px; text-transform: uppercase; letter-spacing: .08em;
}
.rds-rail-toggle:hover { color: var(--accent); }
.rds-rail-toggle-label { flex: 1; text-align: left; }
.rds-rail-caret { margin-left: auto; color: var(--text-3); }
.rds-rail-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--accent); }
.rds-rail--collapsed { flex: 0 0 auto; }
.rds-rail--collapsed .rds-rail-toggle { flex-direction: column; gap: 6px; padding: 12px 10px; }
.rds-rail--collapsed .rds-rail-caret { margin-left: 0; }
.rds-rail-scope { border-top: 1px solid var(--border); padding-bottom: 6px; }

.rds-rail-sub { padding: 10px 12px 4px; }
.rds-chip {
  font-size: 10.5px;
  font-weight: 600;
  height: 22px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: 11px;
  background: var(--adirra-card);
  color: var(--text-2);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 4px;
}
.rds-chip--active { background: var(--accent); border-color: var(--accent); color: #fff; }
.rds-chip--clear { color: var(--adirra-danger); border-color: var(--adirra-danger); background: transparent; }

/* Cascading Source / Schema / Dataset dropdowns — same modernized "card"
   dropdown look as the Asset Workspace rail (translucent bg, accent-glow
   focus), reused here via the local --accent/--card-bg/--border overrides
   defined on .rds-page. */
.rds-rail-field-row { display: flex; flex-direction: column; gap: 8px; padding: 6px 12px 12px; }
.rds-field--source, .rds-field--schema { width: 100%; }
.rds-select :deep(.q-field__control) {
  font-size: 12.5px;
  background: var(--adirra-card);
  border-radius: 9px;
}
.rds-select :deep(.q-field__control)::before { border-color: var(--border) !important; border-radius: 9px; }
.rds-select:hover :deep(.q-field__control)::before { border-color: var(--accent) !important; }
.rds-select :deep(.q-icon) { color: var(--accent); opacity: .85; }
.rds-select :deep(.q-field--focused .q-field__control),
.rds-select :deep(.q-field--highlighted .q-field__control) { background: var(--accent-light) !important; }
.rds-select :deep(.q-field--focused .q-field__control::after),
.rds-select :deep(.q-field--highlighted .q-field__control::after) { border-color: var(--accent) !important; border-width: 1.5px !important; border-radius: 9px; box-shadow: none !important; }

.rds-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* ── Stat cards (same visual language as Asset Workspace's stat-cards) ── */
.rds-stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.rds-stat-card {
  text-align: left;
  min-height: 84px;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--card-bg);
  backdrop-filter: blur(8px);
  color: var(--text);
  cursor: pointer;
}
.rds-stat-card--neutral { cursor: default; }
.rds-stat-card--active { outline: 2px solid var(--accent); outline-offset: -2px; }
.rds-stat-lbl { display: block; font-size: 10px; text-transform: uppercase; letter-spacing: .07em; color: var(--text-3); }
.rds-stat-val { display: block; font-size: 25px; font-weight: 700; margin: 5px 0; font-family: 'IBM Plex Mono', monospace; }
.rds-stat-val--approved { color: var(--adirra-released); }
.rds-stat-val--review { color: var(--adirra-reviewed); }
.rds-stat-card small { color: var(--text-3); font-size: 11px; }

/* ── Search + status-chip filter bar (moved out of the rail) ──────────── */
.rds-filterbar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.rds-filter-search { flex: 1 1 320px; min-width: 240px; max-width: 520px; }
.rds-filter-search :deep(.q-field__control) { background: var(--adirra-card); border-radius: 9px; font-size: 13px; }
.rds-filter-search :deep(.q-field__control)::before { border-color: var(--border) !important; border-radius: 9px; }
.rds-filter-search:hover :deep(.q-field__control)::before { border-color: var(--accent) !important; }
.rds-filter-search :deep(.q-icon) { color: var(--accent); opacity: .85; }
.rds-filter-chips { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }

/* ── View toggle, styled like the Asset Workspace's tab bar ───────────── */
.rds-view-toggle { display: flex; gap: 6px; }
.rds-tab-btn {
  font-size: 12.5px;
  padding: 7px 14px;
  border: 1px solid var(--border);
  border-radius: 9px;
  background: var(--card-bg);
  color: var(--text);
  cursor: pointer;
  font-weight: 600;
  display: flex;
  align-items: center;
}
.rds-tab-btn--active {
  color: #fff;
  background: linear-gradient(160deg, #16887c 0%, var(--accent) 55%, #0a4a43 100%);
  border-color: #0a4a43;
}

/* ── Register (flat table groups instead of a triple-nested accordion) ── */
.rds-register {
  background: var(--card-bg);
  backdrop-filter: blur(8px);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
}
.rds-register-heading {
  display: flex; gap: 8px; align-items: center;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; color: var(--text-2);
}
.rds-register-heading small { margin-left: auto; text-transform: none; letter-spacing: 0; color: var(--text-3); font-weight: 400; }
.rds-expand-count { text-transform: none; letter-spacing: 0; color: var(--text-3); font-weight: 400; font-size: 11px; }
.rds-expand-all {
  display: inline-flex; align-items: center;
  border: 1px solid var(--border); background: var(--adirra-card);
  border-radius: 7px; padding: 3px 9px;
  font: inherit; font-size: 11px; font-weight: 600; text-transform: none; letter-spacing: 0;
  color: var(--accent); cursor: pointer;
}
.rds-expand-all:hover { background: var(--accent-light); }

.rds-table-group + .rds-table-group { border-top: 1px solid var(--border); }
.rds-table-group-head, .rds-table-group-head--set {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 14px;
  background: var(--adirra-paper-2);
  border-bottom: 1px solid var(--border);
  font-size: 12.5px;
}
/* Table name must clearly outrank the field rows beneath it — bump both
   size and weight so it reads as the group heading, not a peer of the
   business-field names it contains. */
.rds-table-group-head strong, .rds-table-group-head--set strong {
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
}
.rds-table-group-path { color: var(--text-3); font-size: 11.5px; }
.rds-table-group-rollup { margin-left: auto; color: var(--text-3); font-size: 11.5px; }

.rds-field-row { padding: 8px 14px; border-top: 1px solid color-mix(in srgb, var(--border) 60%, transparent); }
/* A code set with 0 values has nothing to show when expanded — hide the
   chevron entirely rather than inviting a click into an empty ledger. */
.rds-field-expand--none { visibility: hidden; }
.rds-field-grid { display: grid; grid-template-columns: minmax(0,1fr) 90px 110px 80px; align-items: center; gap: 14px; width: 100%; }
.rds-business-name { font-weight: 600; font-size: 12.5px; }
.rds-business-name.fallback { font-weight: 500; font-style: italic; color: var(--text-2); }
.rds-technical { display: flex; gap: 8px; margin-top: 2px; color: var(--text-3); font-size: 11px; }
.rds-technical code { color: var(--text-2); }
.rds-code-count { font-size: 13px; }
.rds-code-count span { color: var(--text-3); font-size: 11px; }
.rds-kind-chip { width: max-content; background: var(--accent-light); color: var(--accent); font-size: 10px; font-weight: 700; }

.rds-ledger { padding: 10px 16px 14px 32px; background: color-mix(in srgb, var(--adirra-paper) 65%, var(--adirra-card)); }
.rds-ledger-meta { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 9px; font-size: 12px; }
.rds-sample-note { color: var(--text-2); display: flex; gap: 4px; align-items: center; }
.rds-asset-link { margin-left: auto; color: var(--accent); text-decoration: none; font-weight: 700; display: flex; align-items: center; gap: 3px; }
/* Fixed layout with explicit per-column widths so Code/Value/Meaning always
   line up under their own headers (Quasar's markup-table otherwise
   auto-sizes columns from cell content, which drifts when values vary a lot
   in length). By-source view: Code/Value/Meaning. By-set view adds a
   trailing Status column (`--set` modifier), so its three text columns are
   proportionally narrower. */
.rds-ledger-table { width: 100%; table-layout: fixed; border: 1px solid var(--border); background: var(--adirra-card); }
.rds-ledger-table th, .rds-ledger-table td { text-align: left; vertical-align: top; }
.rds-ledger-table th:nth-child(1), .rds-ledger-table td:nth-child(1) { width: 18%; }
.rds-ledger-table th:nth-child(2), .rds-ledger-table td:nth-child(2) { width: 32%; }
.rds-ledger-table th:nth-child(3), .rds-ledger-table td:nth-child(3) { width: 50%; }
.rds-ledger-table--set th:nth-child(1), .rds-ledger-table--set td:nth-child(1) { width: 15%; }
.rds-ledger-table--set th:nth-child(2), .rds-ledger-table--set td:nth-child(2) { width: 27%; }
.rds-ledger-table--set th:nth-child(3), .rds-ledger-table--set td:nth-child(3) { width: 43%; }
.rds-ledger-table--set th:nth-child(4), .rds-ledger-table--set td:nth-child(4) { width: 15%; }
.rds-ledger-table th { color: var(--text-3); font-size: 10px; text-transform: uppercase; letter-spacing: .06em; }
.rds-ledger-table .muted { color: var(--text-3); font-style: italic; }
.rds-approval-meta { margin-top: 8px; font-size: 11px; color: var(--text-3); }

/* ── Browse-by-set detail ──────────────────────────────────────────────── */
.rds-set-detail { padding: 10px 16px 14px; }
.rds-set-meta { font-size: 11px; color: var(--text-3); margin-bottom: 8px; }
.rds-set-fields { display: flex; flex-direction: column; gap: 4px; }
.rds-set-fields-label { font-size: 10px; text-transform: uppercase; letter-spacing: .08em; color: var(--text-3); font-weight: 700; margin-top: 10px; }
.rds-set-field-row { display: flex; align-items: baseline; gap: 10px; font-size: 12px; }
.rds-set-field-row code { color: var(--text-2); font-size: 11px; }
.rds-set-fields-empty { font-size: 12px; color: var(--text-3); font-style: italic; }

@media (max-width: 1100px) {
  .rds-stats { grid-template-columns: repeat(2, 1fr); }
  .rds-layout { flex-direction: column; overflow-y: auto; }
  .rds-rail { flex: 0 0 auto; max-height: 260px; }
}
</style>

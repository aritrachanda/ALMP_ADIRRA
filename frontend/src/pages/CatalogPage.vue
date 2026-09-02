<template>
  <q-page class="catalog-page q-pa-md">
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

    <!-- Selectors -->
    <div class="panel-container q-pa-md q-mb-md">
      <div class="row q-gutter-md items-end">
        <q-select
          v-model="selectedType"
          :options="['sources', 'targets']"
          label="Catalog type"
          outlined dense
          style="width: 160px"
          @update:model-value="onTypeChange"
        />
        <q-select
          v-model="selectedDataset"
          :options="datasetOptions"
          label="Dataset"
          :loading="tableListLoading"
          outlined dense
          style="width: 220px"
          @update:model-value="onDatasetChange"
        />
        <q-select
          v-model="selectedTable"
          :options="tableOptions"
          label="Table"
          :loading="tableListLoading"
          :disable="tableListLoading"
          outlined dense
          style="width: 220px"
          @update:model-value="onTableChange"
        />
      </div>
    </div>

    <!-- Table detail -->
    <template v-if="catalogStore.activeTable">
      <!-- Table metadata header -->
      <div class="panel-container q-pa-md q-mb-md">
        <div class="text-h6 text-grey-8 q-mb-xs">
          {{ catalogStore.activeTable.schema_name }}.{{ catalogStore.activeTable.table_name }}
        </div>
        <div class="row q-gutter-md text-caption text-grey-6">
          <span v-if="catalogStore.activeTable.row_count != null">
            <strong>{{ catalogStore.activeTable.row_count?.toLocaleString() }}</strong> rows
          </span>
          <span v-if="catalogStore.activeTable.primary_key?.length">
            <q-icon name="vpn_key" size="12px" class="q-mr-xs" />PK: {{ catalogStore.activeTable.primary_key.join(', ') }}
          </span>
          <span>
            <strong>{{ descriptionCoverage }}</strong>% described
          </span>
        </div>

        <!-- Smart Data Assessment deep-link (sources only) -->
        <div v-if="selectedType === 'sources'" class="row items-center q-gutter-sm q-mt-sm">
          <q-icon name="fact_check" size="16px" color="primary" />
          <span class="text-caption text-grey-7">Smart Data Assessment:</span>
          <q-spinner-dots v-if="assessmentLoading" size="16px" color="primary" />
          <template v-else-if="assessmentSummary">
            <q-badge
              v-if="assessmentSummary.high"
              color="red-1" text-color="red-9"
              :label="`${assessmentSummary.high} high`"
            />
            <q-badge
              v-if="assessmentSummary.attention"
              color="orange-1" text-color="orange-9"
              :label="`${assessmentSummary.attention} attention`"
            />
            <span v-if="!assessmentSummary.total" class="text-caption text-grey-6">no findings</span>
            <q-badge
              v-else-if="!assessmentSummary.high && !assessmentSummary.attention"
              color="blue-1" text-color="blue-9"
              :label="`${assessmentSummary.total} info`"
            />
          </template>
          <q-btn
            flat dense size="sm" no-caps
            icon="open_in_new"
            label="View in Discovery"
            color="primary"
            @click="openInDiscovery"
          />
        </div>

        <!-- Table-level descriptions -->
        <div class="row q-gutter-md q-mt-md">
          <div class="col">
            <div class="section-label q-mb-xs">
              Table Description
              <q-btn
                flat dense size="sm" icon="auto_awesome" color="primary" no-caps
                :loading="generatingTableDesc"
                @click="onAiGenerateTableField('user_description')"
                class="q-ml-sm"
              />
            </div>
            <q-input
              v-model="tableUserDesc"
              type="textarea" outlined dense rows="2"
              placeholder="Add a business description for this table..."
              @blur="onSaveTableAnnotations"
            />
          </div>
          <div class="col">
            <div class="section-label q-mb-xs">
              Mapping Instructions
              <q-btn
                flat dense size="sm" icon="auto_awesome" color="primary" no-caps
                :loading="generatingTableMapping"
                @click="onAiGenerateTableField('mapping_instructions')"
                class="q-ml-sm"
              />
            </div>
            <q-input
              v-model="tableMappingInstr"
              type="textarea" outlined dense rows="2"
              placeholder="Add technical mapping notes for this table..."
              @blur="onSaveTableAnnotations"
            />
          </div>
        </div>
      </div>

      <!-- Column grid -->
      <div class="panel-container q-pa-md">
        <div class="row items-center q-mb-sm">
          <span class="text-subtitle2 text-grey-8 text-weight-bold">Columns</span>
          <q-space />
          <q-btn
            flat dense size="sm" no-caps color="primary" icon="auto_awesome"
            label="Generate all descriptions"
            :loading="generatingAll === 'user_description'"
            @click="onAiGenerateAll('user_description')"
            class="q-mr-sm"
          />
          <q-btn
            flat dense size="sm" no-caps color="primary" icon="auto_awesome"
            label="Generate all mapping"
            :loading="generatingAll === 'mapping_instructions'"
            @click="onAiGenerateAll('mapping_instructions')"
          />
        </div>

        <q-markup-table flat dense separator="horizontal" class="catalog-table">
          <thead>
            <tr>
              <th class="text-left col-name-th">Column</th>
              <th class="text-left col-type-th">Type</th>
              <th class="text-right col-narrow-th">Null %</th>
              <th class="text-right col-narrow-th">Unique</th>
              <th class="text-left col-desc-th">Description</th>
              <th class="text-left col-desc-th">Mapping Instructions</th>
              <th class="text-center col-glossary-th">Glossary</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(col, idx) in catalogStore.activeTable.columns" :key="col.name" :class="{'alt-row': idx % 2 === 0}">
              <!-- Column name -->
              <td class="text-body2">
                <span v-if="pkSet.has(col.name)" class="q-mr-xs" title="Primary Key">🔑</span>
                <span v-else-if="fkSet.has(col.name)" class="q-mr-xs" title="Foreign Key">→</span>
                <strong>{{ col.name }}</strong>
              </td>
              <!-- Type -->
              <td class="text-caption text-grey-7">{{ col.data_type }}</td>
              <!-- Null % -->
              <td class="text-right text-caption">{{ fmtNullPct(col) }}</td>
              <!-- Unique count -->
              <td class="text-right text-caption">
                <template v-if="col.distinct_count != null && (col.sample_values?.length || col.min_value != null)">
                  <span class="unique-link" @click="openUniquePopover($event, col)">{{ col.distinct_count }}</span>
                </template>
                <template v-else-if="col.distinct_count != null">
                  {{ col.distinct_count }}
                </template>
                <template v-else>—</template>
              </td>
              <!-- Description -->
              <td class="desc-cell">
                <div v-if="col.description" class="text-caption text-grey-5 q-mb-xs desc-wrap">
                  <q-icon name="description" size="12px" class="q-mr-xs" />{{ col.description }}
                </div>
                <div class="row items-start">
                  <q-input
                    v-model="editedDescriptions[col.name]"
                    dense borderless
                    type="textarea"
                    autogrow
                    placeholder="Add description..."
                    class="col"
                    input-class="text-body2 desc-wrap"
                    @blur="onSaveAnnotation(col.name)"
                  />
                  <q-btn
                    flat dense size="xs" icon="auto_awesome" color="primary"
                    :loading="generatingCol === col.name + ':user_description'"
                    @click="onAiGenerateCol(col.name, 'user_description')"
                  />
                </div>
              </td>
              <!-- Mapping instructions -->
              <td class="desc-cell">
                <div class="row items-start">
                  <q-input
                    v-model="editedMappingInstr[col.name]"
                    dense borderless
                    type="textarea"
                    autogrow
                    placeholder="Mapping instructions..."
                    class="col"
                    input-class="text-body2 desc-wrap"
                    @blur="onSaveAnnotation(col.name)"
                  />
                  <q-btn
                    flat dense size="xs" icon="auto_awesome" color="primary"
                    :loading="generatingCol === col.name + ':mapping_instructions'"
                    @click="onAiGenerateCol(col.name, 'mapping_instructions')"
                  />
                </div>
              </td>
              <!-- Glossary -->
              <td class="text-center">
                <template v-if="glossaryMap[col.name]">
                  <q-btn
                    flat dense size="sm" no-caps color="primary"
                    icon="menu_book" :label="glossaryMap[col.name]!.title"
                    @click="goToGlossaryTerm(glossaryMap[col.name]!.id)"
                  />
                </template>
                <template v-else>
                  <q-btn
                    flat dense size="sm" no-caps color="grey-7"
                    icon="add" label="Glossary"
                    @click="addToGlossary(col)"
                  />
                </template>
              </td>
            </tr>
          </tbody>
        </q-markup-table>
      </div>

      <!-- Save button -->
      <div class="q-mt-md row justify-end">
        <q-btn
          color="primary" no-caps
          label="Save descriptions"
          icon="save"
          :loading="saving"
          @click="onSaveAll"
        />
      </div>
    </template>

    <!-- Unique values popover -->
    <q-menu v-if="uniquePopoverTarget" v-model="uniquePopoverVisible" :target="uniquePopoverTarget" anchor="bottom middle" self="top middle" class="unique-popover q-pa-md">
      <template v-if="uniquePopoverCol">
        <div class="text-subtitle2 text-weight-bold q-mb-sm">{{ uniquePopoverCol.name }}</div>
        <div v-if="uniquePopoverCol.min_value != null || uniquePopoverCol.max_value != null" class="text-caption text-grey-6 q-mb-sm">
          <strong>Range:</strong> {{ uniquePopoverCol.min_value ?? '—' }} — {{ uniquePopoverCol.max_value ?? '—' }}
        </div>
        <div v-if="uniquePopoverCol.sample_values?.length" class="q-mb-xs">
          <div class="text-caption text-grey-6 q-mb-xs"><strong>Sample values</strong> ({{ uniquePopoverCol.distinct_count }} unique)</div>
          <q-input
            v-model="uniqueFilter"
            dense outlined
            placeholder="Search values..."
            clearable
            class="q-mb-sm"
          >
            <template #prepend><q-icon name="search" size="16px" /></template>
          </q-input>
          <q-virtual-scroll :items="filteredSamples" style="max-height: 200px;" v-slot="{ item }">
            <div class="text-body2 q-py-xs q-px-sm">{{ item }}</div>
          </q-virtual-scroll>
          <div v-if="uniquePopoverCol.distinct_count != null && uniquePopoverCol.distinct_count > uniquePopoverCol.sample_values.length" class="text-caption text-grey-5 q-mt-xs">
            … and {{ uniquePopoverCol.distinct_count - uniquePopoverCol.sample_values.length }} more
          </div>
        </div>
      </template>
    </q-menu>
  </q-page>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { Notify } from 'quasar';
import { useCatalogStore } from 'src/stores/catalogStore';
import { useAnnotationStore } from 'src/stores/annotationStore';
import { useGlossaryStore } from 'src/stores/glossaryStore';
import { crossRef } from 'src/api/glossary';
import { getTableAssessment } from 'src/api/discovery';
import StagedLoader from 'src/components/StagedLoader.vue';
import type { Column, GlossaryTerm } from 'src/types';

const route = useRoute();
const router = useRouter();
const catalogStore = useCatalogStore();
const annotationStore = useAnnotationStore();
const glossaryStore = useGlossaryStore();

// region State
const selectedType = ref<'sources' | 'targets'>('sources');
const selectedDataset = ref<string | null>(null);
const selectedTable = ref<string | null>(null);
const editedDescriptions = ref<Record<string, string>>({});
const editedMappingInstr = ref<Record<string, string>>({});
const tableUserDesc = ref('');
const tableMappingInstr = ref('');
const saving = ref(false);
const generatingAll = ref<string | null>(null);
const generatingCol = ref<string | null>(null);
const generatingTableDesc = ref(false);
const generatingTableMapping = ref(false);
const tableListLoading = ref(false);
const loadSuccessMessage = ref<string | null>(null);
let loadSuccessTimer: number | null = null;
const tableLoadStages = computed(() => [
  `Opening ${selectedDataset.value ?? 'the selected dataset'}…`,
  'Loading the catalog entry…',
  'Preparing descriptions…',
]);

// Unique values popover state
const uniquePopoverVisible = ref(false);
const uniquePopoverTarget = ref<Element | undefined>(undefined);
const uniquePopoverCol = ref<Column | null>(null);
const uniqueFilter = ref('');

// Glossary cross-ref cache: columnName -> term or null
const glossaryMap = ref<Record<string, GlossaryTerm | null>>({});

// Smart Data Assessment summary (sources only; Discovery excludes targets).
const assessmentSummary = ref<{ total: number; high: number; attention: number } | null>(null);
const assessmentLoading = ref(false);
// endregion

// region Computed
const datasetOptions = computed(() => {
  const list = selectedType.value === 'sources' ? catalogStore.sources : catalogStore.targets;
  return list.map(c => c.name);
});

const tableOptions = computed(() => {
  if (!catalogStore.activeCatalog) return [];
  return catalogStore.activeCatalog.schemas.flatMap(s => s.tables.map(t => t.table_name));
});

const descriptionCoverage = computed(() => {
  const cols = catalogStore.activeTable?.columns ?? [];
  if (!cols.length) return 0;
  const described = cols.filter(c => c.description || editedDescriptions.value[c.name]).length;
  return Math.round((described / cols.length) * 100);
});

const pkSet = computed(() => new Set(catalogStore.activeTable?.primary_key ?? []));
const fkSet = computed(() => new Set(catalogStore.activeTable?.foreign_keys ?? []));

const filteredSamples = computed(() => {
  const samples = uniquePopoverCol.value?.sample_values ?? [];
  const sorted = [...samples].sort((a, b) =>
    String(a).toLowerCase().localeCompare(String(b).toLowerCase()),
  );
  if (!uniqueFilter.value) return sorted;
  const q = uniqueFilter.value.toLowerCase();
  return sorted.filter(s => String(s).toLowerCase().includes(q));
});
// endregion

// region Helpers
function fmtNullPct(col: Column): string {
  const v = col.null_pct;
  if (v == null) return '—';
  return v > 0 ? `${(v * 100).toFixed(0)}%` : '0%';
}

function catalogKind(): 'source' | 'target' {
  return selectedType.value === 'sources' ? 'source' : 'target';
}

function colRef(colName: string): string {
  const t = catalogStore.activeTable;
  if (!t) return '';
  return `${catalogKind()}|${selectedDataset.value}|${t.schema_name}.${t.table_name}.${colName}`;
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
// endregion

// region Navigation handlers
function onTypeChange() {
  selectedDataset.value = null;
  selectedTable.value = null;
  if (selectedType.value === 'sources') catalogStore.loadSources();
  else catalogStore.loadTargets();
}

async function onDatasetChange() {
  selectedTable.value = null;
  if (selectedDataset.value) {
    tableListLoading.value = true;
    loadSuccessMessage.value = null;
    try {
      await catalogStore.loadCatalog(selectedType.value, selectedDataset.value);
      showLoadSuccess(
        tableOptions.value.length
          ? `Data Catalog loaded ${tableOptions.value.length} tables for ${selectedDataset.value}.`
          : `Data Catalog loaded ${selectedDataset.value}, but no tables were found.`,
      );
    } catch (e) {
      Notify.create({
        message: `Failed to load Data Catalog tables: ${e}`,
        color: 'negative',
        position: 'top',
      });
    } finally {
      tableListLoading.value = false;
    }
  }
}

async function onTableChange() {
  if (!selectedDataset.value || !selectedTable.value) return;
  await catalogStore.loadTable(selectedType.value, selectedDataset.value, selectedTable.value);
  await annotationStore.loadAnnotations(selectedDataset.value);
  applyAnnotations();
  loadGlossaryRefs();
  loadAssessmentSummary();
}

async function loadAssessmentSummary() {
  assessmentSummary.value = null;
  // Discovery (and the assessment endpoint) only serves source datasets.
  if (selectedType.value !== 'sources') return;
  const t = catalogStore.activeTable;
  if (!selectedDataset.value || !t) return;
  const qualified = `${t.schema_name}.${t.table_name}`;
  assessmentLoading.value = true;
  try {
    const res = await getTableAssessment(selectedDataset.value, qualified);
    assessmentSummary.value = {
      total: res.summary.total,
      high: res.summary.by_severity.high ?? 0,
      attention: res.summary.by_severity.attention ?? 0,
    };
  } catch (e) {
    // eslint-disable-next-line no-console
    console.debug('Catalog: assessment summary failed', e);
  } finally {
    assessmentLoading.value = false;
  }
}

function openInDiscovery() {
  const t = catalogStore.activeTable;
  if (!selectedDataset.value || !t) return;
  const qualified = `${t.schema_name}.${t.table_name}`;
  void router.push({
    path: '/tools/discovery',
    query: { dataset: selectedDataset.value, table: qualified },
  });
}

function applyAnnotations() {
  const cols = catalogStore.activeTable?.columns ?? [];
  const schemaName = catalogStore.activeTable?.schema_name ?? '';
  const tableName = catalogStore.activeTable?.table_name ?? '';
  const key = `${schemaName}.${tableName}`;
  const ann = annotationStore.overlay?.annotations?.[key];

  tableUserDesc.value = ann?.user_description ?? '';
  tableMappingInstr.value = ann?.mapping_instructions ?? '';

  const colAnn = ann?.columns ?? {};
  editedDescriptions.value = Object.fromEntries(
    cols.map(c => [c.name, colAnn[c.name]?.user_description ?? '']),
  );
  editedMappingInstr.value = Object.fromEntries(
    cols.map(c => [c.name, colAnn[c.name]?.mapping_instructions ?? '']),
  );
}
// endregion

// region Glossary cross-references
async function loadGlossaryRefs() {
  const cols = catalogStore.activeTable?.columns ?? [];
  const map: Record<string, GlossaryTerm | null> = {};
  const results = await Promise.allSettled(
    cols.map(async (col) => {
      const ref = colRef(col.name);
      if (!ref) return { name: col.name, term: null };
      const terms = await crossRef(ref);
      return { name: col.name, term: terms.length ? terms[0] : null };
    }),
  );
  for (const r of results) {
    if (r.status === 'fulfilled' && r.value) {
      map[r.value.name] = r.value.term;
    }
  }
  glossaryMap.value = map;
}

function goToGlossaryTerm(id: string) {
  router.push({ path: '/tools/glossary', query: { term: id } });
}

function addToGlossary(col: Column) {
  const t = catalogStore.activeTable;
  if (!t) return;
  const title = col.name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  glossaryStore.setPrefill({
    title,
    tags: [],
    related_objects: [colRef(col.name)],
  });
  router.push({ path: '/tools/glossary', query: { new: '1' } });
}
// endregion

// region Save
async function onSaveAnnotation(_colName: string) {
  if (!selectedDataset.value || !catalogStore.activeTable) return;
  const key = `${catalogStore.activeTable.schema_name}.${catalogStore.activeTable.table_name}`;
  await annotationStore.saveAnnotations(selectedDataset.value, key, {
    user_description: tableUserDesc.value || null,
    mapping_instructions: tableMappingInstr.value || null,
    columns: Object.fromEntries(
      catalogStore.activeTable.columns.map(c => [
        c.name,
        {
          user_description: editedDescriptions.value[c.name] || null,
          mapping_instructions: editedMappingInstr.value[c.name] || null,
        },
      ]),
    ),
  });
}

async function onSaveTableAnnotations() {
  await onSaveAnnotation('');
}

async function onSaveAll() {
  saving.value = true;
  try {
    await onSaveAnnotation('');
    Notify.create({ message: 'Descriptions saved', color: 'positive', position: 'top', timeout: 1500 });
  } finally {
    saving.value = false;
  }
}
// endregion

// region AI generation
async function onAiGenerateCol(colName: string, field: string) {
  generatingCol.value = `${colName}:${field}`;
  try {
    const results = await catalogStore.aiGenerate(field, colName);
    const val = results[colName] ?? '';
    if (field === 'user_description') {
      editedDescriptions.value[colName] = val;
    } else {
      editedMappingInstr.value[colName] = val;
    }
    await onSaveAnnotation(colName);
  } catch (e) {
    Notify.create({ message: `AI generation failed: ${e}`, color: 'negative', position: 'top' });
  } finally {
    generatingCol.value = null;
  }
}

async function onAiGenerateAll(field: string) {
  generatingAll.value = field;
  try {
    const results = await catalogStore.aiGenerate(field);
    for (const [colName, val] of Object.entries(results)) {
      if (field === 'user_description') {
        editedDescriptions.value[colName] = val;
      } else {
        editedMappingInstr.value[colName] = val;
      }
    }
    await onSaveAnnotation('');
    Notify.create({ message: `Generated ${field.replace('_', ' ')} for all columns`, color: 'positive', position: 'top', timeout: 2000 });
  } catch (e) {
    Notify.create({ message: `AI generation failed: ${e}`, color: 'negative', position: 'top' });
  } finally {
    generatingAll.value = null;
  }
}

async function onAiGenerateTableField(field: string) {
  // Table-level AI generation uses "all columns" context but returns a summary
  if (field === 'user_description') generatingTableDesc.value = true;
  else generatingTableMapping.value = true;
  try {
    const results = await catalogStore.aiGenerate(field);
    // For table-level, take first result or combine
    const combined = Object.values(results).join(' ');
    if (field === 'user_description') tableUserDesc.value = combined;
    else tableMappingInstr.value = combined;
    await onSaveTableAnnotations();
  } catch (e) {
    Notify.create({ message: `AI generation failed: ${e}`, color: 'negative', position: 'top' });
  } finally {
    generatingTableDesc.value = false;
    generatingTableMapping.value = false;
  }
}
// endregion

// region Unique values popover
function openUniquePopover(event: Event, col: Column) {
  uniquePopoverCol.value = col;
  uniqueFilter.value = '';
  uniquePopoverTarget.value = event.currentTarget as Element;
  uniquePopoverVisible.value = true;
}
// endregion

// region Init
onMounted(async () => {
  await Promise.all([catalogStore.loadSources(), catalogStore.loadTargets()]);
  if (route.query.type === 'sources' || route.query.type === 'targets') {
    selectedType.value = route.query.type;
  }
  if (route.query.dataset) {
    selectedDataset.value = route.query.dataset as string;
    await onDatasetChange();
    if (route.query.table) {
      selectedTable.value = route.query.table as string;
      await onTableChange();
    }
  }
});

onBeforeUnmount(() => {
  if (loadSuccessTimer !== null) {
    window.clearTimeout(loadSuccessTimer);
  }
});
// endregion
</script>

<style scoped lang="scss">
.catalog-page {
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
  display: flex;
  align-items: center;
}

.catalog-table {
  width: 100%;
  table-layout: fixed;

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
    word-wrap: break-word;
    overflow-wrap: break-word;
    white-space: normal;
  }

  .alt-row {
    background: #fafafa;
  }
}

.col-name-th {
  width: 160px;
}
.col-type-th {
  width: 100px;
}
.col-narrow-th {
  width: 70px;
}
.col-desc-th {
  width: 220px;
  max-width: 280px;
}

.desc-cell {
  max-width: 280px;
}

.desc-wrap {
  white-space: pre-wrap !important;
  word-wrap: break-word !important;
  overflow-wrap: break-word !important;
}

.col-glossary-th {
  width: 130px;
}

.unique-link {
  cursor: pointer;
  color: #0d4da1;
  text-decoration: underline;
  text-decoration-style: dotted;
  &:hover {
    text-decoration-style: solid;
  }
}

.unique-popover {
  min-width: 280px;
  max-width: 360px;
  border-radius: 12px !important;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.12) !important;
}
</style>

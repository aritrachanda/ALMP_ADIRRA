<template>
  <q-page class="settings-page">
    <h3 class="page-title">Settings</h3>
    <p class="page-caption">Application settings with separate centralized export and import workspaces.</p>

    <q-tabs v-model="activeTab" dense align="left" active-color="primary" indicator-color="primary" class="q-mb-md">
      <q-tab name="export" label="Export Center" icon="folder_zip" />
      <q-tab name="import" label="Import Center" icon="upload_file" />
      <q-tab name="integrations" label="Integrations" icon="hub" />
      <q-tab name="environment" label="Environment" icon="tune" />
      <q-tab name="ai-persona" label="Chat Assistant Persona" icon="smart_toy" />
      <q-tab name="ai-governance" label="AI Governance" icon="policy" />
    </q-tabs>

    <q-tab-panels v-model="activeTab" animated class="tab-panels">
      <!-- ───────── Export Center ───────── -->
      <q-tab-panel name="export">
        <div class="hero-card">
          <h4>Export center</h4>
          <p>Package the governed working set for download today, while previewing the handoff patterns that will later connect ADIRRA to enterprise catalog platforms.</p>
        </div>

        <!-- Showcase cards -->
        <div class="showcase-grid q-mt-md">
          <div class="showcase-card card-zip">
            <div class="card-head"><div class="card-logo"><q-icon name="folder_zip" size="20px" color="teal" /></div>
              <div><h5>ZIP package</h5><p class="mini">Bundle selected glossary, catalog, mapping, and annotation artifacts into one portable export.</p></div>
            </div>
            <span class="pill pill-live">Available now</span>
          </div>
          <div class="showcase-card card-pdf">
            <div class="card-head"><div class="card-logo"><q-icon name="picture_as_pdf" size="20px" color="red" /></div>
              <div><h5>PDF summary</h5><p class="mini">Generate a compact handoff summary for reviewers, steering meetings, or governance sign-off packs.</p></div>
            </div>
            <span class="pill pill-live">Available now</span>
          </div>
          <div class="showcase-card card-sync">
            <div class="card-head"><div class="card-logo card-logo-pair"><GovernanceLogo system="collibra" :size="16" /><GovernanceLogo system="purview" :size="16" /></div>
              <div><h5>Enterprise handoff</h5><p class="mini">Keep the same export package model while preparing future sync paths into Collibra and Microsoft Purview.</p></div>
            </div>
            <span class="pill pill-future">Planned integration flow</span>
          </div>
        </div>

        <q-banner class="q-mt-md" rounded dense>
          <template #avatar><q-icon name="info" color="primary" /></template>
          Term-level export remains available from each Business Glossary term page. This centralized export view packages one component, multiple components, or the full governance set together.
        </q-banner>

        <!-- Metrics -->
        <div v-if="inventory" class="metric-row q-mt-md">
          <div class="metric-card"><div class="metric-val">{{ inventory.glossary_terms }}</div><div class="metric-lbl">Glossary terms</div></div>
          <div class="metric-card"><div class="metric-val">{{ inventory.source_datasets.length }}</div><div class="metric-lbl">Source catalogs</div></div>
          <div class="metric-card"><div class="metric-val">{{ inventory.target_datasets.length }}</div><div class="metric-lbl">Target catalogs</div></div>
          <div class="metric-card"><div class="metric-val">{{ inventory.mapping_files.length }}</div><div class="metric-lbl">Mappings</div></div>
          <div class="metric-card"><div class="metric-val">{{ inventory.annotation_count }}</div><div class="metric-lbl">Annotation overlays</div></div>
        </div>

        <h5 class="q-mt-lg q-mb-sm">Export package builder</h5>
        <p class="mini q-mb-md">Build a ZIP package or a PDF summary from the app's current governance artifacts. Select one component, multiple components, or everything together, then narrow to individual items where supported.</p>

        <q-select v-model="selectedComponents" :options="componentOptions" multiple chips outlined dense label="Components to include" class="q-mb-md" />

        <div class="builder-layout">
          <!-- Left: component expanders -->
          <div class="builder-left">
            <q-expansion-item label="Business Glossary" default-opened header-class="exp-header">
              <q-card flat bordered class="exp-body">
                <q-card-section>
                  <q-toggle v-model="exp.glossaryEnabled" label="Include Business Glossary" :disable="!compGlossary" />
                  <q-option-group v-model="exp.glossaryScope" :options="[{label:'Entire glossary',value:'entire'},{label:'Selected terms',value:'selected'}]" inline :disable="!exp.glossaryEnabled" class="q-mt-xs" />
                  <q-select v-if="exp.glossaryScope==='selected'" v-model="exp.selectedTermIds" :options="termSelectOptions" multiple chips outlined dense label="Glossary terms" option-value="value" option-label="label" emit-value map-options :disable="!exp.glossaryEnabled" class="q-mt-sm" />
                  <q-toggle v-model="exp.includeMeta" label="Include glossary group descriptions" :disable="!exp.glossaryEnabled" />
                  <div class="row q-gutter-sm q-mt-xs">
                    <q-toggle v-model="exp.includeDescriptions" label="Descriptions & context" :disable="!exp.glossaryEnabled" dense />
                    <q-toggle v-model="exp.includeSynonyms" label="Synonyms & tags" :disable="!exp.glossaryEnabled" dense />
                    <q-toggle v-model="exp.includeRelated" label="Related objects" :disable="!exp.glossaryEnabled" dense />
                    <q-toggle v-model="exp.includeGovernance" label="Status & stewardship" :disable="!exp.glossaryEnabled" dense />
                    <q-toggle v-model="exp.includeAi" label="AI-generated markers" :disable="!exp.glossaryEnabled" dense />
                  </div>
                </q-card-section>
              </q-card>
            </q-expansion-item>

            <q-expansion-item label="Data Catalog & Dictionary" default-opened header-class="exp-header" class="q-mt-sm">
              <q-card flat bordered class="exp-body">
                <q-card-section>
                  <q-option-group v-model="exp.catalogScope" :options="[{label:'Everything available',value:'all'},{label:'Selected datasets',value:'selected'}]" inline :disable="!compCatalog" class="q-mb-sm" />
                  <q-toggle v-model="exp.includeAnnotations" label="Include user annotation overlays" :disable="!compCatalog" />
                  <q-select v-if="exp.catalogScope==='selected'" v-model="exp.selectedSources" :options="inventory?.source_datasets??[]" multiple chips outlined dense label="Source datasets" :disable="!compCatalog" class="q-mt-sm" />
                  <q-select v-if="exp.catalogScope==='selected'" v-model="exp.selectedTargets" :options="inventory?.target_datasets??[]" multiple chips outlined dense label="Target datasets" :disable="!compCatalog" class="q-mt-sm" />
                </q-card-section>
              </q-card>
            </q-expansion-item>

            <q-expansion-item label="Mappings" default-opened header-class="exp-header" class="q-mt-sm">
              <q-card flat bordered class="exp-body">
                <q-card-section>
                  <q-option-group v-model="exp.mappingScope" :options="[{label:'All mappings',value:'all'},{label:'Selected mapping files',value:'selected'}]" inline :disable="!compMapping" class="q-mb-sm" />
                  <q-select v-if="exp.mappingScope==='selected'" v-model="exp.selectedMappings" :options="inventory?.mapping_files??[]" multiple chips outlined dense label="Mapping files" :disable="!compMapping" class="q-mt-sm" />
                </q-card-section>
              </q-card>
            </q-expansion-item>
          </div>

          <!-- Right: preview & download -->
          <div class="builder-right">
            <h5>Export preview</h5>
            <p class="mini q-mb-sm">A centralized view of the structure, selected components, and the files that would be exported.</p>
            <pre class="json-preview">{{ exportPreviewJson }}</pre>

            <div class="delivery-note q-mt-md">
              <strong>Delivery options</strong>
              <p class="mini">Use the ZIP package for machine-readable governance artifacts, or the PDF summary for meeting-ready export documentation.</p>
            </div>

            <q-btn label="Download ZIP package" icon="folder_zip" color="primary" class="full-width q-mt-md" :loading="downloading==='zip'" :disable="!hasExportContent" @click="doExportZip" />
            <q-btn label="Download PDF summary" icon="picture_as_pdf" color="secondary" class="full-width q-mt-sm" :loading="downloading==='pdf'" :disable="!hasExportContent" @click="doExportPdf" />
            <p v-if="!hasExportContent" class="mini q-mt-xs text-center">Choose at least one artifact to populate the export outputs.</p>
            <p v-else class="mini q-mt-xs text-center">ZIP contains YAML artifacts plus a manifest.json summary. PDF contains a compact export handoff sheet.</p>
          </div>
        </div>
      </q-tab-panel>

      <!-- ───────── Import Center ───────── -->
      <q-tab-panel name="import">
        <div class="hero-card">
          <h4>Import center</h4>
          <p>Bring prior governance work into the app with a controlled first-cut workflow: upload, detect, preview, choose a merge strategy, and apply into the canonical YAML files.</p>
        </div>

        <div class="showcase-grid q-mt-md">
          <div class="showcase-card card-zip">
            <div class="card-head"><div class="card-logo step-badge">1</div>
              <div><h5>Upload and detect</h5><p class="mini">Choose the artifact lane and upload a YAML, CSV, or Excel file where that lane supports it.</p></div>
            </div>
            <span class="pill pill-live">Working now</span>
          </div>
          <div class="showcase-card card-pdf">
            <div class="card-head"><div class="card-logo step-badge">2</div>
              <div><h5>Preview and compare</h5><p class="mini">See record counts, likely creates vs updates, and the first rows before committing any changes.</p></div>
            </div>
            <span class="pill pill-live">Working now</span>
          </div>
          <div class="showcase-card card-sync">
            <div class="card-head"><div class="card-logo step-badge">3</div>
              <div><h5>Apply to canonical files</h5><p class="mini">Write the imported content into the existing glossary or mapping YAML structure used by the app.</p></div>
            </div>
            <span class="pill pill-live">Working now</span>
          </div>
        </div>

        <div class="import-layout q-mt-lg">
          <div class="import-left">
            <q-option-group v-model="imp.lane" :options="importLanes" inline class="q-mb-md" />

            <q-select v-if="imp.lane!=='mappings'" v-model="imp.mergeMode" :options="mergeModes" outlined dense label="Merge strategy" class="q-mb-md" />
            <p class="mini q-mb-sm">{{ importHelperText }}</p>

            <q-file v-model="imp.file" outlined dense :accept="importAccept" label="Upload import file" class="q-mb-md" @update:model-value="onFileSelected">
              <template #prepend><q-icon name="attach_file" /></template>
            </q-file>

            <template v-if="imp.lane==='mappings'">
              <q-input v-model="imp.mappingDest" outlined dense label="Destination mapping file" class="q-mb-sm" />
              <q-toggle v-model="imp.replaceExisting" label="Replace existing file if present" />
            </template>
          </div>

          <div class="import-right">
            <h5>Canonical landing files</h5>
            <code class="q-mb-sm" style="display:block">{{ canonicalFile }}</code>
            <p class="mini q-mb-md">This first cut updates the same YAML-backed files the current app already reads.</p>

            <template v-if="imp.result">
              <q-banner rounded class="bg-positive text-white q-mb-md">
                <template v-if="imp.result.stats">
                  Import applied. Created {{ imp.result.stats.created }}, updated {{ imp.result.stats.updated }}, skipped {{ imp.result.stats.skipped }}.
                </template>
                <template v-else>
                  Mapping saved to {{ imp.result.destination }}.
                </template>
              </q-banner>
            </template>

            <q-btn v-if="imp.file" :label="applyLabel" color="primary" class="full-width" :loading="imp.applying" @click="doImport" />
            <p v-else class="mini">Upload a file to preview the import and enable apply controls.</p>
          </div>
        </div>

        <q-separator class="q-my-md" />
        <p class="mini"><strong>Current first-cut scope</strong></p>
        <ul class="mini">
          <li>Business Glossary import: working for YAML</li>
          <li>Mapping import: working for YAML mapping drafts</li>
          <li>Catalog annotation overlays and spreadsheet-driven mapping conversion: next iteration</li>
        </ul>
      </q-tab-panel>

      <!-- ───────── Integrations ───────── -->
      <q-tab-panel name="integrations">
        <div class="hero-card">
          <h4>Integrations</h4>
          <p>Shape future outbound sync patterns now, while keeping the current demo honest about what is configured and what is still planned.</p>
        </div>

        <div class="showcase-grid q-mt-md" style="grid-template-columns:repeat(2,1fr)">
          <div class="int-card">
            <div class="card-head"><div class="card-logo"><GovernanceLogo system="collibra" :size="20" /></div>
              <div><h5>Collibra</h5><p class="mini">Enterprise governance catalog handoff for glossary terms, business descriptions, ownership, and status-oriented metadata.</p></div>
            </div>
            <span class="pill pill-future">Planned</span>
          </div>
          <div class="int-card">
            <div class="card-head"><div class="card-logo"><GovernanceLogo system="purview" :size="20" /></div>
              <div><h5>Microsoft Purview</h5><p class="mini">Azure Data Catalog integration for schema classification, sensitivity labels, and lineage propagation.</p></div>
            </div>
            <span class="pill pill-future">Planned</span>
          </div>
        </div>

        <div class="section-label q-mt-xl q-mb-sm">Active connections</div>
        <div class="showcase-grid">
          <div class="int-card" v-for="c in activeConnections" :key="c.title">
            <div class="card-head"><div class="card-logo"><q-icon :name="c.icon" size="20px" color="primary" /></div>
              <div><h5>{{ c.title }}</h5><p class="mini">{{ c.desc }}</p></div>
            </div>
            <span class="pill pill-live">Live</span>
          </div>
        </div>
      </q-tab-panel>

      <!-- ───────── Environment ───────── -->
      <q-tab-panel name="environment">
        <div class="hero-card">
          <h4>Environment</h4>
          <p>Configuration snapshot of the running application instance, resolved paths, and feature flags.</p>
        </div>

        <div class="env-grid q-mt-md">
          <div class="env-section">
            <h5>File paths</h5>
            <q-list dense bordered class="rounded-borders">
              <q-item v-for="(val,key) in envPaths" :key="key">
                <q-item-section><q-item-label>{{ key }}</q-item-label></q-item-section>
                <q-item-section side><code>{{ val }}</code></q-item-section>
              </q-item>
            </q-list>
          </div>
          <div class="env-section">
            <h5>Governance scope</h5>
            <q-list dense bordered class="rounded-borders" v-if="inventory">
              <q-item><q-item-section>Glossary terms</q-item-section><q-item-section side>{{ inventory.glossary_terms }}</q-item-section></q-item>
              <q-item><q-item-section>Source catalogs</q-item-section><q-item-section side>{{ inventory.source_datasets.length }}</q-item-section></q-item>
              <q-item><q-item-section>Target catalogs</q-item-section><q-item-section side>{{ inventory.target_datasets.length }}</q-item-section></q-item>
              <q-item><q-item-section>Mapping artifacts</q-item-section><q-item-section side>{{ inventory.mapping_files.length }}</q-item-section></q-item>
              <q-item><q-item-section>Annotation overlays</q-item-section><q-item-section side>{{ inventory.annotation_count }}</q-item-section></q-item>
            </q-list>
          </div>
        </div>
      </q-tab-panel>

      <!-- ───────── AI Persona ───────── -->
      <q-tab-panel name="ai-persona">
        <div class="hero-card hero-card--persona">
          <h4>Chat Assistant Persona</h4>
          <p>Customise how the chat assistant on Home presents itself, reasons, and formats answers — this governs chat only. Changes apply to the next message — no restart needed.</p>
        </div>

        <div v-if="personaStore.loading" class="q-mt-lg flex flex-center"><q-spinner-dots color="primary" size="40px" /></div>

        <template v-else>
          <div class="persona-layout q-mt-lg">

            <!-- Left: Identity -->
            <div class="persona-section">
              <div class="section-label q-mb-sm">Identity</div>

              <q-input v-model="draft.name" outlined dense label="Assistant name" class="q-mb-sm"
                hint="Displayed in the chat header and throughout the UI." />

              <q-input v-model="draft.role" outlined dense label="Role" class="q-mb-sm"
                hint="Injected into the system prompt as the assistant's professional identity." />

              <q-select
                v-model="draft.expertise"
                outlined dense multiple use-chips use-input new-value-mode="add-unique"
                label="Expertise areas" class="q-mb-sm"
                hint="Press Enter to add. Shown to the model as specialist domains."
                :input-debounce="0"
              />

              <q-input v-model="draft.avatar_url" outlined dense label="Avatar URL (optional)" class="q-mb-sm"
                hint="HTTPS image URL shown in the chat floater header." />
            </div>

            <!-- Right: Behaviour -->
            <div class="persona-section">
              <div class="section-label q-mb-sm">Behaviour</div>

              <div class="persona-field-label">Tone</div>
              <q-option-group v-model="draft.tone" inline :options="toneOptions" class="q-mb-sm" />

              <div class="persona-field-label">Verbosity</div>
              <q-option-group v-model="draft.verbosity" inline :options="verbosityOptions" class="q-mb-sm" />

              <div class="persona-field-label">Response format</div>
              <q-option-group v-model="draft.response_format" inline :options="formatOptions" class="q-mb-sm" />

              <div class="section-label q-mt-md q-mb-xs">What the assistant can access</div>
              <p class="mini q-mb-sm">Turn a topic off and the assistant loses that tool right away — it can't look it up or discuss it. Turn it back on and access returns just as fast. Nothing else in the app is affected.</p>
              <div class="context-toggles">
                <q-toggle v-model="draft.context.glossary_links" label="Glossary linkage" dense />
                <q-toggle v-model="draft.context.mapping_candidates" label="Mapping candidates" dense />
                <q-toggle v-model="draft.context.profiling_stats" label="Profiling &amp; quality findings" dense />
                <q-toggle v-model="draft.context.audit_history" label="Audit history" dense />
                <q-toggle v-model="draft.knowledge_sources.crr3_regulation" label="CRR3 regulation (EU 2024/1623)" dense />
                <q-toggle v-model="draft.knowledge_sources.eba_dpm" label="EBA DPM 2.0 (COREP / FINREP templates)" dense />
                <div class="ks-placeholder">
                  <q-toggle v-model="draft.knowledge_sources.internal_kb" label="Internal knowledge base" dense disable />
                  <q-badge color="grey-5" text-color="grey-8" label="Not built yet" class="q-ml-sm" />
                </div>
                <div class="ks-placeholder">
                  <q-toggle v-model="draft.knowledge_sources.policy_documents" label="Policy documents" dense disable />
                  <q-badge color="grey-5" text-color="grey-8" label="Not built yet" class="q-ml-sm" />
                </div>
              </div>

              <div class="section-label q-mt-md q-mb-xs">Inference</div>
              <div class="persona-field-label">
                Temperature
                <span class="persona-val-chip">{{ draft.inference.temperature ?? 'model default' }}</span>
              </div>
              <q-slider
                v-model="draft.inference.temperature"
                :min="0" :max="2" :step="0.05"
                label color="primary" class="q-mb-xs q-px-sm"
              />
              <p class="mini q-mb-sm">Higher = more creative; lower = more deterministic. May have no effect on reasoning-class models.</p>
            </div>
          </div>

          <!-- Actions -->
          <div class="persona-actions q-mt-lg">
            <q-banner v-if="personaStore.error" class="bg-negative text-white q-mb-sm" rounded dense>{{ personaStore.error }}</q-banner>
            <q-banner v-if="personaStore.saveSuccess" class="bg-positive text-white q-mb-sm" rounded dense>Persona saved — next message will use the updated settings.</q-banner>
            <q-btn label="Save persona" icon="save" color="primary" :loading="personaStore.saving" @click="doSavePersona" />
            <q-btn label="Reset to defaults" flat color="negative" class="q-ml-sm" :loading="personaStore.saving" @click="doResetPersona" />
          </div>
        </template>
      </q-tab-panel>

      <!-- ───────── AI Governance ───────── -->
      <q-tab-panel name="ai-governance">
        <div class="hero-card hero-card--persona">
          <h4>AI Governance</h4>
          <p>How ADIRRA constrains what reaches an LLM, and the standing rules every AI feature operates under — platform-wide, not tied to chat alone.</p>
        </div>

        <AiGovernancePanel :api="API" class="q-mt-lg" />
      </q-tab-panel>
    </q-tab-panels>
  </q-page>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { useRoute } from 'vue-router';
import GovernanceLogo from 'src/components/GovernanceLogo.vue';
import AiGovernancePanel from 'src/components/AiGovernancePanel.vue';
import { usePersonaStore } from 'src/stores/personaStore';
import type { Persona } from 'src/stores/personaStore';
import {
  fetchExportInventory,
  downloadZip,
  downloadPdf,
  importGlossary,
  importMapping,
  type ExportInventory,
  type ExportConfig,
} from '../api/settings';

// ── Tab state ──
const VALID_TABS = ['export', 'import', 'integrations', 'environment', 'ai-persona', 'ai-governance'];
const route = useRoute();
const requestedTab = route.query.tab;
const activeTab = ref(typeof requestedTab === 'string' && VALID_TABS.includes(requestedTab) ? requestedTab : 'export');

const API = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://127.0.0.1:8000';

// ── AI Persona ──
const personaStore = usePersonaStore();

const toneOptions = [
  { label: 'Precise', value: 'precise' },
  { label: 'Friendly', value: 'friendly' },
  { label: 'Formal', value: 'formal' },
  { label: 'Concise', value: 'concise' },
];
const verbosityOptions = [
  { label: 'Terse', value: 'terse' },
  { label: 'Balanced', value: 'balanced' },
  { label: 'Detailed', value: 'detailed' },
];
const formatOptions = [
  { label: 'Prose', value: 'prose' },
  { label: 'Bullets', value: 'bullets' },
  { label: 'Auto', value: 'auto' },
];

function _clonePersona(p: Persona): Persona {
  return JSON.parse(JSON.stringify(p));
}

const draft = ref<Persona>(_clonePersona(personaStore.persona));

// Keep draft in sync when store loads from API
watch(() => personaStore.persona, (p) => { draft.value = _clonePersona(p); }, { deep: true });

// Load persona on first visit to the tab
watch(activeTab, async (tab) => {
  if (tab === 'ai-persona' && !personaStore.loading) {
    await personaStore.loadPersona();
  }
});

async function doSavePersona() {
  await personaStore.savePersona(draft.value);
}

async function doResetPersona() {
  await personaStore.resetPersona();
}

// ── Export inventory ──
const inventory = ref<ExportInventory | null>(null);
onMounted(async () => {
  try { inventory.value = await fetchExportInventory(); } catch { /* noop */ }
});

// ── Export config ──
const componentOptions = ['Business Glossary', 'Data Catalog & Dictionary', 'Mappings'];
const selectedComponents = ref([...componentOptions]);

const compGlossary = computed(() => selectedComponents.value.includes('Business Glossary'));
const compCatalog = computed(() => selectedComponents.value.includes('Data Catalog & Dictionary'));
const compMapping = computed(() => selectedComponents.value.includes('Mappings'));

const exp = ref({
  glossaryEnabled: true,
  glossaryScope: 'entire' as 'entire' | 'selected',
  selectedTermIds: [] as string[],
  includeMeta: true,
  includeDescriptions: true,
  includeSynonyms: true,
  includeRelated: true,
  includeGovernance: true,
  includeAi: false,
  catalogScope: 'all' as 'all' | 'selected',
  selectedSources: [] as string[],
  selectedTargets: [] as string[],
  includeAnnotations: true,
  mappingScope: 'all' as 'all' | 'selected',
  selectedMappings: [] as string[],
});

const termSelectOptions = computed(() =>
  (inventory.value?.term_options ?? []).map(t => ({ label: `${t.title} (${t.id})`, value: t.id }))
);

const resolvedSources = computed(() =>
  compCatalog.value
    ? exp.value.catalogScope === 'all' ? (inventory.value?.source_datasets ?? []) : exp.value.selectedSources
    : []
);
const resolvedTargets = computed(() =>
  compCatalog.value
    ? exp.value.catalogScope === 'all' ? (inventory.value?.target_datasets ?? []) : exp.value.selectedTargets
    : []
);
const resolvedMappings = computed(() =>
  compMapping.value
    ? exp.value.mappingScope === 'all' ? (inventory.value?.mapping_files ?? []) : exp.value.selectedMappings
    : []
);

const hasExportContent = computed(() =>
  (compGlossary.value && exp.value.glossaryEnabled) || resolvedSources.value.length > 0 || resolvedTargets.value.length > 0 || resolvedMappings.value.length > 0
);

function buildConfig(): ExportConfig {
  return {
    components: selectedComponents.value,
    glossary_enabled: compGlossary.value && exp.value.glossaryEnabled,
    glossary_scope: exp.value.glossaryScope,
    selected_term_ids: exp.value.selectedTermIds,
    include_meta: exp.value.includeMeta,
    include_descriptions: exp.value.includeDescriptions,
    include_synonyms_tags: exp.value.includeSynonyms,
    include_related: exp.value.includeRelated,
    include_governance: exp.value.includeGovernance,
    include_ai: exp.value.includeAi,
    selected_sources: resolvedSources.value,
    selected_targets: resolvedTargets.value,
    include_annotations: exp.value.includeAnnotations,
    selected_mappings: resolvedMappings.value,
  };
}

const exportPreviewJson = computed(() => {
  const cfg = buildConfig();
  return JSON.stringify({
    components: cfg.components,
    glossary: { enabled: cfg.glossary_enabled, scope: cfg.glossary_scope, selected_terms: cfg.selected_term_ids },
    catalogs: { sources: cfg.selected_sources, targets: cfg.selected_targets, include_annotations: cfg.include_annotations },
    mappings: cfg.selected_mappings,
  }, null, 2);
});

const downloading = ref<'zip' | 'pdf' | null>(null);
async function doExportZip() {
  downloading.value = 'zip';
  try { await downloadZip(buildConfig()); } finally { downloading.value = null; }
}
async function doExportPdf() {
  downloading.value = 'pdf';
  try { await downloadPdf(buildConfig()); } finally { downloading.value = null; }
}

// ── Import ──
const importLanes = [
  { label: 'Business Glossary', value: 'glossary' },
  { label: 'Mappings', value: 'mappings' },
];
const mergeModes = ['Skip existing', 'Update empty only', 'Overwrite existing'];

const imp = ref({
  lane: 'glossary',
  mergeMode: 'Skip existing',
  file: null as File | null,
  mappingDest: '',
  replaceExisting: false,
  applying: false,
  result: null as { stats?: { created: number; updated: number; skipped: number }; destination?: string } | null,
});

const importHelperText = computed(() =>
  imp.value.lane === 'glossary'
    ? 'Supports exported glossary YAML with a terms list. Merge strategy controls how existing terms are handled.'
    : 'Supports YAML mapping drafts. The file is saved directly into the mappings folder.'
);
const importAccept = computed(() => imp.value.lane === 'glossary' ? '.yaml,.yml' : '.yaml,.yml');
const canonicalFile = computed(() => imp.value.lane === 'glossary' ? 'glossary/glossary.yaml' : 'mappings/*.yaml');
const applyLabel = computed(() => imp.value.lane === 'glossary' ? 'Apply glossary import' : 'Apply mapping import');

function onFileSelected() {
  imp.value.result = null;
  if (imp.value.file && imp.value.lane === 'mappings') {
    imp.value.mappingDest = imp.value.file.name;
  }
}

async function doImport() {
  if (!imp.value.file) return;
  imp.value.applying = true;
  imp.value.result = null;
  try {
    if (imp.value.lane === 'glossary') {
      const modeMap: Record<string, string> = { 'Skip existing': 'skip', 'Update empty only': 'empty', 'Overwrite existing': 'overwrite' };
      imp.value.result = await importGlossary(imp.value.file, modeMap[imp.value.mergeMode] ?? 'skip');
    } else {
      imp.value.result = await importMapping(imp.value.file, imp.value.mappingDest, imp.value.replaceExisting);
    }
  } catch (e) {
    console.error('Import failed', e);
  } finally {
    imp.value.applying = false;
  }
}

// ── Integrations ──
const activeConnections = [
  { icon: 'storage', title: 'DuckDB', desc: 'Local analytical database for profiling and query execution.' },
  { icon: 'smart_toy', title: 'Gemini / OpenAI', desc: 'LLM providers for mapping suggestions, glossary enrichment, and chat.' },
];

// ── Environment ──
const envPaths = {
  'project.yaml': 'project.yaml',
  'connections.yaml': 'connections.yaml',
  'glossary': 'glossary/',
  'sources': 'sources/',
  'targets': 'targets/',
  'mappings': 'mappings/',
};
</script>

<style lang="scss" scoped>
.settings-page {
  padding: 1.5rem 1.5rem 0;
  background: #fdfdfd;
  /* Fill the available viewport height (same pattern as AssetWorkspace) */
  height: 100%;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.page-title {
  margin: 0 0 0.2rem;
  color: #0f172a;
}
.page-caption {
  margin: 0 0 1rem;
  color: #475569;
  font-size: 0.93rem;
}

.tab-panels {
  background: transparent;
  flex: 1;
  min-height: 0;
}

/* Each tab panel is its own scroll container — works for any viewport size */
:deep(.q-panel-parent) {
  height: 100%;
}
:deep(.q-tab-panel) {
  height: 100%;
  overflow-y: auto;
  padding-bottom: 2rem;
  box-sizing: border-box;
}

/* Hero */
.hero-card {
  padding: 1rem 1.1rem;
  border-radius: 18px;
  background: linear-gradient(135deg, #ecfdf3 0%, #f0fdf4 36%, #eff6ff 100%);
  border: 1px solid #bbf7d0;

  h4 { margin: 0; color: #0f172a; }
  p { margin: 0.3rem 0 0; color: #475569; font-size: 0.93rem; }
}

/* Showcase grid */
.showcase-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
}

.showcase-card,
.int-card {
  padding: 1rem;
  border-radius: 18px;
  border: 1px solid #dbeafe;
  background: #ffffff;
  box-shadow: 0 14px 32px rgba(15, 23, 42, 0.06);

  h5 { margin: 0; color: #0f172a; font-size: 0.95rem; }
}

.card-zip { border-color: #99f6e4; background: linear-gradient(180deg, #f0fdfa 0%, #fff 100%); }
.card-pdf { border-color: #fecaca; background: linear-gradient(180deg, #fef2f2 0%, #fff 100%); }
.card-sync { border-color: #c7d2fe; background: linear-gradient(180deg, #eef2ff 0%, #fff 100%); }

.card-head {
  display: flex; align-items: flex-start; gap: 0.7rem; margin-bottom: 0.5rem;
}
.card-logo {
  width: 36px; height: 36px; border-radius: 12px;
  display: inline-flex; align-items: center; justify-content: center;
  background: #f8fafc; border: 1px solid #e2e8f0; flex-shrink: 0;
}

.card-logo-pair {
  gap: 6px;
}

.step-badge {
  font-weight: 800; font-size: 1rem; color: #0d4da1;
}

.pill {
  display: inline-block; padding: 0.22rem 0.58rem; border-radius: 999px;
  font-size: 0.75rem; font-weight: 700; letter-spacing: 0.02em; margin-top: 0.5rem;
}
.pill-live { background: #dcfce7; color: #166534; }
.pill-future { background: #ede9fe; color: #6d28d9; }

.mini { color: #475569; font-size: 0.88rem; margin: 0; }

/* Metrics */
.metric-row {
  display: flex; gap: 1rem; flex-wrap: wrap;
}
.metric-card {
  flex: 1; min-width: 100px; padding: 0.75rem; border-radius: 14px;
  background: #fff; border: 1px solid #e2e8f0; text-align: center;
}
.metric-val { font-size: 1.3rem; font-weight: 800; color: #0d4da1; }
.metric-lbl { font-size: 0.78rem; color: #64748b; margin-top: 0.15rem; }

/* Builder layout */
.builder-layout {
  display: grid; grid-template-columns: 1.3fr 0.9fr; gap: 1.5rem;
}
.builder-left, .builder-right { min-width: 0; }
.builder-right h5 { margin: 0 0 0.3rem; color: #0f172a; }

.exp-header { font-weight: 600; }
.exp-body { border-radius: 0 0 12px 12px; }

.json-preview {
  background: #f1f5f9; border: 1px solid #e2e8f0; border-radius: 10px;
  padding: 0.75rem; font-size: 0.8rem; overflow-x: auto; max-height: 260px;
  white-space: pre-wrap; word-break: break-word;
}

.delivery-note {
  padding: 0.75rem 0.85rem; border-radius: 14px;
  background: #f8fafc; border: 1px dashed #cbd5e1;
}

/* Import layout */
.import-layout {
  display: grid; grid-template-columns: 1.15fr 0.85fr; gap: 1.5rem;
}
.import-left, .import-right { min-width: 0; }
.import-right h5 { margin: 0 0 0.5rem; color: #0f172a; }

/* Environment */
.env-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem;
}
.env-section h5 { margin: 0 0 0.5rem; color: #0f172a; }

.section-label {
  font-size: 0.78rem; font-weight: 800; letter-spacing: 0.1em;
  text-transform: uppercase; color: #0d4da1;
}

/* AI Persona tab */
.hero-card--persona {
  background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 50%, #eff6ff 100%);
  border-color: #bae6fd;
}

.persona-layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
}

.persona-section {
  min-width: 0;
}

.persona-field-label {
  font-size: 0.82rem;
  font-weight: 600;
  color: #374151;
  margin-bottom: 0.25rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.persona-val-chip {
  display: inline-block;
  padding: 0.1rem 0.45rem;
  border-radius: 999px;
  background: #dbeafe;
  color: #1d4ed8;
  font-size: 0.74rem;
  font-weight: 700;
  font-family: 'IBM Plex Mono', monospace;
}

.context-toggles {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.ks-placeholder {
  display: flex;
  align-items: center;
  opacity: 0.6;
}

.persona-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
}
</style>

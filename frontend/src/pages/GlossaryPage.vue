<template>
  <q-page class="glossary-page q-pa-md">
    <div class="glossary-layout">
      <!-- Left panel: tree + search -->
      <div class="left-panel">
        <div class="panel-container q-pa-md">
          <div class="business-glossary-title q-mb-sm">Business Glossary</div>

          <q-input
            v-model="treeFilter"
            clearable
            dense
            outlined
            placeholder="Search for Glossary term or tag"
            class="q-mb-sm glossary-search-input"
            @clear="clearSearchInput"
          >
            <template #append><q-icon name="search" color="grey-7" /></template>
          </q-input>

          <div v-if="showSearchSuggestions" class="glossary-search-suggestions q-mb-sm">
            <q-list dense separator>
              <q-item
                v-for="option in searchSuggestions"
                :key="option.value"
                clickable
                @click="onSearchSelection(option.value)"
              >
                <q-item-section>{{ option.label }}</q-item-section>
              </q-item>
            </q-list>
          </div>

          <div v-if="leftTab === 'tree'" class="row items-end no-wrap q-col-gutter-sm q-mb-sm glossary-sort-row">
            <div class="col-6 glossary-sort-select">
              <q-select
                v-model="groupByMode"
                :options="groupByOptions"
                option-label="label"
                option-value="value"
                emit-value
                map-options
                dense
                outlined
                label="Sort by"
              />
            </div>
            <div class="col-auto">
              <q-btn flat dense no-caps color="primary" label="Add new +" @click="startNewTermForm()" />
            </div>
          </div>

          <div v-if="leftTab === 'tree'" class="row items-center q-mb-sm glossary-tree-actions">
            <q-space />
            <q-btn flat dense no-caps size="sm" color="primary" label="Expand all" @click="expandAllTermsTree" />
            <q-btn flat dense no-caps size="sm" color="grey-7" label="Collapse all" @click="collapseAllTermsTree" />
          </div>

          <q-tabs v-model="leftTab" dense class="text-grey-8 q-mb-sm" active-color="primary" indicator-color="primary">
            <q-tab name="tree" label="Terms" />
            <q-tab name="uncovered" label="Uncovered" />
          </q-tabs>

          <!-- Terms tree -->
          <div v-if="leftTab === 'tree'" class="tree-scroll">
            <q-tree
              v-model:expanded="expandedNodes"
              :nodes="treeNodes"
              node-key="id"
              label-key="label"
              dense
              no-connectors
            >
              <template #default-header="{ node }">
                <div
                  class="tree-node-label"
                  :class="{
                    'tree-node-term': !!node.termId,
                    'tree-node-selected': node.termId && glossaryStore.selectedTerm?.id === node.termId,
                  }"
                  @click="node.termId && selectTerm(node.termId)"
                >
                  {{ node.label }}
                </div>
              </template>
            </q-tree>
          </div>

          <!-- Uncovered concepts -->
          <div v-else class="tree-scroll">
            <div class="row q-gutter-sm q-mb-sm">
              <q-input v-model="uncoveredFilter" dense outlined placeholder="Filter uncovered..." class="col">
                <template #append><q-icon name="search" size="xs" color="grey-7" /></template>
              </q-input>
            </div>
            <q-list separator dense>
              <q-item v-for="uc in filteredUncovered" :key="uc.related_object || uc.column" clickable>
                <q-item-section>
                  <q-item-label class="text-grey-8">{{ uc.column }}</q-item-label>
                  <q-item-label caption>{{ uc.dataset }} / {{ uc.table }}</q-item-label>
                </q-item-section>
                <q-item-section side>
                  <div class="row q-gutter-xs">
                    <q-btn flat dense size="sm" icon="list_alt" color="grey-7" @click="goToCatalog(uc)" />
                    <q-btn flat dense size="sm" icon="add" color="primary" @click="addTermFromUncovered(uc)" />
                  </div>
                </q-item-section>
              </q-item>
            </q-list>
          </div>
        </div>
      </div>

      <!-- Center panel: detail / new term form -->
      <div class="center-panel">
        <!-- New term form -->
        <template v-if="showNewTermForm">
          <div class="panel-container q-pa-lg">
            <div class="text-h5 text-grey-8 q-mb-lg">New Term</div>
            <q-input v-model="newTerm.title" label="Title" outlined dense class="q-mb-sm" />
            <div class="row q-gutter-sm q-mb-sm">
              <q-select
                v-model="newTerm.domain"
                :options="domainOptions"
                label="Domain"
                outlined dense
                use-input
                fill-input
                hide-selected
                new-value-mode="add-unique"
                input-debounce="0"
                class="col"
                hint="Choose an existing domain or type a new one"
              />
              <q-select
                v-model="newTerm.category"
                :options="categoryOptions"
                label="Category"
                outlined dense
                use-input
                fill-input
                hide-selected
                new-value-mode="add-unique"
                input-debounce="0"
                class="col"
                :disable="!newTerm.domain && !allCategoryOptions.length"
                hint="Category options follow the selected domain"
              />
            </div>
            <q-input v-model="newTerm.steward" label="Steward" outlined dense class="q-mb-sm" />
            <div class="row items-center q-mb-xs q-mt-md">
              <span class="section-label">Business Description</span>
              <q-badge v-if="isNewTermAIGenerated('business_description')" class="q-ml-sm ai-badge" outline>
                <q-icon name="bolt" size="12px" class="q-mr-xs" />AI-generated
              </q-badge>
              <q-space />
              <q-btn flat dense size="sm" no-caps icon="auto_awesome" color="primary" label="Generate" :loading="generatingNewField === 'business_description'" @click="onGenerateNewField('business_description', 'field')" />
            </div>
            <q-input v-model="newTerm.business_description" outlined dense type="textarea" rows="3" class="q-mb-sm" />

            <div class="row items-center q-mb-xs q-mt-md">
              <span class="section-label">Detailed Description</span>
              <q-badge v-if="isNewTermAIGenerated('detailed_description')" class="q-ml-sm ai-badge" outline>
                <q-icon name="bolt" size="12px" class="q-mr-xs" />AI-generated
              </q-badge>
              <q-space />
              <q-btn flat dense size="sm" no-caps icon="auto_awesome" color="primary" label="Generate" :loading="generatingNewField === 'detailed_description'" @click="onGenerateNewField('detailed_description', 'field')" />
            </div>
            <q-input v-model="newTerm.detailed_description" outlined dense type="textarea" rows="3" class="q-mb-sm" />

            <div class="row items-center q-mb-xs q-mt-md">
              <span class="section-label">Regulatory Context (CRR3)</span>
              <q-badge v-if="isNewTermAIGenerated('CRR_context')" class="q-ml-sm ai-badge" outline>
                <q-icon name="bolt" size="12px" class="q-mr-xs" />AI-generated
              </q-badge>
              <q-space />
              <q-btn flat dense size="sm" no-caps icon="auto_awesome" color="primary" label="Generate" :loading="generatingNewField === 'CRR_context'" @click="onGenerateNewField('CRR_context', 'crr')" />
            </div>
            <q-input v-model="newTerm.CRR_context" outlined dense type="textarea" rows="3" class="q-mb-sm" />

            <div class="row items-center q-mb-xs q-mt-md">
              <span class="section-label">DPM 2.0 Interpretation</span>
              <q-badge v-if="isNewTermAIGenerated('DPM_context')" class="q-ml-sm ai-badge" outline>
                <q-icon name="bolt" size="12px" class="q-mr-xs" />AI-generated
              </q-badge>
              <q-space />
              <q-btn flat dense size="sm" no-caps icon="auto_awesome" color="primary" label="Generate" :loading="generatingNewField === 'DPM_context'" @click="onGenerateNewField('DPM_context', 'dpm')" />
            </div>
            <q-input v-model="newTerm.DPM_context" outlined dense type="textarea" rows="3" class="q-mb-sm" />

            <div class="row items-center q-mb-xs q-mt-md">
              <span class="section-label">Synonyms & Tags</span>
              <q-badge v-if="isNewTermAIGenerated('synonyms') || isNewTermAIGenerated('tags')" class="q-ml-sm ai-badge" outline>
                <q-icon name="bolt" size="12px" class="q-mr-xs" />AI-generated
              </q-badge>
              <q-space />
              <q-btn flat dense size="sm" no-caps icon="auto_awesome" color="primary" label="Generate" :loading="generatingNewField === 'synonyms_tags'" @click="onGenerateNewField('synonyms_tags', 'synonyms_tags')" />
            </div>
            <q-input v-model="newTermSynonyms" label="Synonyms (comma-separated)" outlined dense class="q-mb-sm" />
            <q-input v-model="newTermTags" label="Tags (comma-separated)" outlined dense class="q-mb-sm" />
            <div class="row items-center q-mb-xs q-mt-md">
              <span class="section-label">Related objects</span>
            </div>
            <div class="related-objects-hint">Format: <code>kind|dataset|schema.table.column</code> &nbsp;e.g. <code>source|banking|public.bank_loans.loan_id</code></div>
            <q-input v-model="newTermRelatedObjects" label="Related objects (one per line)" type="textarea" outlined dense rows="3" class="q-mb-sm" />
            <div class="row q-gutter-sm justify-end q-mt-md">
              <q-btn flat label="Cancel" color="grey-7" @click="cancelNewTermForm" />
              <q-btn color="primary" label="Save" @click="saveNewTerm" />
            </div>
          </div>
        </template>

        <!-- Selected term detail -->
        <template v-else-if="glossaryStore.selectedTerm">
          <div class="panel-container q-pa-lg">
            <!-- Term header -->
            <div class="row items-center q-mb-lg">
              <div class="text-h5 text-grey-8">{{ glossaryStore.selectedTerm.title }}</div>
              <q-space />
              <ExportSyncMenu :term="glossaryStore.selectedTerm" />
              <q-btn flat dense icon="content_copy" color="grey-6" @click="copyToClipboard('title')" class="q-ml-xs">
                <q-tooltip>Copy title</q-tooltip>
              </q-btn>
              <template v-if="!isEditMode">
                <q-btn flat dense icon="edit" color="primary" @click="enterEditMode" class="q-ml-xs">
                  <q-tooltip>Enter edit mode</q-tooltip>
                </q-btn>
              </template>
              <template v-else>
                <q-btn flat dense label="Cancel" color="grey-7" @click="exitEditMode" class="q-ml-xs" />
                <q-btn flat dense label="Save" color="primary" @click="saveTermAndExit" class="q-ml-xs" />
              </template>
              <q-btn flat dense icon="delete_outline" color="negative" @click="onDeleteTerm" class="q-ml-xs">
                <q-tooltip>Delete term</q-tooltip>
              </q-btn>
            </div>

            <!-- Timestamps -->
            <div class="row q-gutter-md q-mb-md text-caption text-grey-6">
              <div>
                <span class="text-weight-bold">Last Updated:</span> {{ formatTimestamp(glossaryStore.selectedTerm.last_updated) }}
              </div>
              <div>
                <span class="text-weight-bold">Last Reviewed:</span> {{ formatTimestamp(glossaryStore.selectedTerm.last_reviewed) }}
              </div>
            </div>

            <div class="section-card q-mb-md header-card">
              <div class="row items-center q-mb-sm">
                <q-space />
                <q-btn v-if="isEditMode" flat dense size="sm" icon="edit" color="primary" @click="toggleEdit('header_meta')" />
              </div>
              <template v-if="editingSection !== 'header_meta'">
                <div class="steward-line q-mt-xs">
                  <q-icon name="person" size="14px" class="q-mr-xs" />
                  Steward: {{ glossaryStore.selectedTerm.steward || 'Not assigned' }}
                </div>
                <div class="row q-gutter-sm q-mt-sm">
                  <q-badge outline color="primary">{{ glossaryStore.selectedTerm.domain || 'No domain' }}</q-badge>
                  <q-badge outline color="grey-7">{{ glossaryStore.selectedTerm.category || 'No category' }}</q-badge>
                  <StatusPill :status="glossaryStore.selectedTerm.status || 'draft'" />
                </div>
              </template>
              <template v-else>
                <q-input v-model="editHeader.title" label="Title" outlined dense class="q-mb-sm" />
                <div class="row q-gutter-sm q-mb-sm">
                  <q-select v-model="editHeader.domain" :options="domainOptions" label="Domain" outlined dense use-input fill-input hide-selected new-value-mode="add-unique" input-debounce="0" class="col" />
                  <q-select v-model="editHeader.category" :options="headerCategoryOptions" label="Category" outlined dense use-input fill-input hide-selected new-value-mode="add-unique" input-debounce="0" class="col" />
                </div>
                <div class="row q-gutter-sm q-mb-sm">
                  <q-input v-model="editHeader.steward" label="Steward" outlined dense class="col" />
                  <q-select v-model="editHeader.status" :options="statusOptions" option-label="label" option-value="value" emit-value map-options label="Review Status" outlined dense class="col">
                    <template #selected-item="scope">
                      <StatusPill :status="String(scope.opt.value)" compact />
                    </template>
                    <template #option="scope">
                      <q-item v-bind="scope.itemProps">
                        <q-item-section>
                          <StatusPill :status="String(scope.opt.value)" compact />
                        </q-item-section>
                      </q-item>
                    </template>
                  </q-select>
                </div>
                <div class="row q-gutter-sm justify-end">
                  <q-btn flat dense label="Cancel" color="grey-7" @click="editingSection = null" />
                  <q-btn flat dense label="Save" color="primary" @click="saveHeaderMeta" />
                </div>
              </template>
            </div>

            <!-- Editable sections -->
            <GlossarySection
              v-for="section in termSections"
              :key="section.key"
              :label="section.label"
              :value="sectionValue(section.key)"
              :ai-generated="isAIGenerated(section.key)"
              :editing="editingSection === section.key"
              :generating="generatingField === section.key"
              :show-generate="section.canGenerate && isEditMode"
              :show-edit-button="isEditMode"
              :generate-label="section.generateLabel"
              @edit="toggleEdit(section.key)"
              @save="saveSection(section.key, $event)"
              @cancel="editingSection = null"
              @copy="copyToClipboard(section.key)"
              @generate="onGenerateField(section.key, section.generateAction)"
            />

            <!-- Synonyms & Tags -->
            <div class="section-card q-mb-md">
              <div class="row items-center q-mb-xs">
                <span class="section-label">Synonyms & Tags</span>
                <q-badge v-if="isAIGenerated('synonyms') || isAIGenerated('tags')" class="q-ml-sm ai-badge" outline>
                  <q-icon name="bolt" size="12px" class="q-mr-xs" />AI-generated
                </q-badge>
                <q-space />
                <q-btn v-if="isEditMode" flat dense size="sm" no-caps icon="auto_awesome" color="primary" label="Generate" :loading="generatingField === 'synonyms_tags'" @click="onGenerateSynonymsTags" class="q-mr-xs" />
                <q-btn flat dense size="sm" icon="content_copy" color="grey-6" @click="copySynonymsTags" />
                <q-btn v-if="isEditMode" flat dense size="sm" icon="edit" color="primary" @click="toggleEdit('synonyms_tags')" />
              </div>
              <template v-if="editingSection !== 'synonyms_tags'">
                <div class="q-mb-xs">
                  <q-chip v-for="s in glossaryStore.selectedTerm.synonyms" :key="s" dense outline color="primary" size="sm">{{ s }}</q-chip>
                  <span v-if="!glossaryStore.selectedTerm.synonyms?.length" class="text-grey-5 text-body2">No synonyms</span>
                </div>
                <div>
                  <q-chip v-for="t in glossaryStore.selectedTerm.tags" :key="t" dense color="grey-3" text-color="grey-8" size="sm">{{ t }}</q-chip>
                  <span v-if="!glossaryStore.selectedTerm.tags?.length" class="text-grey-5 text-body2">No tags</span>
                </div>
              </template>
              <template v-else>
                <q-input v-model="editSynonyms" label="Synonyms (comma-separated)" outlined dense class="q-mb-sm" />
                <q-input v-model="editTags" label="Tags (comma-separated)" outlined dense class="q-mb-sm" />
                <div class="row q-gutter-sm justify-end">
                  <q-btn flat dense label="Cancel" color="grey-7" @click="editingSection = null" />
                  <q-btn flat dense label="Save" color="primary" @click="saveSynonymsTags" />
                </div>
              </template>
            </div>

            <!-- Related Objects -->
            <div class="section-card q-mb-md">
              <div class="row items-center q-mb-xs">
                <span class="section-label">Related objects</span>
                <q-space />
                <q-btn v-if="isEditMode" flat dense size="sm" icon="edit" color="primary" @click="toggleEdit('related_objects')" />
              </div>
              <template v-if="editingSection !== 'related_objects'">
                <div v-if="linkedRelatedObjects.length" class="related-object-grid">
                  <div
                    v-for="ref in linkedRelatedObjects"
                    :key="ref"
                    class="related-object-row"
                  >
                    <div
                      class="related-object-label"
                      :class="{ 'text-primary cursor-pointer': canOpenGlossary(ref) }"
                      @click="canOpenGlossary(ref) && goToGlossaryFromRef(ref)"
                    >
                      {{ formatRelatedObject(ref) }}
                    </div>
                    <div class="row q-gutter-xs q-mt-xs">
                      <q-btn v-if="canOpenGlossary(ref)" flat dense size="sm" no-caps icon="menu_book" color="primary" label="Glossary" @click="goToGlossaryFromRef(ref)" />
                      <q-btn v-if="canOpenInCatalog(ref)" flat dense size="sm" no-caps icon="list_alt" color="primary" label="Catalog" @click="goToRelatedObject(ref, 'catalog')" />
                      <q-btn v-if="canOpenInDiscovery(ref)" flat dense size="sm" no-caps icon="explore" color="grey-7" label="Discovery" @click="goToRelatedObject(ref, 'discovery')" />
                    </div>
                  </div>
                </div>
                <div v-else class="text-grey-5 text-body2">No related catalog objects linked.</div>
              </template>
              <template v-else>
                <q-input
                  v-model="editRelatedObjects"
                  type="textarea"
                  label="Related objects (one per line, format: kind|dataset|schema.table.column)"
                  outlined dense
                  rows="3"
                />
                <div class="row q-gutter-sm justify-end q-mt-sm">
                  <q-btn flat dense label="Cancel" color="grey-7" @click="editingSection = null" />
                  <q-btn flat dense label="Save" color="primary" @click="saveRelatedObjects" />
                </div>
              </template>
            </div>
          </div>
        </template>

        <!-- Loading state -->
        <div v-else-if="glossaryStore.loading" class="panel-container q-pa-xl text-center">
          <q-spinner-oval size="48px" color="primary" class="q-mb-md" />
          <div class="text-grey-6">Loading glossary term...</div>
        </div>

        <!-- Empty state -->
        <div v-else class="panel-container q-pa-xl text-center text-grey-5">
          Select a term from the tree or create a new one.
        </div>
      </div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { copyToClipboard as quasarCopy, Notify } from 'quasar';
import { useGlossaryStore } from 'src/stores/glossaryStore';
import type { GlossaryTerm, UncoveredConcept } from 'src/types';
import GlossarySection from 'src/components/GlossarySection.vue';
import ExportSyncMenu from 'src/components/ExportSyncMenu.vue';
import StatusPill from 'src/components/StatusPill.vue';
import { statusLabel } from 'src/utils/statusDisplay';

const route = useRoute();
const router = useRouter();
const glossaryStore = useGlossaryStore();

// region State
const treeFilter = ref('');
const uncoveredFilter = ref('');
const leftTab = ref('tree');
const showNewTermForm = ref(false);
const newTerm = ref<Partial<GlossaryTerm>>({
  title: '', domain: '', category: '', business_description: '',
  detailed_description: '', steward: '', CRR_context: '', DPM_context: '', ai_generated_fields: [],
});
const newTermSynonyms = ref('');
const newTermTags = ref('');
const newTermRelatedObjects = ref('');
const editingSection = ref<string | null>(null);
const editHeader = ref({ title: '', domain: '', category: '', steward: '', status: 'draft' });
const editSynonyms = ref('');
const editTags = ref('');
const editRelatedObjects = ref('');
const expandedNodes = ref<string[]>([]);
const groupByMode = ref<'alphabetical' | 'domain' | 'category' | 'tags' | 'status'>('category');
const generatingField = ref<string | null>(null);
const generatingNewField = ref<string | null>(null);
const isEditMode = ref(false);
const originalTermSnapshot = ref<GlossaryTerm | null>(null);
// endregion

// region Sections config
interface SectionDef {
  key: string;
  label: string;
  canGenerate: boolean;
  generateLabel?: string;
  generateAction?: string;
}

const termSections: SectionDef[] = [
  { key: 'business_description', label: 'Business description', canGenerate: true, generateLabel: 'Generate', generateAction: 'field' },
  { key: 'detailed_description', label: 'Detailed description', canGenerate: true, generateLabel: 'Generate', generateAction: 'field' },
  { key: 'CRR_context', label: 'CRR3 Interpretation', canGenerate: true, generateLabel: 'Generate', generateAction: 'crr' },
  { key: 'DPM_context', label: 'DPM 2.0 Interpretation', canGenerate: true, generateLabel: 'Generate', generateAction: 'dpm' },
];

interface TreeNode {
  id: string;
  label: string;
  termId?: string;
  children?: TreeNode[];
  searchText?: string;
}

const groupByOptions = [
  { label: 'Alphabetically', value: 'alphabetical' },
  { label: 'Domain', value: 'domain' },
  { label: 'Category', value: 'category' },
  { label: 'Tags', value: 'tags' },
  { label: 'Review Status', value: 'status' },
];

const minSearchChars = 2;
// endregion

// region Tree
function termSearchText(term: GlossaryTerm): string {
  return [term.title, term.domain, term.category, term.status, ...(term.tags ?? []), ...(term.synonyms ?? [])]
    .join(' ')
    .toLowerCase();
}

function buildTermNode(term: GlossaryTerm): TreeNode {
  return {
    id: `t_${term.id}`,
    label: term.title,
    termId: term.id,
    searchText: termSearchText(term),
  };
}

function groupTermsBy(labelFor: (term: GlossaryTerm) => string, prefix: string): TreeNode[] {
  const groups = new Map<string, GlossaryTerm[]>();
  for (const term of glossaryStore.terms) {
    const label = labelFor(term) || 'Unassigned';
    const bucket = groups.get(label) ?? [];
    bucket.push(term);
    groups.set(label, bucket);
  }
  return Array.from(groups.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([label, terms]) => ({
      id: `${prefix}_${label}`,
      label,
      searchText: label.toLowerCase(),
      children: [...terms]
        .sort((a, b) => a.title.localeCompare(b.title))
        .map(buildTermNode),
    }));
}

const treeNodes = computed<TreeNode[]>(() => {
  if (groupByMode.value === 'alphabetical') {
    return groupTermsBy((term) => (term.title?.trim()?.charAt(0) || '#').toUpperCase(), 'alpha');
  }
  if (groupByMode.value === 'category') {
    return groupTermsBy((term) => term.category?.trim() || 'Unassigned', 'category');
  }
  if (groupByMode.value === 'tags') {
    return groupTermsBy((term) => term.tags?.[0]?.trim() || 'Untagged', 'tag');
  }
  if (groupByMode.value === 'status') {
    return groupTermsBy((term) => term.status?.trim() || 'draft', 'status');
  }
  return groupTermsBy((term) => term.domain?.trim() || 'Unassigned', 'domain');
});

const allExpandableNodeIds = computed(() => {
  const ids: string[] = [];
  for (const node of treeNodes.value) {
    ids.push(node.id);
    for (const child of node.children ?? []) {
      if (child.children?.length) ids.push(child.id);
    }
  }
  return ids;
});

const normalizedTreeFilter = computed(() => String(treeFilter.value ?? '').trim().toLowerCase());

const searchSuggestions = computed(() => {
  const query = normalizedTreeFilter.value;
  if (query.length < minSearchChars) return [];
  const matches = glossaryStore.terms
    .filter((term) => term.title.toLowerCase().includes(query))
    .sort((a, b) => a.title.localeCompare(b.title))
    .slice(0, 12)
    .map((term) => ({
      label: term.title,
      value: term.id,
    }));
  return matches;
});

const showSearchSuggestions = computed(() => searchSuggestions.value.length > 0);

const filteredUncovered = computed(() => {
  const q = uncoveredFilter.value.toLowerCase();
  if (!q) return glossaryStore.uncoveredConcepts;
  return glossaryStore.uncoveredConcepts.filter(uc =>
    uc.column.toLowerCase().includes(q) ||
    uc.dataset.toLowerCase().includes(q) ||
    uc.table.toLowerCase().includes(q)
  );
});

const domainOptions = computed(() => {
  const domains = new Set(
    glossaryStore.terms
      .map(term => term.domain?.trim())
      .filter((value): value is string => Boolean(value))
  );
  return Array.from(domains).sort((a, b) => a.localeCompare(b));
});

const allCategoryOptions = computed(() => {
  const categories = new Set(
    glossaryStore.terms
      .map(term => term.category?.trim())
      .filter((value): value is string => Boolean(value))
  );
  return Array.from(categories).sort((a, b) => a.localeCompare(b));
});

const categoryOptions = computed(() => {
  const selectedDomain = newTerm.value.domain?.trim();
  if (!selectedDomain) return allCategoryOptions.value;
  const categories = new Set(
    glossaryStore.terms
      .filter(term => term.domain?.trim() === selectedDomain)
      .map(term => term.category?.trim())
      .filter((value): value is string => Boolean(value))
  );
  return Array.from(categories).sort((a, b) => a.localeCompare(b));
});

const linkedRelatedObjects = computed(() =>
  (glossaryStore.selectedTerm?.related_objects ?? [])
);

const glossaryRefLookup = computed(() => {
  const map = new Map<string, string>();
  for (const term of glossaryStore.terms) {
    const termId = term.id;
    const keys = [term.id, term.title, ...(term.synonyms ?? [])]
      .map(normalizeRefText)
      .filter((v): v is string => Boolean(v));
    for (const key of keys) {
      if (!map.has(key)) map.set(key, termId);
    }
  }
  return map;
});

const headerCategoryOptions = computed(() => {
  const selectedDomain = editHeader.value.domain?.trim();
  if (!selectedDomain) return allCategoryOptions.value;
  const categories = new Set(
    glossaryStore.terms
      .filter(term => term.domain?.trim() === selectedDomain)
      .map(term => term.category?.trim())
      .filter((value): value is string => Boolean(value))
  );
  return Array.from(categories).sort((a, b) => a.localeCompare(b));
});

const statusOptions = ['draft', 'approved', 'retired'].map((status) => ({
  label: statusLabel(status),
  value: status,
}));
// endregion

// region Helpers
function sectionValue(key: string): string {
  const term = glossaryStore.selectedTerm;
  if (!term) return '';
  return String((term as Record<string, unknown>)[key] ?? '');
}

function hasFieldContent(termLike: Partial<GlossaryTerm> | null | undefined, key: string): boolean {
  if (!termLike) return false;
  if (key === 'synonyms') return (termLike.synonyms?.length ?? 0) > 0;
  if (key === 'tags') return (termLike.tags?.length ?? 0) > 0;
  if (key === 'related_objects') return (termLike.related_objects?.length ?? 0) > 0 || splitLines(newTermRelatedObjects.value).length > 0;
  const value = (termLike as Record<string, unknown>)[key];
  return typeof value === 'string' ? value.trim().length > 0 : Boolean(value);
}

function isAIGenerated(key: string): boolean {
  return (glossaryStore.selectedTerm?.ai_generated_fields?.includes(key) ?? false) && hasFieldContent(glossaryStore.selectedTerm, key);
}

function isNewTermAIGenerated(key: string): boolean {
  return (newTerm.value.ai_generated_fields ?? []).includes(key) && hasFieldContent(newTerm.value, key);
}

function formatRelatedObject(ref: string): string {
  const parsed = parseRelatedObject(ref);
  if (parsed) return `${parsed.schema}.${parsed.table}.${parsed.column}  (${parsed.kind}: ${parsed.dataset})`;
  return ref;
}

function normalizeRefText(value: string | null | undefined): string {
  return (value ?? '')
    .trim()
    .toLowerCase()
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ');
}

function resolveGlossaryTermIdFromRef(ref: string): string | null {
  if (parseRelatedObject(ref)) return null;
  const normalized = normalizeRefText(ref);
  if (!normalized) return null;
  return glossaryRefLookup.value.get(normalized) ?? null;
}

function parseRelatedObject(ref: string): { kind: string; dataset: string; schema: string; table: string; column: string } | null {
  const parts = ref.split('|').map(part => part.trim());
  if (parts.length !== 3) return null;
  const objectPath = parts[2].split('.').map(segment => segment.trim()).filter(Boolean);
  if (objectPath.length < 3) return null;
  return {
    kind: parts[0],
    dataset: parts[1],
    schema: objectPath[0],
    table: objectPath[1],
    column: objectPath.slice(2).join('.'),
  };
}

function canOpenInDiscovery(ref: string): boolean {
  const parsed = parseRelatedObject(ref);
  return parsed?.kind === 'source';
}

function canOpenInCatalog(ref: string): boolean {
  return parseRelatedObject(ref)?.kind === 'source';
}

function canOpenGlossary(ref: string): boolean {
  return Boolean(resolveGlossaryTermIdFromRef(ref));
}

function notifyPositive(message: string) {
  Notify.create({ message, color: 'positive', position: 'top', timeout: 1600, icon: 'check' });
}

function notifyWarning(message: string) {
  Notify.create({ message, color: 'warning', textColor: 'dark', position: 'top', timeout: 2200, icon: 'info' });
}

function notifyError(message: string) {
  Notify.create({ message, color: 'negative', position: 'top', timeout: 2600, icon: 'error' });
}

function expandAllTermsTree() {
  expandedNodes.value = [...allExpandableNodeIds.value];
}

function collapseAllTermsTree() {
  expandedNodes.value = [];
}

function splitCsv(value: string): string[] {
  return value.split(',').map(s => s.trim()).filter(Boolean);
}

function splitLines(value: string): string[] {
  return value.split('\n').map(s => s.trim()).filter(Boolean);
}

function hasGeneratedValue(actionKey: string, result: Record<string, unknown>): boolean {
  if (actionKey === 'synonyms_tags') {
    return Array.isArray(result.synonyms) || Array.isArray(result.tags);
  }
  if (actionKey === 'crr') {
    // Treat CRR generation as successful only when CRR_context is populated.
    return Boolean(result.CRR_context);
  }
  if (actionKey === 'dpm') {
    return Boolean(result.DPM_context);
  }
  return Boolean(result[actionKey]);
}

function generationResultKey(key: string, action?: string): string {
  return action === 'field' || !action ? key : action;
}

function formatTimestamp(ts: string | null | undefined): string {
  if (!ts) return 'Never';
  try {
    const date = new Date(ts);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch {
    return 'Unknown';
  }
}
// endregion

// region Actions
function selectTerm(id: string) {
  showNewTermForm.value = false;
  glossaryStore.loadTerm(id);
  editingSection.value = null;
  isEditMode.value = false;
  originalTermSnapshot.value = null;
  void router.replace({ query: { ...route.query, term: id } });
}

function enterEditMode() {
  if (glossaryStore.selectedTerm) {
    originalTermSnapshot.value = { ...glossaryStore.selectedTerm };
  }
  isEditMode.value = true;
}

function exitEditMode() {
  if (originalTermSnapshot.value) {
    glossaryStore.selectedTerm = { ...originalTermSnapshot.value };
  }
  editingSection.value = null;
  isEditMode.value = false;
  originalTermSnapshot.value = null;
}

function applyActiveSectionEdits() {
  const term = glossaryStore.selectedTerm;
  if (!term) return;

  if (editingSection.value === 'header_meta') {
    glossaryStore.selectedTerm = {
      ...term,
      title: editHeader.value.title,
      domain: editHeader.value.domain,
      category: editHeader.value.category,
      steward: editHeader.value.steward,
      status: editHeader.value.status,
    } as GlossaryTerm;
  } else if (editingSection.value === 'synonyms_tags') {
    glossaryStore.selectedTerm = {
      ...term,
      synonyms: splitCsv(editSynonyms.value),
      tags: splitCsv(editTags.value),
    } as GlossaryTerm;
  } else if (editingSection.value === 'related_objects') {
    glossaryStore.selectedTerm = {
      ...term,
      related_objects: splitLines(editRelatedObjects.value),
    } as GlossaryTerm;
  }
}

async function saveTermAndExit() {
  if (!glossaryStore.selectedTerm) return;

  applyActiveSectionEdits();

  const previousStatus = originalTermSnapshot.value?.status?.toLowerCase() ?? '';
  const nextStatus = glossaryStore.selectedTerm.status?.toLowerCase() ?? '';
  const nowIso = new Date().toISOString();
  const lastReviewed = previousStatus !== 'approved' && nextStatus === 'approved'
    ? nowIso
    : (glossaryStore.selectedTerm.last_reviewed ?? null);

  const saved = await glossaryStore.saveTerm({
    ...glossaryStore.selectedTerm,
    last_updated: nowIso,
    last_reviewed: lastReviewed,
  } as GlossaryTerm);

  glossaryStore.selectedTerm = saved;
  originalTermSnapshot.value = { ...saved };
  isEditMode.value = false;
  editingSection.value = null;
  originalTermSnapshot.value = null;

  const termTitle = saved.title || 'Glossary Term';
  notifyPositive(`Glossary for ${termTitle} updated`);
}



function resetNewTermForm() {
  newTerm.value = {
    title: '',
    domain: '',
    category: '',
    business_description: '',
    detailed_description: '',
    steward: '',
    CRR_context: '',
    DPM_context: '',
    ai_generated_fields: [],
  };
  newTermSynonyms.value = '';
  newTermTags.value = '';
  newTermRelatedObjects.value = '';
  generatingNewField.value = null;
}

function startNewTermForm() {
  glossaryStore.selectedTerm = null;
  resetNewTermForm();
  showNewTermForm.value = true;
  void router.replace({ query: { ...route.query, term: undefined } });
}

function cancelNewTermForm() {
  showNewTermForm.value = false;
  resetNewTermForm();
  if (!glossaryStore.selectedTerm) {
    void router.replace({ query: { ...route.query, term: undefined } });
  }
}

function toggleEdit(key: string) {
  if (editingSection.value === key) {
    editingSection.value = null;
    return;
  }
  editingSection.value = key;
  const term = glossaryStore.selectedTerm;
  if (!term) return;
  if (key === 'synonyms_tags') {
    editSynonyms.value = (term.synonyms ?? []).join(', ');
    editTags.value = (term.tags ?? []).join(', ');
  } else if (key === 'header_meta') {
    editHeader.value = {
      title: term.title,
      domain: term.domain ?? '',
      category: term.category ?? '',
      steward: term.steward ?? '',
      status: term.status || 'draft',
    };
  } else if (key === 'related_objects') {
    editRelatedObjects.value = (term.related_objects ?? []).join('\n');
  }
}

async function saveHeaderMeta() {
  const term = glossaryStore.selectedTerm;
  if (!term) return;
  glossaryStore.selectedTerm = {
    ...term,
    title: editHeader.value.title,
    domain: editHeader.value.domain,
    category: editHeader.value.category,
    steward: editHeader.value.steward,
    status: editHeader.value.status,
  } as GlossaryTerm;
  editingSection.value = null;
  notifyPositive('Metadata staged.');
}

async function saveSection(key: string, value: string) {
  const term = glossaryStore.selectedTerm;
  if (!term) return;
  glossaryStore.selectedTerm = {
    ...term,
    [key]: value,
  } as GlossaryTerm;
  editingSection.value = null;
  notifyPositive('Section staged.');
}

async function saveSynonymsTags() {
  const term = glossaryStore.selectedTerm;
  if (!term) return;
  const synonyms = splitCsv(editSynonyms.value);
  const tags = splitCsv(editTags.value);
  glossaryStore.selectedTerm = {
    ...term,
    synonyms,
    tags,
  } as GlossaryTerm;
  editingSection.value = null;
  notifyPositive('Synonyms & tags staged.');
}

async function saveRelatedObjects() {
  const term = glossaryStore.selectedTerm;
  if (!term) return;
  const related_objects = splitLines(editRelatedObjects.value);
  glossaryStore.selectedTerm = {
    ...term,
    related_objects,
  } as GlossaryTerm;
  editingSection.value = null;
  notifyPositive('Related objects staged.');
}

async function saveNewTerm() {
  const synonyms = splitCsv(newTermSynonyms.value);
  const tags = splitCsv(newTermTags.value);
  const related_objects = splitLines(newTermRelatedObjects.value);
  const saved = await glossaryStore.saveTerm({ ...newTerm.value, synonyms, tags, related_objects, last_updated: new Date().toISOString() });
  showNewTermForm.value = false;
  resetNewTermForm();
  void router.replace({ query: { ...route.query, term: saved.id } });
}

async function ensureDraftTermForGeneration(): Promise<string> {
  const synonyms = splitCsv(newTermSynonyms.value);
  const tags = splitCsv(newTermTags.value);
  const related_objects = splitLines(newTermRelatedObjects.value);
  const saved = await glossaryStore.saveTerm({ ...newTerm.value, synonyms, tags, related_objects, status: newTerm.value.status ?? 'draft', last_updated: new Date().toISOString() });
  newTerm.value = { ...saved };
  newTermSynonyms.value = (saved.synonyms ?? []).join(', ');
  newTermTags.value = (saved.tags ?? []).join(', ');
  newTermRelatedObjects.value = (saved.related_objects ?? []).join('\n');
  return saved.id;
}

async function onGenerateNewField(key: string, action?: string) {
  generatingNewField.value = key;
  try {
    const id = await ensureDraftTermForGeneration();
    let result: Record<string, unknown>;
    if (action === 'crr') {
      result = await glossaryStore.generateCRR(id);
    } else if (action === 'dpm') {
      result = await glossaryStore.generateDPM(id);
    } else if (action === 'synonyms_tags') {
      result = await glossaryStore.suggestFieldsAI(id, ['synonyms', 'tags']);
    } else {
      result = await glossaryStore.suggestFieldsAI(id, [key]);
    }

    const aiFields = [...(newTerm.value.ai_generated_fields ?? [])];
    const markAI = (fieldKey: string) => {
      if (!aiFields.includes(fieldKey)) aiFields.push(fieldKey);
    };

    let nextTerm: Partial<GlossaryTerm> = { ...newTerm.value };
    let nextSynonyms = newTermSynonyms.value;
    let nextTags = newTermTags.value;
    let nextRelatedObjects = newTermRelatedObjects.value;

    if (action === 'synonyms_tags') {
      const synonyms = Array.isArray(result.synonyms) ? result.synonyms.map(String) : [];
      const tags = Array.isArray(result.tags) ? result.tags.map(String) : [];
      if (Array.isArray(result.synonyms)) {
        nextSynonyms = synonyms.join(', ');
        markAI('synonyms');
      }
      if (Array.isArray(result.tags)) {
        nextTags = tags.join(', ');
        markAI('tags');
      }
    } else {
      const newValue = result[key];
      if (newValue !== undefined && newValue !== '') {
        nextTerm = { ...nextTerm, [key]: String(newValue) };
        markAI(key);
      }

      if (action === 'crr' && Array.isArray(result.related_objects)) {
        const mergedRelatedObjects = Array.from(new Set([
          ...splitLines(nextRelatedObjects),
          ...result.related_objects.map(String),
        ]));
        nextRelatedObjects = mergedRelatedObjects.join('\n');
      }
    }

    if (Array.isArray(result.ai_generated_fields)) {
      result.ai_generated_fields.map(String).forEach(markAI);
    }

    if (!hasGeneratedValue(generationResultKey(key, action), result)) {
      notifyWarning(typeof result.message === 'string' ? result.message : 'No AI suggestion was generated for this section.');
      return;
    }

    const saved = await glossaryStore.saveTerm({
      ...nextTerm,
      id,
      synonyms: splitCsv(nextSynonyms),
      tags: splitCsv(nextTags),
      related_objects: splitLines(nextRelatedObjects),
      ai_generated_fields: aiFields,
      last_updated: new Date().toISOString(),
    });

    newTerm.value = { ...saved };
    newTermSynonyms.value = (saved.synonyms ?? []).join(', ');
    newTermTags.value = (saved.tags ?? []).join(', ');
    newTermRelatedObjects.value = (saved.related_objects ?? []).join('\n');
    notifyPositive('AI suggestion applied.');
  } catch (error) {
    notifyError(`AI generation failed: ${error instanceof Error ? error.message : String(error)}`);
  } finally {
    generatingNewField.value = null;
  }
}

async function onDeleteTerm() {
  if (!glossaryStore.selectedTerm) return;
  await glossaryStore.removeTerm(glossaryStore.selectedTerm.id);
}

async function onGenerateField(key: string, action?: string) {
  if (!glossaryStore.selectedTerm) return;
  const id = glossaryStore.selectedTerm.id;
  generatingField.value = key;
  try {
    let result: Record<string, unknown>;
    if (action === 'crr') {
      result = await glossaryStore.generateCRR(id);
    } else if (action === 'dpm') {
      result = await glossaryStore.generateDPM(id);
    } else {
      result = await glossaryStore.suggestFieldsAI(id, [key]);
    }
    if (!hasGeneratedValue(generationResultKey(key, action), result)) {
      notifyWarning(typeof result.message === 'string' ? result.message : 'No AI suggestion was generated for this section.');
      return;
    }

    const nextTerm: GlossaryTerm = { ...glossaryStore.selectedTerm! };
    const aiFields = [...(glossaryStore.selectedTerm?.ai_generated_fields ?? [])];
    const markAI = (fieldKey: string) => {
      if (!aiFields.includes(fieldKey)) aiFields.push(fieldKey);
    };

    const newValue = result[key];
    if (newValue !== undefined && newValue !== '') {
      nextTerm[key as keyof GlossaryTerm] = String(newValue) as never;
      markAI(key);
    }

    if (action === 'crr' && Array.isArray(result.related_objects)) {
      nextTerm.related_objects = Array.from(new Set([
        ...(nextTerm.related_objects ?? []),
        ...result.related_objects.map(String),
      ]));
    }

    nextTerm.ai_generated_fields = aiFields;
    glossaryStore.selectedTerm = nextTerm;
    notifyPositive('AI suggestion applied.');
  } catch (error) {
    notifyError(`AI generation failed: ${error instanceof Error ? error.message : String(error)}`);
  } finally {
    generatingField.value = null;
  }
}

async function onGenerateSynonymsTags() {
  if (!glossaryStore.selectedTerm) return;
  generatingField.value = 'synonyms_tags';
  try {
    const result = await glossaryStore.suggestFieldsAI(glossaryStore.selectedTerm.id, ['synonyms', 'tags']);
    if (!hasGeneratedValue('synonyms_tags', result)) {
      notifyWarning(typeof result.message === 'string' ? result.message : 'No AI suggestion was generated for synonyms or tags.');
      return;
    }

    const aiFields = [...(glossaryStore.selectedTerm.ai_generated_fields ?? [])];
    const markAI = (fieldKey: string) => {
      if (!aiFields.includes(fieldKey)) aiFields.push(fieldKey);
    };
    const nextTerm: GlossaryTerm = { ...glossaryStore.selectedTerm };

    if (Array.isArray(result.synonyms)) {
      nextTerm.synonyms = result.synonyms.map(String);
      markAI('synonyms');
    }
    if (Array.isArray(result.tags)) {
      nextTerm.tags = result.tags.map(String);
      markAI('tags');
    }

    nextTerm.ai_generated_fields = aiFields;
    glossaryStore.selectedTerm = nextTerm;
    notifyPositive('AI suggestion applied.');
  } catch (error) {
    notifyError(`AI generation failed: ${error instanceof Error ? error.message : String(error)}`);
  } finally {
    generatingField.value = null;
  }
}

function copyToClipboard(key: string) {
  const value = sectionValue(key);
  if (value) quasarCopy(value);
}

function onSearchSelection(termId: string | null) {
  if (!termId) return;
  const match = glossaryStore.terms.find(term => term.id === termId);
  if (match) {
    treeFilter.value = match.title;
  }
  selectTerm(termId);
}

function clearSearchInput() {
  treeFilter.value = '';
}

function copySynonymsTags() {
  const term = glossaryStore.selectedTerm;
  if (!term) return;
  const text = `Synonyms: ${(term.synonyms ?? []).join(', ')}\nTags: ${(term.tags ?? []).join(', ')}`;
  quasarCopy(text);
}

function goToCatalog(uc: UncoveredConcept) {
  router.push({ path: '/tools/catalog', query: { dataset: uc.dataset, table: uc.table } });
}

function goToRelatedObject(ref: string, destination: 'catalog' | 'discovery' = 'catalog') {
  const parsed = parseRelatedObject(ref);
  if (!parsed) return;
  if (destination === 'discovery' && parsed.kind === 'source') {
    router.push({ path: '/tools/discovery', query: { dataset: parsed.dataset, table: parsed.table, column: parsed.column } });
    return;
  }
  const type = parsed.kind === 'target' ? 'targets' : 'sources';
  router.push({ path: '/tools/catalog', query: { type, dataset: parsed.dataset, table: parsed.table } });
}

function goToGlossaryFromRef(ref: string) {
  const termId = resolveGlossaryTermIdFromRef(ref);
  if (!termId) return;
  selectTerm(termId);
}

function addTermFromUncovered(uc: UncoveredConcept) {
  const sourceRef = `${uc.kind}|${uc.dataset}|${uc.schema_name}.${uc.table}.${uc.column}`;
  newTerm.value = {
    title: uc.column,
    domain: '',
    category: '',
    business_description: uc.description ?? '',
    detailed_description: '',
    steward: '',
    CRR_context: '',
    DPM_context: '',
    ai_generated_fields: [],
  };
  newTermSynonyms.value = '';
  newTermTags.value = '';
  newTermRelatedObjects.value = sourceRef;
  showNewTermForm.value = true;
}
// endregion

// region Lifecycle
onMounted(async () => {
  // If loading a specific term, keep loading state throughout entire initialization
  const loadingSpecificTerm = !!route.query.term;

  if (loadingSpecificTerm) {
    glossaryStore.loading = true;
  }

  await glossaryStore.loadGlossary();
  await glossaryStore.loadUncovered();
  collapseAllTermsTree();

  if (glossaryStore.prefill) {
    newTerm.value = { ...newTerm.value, ...glossaryStore.prefill };
    if (glossaryStore.prefill.related_objects?.length) {
      newTermRelatedObjects.value = glossaryStore.prefill.related_objects.join('\n');
    }
    showNewTermForm.value = true;
    glossaryStore.clearPrefill();
  } else if (route.query.new === '1') {
    startNewTermForm();
    void router.replace({ query: { ...route.query, new: undefined } });
  }

  if (loadingSpecificTerm) {
    // Maintain loading state when loading specific term
    glossaryStore.loading = true;
    selectTerm(route.query.term as string);
  }
});

watch(() => route.query.term, (termId) => {
  if (termId) {
    showNewTermForm.value = false;
    glossaryStore.loadTerm(termId as string);
    return;
  }
  if (!showNewTermForm.value) {
    glossaryStore.selectedTerm = null;
  }
});

watch(() => newTerm.value.domain, (domain) => {
  if (!domain) return;
  const currentCategory = newTerm.value.category?.trim();
  if (!currentCategory) return;
  if (categoryOptions.value.length && !categoryOptions.value.includes(currentCategory)) {
    newTerm.value = { ...newTerm.value, category: '' };
  }
});

watch(groupByMode, () => {
  collapseAllTermsTree();
});
// endregion
</script>

<style scoped lang="scss">
.glossary-page {
  color: #2b2a31;
}

.glossary-layout {
  display: flex;
  gap: 16px;
  height: calc(100vh - 100px);
}

.left-panel {
  width: 300px;
  min-width: 280px;
  flex-shrink: 0;
}

.center-panel {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
}

.panel-container {
  background: #fdfdfd;
  border-radius: 10px;
  height: 100%;
  overflow-y: auto;
}

.business-glossary-title {
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.02em;
  color: #2b2a31;
}

.glossary-search-input :deep(.q-field__native),
.glossary-search-input :deep(.q-field__input) {
  font-size: 12px;
}

.glossary-search-input :deep(.q-placeholder) {
  font-size: 12px;
}

.glossary-sort-row {
  align-items: flex-end;
}

.glossary-sort-select {
  min-width: 0;
}

.glossary-sort-row > .col-auto {
  padding-left: 10px;
}

.glossary-search-suggestions {
  border: 1px solid #d6dde8;
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 6px 18px rgba(18, 38, 63, 0.12);
  overflow: hidden;
}

.glossary-search-suggestions :deep(.q-item) {
  min-height: 38px;
}

.glossary-search-suggestions :deep(.q-item:hover) {
  background: #f5f9ff;
}

.tree-scroll {
  overflow-y: auto;
  max-height: calc(100vh - 320px);
}

.glossary-tree-actions :deep(.q-btn) {
  padding-left: 4px;
  padding-right: 4px;
}

.tree-node-label {
  font-size: 13px;
  color: #2b2a31;
  padding: 2px 4px;
  border-radius: 4px;
}

.tree-node-term {
  cursor: pointer;
  &:hover {
    background: #e9f3ff;
  }
}

.tree-node-selected {
  background: #0d4da1;
  color: white;
  &:hover {
    background: #0d4da1;
  }
}

.section-card {
  border-bottom: 1px solid #eee;
  padding-bottom: 16px;
}

.header-card {
  border-top: 1px solid #eee;
  padding-top: 8px;
}

.header-title {
  font-size: 24px;
  font-weight: 700;
  color: #2b2a31;
}

.section-label {
  font-weight: 700;
  font-size: 14px;
  color: #2b2a31;
}

.related-objects-hint {
  font-size: 11px;
  color: #86827a;
  margin-bottom: 6px;
  line-height: 1.5;
}
.related-objects-hint code {
  background: #f0ede8;
  border-radius: 3px;
  padding: 1px 4px;
  font-size: 10.5px;
  color: #0d5c54;
}

.steward-line {
  color: #5f6b7a;
  font-size: 13px;
  display: flex;
  align-items: center;
}

.ai-badge {
  color: #c2410c !important;
  border-color: #fed7aa !important;
  background: #fff7ed !important;
  font-size: 11px;
  font-weight: 600;
}

.related-object-row {
  padding: 6px 0;
  border-bottom: 1px dashed #e5e7eb;
}

.related-object-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 10px 18px;
}

.related-object-label {
  color: #0d4da1;
  font-size: 13px;
}
</style>

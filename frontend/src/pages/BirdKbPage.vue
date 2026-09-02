<template>
  <q-page class="bird-kb-page column no-wrap">

    <!-- ── Page header ─────────────────────────────────────────────── -->
    <div class="bird-header">
      <div class="bird-header-row">
        <div class="bird-title-block">
          <q-icon name="account_tree" size="22px" color="teal-8" />
          <span class="bird-title-text">BIRD Knowledge Base</span>
          <q-badge label="v6.7" color="teal-8" class="bird-version-chip" />
        </div>
        <q-btn
          flat dense round icon="help_outline" size="sm"
          color="blue-grey-4"
          class="q-ml-auto"
          @click="explainerOpen = !explainerOpen"
        >
          <q-tooltip>SMCube vocabulary</q-tooltip>
        </q-btn>
      </div>

      <q-tabs
        v-model="activeLayer"
        dense align="left"
        class="bird-layer-tabs"
        indicator-color="teal-8"
        active-color="teal-8"
        @update:model-value="onLayerChange"
      >
        <q-tab
          v-for="l in LAYERS"
          :key="l.value"
          :name="l.value"
          :label="l.value"
          :class="['bird-layer-tab', l.primary ? 'layer-primary' : 'layer-secondary']"
        >
          <q-tooltip>{{ l.tip }}</q-tooltip>
        </q-tab>
      </q-tabs>

      <div class="bird-framework-row">
        <span class="bird-framework-label">Framework</span>
        <q-btn-toggle
          v-model="activeFramework"
          flat dense
          toggle-color="deep-purple-6"
          :options="[
            { label: 'All', value: 'All' },
            { label: 'BIRD', value: 'BIRD' },
            { label: 'AnaCredit', value: 'AnaCredit' },
          ]"
          class="bird-framework-toggle"
          @update:model-value="onFrameworkChange"
        />
      </div>
    </div>

    <!-- ── SMCube vocabulary explainer ─────────────────────────────── -->
    <q-slide-transition>
      <div v-if="explainerOpen" class="smcube-explainer">
        <div class="smcube-explainer-head">
          <span>SMCube Vocabulary</span>
          <q-btn flat dense round icon="close" size="xs" @click="explainerOpen = false" />
        </div>
        <div class="smcube-grid">
          <div v-for="t in SMCUBE_VOCAB" :key="t.term" class="smcube-row">
            <span class="smcube-term">{{ t.term }}</span>
            <span class="smcube-meaning">{{ t.meaning }}</span>
          </div>
        </div>
      </div>
    </q-slide-transition>

    <!-- ── Two-panel body ───────────────────────────────────────────── -->
    <div class="bird-body">

      <!-- LEFT: Entity Group Browser -->
      <div class="bird-left">

        <!-- Scope filter bar -->
        <div class="bird-scope-bar">
          <span
            v-for="sc in SEARCH_SCOPES"
            :key="sc"
            class="bird-scope-pill"
            :class="{ 'is-active': searchScope === sc }"
            @click="onScopeChange(sc)"
          >{{ sc }}</span>
        </div>

        <div class="bird-search-wrap q-ma-sm">
          <q-input
            v-model="searchQuery" dense outlined clearable
            placeholder="Search groups / entities…"
            class="bird-search"
            @update:model-value="onSearchInput"
            @blur="onSearchBlur"
            @focus="suggestOpen = suggestions.length > 0"
          >
            <template #prepend><q-icon name="search" size="16px" /></template>
          </q-input>
          <div v-if="suggestOpen && suggestions.length" class="bird-suggest-dropdown">
            <div
              v-for="s in suggestions"
              :key="s.text + s.type"
              class="bird-suggest-item"
              @click="applySuggestion(s)"
            >
              <q-icon
                :name="s.type === 'entity' ? 'table_chart' : 'label_outline'"
                size="13px" color="grey-5"
              />
              <span class="bird-suggest-text">{{ s.text }}</span>
              <span class="bird-suggest-type-label">{{ s.type }}</span>
            </div>
          </div>
        </div>

        <!-- Exact match toggle -->
        <div class="bird-exact-row">
          <button
            :class="['bird-exact-pill', { 'is-active': exactSearch }]"
            @click="onExactToggle"
          >
            <q-icon name="spellcheck" size="11px" />
            Exact match
          </button>
          <span class="bird-exact-hint" v-if="exactSearch">Showing exact hits only</span>
        </div>

        <div class="bird-group-scroll">
          <div v-if="store.loadingGroups" class="bird-spinner-row">
            <q-spinner color="teal" size="22px" />
          </div>
          <template v-else>
            <div
              v-for="group in filteredGroups"
              :key="group.cube_group_id"
              class="bird-group-block"
            >
              <div
                class="bird-group-header"
                :class="{ 'is-active': store.selectedGroup?.cube_group_id === group.cube_group_id }"
                @click="toggleGroup(group)"
              >
                <q-icon
                  :name="isGroupOpen(group.cube_group_id) ? 'expand_more' : 'chevron_right'"
                  size="16px" class="bird-group-chevron"
                />
                <span class="bird-group-name">{{ group.name }}</span>
                <q-badge
                  :label="group.entity_count"
                  color="teal-8" class="bird-count-badge"
                />
              </div>

              <q-slide-transition>
                <div v-if="isGroupOpen(group.cube_group_id)" class="bird-entity-list">
                  <div
                    v-if="store.loadingEntities && store.selectedGroup?.cube_group_id === group.cube_group_id"
                    class="bird-spinner-row-sm"
                  >
                    <q-spinner size="14px" />
                  </div>
                  <template v-else>
                    <div
                      v-for="entity in cachedEntities(group.cube_group_id)"
                      :key="entity.cube_id"
                      class="bird-entity-row"
                      :class="{ 'is-selected': store.selectedEntity?.cube_id === entity.cube_id }"
                      @click="onEntityClick(entity)"
                    >
                      <q-icon name="table_chart" size="13px" color="blue-grey-5" />
                      <span class="bird-entity-name">{{ entity.name }}</span>
                      <q-badge
                        v-if="entity.framework_id === 'ANCRDT'"
                        label="AnaCredit" color="deep-purple-6" class="bird-fw-badge"
                      />
                    </div>
                  </template>
                </div>
              </q-slide-transition>
            </div>
          </template>
        </div>
      </div>

      <!-- RIGHT: Graph / Table / Data Model -->
      <div class="bird-right" ref="birdRightEl">

        <!-- View toolbar -->
        <div class="bird-right-toolbar">
          <q-btn-toggle
            v-model="rightView"
            flat dense
            toggle-color="teal-7"
            :options="[
              { label: 'Graph', value: 'graph', icon: 'hub' },
              { label: 'Table', value: 'table', icon: 'table_rows' },
              { label: 'Data Model', value: 'model', icon: 'schema' },
            ]"
            class="bird-view-toggle"
          />
          <div v-if="store.selectedGroup" class="bird-breadcrumb">
            <span class="bc-layer">{{ activeLayer }}</span>
            <q-icon name="chevron_right" size="13px" />
            <span class="bc-group">{{ store.selectedGroup.name }}</span>
            <template v-if="store.selectedEntity">
              <q-icon name="chevron_right" size="13px" />
              <span class="bc-entity">{{ store.selectedEntity.name }}</span>
            </template>
          </div>
          <q-space />
          <q-btn
            v-if="rightView === 'graph' || rightView === 'model'"
            flat dense round icon="open_in_full" size="sm" color="grey-6"
            @click="openFs"
          >
            <q-tooltip>Full screen view</q-tooltip>
          </q-btn>
        </div>

        <!-- Graph View -->
        <div v-show="rightView === 'graph'" class="bird-graph-wrap">
          <div v-if="store.loadingGraph" class="bird-graph-overlay">
            <q-spinner color="teal" size="30px" />
            <span>Building graph…</span>
          </div>
          <div v-else-if="!store.graphData.nodes.length" class="bird-graph-overlay">
            <q-icon name="account_tree" size="42px" color="grey-6" />
            <span>No entities found for this layer</span>
          </div>
          <div ref="graphEl" class="bird-vis-canvas" />
          <div v-if="store.graphData.level === 1" class="bird-graph-hint">
            Click a group bubble to expand its entities
          </div>
        </div>

        <!-- Table View -->
        <div v-if="rightView === 'table'" class="bird-table-wrap">
          <div class="bird-table-filters row items-center q-gutter-sm q-pa-sm">
            <q-btn-toggle
              v-model="roleFilter" flat dense toggle-color="teal-7"
              :options="[
                { label: 'All roles', value: '' },
                { label: 'D — Dimension', value: 'D' },
                { label: 'O — Observation', value: 'O' },
                { label: 'A — Attribute', value: 'A' },
              ]"
            />
            <q-toggle v-model="enumOnly" label="Code lists only" dense />
            <q-space />
            <q-input v-model="tableSearch" dense outlined clearable placeholder="Search variable / entity…" style="width: 240px">
              <template #prepend><q-icon name="search" size="14px" /></template>
            </q-input>
          </div>
          <div v-if="store.loadingTable" class="bird-table-loading">
            <StagedLoader :stages="tableLoadStages" />
          </div>
          <q-table
            v-else
            :rows="tableRows"
            :columns="TABLE_COLS"
            dense flat
            row-key="csi_id"
            class="bird-data-table"
            :rows-per-page-options="[0]"
          >
            <template #body-cell-role="props">
              <q-td :props="props">
                <q-badge :color="roleColor(props.row.role)" :label="props.row.role_label" />
              </q-td>
            </template>
            <template #body-cell-is_enumerated="props">
              <q-td :props="props">
                <q-icon
                  :name="props.row.is_enumerated ? 'check_circle' : 'remove'"
                  :color="props.row.is_enumerated ? 'teal-6' : 'grey-5'"
                  size="15px"
                />
              </q-td>
            </template>
            <template #body-cell-variable_name="props">
              <q-td :props="props">
                {{ props.row.variable_name }}
                <q-badge v-if="props.row.is_nevs" label="NEV" color="orange-7" class="q-ml-xs" />
              </q-td>
            </template>
            <template #body-cell-entity_name="props">
              <q-td :props="props">
                <span class="bird-table-entity-link" @click="onTableEntityClick(props.row.cube_id)">
                  {{ props.row.entity_name }}
                </span>
              </q-td>
            </template>
          </q-table>
          <div v-if="store.tableData.capped" class="bird-table-cap-notice">
            Showing first {{ store.tableData.rows.length }} rows — select a group or use filters to narrow results.
          </div>
        </div>

        <!-- Data Model View -->
        <div v-if="rightView === 'model'" class="bird-model-wrap">
          <q-tabs v-model="modelTab" dense align="left" class="bird-model-tabs" indicator-color="violet-5">
            <q-tab name="erd" label="Entity Diagram" icon="account_tree" />
            <q-tab name="meta" label="SMCube Meta-model" icon="schema" />
          </q-tabs>
          <div ref="modelEl" class="bird-vis-canvas" />
        </div>

        <!-- Entity Detail Panel -->
        <q-slide-transition>
          <div
            v-if="store.entityDetail && rightView !== 'model'"
            class="bird-detail-panel"
            :class="{ 'is-collapsed': detailCollapsed, 'is-resizing': detailResizing }"
            :style="detailPanelStyle"
          >
            <!-- Resize handle (drag up/down to resize) -->
            <div
              class="bird-detail-resize-handle"
              @pointerdown="onResizePointerDown"
              @pointermove="onResizePointerMove"
              @pointerup="onResizePointerUp"
            >
              <span class="bird-detail-resize-grip" />
            </div>
            <div class="bird-detail-head">
              <div class="bird-detail-title-row">
                <q-icon name="table_chart" color="teal-5" size="18px" />
                <span class="bird-detail-name">{{ store.entityDetail.name }}</span>
                <q-badge :label="store.entityDetail.cube_type" color="blue-grey-6" />
                <q-badge
                  v-if="store.entityDetail.framework_id === 'ANCRDT'"
                  label="AnaCredit" color="deep-purple-6"
                />
              </div>
              <div class="bird-detail-actions">
                <q-btn
                  flat dense no-caps icon="linear_scale" label="Transformation chain"
                  color="amber-6" size="sm"
                  :loading="store.loadingChain"
                  @click="onShowChain"
                />
                <q-btn
                  flat dense round
                  :icon="detailCollapsed ? 'expand_less' : 'expand_more'"
                  size="sm" color="grey-6"
                  @click="detailCollapsed = !detailCollapsed"
                >
                  <q-tooltip>{{ detailCollapsed ? 'Expand' : 'Collapse' }}</q-tooltip>
                </q-btn>
                <q-btn
                  flat dense round icon="close"
                  size="sm" color="grey-6"
                  @click="store.clearSelection()"
                >
                  <q-tooltip>Close entity detail</q-tooltip>
                </q-btn>
              </div>
            </div>
            <q-slide-transition>
              <div v-show="!detailCollapsed" class="bird-detail-body">
                <p v-if="store.entityDetail.description" class="bird-detail-desc">
                  {{ store.entityDetail.description }}
                </p>

            <div v-for="role in ['D', 'O', 'A']" :key="role">
              <div v-if="attrsByRole(role).length" class="bird-role-section">
                <div class="bird-role-head">
                  <q-icon :name="roleIcon(role)" :color="roleColor(role)" size="15px" />
                  <span class="bird-role-label">{{ ROLE_LABEL[role] }}</span>
                  <q-badge :label="attrsByRole(role).length" :color="roleColor(role)" />
                </div>
                <div
                  v-for="attr in attrsByRole(role)"
                  :key="attr.csi_id"
                  class="bird-attr-row"
                >
                  <div class="bird-attr-main-row">
                    <span class="bird-attr-varname">{{ attr.variable_name }}</span>
                    <q-badge v-if="attr.is_nevs" label="NEV" color="orange-7" />
                    <q-badge v-if="attr.is_mandatory" label="required" color="red-8" />
                    <span class="bird-attr-domain">{{ attr.domain_name }}</span>
                    <span class="bird-attr-type">{{ attr.data_type }}</span>
                    <q-badge
                      v-if="attr.is_enumerated"
                      label="code list"
                      color="teal-8"
                      class="cursor-pointer"
                      @click.stop="toggleDomain(attr.domain_id)"
                    />
                    <q-icon v-if="attr.role === 'D'" name="key" size="11px" color="teal-7" class="bird-attr-key-icon" />
                  </div>
                  <q-slide-transition>
                    <div v-if="isDomainOpen(attr.domain_id)" class="bird-members-block">
                      <div v-if="!memberCache[attr.domain_id]" class="bird-spinner-row-sm">
                        <q-spinner size="12px" />
                      </div>
                      <template v-else>
                        <div
                          v-for="m in memberCache[attr.domain_id]"
                          :key="m.member_id"
                          class="bird-member-row"
                        >
                          <code class="bird-member-code">{{ m.code }}</code>
                          <span class="bird-member-name">{{ m.name }}</span>
                        </div>
                      </template>
                    </div>
                  </q-slide-transition>
                </div>
              </div>
            </div>

            <q-expansion-item
              v-if="store.entityDetail.legal_references.length"
              icon="gavel" dense
              :label="`Legal basis (${store.entityDetail.legal_references.length})`"
              class="bird-legal-expansion q-mt-sm"
            >
              <div
                v-for="ref in store.entityDetail.legal_references"
                :key="ref.legal_reference_id"
                class="bird-legal-row"
              >
                <span class="bird-legal-code">{{ ref.legal_code }}</span>
                <span v-if="ref.article" class="bird-legal-article">Art. {{ ref.article }}</span>
                <span class="bird-legal-desc">{{ ref.legal_description }}</span>
              </div>
            </q-expansion-item>
              </div>
            </q-slide-transition>
          </div>
        </q-slide-transition>

        <!-- Forward Chain Panel -->
        <q-slide-transition>
          <div v-if="store.chainVisible && store.chainData.length" class="bird-chain-panel">
            <div class="bird-chain-head">
              <q-icon name="linear_scale" color="amber-6" size="16px" />
              <span>Transformation Chain</span>
              <q-icon name="info" size="14px" color="grey-5">
                <q-tooltip>Display-only — rules are shown as reference, not executed</q-tooltip>
              </q-icon>
              <q-btn flat dense round icon="close" size="xs" @click="store.chainVisible = false" />
            </div>
            <div class="bird-chain-flow">
              <template v-for="(hop, idx) in store.chainData" :key="hop.ltr_id">
                <div v-if="idx === 0" class="bird-chain-node bird-chain-source">
                  <q-badge :label="hop.source_layer" color="blue-grey-7" />
                  <div class="bird-chain-node-name">{{ hop.source_name }}</div>
                </div>
                <div class="bird-chain-arrow-block">
                  <div class="bird-chain-arrow-line" />
                  <q-badge :label="hop.transformation_type" color="amber-7" class="bird-chain-type-badge" />
                  <div class="bird-chain-arrow-line" />
                </div>
                <div class="bird-chain-node">
                  <q-badge :label="hop.destination_layer" color="teal-7" />
                  <div class="bird-chain-node-name">{{ hop.destination_name }}</div>
                  <q-expansion-item
                    v-if="hop.algorithm"
                    label="Algorithm" dense
                    class="bird-chain-algo"
                  >
                    <pre class="bird-algo-text">{{ hop.algorithm }}</pre>
                  </q-expansion-item>
                </div>
              </template>
            </div>
          </div>
        </q-slide-transition>

      </div>
    </div>
  </q-page>

  <!-- ── Full-screen overlay ──────────────────────────────────────── -->
  <teleport to="body">
    <transition name="fs-fade">
      <div v-if="fsVisible" class="bird-fs-overlay" @keydown.esc="closeFs" tabindex="0">

        <!-- FS header -->
        <div class="bird-fs-header">
          <div class="bird-fs-header-left">
            <q-icon name="account_tree" size="18px" color="teal-8" />
            <span class="bird-fs-title">{{ store.selectedEntity?.name || store.selectedGroup?.name || 'BIRD ' + activeLayer + ' Data Model' }}</span>
            <q-badge v-if="store.selectedEntity" :label="store.selectedEntity.cube_type" color="blue-grey-5" />
          </div>
          <q-btn flat dense round icon="close_fullscreen" size="sm" color="grey-6" @click="closeFs">
            <q-tooltip>Exit full screen (Esc)</q-tooltip>
          </q-btn>
        </div>

        <!-- FS body: graph (left) + entity detail (right) -->
        <div class="bird-fs-body">

          <!-- Graph canvas -->
          <div class="bird-fs-canvas-wrap">
            <div v-if="store.loadingGraph" class="bird-fs-canvas-overlay">
              <q-spinner color="teal" size="36px" />
            </div>
            <div ref="fsGraphEl" class="bird-fs-canvas" />
            <div class="bird-fs-canvas-hint">
              {{ fsModelMode ? 'Click a node for details' : (store.graphData.level === 1 ? 'Click a group bubble to expand entities' : 'Click an entity node for details') }}
            </div>
          </div>

          <!-- Entity detail panel -->
          <div v-if="store.entityDetail" class="bird-fs-detail">
            <div class="bird-fs-detail-head">
              <span class="bird-fs-detail-name">{{ store.entityDetail.name }}</span>
              <q-badge :label="store.entityDetail.cube_type" color="blue-grey-5" />
              <q-badge v-if="store.entityDetail.framework_id === 'ANCRDT'" label="AnaCredit" color="deep-purple-6" />
            </div>
            <p v-if="store.entityDetail.description" class="bird-fs-detail-desc">{{ store.entityDetail.description }}</p>

            <div v-for="role in ['D', 'O', 'A']" :key="role">
              <div v-if="attrsByRole(role).length" class="bird-fs-role-section">
                <div class="bird-fs-role-head">
                  <q-icon :name="roleIcon(role)" :color="roleColor(role)" size="13px" />
                  <span>{{ ROLE_LABEL[role] }}</span>
                  <q-badge :label="attrsByRole(role).length" :color="roleColor(role)" />
                </div>
                <div v-for="attr in attrsByRole(role)" :key="attr.csi_id" class="bird-fs-attr-row">
                  <span class="bird-fs-attr-name">{{ attr.variable_name }}</span>
                  <q-badge v-if="attr.is_nevs" label="NEV" color="orange-7" />
                  <q-badge v-if="attr.is_mandatory" label="req" color="red-8" />
                  <span class="bird-fs-attr-domain">{{ attr.domain_name }}&nbsp;<em>{{ attr.data_type }}</em></span>
                  <q-badge
                    v-if="attr.is_enumerated"
                    label="code list" color="teal-8"
                    class="cursor-pointer"
                    @click.stop="toggleDomain(attr.domain_id)"
                  />
                  <q-slide-transition>
                    <div v-if="isDomainOpen(attr.domain_id)" class="bird-members-block">
                      <div v-if="!memberCache[attr.domain_id]" class="bird-spinner-row-sm"><q-spinner size="12px" /></div>
                      <template v-else>
                        <div v-for="m in memberCache[attr.domain_id]" :key="m.member_id" class="bird-member-row">
                          <code class="bird-member-code">{{ m.code }}</code>
                          <span class="bird-member-name">{{ m.name }}</span>
                        </div>
                      </template>
                    </div>
                  </q-slide-transition>
                </div>
              </div>
            </div>

            <q-expansion-item
              v-if="store.entityDetail.legal_references.length"
              icon="gavel" dense
              :label="`Legal basis (${store.entityDetail.legal_references.length})`"
              class="bird-legal-expansion q-mt-sm"
            >
              <div v-for="ref in store.entityDetail.legal_references" :key="ref.legal_reference_id" class="bird-legal-row">
                <span class="bird-legal-code">{{ ref.legal_code }}</span>
                <span v-if="ref.article" class="bird-legal-article">Art. {{ ref.article }}</span>
                <span class="bird-legal-desc">{{ ref.legal_description }}</span>
              </div>
            </q-expansion-item>
          </div>

          <!-- Placeholder when no entity selected -->
          <div v-else class="bird-fs-detail bird-fs-detail--empty">
            <q-icon name="touch_app" size="32px" color="grey-4" />
            <p>Click a node to view entity details</p>
          </div>

        </div>
      </div>
    </transition>
  </teleport>

</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, onBeforeUnmount, nextTick } from 'vue';
import { Network } from 'vis-network';
import { DataSet } from 'vis-data';
import { useBirdKbStore } from 'src/stores/birdKbStore';
import StagedLoader from 'src/components/StagedLoader.vue';
import * as api from 'src/api/bird';
import type { BirdGroup, BirdEntity, MemberItem, GraphNode } from 'src/api/bird';

const store = useBirdKbStore();

const tableLoadStages = computed(() => [
  'Loading the variable table…',
  'Matching entities and attributes…',
]);

// ── Refs ─────────────────────────────────────────────────────────────
const activeLayer = ref('LDM');
const activeFramework = ref('All');
const searchScope = ref('All');
const exactSearch = ref(false);
const searchQuery = ref<string | null>('');
const explainerOpen = ref(false);
const rightView = ref<'graph' | 'table' | 'model'>('graph');
const modelTab = ref<'erd' | 'meta'>('erd');
const roleFilter = ref('');
const enumOnly = ref(false);
const tableSearch = ref('');

const openGroups = ref<Record<string, boolean>>({});
const openDomains = ref<Record<string, boolean>>({});
const entityCache = ref<Record<string, BirdEntity[]>>({});
const memberCache = ref<Record<string, MemberItem[]>>({});
const detailCollapsed = ref(false);
const detailHeight = ref<number | null>(null); // null = CSS auto (max-height: 50%)
const detailResizing = ref(false);
const birdRightEl = ref<HTMLElement | null>(null);
let _rds = { y: 0, h: 0 }; // resize drag start snapshot

const detailPanelStyle = computed(() =>
  detailHeight.value !== null && !detailCollapsed.value
    ? { height: `${detailHeight.value}px`, maxHeight: 'none', overflowY: 'auto' as const }
    : {},
);

function onResizePointerDown(e: PointerEvent) {
  const panel = (e.currentTarget as HTMLElement).parentElement;
  if (!panel) return;
  const currentH = panel.getBoundingClientRect().height;
  _rds = { y: e.clientY, h: currentH };
  detailHeight.value = currentH;   // pin height so it won't jump
  detailResizing.value = true;
  (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  e.preventDefault();
}

function onResizePointerMove(e: PointerEvent) {
  if (!detailResizing.value) return;
  const dy = _rds.y - e.clientY;  // positive = dragged up = taller panel
  const containerH = birdRightEl.value?.getBoundingClientRect().height ?? 600;
  const toolbarH = birdRightEl.value?.querySelector('.bird-right-toolbar')?.getBoundingClientRect().height ?? 44;
  const maxH = containerH - toolbarH - 4;
  const minH = 48; // just the header bar
  detailHeight.value = Math.max(minH, Math.min(maxH, _rds.h + dy));
  e.preventDefault();
}

function onResizePointerUp(e: PointerEvent) {
  detailResizing.value = false;
  (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
}

const graphEl = ref<HTMLElement | null>(null);
const modelEl = ref<HTMLElement | null>(null);
let network: Network | null = null;
let modelNetwork: Network | null = null;

// Full-screen state
const fsVisible = ref(false);
const fsModelMode = ref(false); // true = showing meta/erd model, false = entity graph
const fsGraphEl = ref<HTMLElement | null>(null);
let fsNetwork: Network | null = null;

// Search suggestions
const suggestions = ref<{ text: string; type: string }[]>([]);
const suggestOpen = ref(false);
let searchTimer: ReturnType<typeof setTimeout> | null = null;

// ── Constants ─────────────────────────────────────────────────────────
const LAYERS = [
  { value: 'LDM',  primary: true,  tip: 'Logical Data Model — primary mapping target' },
  { value: 'ELDM', primary: true,  tip: 'Extended LDM — enriched input layer' },
  { value: 'IL',   primary: false, tip: 'Input Layer — WUDEN output from LDM' },
  { value: 'EIL',  primary: false, tip: 'Extended Input Layer — DER derivations' },
  { value: 'ROL',  primary: false, tip: 'Regulatory Output Layer — AnaCredit GEN output' },
];

const ROLE_LABEL: Record<string, string> = {
  D: 'Dimension',
  O: 'Observation',
  A: 'Attribute',
};

const SEARCH_SCOPES = [
  'All', 'Cube', 'Cube Link', 'Cube Structure Item', 'Domain',
  'Entity', 'Entity Group', 'Member', 'Sub-Domain', 'Transformation Rule', 'Variable',
];

const SMCUBE_VOCAB = [
  { term: 'Cube',               meaning: 'An entity — a business concept like Party, Instrument, Collateral' },
  { term: 'Variable',           meaning: 'A reusable attribute definition shared across entities' },
  { term: 'Cube Structure Item', meaning: 'This variable as used in a specific entity, with its role (D/O/A)' },
  { term: 'Domain',             meaning: 'The data type + allowed values for a variable' },
  { term: 'Member',             meaning: 'One allowed value in an enumerated domain (a code-list entry)' },
  { term: 'Subdomain',          meaning: "A restricted subset of a domain's values for a specific context" },
  { term: 'Cube Link',          meaning: 'A connection between entities across layers' },
  { term: 'Transformation Rule', meaning: 'The logic that moves or derives data from one layer to the next' },
  { term: 'WUDEN',              meaning: 'Wrap-Up / DENormalise — LDM → IL structural reshaping' },
  { term: 'DER',                meaning: 'Derivation — computing enriched attributes on the EIL' },
  { term: 'GEN',                meaning: 'Generation — producing the final regulatory output (AnaCredit)' },
];

const TABLE_COLS = [
  { name: 'group_name',    label: 'Entity Group', field: 'group_name',    sortable: true, align: 'left' as const },
  { name: 'entity_name',   label: 'Entity',       field: 'entity_name',   sortable: true, align: 'left' as const },
  { name: 'entity_code',   label: 'Code',         field: 'entity_code',   sortable: true, align: 'left' as const },
  { name: 'variable_name', label: 'Variable',     field: 'variable_name', sortable: true, align: 'left' as const },
  { name: 'role',          label: 'Role',         field: 'role',          sortable: true, align: 'center' as const },
  { name: 'domain_name',   label: 'Domain',       field: 'domain_name',   sortable: true, align: 'left' as const },
  { name: 'data_type',     label: 'Type',         field: 'data_type',     sortable: true, align: 'left' as const },
  { name: 'is_enumerated', label: 'Code list',    field: 'is_enumerated', sortable: true, align: 'center' as const },
];

// Static SMCube meta-model nodes/edges for the "Meta-model" diagram
const META_NODES = [
  { id: 'Cube',               label: 'Cube\n(Entity)' },
  { id: 'CubeStructure',      label: 'Cube\nStructure' },
  { id: 'CubeStructureItem',  label: 'Cube\nStructure\nItem' },
  { id: 'Variable',           label: 'Variable' },
  { id: 'Domain',             label: 'Domain' },
  { id: 'Member',             label: 'Member\n(Code list)' },
  { id: 'Subdomain',          label: 'Subdomain' },
];
const META_EDGES = [
  { id: 'e1', from: 'Cube',              to: 'CubeStructure',     label: 'has' },
  { id: 'e2', from: 'CubeStructure',     to: 'CubeStructureItem', label: '1:N' },
  { id: 'e3', from: 'CubeStructureItem', to: 'Variable',          label: 'references' },
  { id: 'e4', from: 'Variable',          to: 'Domain',            label: 'typed by' },
  { id: 'e5', from: 'Domain',            to: 'Member',            label: '1:N (enumerated)' },
  { id: 'e6', from: 'Domain',            to: 'Subdomain',         label: '1:N (optional)' },
];

// ── Computed ──────────────────────────────────────────────────────────
const filteredGroups = computed(() => {
  const q = (searchQuery.value ?? '').toLowerCase().trim();
  if (!q) return store.groups;
  const match = (text: string) => exactSearch.value ? text.toLowerCase() === q : text.toLowerCase().includes(q);
  return store.groups.filter(
    (g) =>
      match(g.name) ||
      cachedEntities(g.cube_group_id).some(
        (e) => match(e.name) || match(e.code ?? ''),
      ),
  );
});

const tableRows = computed(() => {
  const rows = store.tableData.rows;
  const q = tableSearch.value.toLowerCase().trim();
  return rows.filter((r) => {
    if (roleFilter.value && r.role !== roleFilter.value) return false;
    if (enumOnly.value && !r.is_enumerated) return false;
    if (q) {
      const match = (t: string | null | undefined) =>
        exactSearch.value ? (t ?? '').toLowerCase() === q : (t ?? '').toLowerCase().includes(q);
      return match(r.variable_name) || match(r.entity_name) || match(r.group_name);
    }
    return true;
  });
});

// ── Helpers ───────────────────────────────────────────────────────────
function isGroupOpen(id: string) { return !!openGroups.value[id]; }
function isDomainOpen(id: string) { return !!openDomains.value[id]; }
function cachedEntities(groupId: string): BirdEntity[] { return entityCache.value[groupId] ?? []; }
function attrsByRole(role: string) { return store.entityDetail?.attributes.filter((a) => a.role === role) ?? []; }
function roleColor(role: string) { return ({ D: 'blue-8', O: 'teal-7', A: 'orange-7' } as Record<string, string>)[role] ?? 'grey-7'; }
function roleIcon(role: string) { return ({ D: 'key', O: 'data_object', A: 'tune' } as Record<string, string>)[role] ?? 'label'; }

// ── Actions ───────────────────────────────────────────────────────────
async function onLayerChange(layer: string) {
  openGroups.value = {};
  entityCache.value = {};
  store.clearSelection();
  await store.selectLayer(layer);
  if (rightView.value === 'table') await store.loadTable();
}

async function onFrameworkChange(framework: string) {
  openGroups.value = {};
  entityCache.value = {};
  store.clearSelection();
  await store.selectFramework(framework);
  if (rightView.value === 'table') await store.loadTable();
}

async function toggleGroup(group: BirdGroup) {
  const id = group.cube_group_id;
  if (openGroups.value[id]) {
    openGroups.value = { ...openGroups.value, [id]: false };
    return;
  }
  openGroups.value = { ...openGroups.value, [id]: true };
  if (!entityCache.value[id]) {
    await store.selectGroup(group);
    entityCache.value = { ...entityCache.value, [id]: [...store.entities] };
  }
}

async function onEntityClick(entity: BirdEntity) {
  detailCollapsed.value = false; // always expand when selecting a new entity
  detailHeight.value = null;     // reset to CSS auto height
  await store.selectEntity(entity);
  if (rightView.value === 'table') return;

  rightView.value = 'graph';

  // If the graph is still at level-1 (group clusters), expand to the entity's group.
  // This happens when groups were expanded via search (loadAllGroupEntities) without
  // calling store.selectGroup, so the graph still shows 18 cluster bubbles.
  if (store.graphData.level === 1) {
    const groupEntry = Object.entries(entityCache.value)
      .find(([, ents]) => ents.some((e) => e.cube_id === entity.cube_id));
    if (groupEntry) {
      const group = store.groups.find((g) => g.cube_group_id === groupEntry[0]);
      if (group) {
        await store.selectGroup(group);
        entityCache.value = { ...entityCache.value, [groupEntry[0]]: [...store.entities] };
      }
    }
  }
}

async function onShowChain() {
  await store.loadChain();
}

async function toggleDomain(domainId: string) {
  if (openDomains.value[domainId]) {
    openDomains.value = { ...openDomains.value, [domainId]: false };
    return;
  }
  openDomains.value = { ...openDomains.value, [domainId]: true };
  if (!memberCache.value[domainId]) {
    const result = await api.getMembers(domainId);
    memberCache.value = { ...memberCache.value, [domainId]: result.members };
  }
}

// ── Search with live suggestions ──────────────────────────────────────
function onSearchInput() {
  if (searchTimer) clearTimeout(searchTimer);
  const q = (searchQuery.value ?? '').trim();
  if (!q) {
    suggestions.value = [];
    suggestOpen.value = false;
    openGroups.value = {};              // collapse auto-expanded groups
    if (rightView.value === 'table') void store.loadTable(); // reload table without search
    return;
  }
  searchTimer = setTimeout(() => void runSearch(), 280);
}

function onSearchBlur() {
  // Delay so a click on a suggestion fires before suggestions are hidden
  setTimeout(() => { suggestOpen.value = false; }, 160);
}

async function runSearch() {
  const q = (searchQuery.value ?? '').trim();
  if (q.length < 2) { suggestions.value = []; suggestOpen.value = false; return; }
  const s = await api.getSuggestions(q, activeLayer.value, searchScope.value, exactSearch.value);
  suggestions.value = s;
  suggestOpen.value = s.length > 0;
  // Load all uncached group entities then auto-expand matches
  await loadAllGroupEntities();
  autoExpandMatchingGroups(q);
}

async function loadAllGroupEntities() {
  const uncached = store.groups.filter((g) => !entityCache.value[g.cube_group_id]);
  if (!uncached.length) return;
  const fw = store.selectedFramework !== 'All' ? store.selectedFramework : undefined;
  const results = await Promise.all(
    uncached.map((g) => api.getEntities(g.cube_group_id, activeLayer.value, fw)),
  );
  const newCache = { ...entityCache.value };
  uncached.forEach((g, i) => { newCache[g.cube_group_id] = results[i] ?? []; });
  entityCache.value = newCache;
}

function autoExpandMatchingGroups(q: string) {
  const ql = q.toLowerCase();
  const match = (text: string) => exactSearch.value ? text.toLowerCase() === ql : text.toLowerCase().includes(ql);
  const newOpen = { ...openGroups.value };
  store.groups.forEach((g) => {
    const entities = entityCache.value[g.cube_group_id] ?? [];
    if (
      match(g.name) ||
      entities.some((e) => match(e.name) || match(e.code ?? ''))
    ) {
      newOpen[g.cube_group_id] = true;
    }
  });
  openGroups.value = newOpen;
}

async function applySuggestion(s: { text: string; type: string }) {
  searchQuery.value = s.text;
  suggestOpen.value = false;

  // TABLE VIEW: mirror into table search and ensure table data is present
  if (rightView.value === 'table') {
    tableSearch.value = s.text;
    if (!store.tableData.rows.length) void store.loadTable();
  }

  // Refresh left panel (entity cache, auto-expand, suggestions)
  await runSearch();

  // GRAPH/DETAIL VIEW: for entity suggestions, select the entity so the detail panel opens
  if (s.type === 'entity' && rightView.value !== 'table') {
    const entity =
      Object.values(entityCache.value).flat()
        .find((e) => e.name.toLowerCase() === s.text.toLowerCase());
    if (entity) void store.selectEntity(entity);
  }
}

function onScopeChange(scope: string) {
  searchScope.value = scope;
  const q = (searchQuery.value ?? '').trim();
  if (q.length >= 2) void runSearch();
}

function onExactToggle() {
  exactSearch.value = !exactSearch.value;
  const q = (searchQuery.value ?? '').trim();
  if (q.length >= 2) void runSearch();
}

function onTableEntityClick(cubeId: string) {
  // Find entity in any cache and navigate to it in graph view
  const entity =
    store.entities.find((e) => e.cube_id === cubeId) ??
    Object.values(entityCache.value).flat().find((e) => e.cube_id === cubeId);
  if (entity) void store.selectEntity(entity);
  rightView.value = 'graph';
}

// ── vis-network ───────────────────────────────────────────────────────
function buildGraph() {
  if (!graphEl.value) return;
  const { nodes: raw, edges: rawEdges, level } = store.graphData;
  if (!raw.length) { network?.destroy(); network = null; return; }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const nodes = new DataSet<any>(
    raw.map((n) => ({
      ...n,
      shape: level === 1 ? 'ellipse' : 'box',
      size: level === 1 ? Math.max(18, Math.min(55, (n.value ?? 10) * 1.2)) : undefined,
      margin: level === 2 ? 8 : undefined,
    })),
  );
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const edges = new DataSet<any>(
    rawEdges.map((e) => ({ ...e, arrows: { to: { enabled: true, scaleFactor: 0.6 } }, font: { size: 10, align: 'middle' } })),
  );

  network?.destroy();
  network = new Network(
    graphEl.value,
    { nodes, edges },
    {
      groups: {
        cluster: { color: { background: '#0d5c54', border: '#0a4840' }, font: { color: '#fff', size: 12 } },
        entity:  { color: { background: '#2f5d8a', border: '#234870' }, font: { color: '#fff', size: 11 }, shape: 'box' },
      },
      physics: { enabled: level === 1, solver: 'forceAtlas2Based', forceAtlas2Based: { gravitationalConstant: -60 } },
      interaction: { hover: true, tooltipDelay: 120, zoomView: true, dragView: true },
      edges: { smooth: { enabled: true, type: 'dynamic', roundness: 0.5 }, color: { color: '#a8b4c0', highlight: '#0d5c54' } },
    },
  );

  network.on('click', (params) => {
    if (!params.nodes.length) return;
    const id = params.nodes[0] as string;
    if (level === 1) {
      const grp = store.groups.find((g) => g.cube_group_id === id);
      if (grp) void toggleGroup(grp);
    } else {
      const ent = store.entities.find((e) => e.cube_id === id);
      if (ent) void store.selectEntity(ent);
    }
  });

  network.once('afterDrawing', () => {
    network?.fit({ animation: { duration: 400, easingFunction: 'easeInOutQuad' } });
    // Re-apply selection highlight for already-selected entity
    if (store.selectedEntity && raw.some((n) => n.id === store.selectedEntity?.cube_id)) {
      network?.selectNodes([store.selectedEntity.cube_id]);
    }
  });
}

function buildMetaGraph() {
  if (!modelEl.value) return;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const nodes = new DataSet<any>(
    META_NODES.map((n) => ({
      ...n,
      shape: 'box',
      color: { background: '#6d28d9', border: '#5b21b6' },
      font: { color: '#fff', size: 12 },
      margin: 10,
    })),
  );
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const edges = new DataSet<any>(
    META_EDGES.map((e) => ({ ...e, arrows: { to: { enabled: true, scaleFactor: 0.7 } }, font: { size: 10 } })),
  );
  modelNetwork?.destroy();
  modelNetwork = new Network(
    modelEl.value,
    { nodes, edges },
    {
      layout: { hierarchical: { direction: 'LR', sortMethod: 'directed', levelSeparation: 190, nodeSpacing: 80 } },
      physics: false,
      interaction: { hover: true },
    },
  );
  modelNetwork.once('afterDrawing', () => modelNetwork?.fit());
}

function buildErdGraph() {
  if (!modelEl.value) return;
  // Reuse graph data (entity layer ERD) in model canvas
  const { nodes: raw, edges: rawEdges } = store.graphData;
  if (!raw.length) return;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const nodes = new DataSet<any>(raw.map((n) => ({ ...n, shape: 'box', margin: 8 })));
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const edges = new DataSet<any>(rawEdges.map((e) => ({ ...e, arrows: { to: { enabled: true, scaleFactor: 0.6 } } })));
  modelNetwork?.destroy();
  modelNetwork = new Network(modelEl.value, { nodes, edges }, {
    groups: {
      cluster: { color: { background: '#0d5c54', border: '#0a4840' }, font: { color: '#fff' } },
      entity:  { color: { background: '#2f5d8a', border: '#234870' }, font: { color: '#fff' } },
    },
    physics: { enabled: true },
    interaction: { hover: true, zoomView: true, dragView: true },
  });
  modelNetwork.once('afterDrawing', () => modelNetwork?.fit());
}

// ── Full-screen graph ─────────────────────────────────────────────────
function buildFsGraph() {
  if (!fsGraphEl.value) return;
  const { nodes: raw, edges: rawEdges, level } = store.graphData;
  const isModel = fsModelMode.value;
  const src = isModel ? META_NODES : raw;
  const srcEdges = isModel ? META_EDGES : rawEdges;
  if (!src.length) return;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const nodes = new DataSet<any>(
    src.map((n) => ({
      ...n,
      shape: (isModel || level === 2) ? 'box' : 'ellipse',
      size: (!isModel && level === 1) ? Math.max(24, Math.min(70, ((n as GraphNode).value ?? 10) * 1.4)) : undefined,
      margin: (isModel || level === 2) ? 10 : undefined,
      ...(isModel ? { color: { background: '#6d28d9', border: '#5b21b6' }, font: { color: '#fff', size: 13 } } : {}),
    })),
  );
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const edges = new DataSet<any>(
    srcEdges.map((e) => ({ ...e, arrows: { to: { enabled: true, scaleFactor: 0.7 } }, font: { size: 12, align: 'middle' } })),
  );

  fsNetwork?.destroy();
  fsNetwork = new Network(
    fsGraphEl.value,
    { nodes, edges },
    {
      groups: {
        cluster: { color: { background: '#0d5c54', border: '#0a4840' }, font: { color: '#fff', size: 14 } },
        entity:  { color: { background: '#2f5d8a', border: '#234870' }, font: { color: '#fff', size: 13 }, shape: 'box' },
      },
      layout: isModel ? { hierarchical: { direction: 'LR', sortMethod: 'directed', levelSeparation: 220, nodeSpacing: 100 } } : undefined,
      physics: isModel ? false : { enabled: level === 1, solver: 'forceAtlas2Based', forceAtlas2Based: { gravitationalConstant: -80 } },
      interaction: { hover: true, tooltipDelay: 100, zoomView: true, dragView: true },
      edges: { smooth: { enabled: true, type: 'dynamic', roundness: 0.5 }, color: { color: '#a8b4c0', highlight: '#0d5c54' } },
    },
  );

  fsNetwork.on('click', (params) => {
    if (!params.nodes.length || isModel) return;
    const id = params.nodes[0] as string;
    if (level === 1) {
      const grp = store.groups.find((g) => g.cube_group_id === id);
      if (grp) void store.selectGroup(grp);
    } else {
      const ent = store.entities.find((e) => e.cube_id === id);
      if (ent) void store.selectEntity(ent);
    }
  });

  fsNetwork.once('afterDrawing', () => {
    fsNetwork?.fit({ animation: { duration: 500, easingFunction: 'easeInOutQuad' } });
    // Highlight selected entity in FS graph
    if (!isModel && store.selectedEntity && src.some((n) => n.id === store.selectedEntity?.cube_id)) {
      fsNetwork?.selectNodes([store.selectedEntity.cube_id]);
    }
  });
}

async function openFs() {
  fsModelMode.value = (rightView.value === 'model');
  fsVisible.value = true;
  await nextTick();
  buildFsGraph();
  // Focus overlay so Esc key works
  (document.querySelector('.bird-fs-overlay') as HTMLElement | null)?.focus();
}

function closeFs() {
  fsVisible.value = false;
  fsNetwork?.destroy();
  fsNetwork = null;
}

// ── Lifecycle ─────────────────────────────────────────────────────────
onMounted(async () => {
  await store.selectLayer('LDM');
  await nextTick();
  buildGraph();
});

watch(() => store.graphData, async () => {
  await nextTick();
  if (rightView.value === 'graph') buildGraph();
  if (rightView.value === 'model' && modelTab.value === 'erd') buildErdGraph();
  // Rebuild FS graph if open
  if (fsVisible.value) buildFsGraph();
});

// Highlight + focus the selected entity node in main and FS networks
watch(() => store.selectedEntity, (entity) => {
  if (!entity) {
    network?.unselectAll();
    fsNetwork?.unselectAll();
    return;
  }
  const nodeExists = store.graphData.nodes.some((n) => n.id === entity.cube_id);
  if (nodeExists) {
    if (network && rightView.value === 'graph') {
      network.selectNodes([entity.cube_id]);
      network.focus(entity.cube_id, { scale: 1.35, animation: { duration: 400, easingFunction: 'easeInOutQuad' } });
    }
    if (fsNetwork && fsVisible.value && !fsModelMode.value) {
      fsNetwork.selectNodes([entity.cube_id]);
      fsNetwork.focus(entity.cube_id, { scale: 1.35, animation: { duration: 400, easingFunction: 'easeInOutQuad' } });
    }
  }
});

watch(rightView, async (v) => {
  await nextTick();
  if (v === 'graph') buildGraph();
  if (v === 'model') {
    if (modelTab.value === 'meta') buildMetaGraph(); else buildErdGraph();
  }
  if (v === 'table') await store.loadTable();
});

watch(() => store.selectedGroup, async () => {
  if (rightView.value === 'table') await store.loadTable();
});

watch(modelTab, async () => {
  await nextTick();
  if (modelTab.value === 'meta') buildMetaGraph(); else buildErdGraph();
});

onBeforeUnmount(() => { network?.destroy(); modelNetwork?.destroy(); fsNetwork?.destroy(); });
</script>

<style scoped>
/* ── Page shell ────────────────────────────────────────────────────── */
.bird-kb-page { height: calc(100vh - 50px); overflow: hidden; background: #f6f4f0; }

/* ── Header ────────────────────────────────────────────────────────── */
.bird-header { background: #ffffff; border-bottom: 1px solid #ddd6c8; padding: 0 1rem; flex-shrink: 0; box-shadow: 0 1px 3px rgba(28,27,24,0.06); }
.bird-header-row { display: flex; align-items: center; padding: 0.55rem 0 0.3rem; gap: 0.5rem; }
.bird-title-block { display: flex; align-items: center; gap: 0.5rem; }
.bird-title-text { font-size: 15px; font-weight: 700; color: #1c1b18; letter-spacing: 0.01em; }
.bird-version-chip { font-size: 10px; margin-left: 2px; }
.bird-layer-tabs { background: transparent; }
.bird-layer-tab { font-size: 12.5px; font-weight: 600; letter-spacing: 0.04em; min-height: 32px; }
.bird-layer-tab.layer-primary :deep(.q-tab__label) { color: #0d5c54; }
.bird-layer-tab.layer-secondary :deep(.q-tab__label) { color: #86827a; }
.bird-framework-row { display: flex; align-items: center; gap: 0.5rem; padding: 0.2rem 0 0.5rem; }
.bird-framework-label { font-size: 10.5px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: #86827a; }
.bird-framework-toggle { border-radius: 8px; font-size: 11.5px; }

/* ── SMCube explainer ──────────────────────────────────────────────── */
.smcube-explainer { background: #f0f8f6; border-bottom: 1px solid #ddd6c8; padding: 0.6rem 1rem 0.8rem; flex-shrink: 0; }
.smcube-explainer-head { display: flex; justify-content: space-between; align-items: center; font-weight: 600; color: #1c1b18; font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 0.5rem; }
.smcube-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 0.2rem 1rem; }
.smcube-row { display: flex; gap: 0.5rem; font-size: 12px; }
.smcube-term { color: #0d5c54; font-weight: 600; min-width: 160px; flex-shrink: 0; }
.smcube-meaning { color: #4a473f; }

/* ── Body ──────────────────────────────────────────────────────────── */
.bird-body { display: flex; flex: 1; min-height: 0; overflow: hidden; }

/* ── Left panel ────────────────────────────────────────────────────── */
.bird-left { width: 280px; flex-shrink: 0; border-right: 1px solid #ddd6c8; background: #e8edf2; display: flex; flex-direction: column; overflow: hidden; }
.bird-scope-bar { display: flex; gap: 4px; padding: 6px 8px; overflow-x: auto; flex-shrink: 0; border-bottom: 1px solid #ddd6c8; scrollbar-width: thin; scrollbar-color: #c4cbda transparent; }
.bird-scope-bar::-webkit-scrollbar { height: 3px; }
.bird-scope-bar::-webkit-scrollbar-thumb { background: #c4cbda; border-radius: 2px; }
.bird-scope-pill { font-size: 10.5px; padding: 2px 8px; border-radius: 12px; cursor: pointer; white-space: nowrap; color: #86827a; border: 1px solid transparent; transition: all 0.12s; flex-shrink: 0; user-select: none; }
.bird-scope-pill:hover { color: #1c1b18; background: rgba(13,92,84,0.08); }
.bird-scope-pill.is-active { background: rgba(13,92,84,0.12); color: #0d5c54; border-color: rgba(13,92,84,0.28); font-weight: 600; }
.bird-search-wrap { position: relative; }
.bird-search { background: transparent; }
.bird-search :deep(.q-field__control) { background: #ffffff !important; border-radius: 8px; }
.bird-suggest-dropdown { position: absolute; left: 0; right: 0; z-index: 9999; background: #ffffff; border: 1px solid #ddd6c8; border-top: none; border-radius: 0 0 8px 8px; box-shadow: 0 6px 20px rgba(28,27,24,0.12); overflow: hidden; max-height: 210px; overflow-y: auto; }
.bird-suggest-item { display: flex; align-items: center; gap: 6px; padding: 6px 10px; cursor: pointer; font-size: 12px; color: #1c1b18; }
.bird-suggest-item:hover { background: #e6f2f0; }
.bird-suggest-text { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bird-suggest-type-label { font-size: 10px; color: #86827a; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; flex-shrink: 0; }
.bird-exact-row { display: flex; align-items: center; gap: 6px; padding: 2px 12px 6px; flex-shrink: 0; }
.bird-exact-pill { display: inline-flex; align-items: center; gap: 4px; font-size: 10.5px; padding: 2px 8px; border-radius: 12px; cursor: pointer; border: 1px solid #ddd6c8; background: transparent; color: #86827a; font-family: inherit; transition: all 0.12s; user-select: none; }
.bird-exact-pill:hover { color: #1c1b18; border-color: #0d5c54; background: rgba(13,92,84,0.05); }
.bird-exact-pill.is-active { background: rgba(13,92,84,0.12); color: #0d5c54; border-color: rgba(13,92,84,0.4); font-weight: 600; }
.bird-exact-hint { font-size: 10px; color: #0d5c54; font-weight: 600; }
.bird-group-scroll { flex: 1; overflow-y: auto; overflow-x: hidden; padding: 0 4px 8px; }
.bird-group-block { margin-bottom: 2px; }
.bird-group-header { display: flex; align-items: center; gap: 4px; padding: 5px 6px; border-radius: 8px; cursor: pointer; transition: background 0.12s; color: #1c1b18; font-size: 12.5px; font-weight: 600; }
.bird-group-header:hover { background: rgba(13,92,84,0.08); }
.bird-group-header.is-active { background: rgba(13,92,84,0.12); color: #0d5c54; }
.bird-group-chevron { color: #86827a; flex-shrink: 0; }
.bird-group-name { flex: 1; }
.bird-count-badge { font-size: 10px; margin-left: auto; flex-shrink: 0; }
.bird-entity-list { padding-left: 22px; }
.bird-entity-row { display: flex; align-items: center; gap: 5px; padding: 3px 6px; border-radius: 6px; cursor: pointer; color: #4a473f; font-size: 12px; transition: background 0.1s; }
.bird-entity-row:hover { background: rgba(13,92,84,0.08); color: #1c1b18; }
.bird-entity-row.is-selected { background: rgba(13,92,84,0.15); color: #0d5c54; }
.bird-entity-name { flex: 1; }
.bird-fw-badge { font-size: 9px; flex-shrink: 0; }
.bird-spinner-row { display: flex; justify-content: center; padding: 1.5rem 0; }
.bird-spinner-row-sm { display: flex; justify-content: center; padding: 6px 0; }

/* ── Right panel ───────────────────────────────────────────────────── */
.bird-right { flex: 1; display: flex; flex-direction: column; overflow: hidden; background: #f6f4f0; }
.bird-right-toolbar { display: flex; align-items: center; gap: 0.75rem; padding: 0.5rem 0.75rem; background: #ffffff; border-bottom: 1px solid #ddd6c8; flex-shrink: 0; }
.bird-view-toggle :deep(.q-btn) { font-size: 12px; }
.bird-breadcrumb { display: flex; align-items: center; gap: 4px; font-size: 11.5px; color: #86827a; overflow: hidden; }
.bc-layer { color: #0d5c54; font-weight: 700; letter-spacing: 0.04em; }
.bc-group { color: #1c1b18; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bc-entity { color: #2f5d8a; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* ── Graph ─────────────────────────────────────────────────────────── */
.bird-graph-wrap { flex: 1; position: relative; display: flex; flex-direction: column; overflow: hidden; min-height: 0; }
.bird-vis-canvas { flex: 1; min-height: 0; background: #eef2f7; border-radius: 0; }
.bird-graph-overlay { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; color: #86827a; font-size: 13px; z-index: 1; background: rgba(246,244,240,0.75); }
.bird-graph-hint { font-size: 11px; color: #86827a; text-align: center; padding: 4px; background: #ffffff; flex-shrink: 0; border-top: 1px solid #ddd6c8; }

/* ── Table ─────────────────────────────────────────────────────────── */
/* Outer wrap contains but does NOT scroll — inner container owns both scroll axes */
.bird-table-wrap { flex: 1; min-height: 0; display: flex; flex-direction: column; overflow: hidden; }
.bird-table-filters { flex-shrink: 0; background: #ffffff; border-bottom: 1px solid #ddd6c8; }
.bird-table-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; color: #86827a; font-size: 13px; flex: 1; }
.bird-table-loading { display: flex; align-items: center; justify-content: center; gap: 10px; padding: 2rem; color: #86827a; font-size: 13px; flex: 1; }
.bird-table-cap-notice { font-size: 11px; color: #86827a; text-align: center; padding: 6px 4px; background: #ffffff; border-top: 1px solid #ddd6c8; flex-shrink: 0; }
.bird-table-entity-link { color: #2f5d8a; cursor: pointer; }
.bird-table-entity-link:hover { text-decoration: underline; }
/* q-table fills wrap and is the scroll root */
.bird-data-table { background: transparent; flex: 1; min-height: 0; display: flex; flex-direction: column; }
.bird-data-table :deep(.q-table__container) { flex: 1; min-height: 0; display: flex; flex-direction: column; }
/* .q-table__middle owns BOTH scroll axes — scrollbar stays in the visible area */
.bird-data-table :deep(.q-table__middle) { flex: 1; min-height: 0; overflow: auto !important; }
/* Minimum table width keeps all 8 columns visible without collapse */
.bird-data-table :deep(table) { min-width: 1000px; }
/* Sticky column headers — pinned to top of the .q-table__middle scroll area */
.bird-data-table :deep(thead tr th) { position: sticky; top: 0; z-index: 2; background: #f0f4f8 !important; color: #4a473f; font-size: 11px; font-weight: 700; white-space: nowrap; }
.bird-data-table :deep(tbody td) { color: #1c1b18; font-size: 12px; }
.bird-data-table :deep(tbody tr:hover td) { background: #e6f2f0; }

/* ── Data model ────────────────────────────────────────────────────── */
.bird-model-wrap { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.bird-model-tabs { background: #ffffff; border-bottom: 1px solid #ddd6c8; flex-shrink: 0; }

/* ── Entity detail panel ───────────────────────────────────────────── */
.bird-detail-panel { border-top: 1px solid #ddd6c8; background: #ffffff; max-height: 50%; overflow-y: auto; padding: 0.75rem 1rem 0; flex-shrink: 0; box-shadow: 0 -2px 8px rgba(28,27,24,0.05); position: relative; }
.bird-detail-panel.is-collapsed { max-height: none; overflow-y: visible; padding-bottom: 0; }
.bird-detail-panel.is-resizing { user-select: none; }
.bird-detail-resize-handle { position: absolute; top: 0; left: 0; right: 0; height: 10px; cursor: ns-resize; z-index: 2; display: flex; align-items: center; justify-content: center; }
.bird-detail-resize-handle:hover .bird-detail-resize-grip, .bird-detail-panel.is-resizing .bird-detail-resize-grip { background: #0d5c54; width: 40px; }
.bird-detail-resize-grip { display: block; width: 28px; height: 3px; border-radius: 2px; background: #ddd6c8; transition: background 0.12s, width 0.12s; }
.bird-detail-body { padding-bottom: 0.75rem; }
.bird-detail-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 0.5rem; margin-bottom: 0.4rem; flex-wrap: wrap; }
.bird-detail-actions { display: flex; align-items: center; gap: 2px; flex-shrink: 0; margin-left: auto; }
.bird-detail-title-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.bird-detail-name { font-size: 14px; font-weight: 700; color: #1c1b18; }
.bird-detail-desc { font-size: 12px; color: #86827a; margin: 0 0 0.6rem; }
.bird-role-section { margin-bottom: 0.5rem; }
.bird-role-head { display: flex; align-items: center; gap: 5px; margin-bottom: 3px; font-size: 11.5px; font-weight: 700; color: #86827a; text-transform: uppercase; letter-spacing: 0.05em; }
.bird-role-label { }
.bird-attr-row { margin-bottom: 3px; }
.bird-attr-main-row { display: flex; align-items: center; gap: 6px; padding: 2px 4px; border-radius: 5px; }
.bird-attr-main-row:hover { background: #e6f2f0; }
.bird-attr-varname { font-size: 12.5px; color: #1c1b18; font-weight: 500; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bird-attr-domain { font-size: 11px; color: #86827a; }
.bird-attr-type { font-size: 11px; color: #86827a; }
.bird-attr-key-icon { opacity: 0.65; flex-shrink: 0; margin-left: auto; }
.bird-members-block { padding-left: 12px; background: #f0f4f8; border-left: 2px solid #ddd6c8; margin-left: 4px; max-height: 150px; overflow-y: auto; }
.bird-member-row { display: flex; gap: 8px; padding: 1px 4px; font-size: 11px; }
.bird-member-code { color: #0d5c54; font-family: 'IBM Plex Mono', monospace; font-weight: 600; min-width: 60px; }
.bird-member-name { color: #4a473f; }
.bird-legal-expansion { color: #86827a; font-size: 12px; }
.bird-legal-row { display: flex; gap: 8px; padding: 2px 4px; font-size: 11.5px; }
.bird-legal-code { color: #0d5c54; font-weight: 600; }
.bird-legal-article { color: #86827a; }
.bird-legal-desc { color: #86827a; }

/* ── Forward chain ─────────────────────────────────────────────────── */
.bird-chain-panel { border-top: 1px solid #ddd6c8; background: #f0f8f6; padding: 0.6rem 1rem; flex-shrink: 0; }
.bird-chain-head { display: flex; align-items: center; gap: 6px; margin-bottom: 0.5rem; font-size: 13px; font-weight: 700; color: #a9651b; }
.bird-chain-head :deep(.q-btn) { margin-left: auto; }
.bird-chain-flow { display: flex; align-items: flex-start; gap: 0; overflow-x: auto; padding-bottom: 4px; }
.bird-chain-node { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 6px 10px; background: #ffffff; border: 1px solid #ddd6c8; border-radius: 8px; min-width: 120px; flex-shrink: 0; box-shadow: 0 1px 3px rgba(28,27,24,0.06); }
.bird-chain-source { border-color: #2f5d8a; }
.bird-chain-node-name { font-size: 11.5px; color: #1c1b18; font-weight: 600; text-align: center; max-width: 140px; word-break: break-word; }
.bird-chain-arrow-block { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px; padding: 0 4px; flex-shrink: 0; }
.bird-chain-arrow-line { width: 24px; height: 1px; background: #ddd6c8; }
.bird-chain-type-badge { font-size: 9px; }
.bird-chain-algo :deep(.q-expansion-item__header) { font-size: 10px; color: #86827a; padding: 0; min-height: 0; }
.bird-algo-text { font-size: 10px; color: #4a473f; white-space: pre-wrap; background: #f0f4f8; padding: 4px; border-radius: 4px; margin: 2px 0 0; max-width: 200px; }

/* ── Full-screen overlay ───────────────────────────────────────────── */
.bird-fs-overlay { position: fixed; inset: 0; z-index: 8000; background: #f6f4f0; display: flex; flex-direction: column; outline: none; }
.bird-fs-header { display: flex; align-items: center; justify-content: space-between; padding: 0.6rem 1rem; background: #ffffff; border-bottom: 1px solid #ddd6c8; flex-shrink: 0; box-shadow: 0 1px 4px rgba(28,27,24,0.07); }
.bird-fs-header-left { display: flex; align-items: center; gap: 0.5rem; overflow: hidden; }
.bird-fs-title { font-size: 15px; font-weight: 700; color: #1c1b18; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bird-fs-body { display: flex; flex: 1; min-height: 0; overflow: hidden; }
.bird-fs-canvas-wrap { flex: 1; position: relative; display: flex; flex-direction: column; overflow: hidden; min-height: 0; }
.bird-fs-canvas { flex: 1; min-height: 0; background: #eef2f7; }
.bird-fs-canvas-overlay { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; z-index: 1; background: rgba(246,244,240,0.7); }
.bird-fs-canvas-hint { font-size: 11px; color: #86827a; text-align: center; padding: 4px; background: #ffffff; flex-shrink: 0; border-top: 1px solid #ddd6c8; }
.bird-fs-detail { width: 360px; flex-shrink: 0; border-left: 1px solid #ddd6c8; background: #ffffff; overflow-y: auto; padding: 0.85rem 1rem; display: flex; flex-direction: column; gap: 4px; }
.bird-fs-detail--empty { align-items: center; justify-content: center; color: #86827a; font-size: 13px; gap: 10px; }
.bird-fs-detail-head { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 4px; }
.bird-fs-detail-name { font-size: 14px; font-weight: 700; color: #1c1b18; }
.bird-fs-detail-desc { font-size: 12px; color: #86827a; margin: 0 0 6px; }
.bird-fs-role-section { margin-bottom: 6px; }
.bird-fs-role-head { display: flex; align-items: center; gap: 5px; margin-bottom: 3px; font-size: 11px; font-weight: 700; color: #86827a; text-transform: uppercase; letter-spacing: 0.05em; }
.bird-fs-attr-row { display: flex; align-items: center; gap: 5px; padding: 2px 4px; border-radius: 4px; font-size: 12px; flex-wrap: wrap; }
.bird-fs-attr-row:hover { background: #e6f2f0; }
.bird-fs-attr-name { font-weight: 500; color: #1c1b18; min-width: 0; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bird-fs-attr-domain { font-size: 11px; color: #86827a; flex-shrink: 0; }
/* ── Fullscreen transition ─────────────────────────────────────────── */
.fs-fade-enter-active, .fs-fade-leave-active { transition: opacity 0.18s ease; }
.fs-fade-enter-from, .fs-fade-leave-to { opacity: 0; }
</style>

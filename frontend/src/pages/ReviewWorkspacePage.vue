<template>
  <q-page class="rw-page">
    <div class="rw-header">
      <div class="rw-eyebrow">Workspace</div>
      <div class="rw-title-row">
        <q-icon name="rate_review" size="22px" class="rw-title-icon" />
        <h1 class="rw-title">Review Workspace</h1>
        <q-badge v-if="totalPending > 0" :label="totalPending" color="amber-9" text-color="white" />
      </div>
      <p class="rw-subtitle">The <strong>Steward</strong> reviews submitted interpretation sets — definition, business name &amp; semantic type together — plus reference codesets. Roles are advisory (no access control yet).</p>
    </div>

    <transition name="fade">
      <div v-if="displayCoverage" class="cov-panel q-mb-md">
        <div class="cov-header">
          <q-icon name="bar_chart" size="18px" class="q-mr-xs" style="color:var(--ink-3)" />
          <span class="cov-title">Review Coverage — {{ selectedSource || 'All sources' }}</span>
          <q-btn flat dense round icon="refresh" size="sm" @click="refresh" :loading="loading || coverageLoading"><q-tooltip>Refresh queue &amp; coverage</q-tooltip></q-btn>
        </div>
        <div class="cov-grid">
          <!-- Scope -->
          <div class="cov-card">
            <div class="cov-card-label">Scope</div>
            <div class="cov-card-value">{{ displayCoverage.total_elements }}</div>
            <div class="cov-breakdown">
              <span class="cov-pill cov-pill--defined">{{ scopeSources }} source{{ scopeSources === 1 ? '' : 's' }}</span>
              <span class="cov-pill cov-pill--empty">{{ displayCoverage.total_elements }} columns</span>
            </div>
          </div>
          <!-- Interpretations submitted -->
          <div class="cov-card">
            <div class="cov-card-label">Interpretations Submitted</div>
            <div class="cov-card-value" :style="{ color: coverageColor(defSubmittedPct) }">{{ defSubmittedPct }}%</div>
            <div class="cov-progress-wrap"><div class="cov-bar-bg"><div class="cov-bar-fill" :style="{ width: defSubmittedPct + '%', background: coverageColor(defSubmittedPct) }" /></div></div>
            <div class="cov-breakdown">
              <span v-if="displayCoverage.definition.empty > 0" class="cov-pill cov-pill--empty">{{ displayCoverage.definition.empty }} empty</span>
              <span class="cov-pill cov-pill--draft">{{ displayCoverage.definition.draft }} draft</span>
              <span class="cov-pill cov-pill--pending">{{ displayCoverage.definition.in_review }} in review</span>
              <span class="cov-pill cov-pill--approved">{{ displayCoverage.definition.approved }} approved</span>
            </div>
          </div>
          <!-- Approved interpretations -->
          <div class="cov-card">
            <div class="cov-card-label">Approved Interpretations</div>
            <div class="cov-card-value" :style="{ color: coverageColor(defApprovedPct) }">{{ defApprovedPct }}%</div>
            <div class="cov-progress-wrap"><div class="cov-bar-bg"><div class="cov-bar-fill" :style="{ width: defApprovedPct + '%', background: coverageColor(defApprovedPct) }" /></div></div>
            <div class="cov-breakdown"><span class="cov-meta">{{ displayCoverage.definition.approved }} of {{ displayCoverage.total_elements }} columns</span></div>
          </div>
          <!-- Reference codes submitted -->
          <div class="cov-card">
            <div class="cov-card-label">Reference Codes Submitted</div>
            <div class="cov-card-value" :style="{ color: coverageColor(codesSubmittedPct) }">{{ codesSubmittedPct }}%</div>
            <div class="cov-progress-wrap"><div class="cov-bar-bg"><div class="cov-bar-fill" :style="{ width: codesSubmittedPct + '%', background: coverageColor(codesSubmittedPct) }" /></div></div>
            <div class="cov-breakdown"><span class="cov-meta">{{ displayCoverage.reference_codes.submitted }} of {{ displayCoverage.reference_codes.total_coded }} coded columns</span></div>
          </div>
          <!-- Pending reviews (steward workload from the queue) -->
          <div class="cov-card">
            <div class="cov-card-label">Pending Reviews</div>
            <div class="cov-card-value">{{ pendingByAspect.total }}</div>
            <div class="cov-breakdown">
              <span class="cov-pill cov-pill--pending">{{ pendingByAspect.definition }} interpretation{{ pendingByAspect.definition === 1 ? '' : 's' }}</span>
              <span class="cov-pill cov-pill--draft">{{ pendingByAspect.reference }} codeset{{ pendingByAspect.reference === 1 ? '' : 's' }}</span>
            </div>
          </div>
        </div>
        <!-- By-source breakdown — shows at a glance which source is under-represented -->
        <div v-if="!selectedSource && bySourceChartData.labels.length > 1" class="cov-chart-panel">
          <div class="cov-chart-label">Interpretation Lifecycle by Source</div>
          <div class="cov-chart-wrap">
            <Bar :data="bySourceChartData" :options="bySourceChartOptions" />
          </div>
        </div>
      </div>
    </transition>

    <!-- ── Two-panel: source scope + queue (left) · composite review (right) ─ -->
    <div class="rw-split rw-split--open">

      <!-- LEFT: source scope + dataset/column queue -->
      <div class="rw-list-pane">
        <div class="rw-list-head">
          <div class="rw-rail-label">Source</div>
          <q-select
            v-model="selectedSource"
            :options="sourceOptions"
            emit-value
            map-options
            dense outlined
            class="rw-source-select"
            @update:model-value="onSourceChange"
          />
        </div>
        <div v-if="!loading && columnGroups.length" class="rw-list-actions">
          <button class="rw-expand-toggle" @click="toggleAllGroups()">
            <q-icon :name="allExpanded ? 'unfold_less' : 'unfold_more'" size="14px" />{{ allExpanded ? 'Collapse all' : 'Expand all' }}
          </button>
        </div>
        <div v-if="loading" class="rw-list-msg"><StagedLoader :stages="queueLoadStages" :completed="queueProgress.completed" :active-detail="queueProgress.detail" :active-fraction="queueProgress.fraction" /></div>
        <div v-else-if="filteredItems.length === 0" class="rw-list-msg">
          <q-icon name="check_circle" size="30px" color="positive" />
          <span>All items approved<template v-if="selectedSource"> for <strong>{{ selectedSource }}</strong></template>.</span>
        </div>
        <template v-else>
          <div v-for="group in columnGroups" :key="group.tableKey" class="rw-group">
            <button class="rw-group-header" @click="toggleTableGroup(group.tableKey)">
              <span class="rw-group-label">{{ group.label }}</span>
              <span class="rw-group-count">{{ group.total }}</span>
              <q-icon :name="isCollapsed(group.tableKey) ? 'expand_more' : 'expand_less'" size="14px" class="rw-group-chevron" />
            </button>
            <div v-if="!isCollapsed(group.tableKey)" class="rw-group-body">
              <button v-for="entry in group.columns" :key="entry.tableKey + '|' + entry.column"
                class="rw-item-btn"
                :class="{ 'rw-item-btn--active': selectedItem?.source === entry.source && selectedItem?.table === entry.table && selectedItem?.column === entry.column }"
                @click="selectItem(entry.primaryItem)">
                <span class="rw-item-dot dot--blue" />
                <span class="rw-item-info">
                  <code class="rw-item-col">{{ entry.column }}</code>
                  <span v-if="entry.glossTitle" class="rw-item-path">Term: {{ entry.glossTitle }}</span>
                </span>
                <span v-if="entry.hasRefData" class="rw-item-refchip" :title="`${entry.refInReview} code(s) in review` + (entry.refTombstone ? `, ${entry.refTombstone} withdrawn/revoked` : '')">
                  {{ entry.refInReview }} code{{ entry.refInReview === 1 ? '' : 's' }}<template v-if="entry.refTombstone"> · {{ entry.refTombstone }}⌫</template>
                </span>
              </button>
            </div>
          </div>
        </template>
      </div>

      <!-- RIGHT: composite element review -->
      <div class="rw-detail-pane rw-detail-pane--visible">

        <div v-if="!selectedItem" class="rw-dp-placeholder">
          <q-icon name="touch_app" size="40px" style="opacity:.2" />
          <span>Select an item to review.</span>
        </div>

        <template v-else>
          <div class="rw-dp-top">
            <div class="rw-dp-col-row">
              <code class="rw-dp-col-name">{{ selectedItem.source }}.{{ selectedItem.column }}</code>
              <span class="rw-dp-badge">Read-only</span>
              <span v-if="elementDetail?.data_type" class="rw-dp-chip">{{ elementDetail.data_type }}</span>
              <span v-if="elementDetail?.is_primary_key" class="rw-dp-chip rw-dp-chip--pk">Primary key</span>
              <span v-if="elementDetail?.pii" class="rw-dp-pii">PII<template v-if="elementDetail.pii_category"> · {{ elementDetail.pii_category }}</template></span>
            </div>
            <a class="rw-dp-link" href="#" @click.prevent="openInWorkspace">Open in Asset Workspace to edit&nbsp;↗</a>
          </div>

          <!-- Review tabs: Interpretation (definition + semantic + glossary) · Reference Data (own workflow) -->
          <div class="rw-dp-tabs">
            <button :class="['rw-dp-tab-btn', { 'rw-dp-tab-btn--active': activeReviewTab === 'interpretation', 'rw-dp-tab-btn--disabled': interpTabDisabled }]" :disabled="interpTabDisabled" :title="interpTabTitle" @click="onInterpTabClick()">Interpretation</button>
            <button :class="['rw-dp-tab-btn', { 'rw-dp-tab-btn--active': activeReviewTab === 'refdata', 'rw-dp-tab-btn--disabled': refTabDisabled }]" :disabled="refTabDisabled" :title="refTabTitle" @click="onRefTabClick()">Reference Data</button>
          </div>

          <div v-if="elementLoading" class="rw-dp-body">
            <div class="rw-dp-loading"><StagedLoader :stages="elementLoadStages" :completed="elementProgress.completed" :active-detail="elementProgress.detail" :active-fraction="elementProgress.fraction" /></div>
          </div>

          <div v-else-if="elementDetail" class="rw-dp-body">

            <!-- ═══ INTERPRETATION TAB (definition · semantic type · glossary) ═══ -->
            <template v-if="activeReviewTab === 'interpretation'">

              <!-- ── DEFINITION ─────────────────────────────────────────── -->
              <section class="rw-sec">
                <div class="rw-sec-head rw-sec-head--definition">
                  <q-icon name="description" size="14px" />Definition
                  <q-space />
                  <span class="rw-sec-badge">{{ capitalise(elementDetail.lifecycle_state) }}</span>
                </div>
                <div class="rw-sec-body">
                  <div class="rw-dp-row rw-dp-row--tall">
                    <span class="rw-dp-key">Definition</span>
                    <span class="rw-dp-val" :class="{ 'rw-dp-val--muted': !elementDetail.column_description }">{{ elementDetail.column_description || 'No definition recorded.' }}</span>
                  </div>
                  <div class="rw-dp-row">
                    <span class="rw-dp-key">Business name</span>
                    <span class="rw-dp-val">{{ elementDetail.business_name || '—' }}</span>
                  </div>
                </div>
              </section>

              <!-- ── SEMANTIC TYPE ──────────────────────────────────────── -->
              <section class="rw-sec">
                <div class="rw-sec-head rw-sec-head--semantic">
                  <q-icon name="category" size="14px" />Semantic Type
                </div>
                <div class="rw-sec-body">
                  <div class="rw-dp-row">
                    <span class="rw-dp-key">Type</span>
                    <span class="rw-dp-val">{{ formatTypeLabel(elementDetail.semantic_type ?? null) }}<span class="rw-dp-val--muted"> · {{ elementDetail.semantic_source === 'rule' ? 'rule-based' : 'AI-assisted' }}</span></span>
                  </div>
                  <div class="rw-dp-row">
                    <span class="rw-dp-key">Domain &amp; scope</span>
                    <span class="rw-dp-val">{{ semanticDomainLabel(elementDetail.semantic_domain_role) }}<span v-if="elementDetail.semantic_scope" class="rw-dp-val--muted"> · {{ elementDetail.semantic_scope }}</span></span>
                  </div>
                  <div v-if="sampleValuesText" class="rw-dp-row rw-dp-row--tall">
                    <span class="rw-dp-key">Sample values</span>
                    <span class="rw-dp-val rw-dp-val--muted">{{ sampleValuesText }}</span>
                  </div>
                  <div v-if="elementDetail.semantic_type_value_conflict" class="rw-dp-row">
                    <span class="rw-dp-key">Heads-up</span>
                    <span class="rw-dp-val rw-dp-val--danger">⚠ The values don’t match this type — check before approving.</span>
                  </div>
                  <div class="rw-dp-note">Only accepted semantic types can be submitted for review.</div>
                </div>
              </section>

              <!-- ── GLOSSARY LINKAGE (always shown, even when unlinked) ── -->
              <section class="rw-sec">
                <div class="rw-sec-head rw-sec-head--glossary"><q-icon name="menu_book" size="14px" />Glossary Linkage</div>
                <div class="rw-sec-body">
                  <template v-if="elementDetail.glossary_term">
                    <div class="rw-dp-row">
                      <span class="rw-dp-key">Term</span>
                      <a class="rw-dp-val rw-dp-link" href="#" @click.prevent="openGlossaryTerm()">{{ elementDetail.glossary_term.title }}&nbsp;↗</a>
                      <span class="rw-dp-state rw-dp-state--confirmed" style="text-transform:capitalize">{{ elementDetail.glossary_term.status }}</span>
                    </div>
                    <div v-if="elementDetail.glossary_term.business_description" class="rw-dp-row rw-dp-row--tall">
                      <span class="rw-dp-key">Business desc.</span>
                      <span class="rw-dp-val">{{ elementDetail.glossary_term.business_description }}</span>
                    </div>
                    <div v-if="elementDetail.glossary_term.detailed_description && elementDetail.glossary_term.detailed_description !== elementDetail.glossary_term.business_description" class="rw-dp-row rw-dp-row--tall">
                      <span class="rw-dp-key">Detailed desc.</span>
                      <span class="rw-dp-val">{{ elementDetail.glossary_term.detailed_description }}</span>
                    </div>
                    <div v-if="elementDetail.glossary_term.steward" class="rw-dp-row">
                      <span class="rw-dp-key">Steward</span>
                      <span class="rw-dp-val">{{ elementDetail.glossary_term.steward }}</span>
                    </div>
                  </template>
                  <div v-else class="rw-dp-row">
                    <span class="rw-dp-key">Term</span>
                    <span class="rw-dp-val rw-dp-val--muted">No glossary term linked.</span>
                  </div>
                </div>
              </section>

              <!-- ── REFERENCE CODESET APPLICABILITY (coloured bar; links into the Reference Data tab) ── -->
              <section class="rw-sec rw-refbar">
                <div class="rw-sec-head rw-sec-head--refdata">
                  <q-icon name="table_chart" size="14px" />Reference Codeset
                  <q-space />
                  <span v-if="refDataLoading" class="rw-sec-badge">checking…</span>
                  <a v-else-if="refCodesetSubmitted" href="#" class="rw-refbar-link" @click.prevent="onRefTabClick()">Review Reference Codeset&nbsp;↗</a>
                  <span v-else-if="refData?.is_coded" class="rw-sec-badge">No codes submitted</span>
                  <span v-else class="rw-sec-badge">Not applicable</span>
                </div>
              </section>

            </template>

            <!-- ═══ REFERENCE DATA TAB (own per-code review workflow) ═══ -->
            <template v-else>
              <section class="rw-sec">
                <div class="rw-sec-head rw-sec-head--refdata">
                  <q-icon name="table_chart" size="14px" />Reference Data
                  <q-space />
                  <span v-if="refData?.status" class="rw-sec-badge" style="text-transform:capitalize">{{ refData.status }}</span>
                </div>
                <div class="rw-sec-body">
                  <div v-if="refDataLoading" class="rw-dp-loading"><q-spinner size="18px" /><span class="q-ml-sm">Loading codes…</span></div>
                  <template v-else-if="refData">
                    <!-- Bound-field binding decision (2026-08-16 redesign) — a plain statement,
                         never a per-code list, since recognised codes are governed by the set. -->
                    <div v-if="refData.bound_set_id" class="rw-refbind-banner">
                      <q-icon name="link" size="15px" class="q-mr-xs" />
                      Bound to a reference set
                      <span class="rw-refbind-status" :class="`rw-refbind-status--${refData.binding_status}`">{{ (refData.binding_status || 'draft').replace('_', ' ') }}</span>
                    </div>
                    <template v-if="refData.is_coded && (rwRefReviewCodes.length || refBindingPending)">
                      <div class="rw-refrev-bar">
                        <label class="rw-refrev-all"><input type="checkbox" :checked="rwRefAllSelected" @change="rwRefAllSelected = ($event.target as HTMLInputElement).checked" /> Select all</label>
                        <span class="rw-refrev-spacer" />
                        <button class="rw-refrev-btn rw-refrev-btn--approve" :disabled="rwRefActionLoading || (rwRefApprovable.length === 0 && !refBindingPending)" @click="rwRefAction('approve')">
                          Approve{{ rwRefApprovable.length ? ` (${rwRefApprovable.length})` : '' }}{{ refBindingPending && !rwRefApprovable.length ? ' binding' : '' }}
                        </button>
                        <button class="rw-refrev-btn rw-refrev-btn--revoke" :disabled="rwRefActionLoading || rwRefRevocable.length === 0" @click="rwRefAction('revoke')">
                          Revoke{{ rwRefRevocable.length ? ` (${rwRefRevocable.length})` : '' }}
                        </button>
                      </div>
                      <div class="rw-dp-refdata-table">
                        <div v-for="c in rwRefReviewCodes" :key="c.code" class="rw-refrev-row" :class="{ 'rw-refrev-row--tomb': c.tombstone }">
                          <input v-if="rwRefIsSelectable(c)" type="checkbox" :checked="rwRefSelected.has(c.code)" @change="rwRefToggle(c.code, ($event.target as HTMLInputElement).checked)" />
                          <span v-else class="rw-refrev-nocheck" />
                          <code class="rw-dp-code-val">{{ c.code }}</code>
                          <span class="rw-refrev-meaning">{{ c.meaning || '—' }}</span>
                          <span v-if="c.tombstone" class="rw-refrev-tomb" style="text-transform:capitalize">{{ c.tombstone }}</span>
                          <span v-else class="rw-refrev-status" :class="`rw-refrev-status--${c.status}`" style="text-transform:capitalize">{{ (c.status || '').replace('_',' ') }}</span>
                        </div>
                      </div>
                    </template>
                    <div v-else-if="refData.is_coded" class="rw-dp-row">
                      <span class="rw-dp-key">Codes</span>
                      <span class="rw-dp-val rw-dp-val--muted">No codes awaiting review.</span>
                    </div>
                    <div v-else class="rw-dp-row">
                      <span class="rw-dp-key">Code list</span>
                      <span class="rw-dp-val rw-dp-val--muted">None — continuous measure, no enumeration bound.</span>
                    </div>
                  </template>
                  <div v-else class="rw-dp-loading rw-dp-val--muted" style="padding:16px">No reference data loaded.</div>
                </div>
              </section>
            </template>

          </div>

          <div v-else class="rw-dp-body"><div class="rw-dp-loading rw-dp-val--muted">Could not load element details.</div></div>

          <div class="rw-dp-notes-wrap">
            <q-input
              v-model="reviewNotes"
              outlined dense
              placeholder="Review notes or comments…"
              type="textarea"
              rows="2"
              bg-color="white"
              class="rw-dp-notes-input"
            />
          </div>

          <div class="rw-dp-footer">
            <!-- Still resolving the element — don't assert a review state (avoids a "not submitted" flash). -->
            <template v-if="elementLoading">
              <span class="rw-dp-footer-hint">&nbsp;</span>
            </template>
            <!-- Reference Data tab: per-code decisions live inside the tab -->
            <template v-else-if="activeReviewTab === 'refdata'">
              <span class="rw-dp-footer-hint">Approve or revoke individual codes above.</span>
            </template>
            <!-- Interpretation: steward-actionable only once submitted for review -->
            <template v-else-if="interpSubmitted">
              <span class="rw-dp-footer-hint">Decision is recorded on the element</span>
              <div class="rw-dp-footer-btns">
                <q-btn label="Return" no-caps dense unelevated class="rw-dp-btn-return"
                  @click="onReturn(selectedItem)" :loading="actionLoading[selectedItem.key] === 'return'" />
                <q-btn label="Reject" no-caps dense unelevated class="rw-dp-btn-reject"
                  @click="openRejectDialog(selectedItem)" :loading="actionLoading[selectedItem.key] === 'reject'" />
                <q-btn label="Approve" no-caps dense unelevated class="rw-dp-btn-approve"
                  @click="onApprove(selectedItem)" :loading="actionLoading[selectedItem.key] === 'approve'" />
              </div>
            </template>
            <!-- Interpretation not submitted (draft / approved / returned): read-only, no trigger -->
            <template v-else>
              <span class="rw-dp-footer-hint">This interpretation is {{ capitalise(elementDetail?.lifecycle_state || 'draft') }} — not submitted for review.</span>
            </template>
          </div>
        </template>
      </div>
    </div>

    <!-- ── Reject dialog ─────────────────────────────────────────── -->
    <q-dialog v-model="rejectDialog.open">
      <q-card class="rw-dialog">
        <q-card-section>
          <div class="text-h6">Reject — {{ rejectDialog.item?.column }}</div>
          <p class="text-body2 q-mt-xs q-mb-md" style="color: var(--ink-2)">The author can edit and resubmit. Optionally provide a reason.</p>
          <q-input v-model="rejectDialog.reason" label="Reason (optional)" outlined dense autofocus type="textarea" rows="3" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn label="Cancel" flat no-caps @click="rejectDialog.open = false" />
          <q-btn label="Reject" color="negative" unelevated no-caps @click="onRejectConfirm" :loading="rejectDialog.loading" />
        </q-card-actions>
      </q-card>
    </q-dialog>

  </q-page>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useQuasar } from 'quasar'
import { useElementStore } from 'src/stores/elementStore'
import { useRoleStore } from 'src/stores/roleStore'
import { semanticTypeLabel, semanticDomainLabel } from 'src/pages/semanticTypeDisplay'
import { fetchWithRealProgress } from 'src/api/sse'
import StagedLoader from 'src/components/StagedLoader.vue'
import { Bar } from 'vue-chartjs'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Tooltip,
  Legend,
} from 'chart.js'

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend)

const $q = useQuasar()
const router = useRouter()
const elementStore = useElementStore()
const roleStore = useRoleStore()

interface QueueItem {
  key: string; source: string; schema: string; table: string; column: string
  aspect_type: 'definition' | 'glossary' | 'reference_data' | 'reference_binding'; submitted_at: string; submitted_by: string | null
  provenance: string; bulk_eligible: boolean; preview: string; lifecycle_state: string
  semantic_type_id: string | null; confidence: number | null; tier: number | null
  business_name?: string | null
  glossary_term_id?: string | null; glossary_term_title?: string | null
  in_review_count?: number; tombstone_count?: number
  bound_set_id?: string | null; bound_set_name?: string | null
}

const loading = ref(false)
const selectedSource = ref<string | null>(null)
const items = ref<QueueItem[]>([])
const actionLoading = ref<Record<string, string | null>>({})
const selectedItem = ref<QueueItem | null>(null)

// Plain-language, staged progress lines for the queue list + detail-panel loaders.
// Real (non-fabricated) progress: each tick fires only once its real backend work is
// done — no timed simulation. Queue list ticks as each real per-source fetch resolves
// (fetchQueueForSource already makes 2 real calls per source); element detail reuses
// the same SSE-streamed /element/{source}/{table}/{column}/stream endpoint Asset
// Workspace uses, so its 4 stages mirror _build_element's real checkpoints exactly.
const queueLoadStages = computed(() => [
  'Loading the review queue…',
  'Building your queue…',
])
const queueProgress = ref({ completed: 0, detail: '', fraction: 0 })
const elementLoadStages = computed(() => [
  `Opening ${selectedItem.value?.column ?? 'the selected item'}…`,
  'Looking for glossary links and mappings…',
  'Working out its meaning and quality score…',
  'Finishing up…',
])
const elementProgress = ref({ completed: 0, detail: '', fraction: 0 })
let _elementAbort: AbortController | null = null
// Aborted on unmount (leaving the page) so an in-flight load doesn't keep occupying a
// browser connection slot and starving whatever page comes next.
let _queueAbort: AbortController | null = null
let _dashboardAbort: AbortController | null = null

interface RwGlossaryTerm {
  id?: string | null
  title: string
  status: string
  business_description?: string | null
  detailed_description?: string | null
  steward?: string | null
}
interface RwElementDetail {
  column_description: string | null
  business_name: string | null
  lifecycle_state: string
  data_type?: string | null
  is_primary_key?: boolean | null
  stats?: { sample_values?: unknown[] | null } | null
  glossary_term?: RwGlossaryTerm | null
  semantic_type?: string | null
  semantic_source?: string | null
  semantic_state?: string | null
  semantic_confidence?: number | null
  semantic_domain_role?: string | null
  semantic_scope?: string | null
  semantic_type_value_conflict?: boolean | null
  semantic_evidence?: Array<{ kind?: string | null; signal?: string | null; weight?: string | null }>
  semantic_candidates?: Array<{ type_id?: string | null }>
  pii?: boolean | null
  pii_category?: string | null
}
interface RwRefData {
  status?: string | null
  is_coded?: boolean
  codes?: Array<{ code: string; meaning?: string | null; status?: string | null; tombstone?: string | null; tombstone_at?: string | null; governed?: boolean }>
  // 2026-08-16 redesign: the binding decision's OWN submit/approve status.
  bound_set_id?: string | null
  binding_status?: 'draft' | 'in_review' | 'approved' | null
  binding_submitted_at?: string | null
  binding_submitted_by?: string | null
}

const elementDetail = ref<RwElementDetail | null>(null)
const elementLoading = ref(false)
const rejectDialog = ref<{ open: boolean; item: QueueItem | null; reason: string; loading: boolean }>(
  { open: false, item: null, reason: '', loading: false }
)
const reviewNotes = ref('')
// Detail pane tabs: 'interpretation' (definition + semantic + glossary) and 'refdata' (own workflow).
const activeReviewTab = ref<'interpretation' | 'refdata'>('interpretation')
const collapsedTables = ref(new Set<string>())
const refData = ref<RwRefData | null>(null)
const refDataLoading = ref(false)
// Per-code steward review (5b.3.2) — multi-select over the in-review/approved codes.
const rwRefSelected = ref<Set<string>>(new Set())
const rwRefActionLoading = ref(false)

function isCollapsed(tableKey: string): boolean {
  return collapsedTables.value.has(tableKey)
}

function toggleTableGroup(tableKey: string): void {
  const next = new Set(collapsedTables.value)
  if (next.has(tableKey)) next.delete(tableKey)
  else next.add(tableKey)
  collapsedTables.value = next
}

const allExpanded = computed(() => columnGroups.value.every(g => !collapsedTables.value.has(g.tableKey)))

function toggleAllGroups(): void {
  collapsedTables.value = allExpanded.value
    ? new Set(columnGroups.value.map(g => g.tableKey))
    : new Set()
}

const availableSources = computed(() => elementStore.sources ?? [])

// Dropdown shows a real 'All Sources' default (value null) rather than a dull blank.
const sourceOptions = computed(() => [
  { label: 'All Sources', value: null },
  ...availableSources.value.map(s => ({ label: s, value: s })),
])

const filteredItems = computed(() =>
  // Steward lane — submitted interpretations + reference codes/bindings; source is an optional filter.
  items.value.filter(i =>
    (i.aspect_type === 'definition' || i.aspect_type === 'reference_data' || i.aspect_type === 'reference_binding') &&
    (!selectedSource.value || i.source === selectedSource.value)
  )
)

// Deduplicated column entries per table — each column shown once regardless of how many aspect types it has
interface ColEntry {
  tableKey: string; source: string; table: string; column: string
  primaryItem: QueueItem
  hasDef: boolean; hasGloss: boolean; hasRefData: boolean
  glossTitle: string | null
  refItem: QueueItem | null; refInReview: number; refTombstone: number
}

// Raw shapes returned by the /element/{source}/tables endpoint
interface RwColumnRow {
  name: string
  lifecycle_state?: string
  glossary_term_id?: string | null
  glossary_term_status?: string | null
  glossary_term_title?: string | null
}
interface RwTableRow {
  schema: string
  table_name: string
  columns: RwColumnRow[]
}

const columnGroups = computed(() => {
  const byTable = new Map<string, { source: string; table: string; cols: Map<string, ColEntry> }>()
  for (const item of filteredItems.value) {
    const gkey = `${item.source}|${item.table}`
    if (!byTable.has(gkey)) byTable.set(gkey, { source: item.source, table: item.table, cols: new Map() })
    const colMap = byTable.get(gkey)!.cols
    if (!colMap.has(item.column)) {
      colMap.set(item.column, { tableKey: gkey, source: item.source, table: item.table, column: item.column, primaryItem: item, hasDef: false, hasGloss: false, hasRefData: false, glossTitle: null, refItem: null, refInReview: 0, refTombstone: 0 })
    }
    const e = colMap.get(item.column)!
    if (item.aspect_type === 'definition') { e.hasDef = true; e.primaryItem = item }
    else if (item.aspect_type === 'glossary') { e.hasGloss = true; if (!e.hasDef) e.primaryItem = item; e.glossTitle = item.glossary_term_title ?? null }
    else if (item.aspect_type === 'reference_data') { e.hasRefData = true; e.refItem = item; e.refInReview = item.in_review_count ?? 0; e.refTombstone = item.tombstone_count ?? 0; if (!e.hasDef && !e.hasGloss) e.primaryItem = item }
    else if (item.aspect_type === 'reference_binding') { e.hasRefData = true; if (!e.refItem) e.refItem = item; if (!e.hasDef && !e.hasGloss) e.primaryItem = item }
  }
  return Array.from(byTable.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([gkey, g]) => ({ tableKey: gkey, label: `${g.source} · ${g.table}`, total: g.cols.size, columns: Array.from(g.cols.values()).sort((a, b) => a.column.localeCompare(b.column)) }))
})

const totalPending = computed(() => items.value.length)

function formatTypeLabel(typeId: string | null): string {
  return semanticTypeLabel(typeId)
}

function capitalise(s: string | null | undefined): string {
  if (!s) return ''
  return s.charAt(0).toUpperCase() + s.slice(1)
}

// A few raw values shown as evidence (not for review) alongside the physical type.
const sampleValuesText = computed(() => {
  const vals = elementDetail.value?.stats?.sample_values
  if (!Array.isArray(vals) || vals.length === 0) return ''
  return vals.slice(0, 6).map((v) => String(v)).filter((s) => s.length > 0).join('  ·  ')
})

const API = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://127.0.0.1:8000'

async function fetchQueueForSource(source: string, signal?: AbortSignal): Promise<QueueItem[]> {
  try {
    // Defined definitions from all tables
    const tablesResp = await fetch(`${API}/element/${encodeURIComponent(source)}/tables`, { signal })
    const tables: RwTableRow[] = tablesResp.ok ? await tablesResp.json() : []

    const defItems: QueueItem[] = []
    for (const t of tables) {
      for (const col of (t.columns || [])) {
        // Submitted interpretations awaiting a steward decision (canonical state, 5b.3.0).
        if (col.lifecycle_state === 'in_review') {
          defItems.push({
            key: `${source}|${t.schema}|${t.table_name}|${col.name}`,
            source, schema: t.schema, table: t.table_name, column: col.name,
            aspect_type: 'definition',
            submitted_at: '', submitted_by: null,
            provenance: 'human_authored',
            bulk_eligible: false,
            preview: '',
            lifecycle_state: 'in_review',
            semantic_type_id: null, confidence: null, tier: null,
          })
        }
      }
    }

    // Glossary-term review is deferred (Business Glossary owns its own review); glossary-only
    // columns no longer enter this queue. Only submitted interpretations + codesets appear here.

    // Pending reference codesets (Steward lane, 5b.3.2) — columns with in-review
    // codes or an active withdrawn/revoked tombstone.
    const refResp = await fetch(`${API}/review-queue/${encodeURIComponent(source)}/reference-codes`, { signal })
    const refData0 = refResp.ok ? await refResp.json() : { items: [] }
    const refItems: QueueItem[] = ((refData0.items as QueueItem[]) || [])

    return [...defItems, ...refItems]
  } catch {
    return []
  }
}

// Review Workspace shows every submitted set across all sources by default; the source
// dropdown is only a filter (see filteredItems).
async function loadQueue(): Promise<void> {
  if (_queueAbort) _queueAbort.abort()
  _queueAbort = new AbortController()
  const signal = _queueAbort.signal
  loading.value = true
  const total = availableSources.value.length
  let done = 0
  queueProgress.value = { completed: 0, detail: total ? `(0/${total} sources)` : '', fraction: 0 }
  try {
    const results = await Promise.all(availableSources.value.map(async (source) => {
      const result = await fetchQueueForSource(source, signal)
      done += 1
      queueProgress.value = { completed: 0, detail: `(${done}/${total} sources)`, fraction: total ? done / total : 0 }
      return result
    }))
    if (signal.aborted) return
    queueProgress.value = { completed: 1, detail: '', fraction: 0 }
    const all = results.flat()
    items.value = all
    collapsedTables.value = new Set()
    queueProgress.value = { completed: 2, detail: '', fraction: 0 }
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') return
    $q.notify({ type: 'negative', message: 'Failed to load governance items.' })
    items.value = []
  } finally { loading.value = false }
}

async function selectItem(item: QueueItem): Promise<void> {
  selectedItem.value = item
  elementDetail.value = null
  elementLoading.value = true
  elementProgress.value = { completed: 0, detail: '', fraction: 0 }
  reviewNotes.value = ''
  refData.value = null
  rwRefSelected.value = new Set()
  // Land on Interpretation by default; corrected below to Reference Data once both aspects'
  // real state is known, if Interpretation turns out not submitted (tech-debt #16) while
  // Reference Data is the one actually actionable.
  activeReviewTab.value = 'interpretation'
  // Load reference data eagerly so the Interpretation tab can show codeset applicability.
  const refDataPromise = fetchRefData()
  if (_elementAbort) _elementAbort.abort()
  _elementAbort = new AbortController()
  try {
    const qs = item.schema ? `?schema=${encodeURIComponent(item.schema)}` : ''
    elementDetail.value = await fetchWithRealProgress<RwElementDetail>(
      `${API}/element/${item.source}/${item.table}/${item.column}/stream${qs}`,
      (completed) => { elementProgress.value = { ...elementProgress.value, completed, fraction: 0 } },
      (detail, fraction) => { elementProgress.value = { ...elementProgress.value, detail, fraction: fraction ?? 0 } },
      _elementAbort.signal,
    )
  } catch (e) {
    if (!(e instanceof DOMException && e.name === 'AbortError')) elementDetail.value = null
  }
  finally { elementLoading.value = false }
  await refDataPromise
  // Only apply the auto-correction if this is still the selected item (user hasn't clicked
  // away to a different one while both fetches were in flight).
  if (selectedItem.value === item && interpTabDisabled.value && !refTabDisabled.value) {
    activeReviewTab.value = 'refdata'
  }
}

function openInWorkspace(): void {
  const it = selectedItem.value
  if (!it) { void router.push('/workspace'); return }
  void router.push({
    path: '/workspace',
    query: {
      source: it.source,
      ...(it.schema ? { schema: it.schema } : {}),
      table: it.table,
      column: it.column,
      tab: 'interpretation',
    },
  })
}

function openGlossaryTerm(): void {
  const id = elementDetail.value?.glossary_term?.id ?? selectedItem.value?.glossary_term_id
  void router.push(id ? { path: '/standards/glossary', query: { term: id } } : { path: '/standards/glossary' })
}

async function fetchRefData(): Promise<void> {
  if (!selectedItem.value) return
  const { source, table, column, schema } = selectedItem.value
  refDataLoading.value = true
  refData.value = null
  try {
    const qs = schema ? `?schema=${encodeURIComponent(schema)}` : ''
    const resp = await fetch(`${API}/element/${source}/${table}/${column}/reference-data${qs}`)
    if (!resp.ok) throw new Error()
    refData.value = await resp.json()
  } catch { refData.value = null }
  finally { refDataLoading.value = false }
}

function onDetailTabRefdata(): void {
  if (!refData.value && !refDataLoading.value) void fetchRefData()
}

// The Reference Data tab is active only once its codeset has actually been submitted.
const refTabDisabled = computed(() => !refDataLoading.value && !refCodesetSubmitted.value)
const refTabTitle = computed(() => {
  if (refDataLoading.value || refCodesetSubmitted.value) return ''
  return refData.value?.is_coded ? 'No codes submitted for review yet' : 'No reference codeset — not applicable'
})

function onRefTabClick(): void {
  if (refTabDisabled.value) return
  activeReviewTab.value = 'refdata'
  onDetailTabRefdata()
}

// Per-code steward review (5b.3.2): only in-review/approved/tombstone codes are relevant here.
const rwRefReviewCodes = computed(() =>
  (refData.value?.codes ?? []).filter(c => c.status === 'in_review' || c.status === 'approved' || c.tombstone),
)
// A codeset counts as "submitted" once any code is in review, approved, or carries a tombstone,
// OR (2026-08-16) the field's own binding decision has been submitted for review.
const refBindingPending = computed(() => refData.value?.binding_status === 'in_review')
const refCodesetSubmitted = computed(() =>
  !!refData.value?.is_coded && (rwRefReviewCodes.value.length > 0 || refBindingPending.value),
)
// The interpretation is steward-actionable only once it has been submitted for review.
const interpSubmitted = computed(() => elementDetail.value?.lifecycle_state === 'in_review')
// The Interpretation tab is active only once its definition has ever left Draft — mirrors the
// Reference Data tab's own disabled/tooltip pattern (tech-debt #16). Unlike interpSubmitted above
// (steward-actionable check, 'in_review' only), this also allows already-approved/returned/
// rejected items through, since those genuinely were submitted at some point and are worth
// opening — only 'draft'/'empty' (never submitted) should block entry.
const interpTabDisabled = computed(() => {
  const state = elementDetail.value?.lifecycle_state || 'draft'
  return state === 'draft' || state === 'empty'
})
const interpTabTitle = computed(() => interpTabDisabled.value ? 'Not submitted for review yet' : '')
function onInterpTabClick(): void {
  if (interpTabDisabled.value) return
  activeReviewTab.value = 'interpretation'
}
const rwRefApprovable = computed(() =>
  rwRefReviewCodes.value.filter(c => rwRefSelected.value.has(c.code) && c.status === 'in_review').map(c => c.code),
)
const rwRefRevocable = computed(() =>
  rwRefReviewCodes.value.filter(c => rwRefSelected.value.has(c.code) && c.status === 'approved').map(c => c.code),
)
function rwRefIsSelectable(c: { status?: string | null; tombstone?: string | null }): boolean {
  return !c.tombstone && (c.status === 'in_review' || c.status === 'approved')
}
const rwRefAllSelected = computed<boolean>({
  get: () => {
    const sel = rwRefReviewCodes.value.filter(rwRefIsSelectable)
    return sel.length > 0 && sel.every(c => rwRefSelected.value.has(c.code))
  },
  set: (on) => {
    if (on) rwRefReviewCodes.value.filter(rwRefIsSelectable).forEach(c => rwRefSelected.value.add(c.code))
    else rwRefSelected.value.clear()
  },
})
function rwRefToggle(code: string, on: boolean): void {
  if (on) rwRefSelected.value.add(code)
  else rwRefSelected.value.delete(code)
}
async function rwRefAction(kind: 'approve' | 'revoke'): Promise<void> {
  if (!selectedItem.value) return
  const codes = kind === 'approve' ? rwRefApprovable.value : rwRefRevocable.value
  // 2026-08-16 redesign — ONE COMBINED ACTION: approving/revoking also covers the field's own
  // binding decision when it is pending, even if zero per-code rows were also selected.
  const bindingActionable = kind === 'approve' ? refBindingPending.value : false
  if (!codes.length && !bindingActionable) return
  const { source, table, column, schema } = selectedItem.value
  rwRefActionLoading.value = true
  try {
    const qs = schema ? `?schema=${encodeURIComponent(schema)}` : ''
    const resp = await fetch(`${API}/element/${source}/${table}/${column}/reference-data/${kind}-codes${qs}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ codes, actor_role: roleStore.currentRole }),
    })
    if (!resp.ok) throw new Error()
    rwRefSelected.value = new Set()
    await fetchRefData()
    await loadQueue()
    void refreshDashboard()
    const suffix = codes.length ? ` ${codes.length} code${codes.length === 1 ? '' : 's'}` : ' the binding'
    $q.notify({ type: 'positive', message: `${kind === 'approve' ? 'Approved' : 'Revoked'}${suffix}` })
  } catch {
    $q.notify({ type: 'negative', message: `Failed to ${kind} codes.` })
  } finally {
    rwRefActionLoading.value = false
  }
}

async function onSourceChange(_src: string | null): Promise<void> {
  selectedItem.value = null
  elementDetail.value = null
  coverage.value = null
  if (selectedSource.value) void fetchCoverage(selectedSource.value)
}

async function refresh(): Promise<void> {
  selectedItem.value = null
  elementDetail.value = null
  await loadQueue()
  await loadDashboard()
  if (selectedSource.value) void fetchCoverage(selectedSource.value)
}

async function onApprove(item: QueueItem): Promise<void> {
  actionLoading.value[item.key] = 'approve'
  try {
    let url: string
    let approveBody: Record<string, unknown>
    if (item.aspect_type === 'definition') {
      url = `${API}/element/${item.source}/${item.table}/${item.column}/approve?schema=${item.schema}`
      approveBody = { decided_by_role: roleStore.currentRole }
    } else if (item.aspect_type === 'glossary') {
      url = `${API}/glossary/terms/${item.glossary_term_id}/confirm`
      approveBody = { decided_by_role: roleStore.currentRole }
    } else {
      return  // no other aspect is approvable here
    }
    const resp = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(approveBody) })
    if (!resp.ok) throw new Error()
    items.value = items.value.filter(i => i.key !== item.key)
    if (selectedItem.value?.key === item.key) { selectedItem.value = null; elementDetail.value = null }
    $q.notify({ type: 'positive', message: `Approved: ${item.column}` })
    void refreshDashboard()
  } catch { $q.notify({ type: 'negative', message: `Failed to approve ${item.column}.` }) }
  finally { actionLoading.value[item.key] = null }
}

// Steward returns a submitted interpretation for rework → canonical 'returned' (5b.3.2).
async function onReturn(item: QueueItem): Promise<void> {
  if (item.aspect_type !== 'definition') return
  actionLoading.value[item.key] = 'return'
  try {
    const resp = await fetch(`${API}/element/${item.source}/${item.table}/${item.column}/return?schema=${item.schema}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: reviewNotes.value || null, decided_by_role: roleStore.currentRole }),
    })
    if (!resp.ok) throw new Error()
    items.value = items.value.filter(i => i.key !== item.key)
    if (selectedItem.value?.key === item.key) { selectedItem.value = null; elementDetail.value = null }
    $q.notify({ type: 'warning', message: `Returned for rework: ${item.column}` })
    void refreshDashboard()
  } catch { $q.notify({ type: 'negative', message: `Failed to return ${item.column}.` }) }
  finally { actionLoading.value[item.key] = null }
}

function openRejectDialog(item: QueueItem): void {
  rejectDialog.value = { open: true, item, reason: reviewNotes.value, loading: false }
}

async function onRejectConfirm(): Promise<void> {
  const item = rejectDialog.value.item
  if (!item) return
  rejectDialog.value.loading = true
  actionLoading.value[item.key] = 'reject'
  try {
    let url: string
    let rejectBody: Record<string, unknown>
    if (item.aspect_type === 'definition') {
      url = `${API}/element/${item.source}/${item.table}/${item.column}/reject?schema=${item.schema}`
      rejectBody = { reason: rejectDialog.value.reason || null, decided_by_role: roleStore.currentRole }
    } else if (item.aspect_type === 'glossary') {
      url = `${API}/glossary/terms/${item.glossary_term_id}/reject`
      rejectBody = { reason: rejectDialog.value.reason || null, decided_by_role: roleStore.currentRole }
    } else {
      rejectDialog.value.loading = false
      actionLoading.value[item.key] = null
      return  // no other aspect is rejectable here
    }
    const resp = await fetch(url, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(rejectBody),
    })
    if (!resp.ok) throw new Error()
    items.value = items.value.filter(i => i.key !== item.key)
    if (selectedItem.value?.key === item.key) { selectedItem.value = null; elementDetail.value = null }
    $q.notify({ type: 'warning', message: `Rejected: ${item.column}` })
    rejectDialog.value.open = false
    void refreshDashboard()
  } catch { $q.notify({ type: 'negative', message: `Failed to reject ${item.column}.` }) }
  finally { rejectDialog.value.loading = false; actionLoading.value[item.key] = null }
}

interface CoverageData {
  source: string; total_elements: number
  definition: { empty: number; draft: number; in_review: number; approved: number; pending_review: number }
  definition_submitted_pct: number; definition_approved_pct: number
  semantic_type: { total_resolved: number; accepted: number; pending: number; unresolved: number }
  semantic_accepted_pct: number
  reference_codes: { total_coded: number; submitted: number }
  reference_codes_submitted_pct: number
}
const coverage = ref<CoverageData | null>(null)
const coverageLoading = ref(false)

// Always-on dashboard: aggregate governance summaries across every source.
function emptyCoverage(): CoverageData {
  return {
    source: 'all', total_elements: 0,
    definition: { empty: 0, draft: 0, in_review: 0, approved: 0, pending_review: 0 },
    definition_submitted_pct: 0, definition_approved_pct: 0,
    semantic_type: { total_resolved: 0, accepted: 0, pending: 0, unresolved: 0 },
    semantic_accepted_pct: 0,
    reference_codes: { total_coded: 0, submitted: 0 },
    reference_codes_submitted_pct: 0,
  }
}
const aggregate = ref<CoverageData | null>(null)
// Per-source breakdown kept alongside the aggregate — needed for the by-source bar chart
// (the reduced aggregate alone can't show which source is under/over-represented).
const perSourceCoverage = ref<CoverageData[]>([])

async function loadDashboard(): Promise<void> {
  const sources = availableSources.value
  if (!sources.length) { aggregate.value = null; perSourceCoverage.value = []; return }
  if (_dashboardAbort) _dashboardAbort.abort()
  _dashboardAbort = new AbortController()
  const signal = _dashboardAbort.signal
  coverageLoading.value = true
  try {
    const results = await Promise.all(sources.map(async (s) => {
      const r = await fetch(`${API}/element/${encodeURIComponent(s)}/governance-summary`, { signal })
      return r.ok ? (await r.json() as CoverageData) : null
    }))
    if (signal.aborted) return
    const valid = results.filter((r): r is CoverageData => r !== null)
    perSourceCoverage.value = valid
    aggregate.value = valid.length ? valid.reduce((acc, c) => {
      acc.total_elements += c.total_elements
      acc.definition.empty += c.definition.empty
      acc.definition.draft += c.definition.draft
      acc.definition.in_review += c.definition.in_review
      acc.definition.approved += c.definition.approved
      acc.definition.pending_review += c.definition.pending_review
      acc.semantic_type.total_resolved += c.semantic_type.total_resolved
      acc.semantic_type.accepted += c.semantic_type.accepted
      acc.semantic_type.pending += c.semantic_type.pending
      acc.semantic_type.unresolved += c.semantic_type.unresolved
      acc.reference_codes.total_coded += c.reference_codes.total_coded
      acc.reference_codes.submitted += c.reference_codes.submitted
      return acc
    }, emptyCoverage()) : null
    if (aggregate.value) {
      const a = aggregate.value
      a.definition_submitted_pct = a.total_elements > 0
        ? Math.round((a.definition.in_review + a.definition.approved) / a.total_elements * 100) : 0
      a.definition_approved_pct = a.total_elements > 0 ? Math.round(a.definition.approved / a.total_elements * 100) : 0
      a.reference_codes_submitted_pct = a.reference_codes.total_coded > 0
        ? Math.round(a.reference_codes.submitted / a.reference_codes.total_coded * 100) : 0
    }
  } catch (e) { if (!(e instanceof DOMException && e.name === 'AbortError')) { aggregate.value = null; perSourceCoverage.value = [] } }
  finally { coverageLoading.value = false }
}

// When a source is picked the dashboard narrows to it; otherwise it shows the all-source aggregate.
const displayCoverage = computed<CoverageData | null>(() => selectedSource.value ? coverage.value : aggregate.value)
const scopeSources = computed(() => selectedSource.value ? 1 : availableSources.value.length)

// Straight pass-through of the backend's own (now catalog-wide, tech-debt #17) percentages —
// no client-side recompute, so the cards can never drift out of sync with what the backend
// actually means by "submitted"/"approved".
const defSubmittedPct = computed(() => Math.round(displayCoverage.value?.definition_submitted_pct ?? 0))
const defApprovedPct = computed(() => Math.round(displayCoverage.value?.definition_approved_pct ?? 0))
const codesSubmittedPct = computed(() => Math.round(displayCoverage.value?.reference_codes_submitted_pct ?? 0))

// Steward workload straight from the queue (filtered to the selected source when set).
const pendingByAspect = computed(() => {
  const src = selectedSource.value
  const pool = src ? items.value.filter(i => i.source === src) : items.value
  return {
    definition: pool.filter(i => i.aspect_type === 'definition').length,
    reference: pool.filter(i => i.aspect_type === 'reference_data' || i.aspect_type === 'reference_binding').length,
    total: pool.length,
  }
})

// By-source stacked bar — Empty/Draft/In Review/Approved counts per source, so a demo
// audience can see at a glance which source is under-represented (colours echo the
// .cov-pill--* palette used in the cards above for visual consistency).
const bySourceChartData = computed(() => {
  const rows = perSourceCoverage.value
  return {
    labels: rows.map(r => r.source),
    datasets: [
      { label: 'Empty', data: rows.map(r => r.definition.empty), backgroundColor: '#d8d5cc', borderRadius: 4, maxBarThickness: 40 },
      { label: 'Draft', data: rows.map(r => r.definition.draft), backgroundColor: '#d97706', borderRadius: 4, maxBarThickness: 40 },
      { label: 'In Review', data: rows.map(r => r.definition.in_review), backgroundColor: '#7c3aed', borderRadius: 4, maxBarThickness: 40 },
      { label: 'Approved', data: rows.map(r => r.definition.approved), backgroundColor: '#059669', borderRadius: 4, maxBarThickness: 40 },
    ],
  }
})
const bySourceChartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { position: 'bottom' as const, labels: { usePointStyle: true, pointStyleWidth: 10 } } },
  scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true } },
}

async function refreshDashboard(): Promise<void> {
  if (selectedSource.value) await fetchCoverage(selectedSource.value)
  else await loadDashboard()
}

async function fetchCoverage(source: string): Promise<void> {
  if (_dashboardAbort) _dashboardAbort.abort()
  _dashboardAbort = new AbortController()
  const signal = _dashboardAbort.signal
  coverageLoading.value = true
  try {
    const resp = await fetch(`${API}/element/${encodeURIComponent(source)}/governance-summary`, { signal })
    if (!resp.ok) throw new Error()
    coverage.value = await resp.json() as CoverageData
  } catch (e) { if (!(e instanceof DOMException && e.name === 'AbortError')) coverage.value = null }
  finally { coverageLoading.value = false }
}

function coverageColor(pct: number): string {
  if (pct >= 75) return 'var(--released, #2f6b3a)'
  if (pct >= 40) return 'var(--draft, #a9651b)'
  return 'var(--danger, #9e3326)'
}

onMounted(async () => {
  if (!elementStore.sources?.length) await elementStore.loadSources()
  await loadQueue()
  await loadDashboard()
})

onUnmounted(() => {
  // Leaving the page mid-load must not leave these requests running in the background —
  // each one holds a browser connection slot open until it finishes, starving whatever
  // page comes next (confirmed live: unrelated requests stalling behind lingering
  // governance-summary/tables calls that outlived a previous Review Workspace visit).
  _queueAbort?.abort()
  _dashboardAbort?.abort()
  _elementAbort?.abort()
})
</script>

<style scoped>
.rw-page {
  /* Local aliases → shared --adirra-* tokens (matches .rds-page / .glossary-v2) so the page
     follows the app palette + dark mode instead of the hardcoded fallbacks. */
  --accent: var(--adirra-accent);
  --paper: var(--adirra-paper);
  --paper-2: var(--adirra-paper-2);
  --card: var(--adirra-card);
  --card-bg: rgba(255, 253, 248, .62);
  --border: var(--adirra-line);
  --line: var(--adirra-line);
  --ink: var(--adirra-ink);
  --ink-1: var(--adirra-ink);
  --ink-2: var(--adirra-ink-2);
  --ink-3: var(--adirra-ink-3);
  padding: 16px clamp(16px, 3vw, 32px) 32px;
  background: radial-gradient(ellipse 110% 55% at 50% 0%, #b8d4ec 0%, #d4e6f2 28%, #e8f0f7 50%, #f6f3ec 75%);
  min-height: 100%;
  box-sizing: border-box;
}
.rw-header { margin-bottom: 8px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }
.rw-eyebrow { font-size: 11px; text-transform: uppercase; letter-spacing: .1em; color: var(--ink-3); font-weight: 700; }
.rw-title-row { display: flex; align-items: center; gap: 10px; margin: 3px 0 4px; }
.rw-title-icon { color: var(--ink-3, #86827a); }
.rw-title { font-family: 'IBM Plex Serif', serif; font-size: 26px; font-weight: 600; letter-spacing: -0.01em; color: var(--ink, #1c1b18); margin: 0; }
.rw-subtitle { font-size: 13px; color: var(--ink-2, #4a473f); margin: 0; max-width: 900px; }
.rw-toolbar-sep { width: 1px; height: 26px; background: var(--line, #ddd6c8); flex-shrink: 0; margin: 0 2px; }
.rw-source-select { width: 100%; }
.rw-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; min-height: 300px; margin-top: 12px; background: var(--card-bg); backdrop-filter: blur(8px); border: 1px solid var(--border); border-radius: 10px; color: var(--ink-3, #86827a); }
.rw-empty-icon { opacity: 0.35; }
.rw-empty-text { font-size: 14px; text-align: center; }

/* ── Split layout ── */
/* Bounded height (was unbounded — grew to fit content, so .rw-list-pane's
   overflow-y:scroll / .rw-dp-body's overflow-y:auto below never actually engaged and the
   whole page had to be scrolled instead, pushing Approve/Revoke far off-screen once the
   coverage dashboard grew). grid-template-rows: 1fr makes both columns stretch to fill
   this bound so they scroll internally like they were always meant to. */
.rw-split { display: grid; grid-template-columns: 280px 1fr; grid-template-rows: 1fr; height: 65vh; min-height: 420px; border: 1px solid var(--border); border-radius: 10px; overflow: hidden; background: var(--card-bg); backdrop-filter: blur(8px); }
.rw-split:not(.rw-split--open) { grid-template-columns: 1fr 0; }

/* ── Left list pane ── */
.rw-list-pane { background: var(--paper-2, #efeae0); border-right: 1px solid var(--line, #ddd6c8); overflow-y: scroll; scrollbar-width: thin; scrollbar-color: var(--line, #ddd6c8) transparent; }
.rw-list-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; padding: 40px 16px; color: var(--ink-3, #86827a); font-size: 13px; text-align: center; }
.rw-group { border-bottom: 1px solid var(--line, #ddd6c8); margin-bottom: 2px; }
.rw-group:last-child { border-bottom: none; }
.rw-group-header {
  display: flex; align-items: center; gap: 6px; width: 100%;
  padding: 9px 14px 7px; border: none; background: var(--paper, #f6f3ec);
  cursor: pointer; text-align: left; position: sticky; top: 0; z-index: 1;
  transition: background 0.12s;
}
.rw-group-header:hover { background: rgba(0,0,0,.03); }
.rw-group-label { font-size: 10.5px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: var(--ink-2, #4a473f); flex: 1; }
.rw-group-count { font-size: 10px; background: var(--line, #ddd6c8); border-radius: 8px; padding: 1px 5px; color: var(--ink-2, #4a473f); font-weight: 700; letter-spacing: 0; }
.rw-group-chevron { color: var(--ink-3, #86827a); flex-shrink: 0; }
.rw-group-body { padding-bottom: 4px; }
.rw-subgroup-header { padding: 5px 14px 3px; font-size: 10px; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; color: var(--ink-3, #86827a); }
.rw-item-btn { display: flex; align-items: center; gap: 9px; width: 100%; padding: 9px 14px; border: none; background: transparent; cursor: pointer; text-align: left; transition: background 0.12s; }
.rw-item-btn:hover { background: rgba(0,0,0,.04); }
.rw-item-btn--active { background: rgba(13,92,84,.1); }
.rw-item-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.dot--green { background: #2f6b3a; } .dot--amber { background: #a9651b; } .dot--orange { background: #c45b2a; } .dot--blue { background: #2f5d8a; }
.rw-item-info { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
code.rw-item-col { font-family: 'IBM Plex Mono', monospace; font-size: 12px; font-weight: 600; color: var(--ink, #1c1b18); }
.rw-item-path { font-size: 11px; color: var(--ink-3, #86827a); }

/* ── Left pane: source header + in-pane messages ───────────────── */
.rw-list-head { padding: 10px 12px; border-bottom: 1px solid var(--border); background: var(--card-bg); backdrop-filter: blur(8px); position: sticky; top: 0; z-index: 2; }
.rw-list-actions { display: flex; justify-content: flex-end; padding: 6px 12px; border-bottom: 1px solid var(--line, #ddd6c8); }
.rw-expand-toggle { display: inline-flex; align-items: center; gap: 4px; font-size: 11px; font-weight: 600; color: var(--accent, #0f6f6a); background: transparent; border: none; cursor: pointer; padding: 2px 4px; }
.rw-expand-toggle:hover { text-decoration: underline; }
.rw-rail-label { font-size: 10px; font-weight: 700; letter-spacing: .10em; text-transform: uppercase; color: var(--ink-3); margin-bottom: 6px; }
.rw-list-msg { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; padding: 44px 16px; color: var(--ink-3); font-size: 13px; text-align: center; }

/* ── Composite review sections (replaces detail tabs) ──────────── */
.rw-sec { border: 1px solid var(--border); border-radius: 10px; overflow: hidden; margin-bottom: 12px; background: var(--card); }
.rw-sec-head { display: flex; align-items: center; gap: 7px; width: 100%; padding: 8px 13px; font-size: 12px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; color: #fff; border: none; }
.rw-sec-head--toggle { cursor: pointer; text-align: left; }
.rw-sec-head--definition { background: linear-gradient(100deg, #16887c, #0d5c54); }
.rw-sec-head--semantic { background: linear-gradient(100deg, #3f7cb8, #2f5d8a); }
.rw-sec-head--glossary { background: linear-gradient(100deg, #3f8f57, #2f6b3a); }
.rw-sec-head--refdata { background: linear-gradient(100deg, #1f9aa2, #147a82); }
.rw-sec-badge { font-size: 10px; font-weight: 700; background: rgba(255, 255, 255, .22); border-radius: 10px; padding: 1px 7px; }
.rw-sec-body { padding: 8px 14px 12px; }

/* ── Right detail pane ─ light theme ──────────────────────── */
.rw-detail-pane { background: var(--card, #fffdf8); color: var(--ink, #1c1b18); border-left: 1px solid var(--line, #ddd6c8); display: flex; flex-direction: column; overflow: hidden; transition: opacity 0.2s; }
.rw-detail-pane:not(.rw-detail-pane--visible) { opacity: 0; pointer-events: none; }
.rw-dp-placeholder { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; font-size: 13px; color: var(--ink-3, #86827a); opacity: .5; }
.rw-dp-top { padding: 18px 22px 12px; border-bottom: 1px solid var(--line, #ddd6c8); flex-shrink: 0; background: var(--paper-2, #efeae0); }
.rw-dp-col-row { display: flex; align-items: center; gap: 10px; margin-bottom: 4px; }
code.rw-dp-col-name { font-family: 'IBM Plex Mono', monospace; font-size: 16px; font-weight: 600; color: var(--ink, #1c1b18); }
.rw-dp-badge { font-size: 10.5px; padding: 2px 8px; border-radius: 4px; border: 1px solid var(--line, #ddd6c8); color: var(--ink-3, #86827a); }
.rw-dp-pii { font-size: 10px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; color: #9e3326; background: #9e33260f; border: 1px solid #e0b6b0; border-radius: 4px; padding: 2px 7px; }
.rw-dp-link { font-size: 12px; color: var(--accent, #0d5c54); text-decoration: none; cursor: pointer; }
.rw-dp-bn-banner { padding: 12px 22px; border-bottom: 1px solid var(--line, #ddd6c8); background: #0d5c540a; flex-shrink: 0; }
.rw-dp-bn-row { display: flex; align-items: baseline; gap: 10px; }
.rw-dp-bn-label { font-size: 10.5px; text-transform: uppercase; letter-spacing: .04em; color: var(--ink-3, #86827a); font-weight: 700; }
.rw-dp-bn-value { font-size: 15px; font-weight: 600; color: var(--ink-1, #2b2a27); }
.rw-dp-bn-hint { font-size: 11.5px; color: var(--ink-3, #86827a); margin-top: 4px; }
.rw-dp-bn-banner--pii { background: #9e33260c; border-bottom-color: #e0b6b0; }
.rw-item-pii { font-size: 9px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; color: #9e3326; background: #9e33260f; border: 1px solid #e0b6b0; border-radius: 4px; padding: 1px 5px; white-space: nowrap; }
.rw-dp-link:hover { text-decoration: underline; }
.rw-dp-body { flex: 1; overflow-y: auto; padding: 12px 22px; }
.rw-dp-loading { padding: 24px; display: flex; align-items: center; color: var(--ink-3, #86827a); font-size: 13px; }
.rw-dp-section { padding: 12px 0 4px; }
.rw-dp-section-title { font-size: 10.5px; font-weight: 700; letter-spacing: 0.12em; color: var(--ink-3, #86827a); margin-bottom: 8px; text-transform: uppercase; }
.rw-dp-row { display: grid; grid-template-columns: 130px 1fr auto; gap: 8px; align-items: start; padding: 7px 0; border-bottom: 1px solid var(--line, #ddd6c8); }
.rw-dp-row--tall { align-items: start; }
.rw-dp-row:last-child { border-bottom: none; }
.rw-dp-key { font-size: 12px; color: var(--ink-3, #86827a); padding-top: 1px; }
.rw-dp-val { font-size: 13px; color: var(--ink, #1c1b18); font-weight: 400; line-height: 1.45; }
.rw-dp-val--muted { color: var(--ink-3, #86827a); }
.rw-dp-note { font-size: 11.5px; font-style: italic; color: var(--ink-3, #86827a); padding: 8px 0 0; }
.rw-dp-chip { font-size: 10.5px; font-weight: 700; letter-spacing: 0.02em; color: var(--ink-2, #55524c); background: var(--paper-2, #efeae0); border: 1px solid var(--line, #ddd6c8); border-radius: 4px; padding: 1px 7px; white-space: nowrap; }
.rw-dp-chip--pk { color: #92400e; background: #fef3c7; border-color: #fcd9a0; }
.rw-dp-samples { display: flex; align-items: baseline; gap: 8px; font-size: 12px; color: var(--ink-2, #55524c); margin-top: 5px; font-family: var(--font-mono, ui-monospace, monospace); word-break: break-word; }
.rw-dp-samples-label { flex-shrink: 0; font-family: inherit; font-size: 9.5px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--ink-3, #86827a); }
.rw-refbar .rw-sec-head--refdata { border-radius: 8px; }
.rw-refbar-link { color: #fff; font-weight: 700; font-size: 12px; text-decoration: none; cursor: pointer; }
.rw-refbar-link:hover { text-decoration: underline; }
.rw-dp-tab-btn--disabled { opacity: .4; cursor: not-allowed; }
.rw-dp-state { font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 4px; white-space: nowrap; align-self: start; }
.rw-dp-state--proposed { background: #d1fae5; color: #065f46; }
.rw-dp-state--confirmed { background: #dbeafe; color: #1e40af; }
.rw-dp-state--rejected { background: #fee2e2; color: #991b1b; }
.rw-dp-state--suggested { background: #fef3c7; color: #92400e; }
.rw-dp-grade { font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 4px; white-space: nowrap; align-self: start; }
.rw-dp-grade--high { background: #d1fae5; color: #065f46; }
.rw-dp-grade--medium { background: #fef3c7; color: #92400e; }
.rw-dp-grade--low { background: #f3eee6; color: #86827a; }
.rw-dp-hr { border: none; border-top: 1px solid var(--line, #ddd6c8); margin: 4px 0; }
.rw-dp-notes-wrap { padding: 10px 22px; border-top: 1px solid var(--line, #ddd6c8); background: var(--paper, #f6f3ec); flex-shrink: 0; }
.rw-dp-notes-input { font-size: 13px; }
.rw-dp-footer { padding: 10px 22px 14px; border-top: 1px solid var(--line, #ddd6c8); display: flex; align-items: center; gap: 12px; flex-shrink: 0; background: var(--paper, #f6f3ec); }

/* ── Detail tabs ── */
.rw-dp-tabs { display: flex; border-bottom: 2px solid var(--line, #ddd6c8); flex-shrink: 0; background: var(--paper-2, #efeae0); }
.rw-dp-tab-btn {
  padding: 9px 16px; border: none; background: transparent; cursor: pointer; font-size: 12.5px;
  font-weight: 500; color: var(--ink-3, #86827a); border-bottom: 2px solid transparent;
  margin-bottom: -2px; transition: color 0.15s, border-color 0.15s;
}
.rw-dp-tab-btn:hover { color: var(--ink, #1c1b18); }
.rw-dp-tab-btn--active { color: var(--accent, #0d5c54); border-bottom-color: var(--accent, #0d5c54); font-weight: 600; }
.rw-tab-content { padding-top: 4px; }

/* ── Evidence ── */
.rw-dp-evidence-row { display: flex; align-items: baseline; gap: 8px; padding: 5px 0; border-bottom: 1px solid var(--line, #ddd6c8); font-size: 12.5px; }
.rw-dp-evidence-row:last-child { border-bottom: none; }
.rw-dp-ev-kind { width: 80px; flex-shrink: 0; color: var(--ink-3, #86827a); font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; }
.rw-dp-ev-signal { flex: 1; color: var(--ink, #1c1b18); }
.rw-dp-ev-weight { font-size: 11px; font-weight: 600; padding: 1px 6px; border-radius: 4px; }
.rw-ev-strong { background: #d1fae5; color: #065f46; }
.rw-ev-medium { background: #fef3c7; color: #92400e; }
.rw-ev-weak { background: #f3f4f6; color: #6b7280; }

/* ── Candidates ── */
.rw-dp-cand-row { display: flex; align-items: center; gap: 8px; padding: 4px 0; font-size: 12.5px; }
.rw-dp-cand-label { width: 160px; flex-shrink: 0; color: var(--ink-2, #4a473f); }
.rw-dp-cand-winner { color: var(--ink, #1c1b18); font-weight: 600; }
.rw-dp-cand-bar { flex: 1; height: 6px; background: var(--line, #ddd6c8); border-radius: 3px; overflow: hidden; }
.rw-dp-cand-fill { height: 100%; background: var(--accent, #0d5c54); border-radius: 3px; }
.rw-dp-cand-pct { width: 36px; text-align: right; font-size: 12px; color: var(--ink-3, #86827a); }

/* ── Reference Data table ── */
.rw-dp-refdata-header { display: flex; align-items: center; gap: 8px; padding: 10px 0 6px; }
.rw-dp-refdata-title { font-size: 14px; font-weight: 600; color: var(--ink, #1c1b18); }
.rw-dp-refdata-nodomain { font-size: 12px; color: var(--ink-3, #86827a); display: flex; align-items: center; padding: 4px 0 8px; }
.rw-dp-refdata-table { border: 1px solid var(--line, #ddd6c8); border-radius: 6px; overflow: hidden; margin-top: 6px; }
.rw-dp-refdata-thead { display: grid; grid-template-columns: 1fr 1fr; padding: 6px 12px; background: var(--paper-2, #efeae0); border-bottom: 1px solid var(--line, #ddd6c8); font-size: 10.5px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: var(--ink-3, #86827a); }
.rw-dp-refdata-trow { display: grid; grid-template-columns: 1fr 1fr; padding: 7px 12px; border-bottom: 1px solid var(--line, #ddd6c8); font-size: 13px; align-items: center; }
.rw-dp-refdata-trow:last-child { border-bottom: none; }
.rw-dp-refdata-trow:hover { background: var(--paper-2, #efeae0); }
/* Ensure codes-wrap still works for backward compat */
.rw-dp-codes-wrap { display: flex; flex-wrap: wrap; gap: 6px; padding: 8px 0; }
.rw-dp-code-row { display: flex; align-items: center; gap: 6px; background: var(--paper-2, #efeae0); border-radius: 5px; padding: 3px 8px; }
.rw-dp-code-val { font-family: 'IBM Plex Mono', monospace; font-size: 12px; color: var(--ink, #1c1b18); }
.rw-dp-code-count { font-size: 11px; }

/* Reference-code chip in the queue list + per-code steward review (5b.3.2) */
.rw-item-refchip { font-size: 9.5px; font-weight: 700; color: #1e5aa8; background: #e7f0fb; border: 1px solid #bcd6f2; border-radius: 4px; padding: 1px 5px; white-space: nowrap; }
.rw-refbind-banner { display: flex; align-items: center; gap: 6px; font-size: 12.5px; margin: 6px 0 10px; padding: 6px 10px; background: #f6f4ef; border-radius: 6px; }
.rw-refbind-status { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; border-radius: 4px; padding: 1px 6px; margin-left: 4px; }
.rw-refbind-status--draft { background: #e9e6df; color: #55524c; }
.rw-refbind-status--in_review { background: #fef3c7; color: #92400e; }
.rw-refbind-status--approved { background: #dcfce7; color: #166534; }
.rw-refrev-bar { display: flex; align-items: center; gap: 8px; margin: 6px 0; }
.rw-refrev-all { display: flex; align-items: center; gap: 5px; font-size: 11.5px; color: var(--ink-2, #55524c); cursor: pointer; }
.rw-refrev-spacer { flex: 1; }
.rw-refrev-btn { font-size: 11.5px; font-weight: 600; padding: 3px 10px; border-radius: 5px; border: 1px solid transparent; cursor: pointer; }
.rw-refrev-btn:disabled { opacity: .45; cursor: default; }
.rw-refrev-btn--approve { background: #e4f4e9; color: #1f7a44; border-color: #b8e0c6; }
.rw-refrev-btn--revoke { background: #fdf3f2; color: #8a2c22; border-color: #f0d5d0; }
.rw-refrev-row { display: grid; grid-template-columns: 18px auto 1fr auto; gap: 8px; align-items: center; padding: 6px 12px; border-bottom: 1px solid var(--line, #ddd6c8); font-size: 13px; }
.rw-refrev-row:last-child { border-bottom: none; }
.rw-refrev-row--tomb { opacity: .6; }
.rw-refrev-nocheck { display: inline-block; width: 13px; }
.rw-refrev-meaning { color: var(--ink-2, #55524c); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rw-refrev-status { font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: 10px; background: #eceae6; color: #6b6862; }
.rw-refrev-status--in_review { background: #fdf3e0; color: #97701a; }
.rw-refrev-status--approved { background: #e4f4e9; color: #1f7a44; }
.rw-refrev-tomb { font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: 10px; background: #efe7e5; color: #8a6d66; }
.rw-dp-tier-badge { font-size: 10px; font-weight: 700; padding: 1px 5px; background: #dbeafe; color: #1e40af; border-radius: 4px; }
.rw-dp-val--danger { color: #991b1b; }
.rw-dp-footer-hint { font-size: 11.5px; color: var(--ink-3, #86827a); flex: 1; }
.rw-dp-footer-btns { display: flex; gap: 8px; }
.rw-dp-btn-reject { background: white !important; color: var(--ink, #1c1b18) !important; border: 1px solid var(--line, #ddd6c8) !important; border-radius: 6px; padding: 0 16px; height: 32px; }
.rw-dp-btn-reject:hover { background: var(--paper-2, #efeae0) !important; }
.rw-dp-btn-return { background: white !important; color: #97701a !important; border: 1px solid #e6cfa0 !important; border-radius: 6px; padding: 0 16px; height: 32px; }
.rw-dp-btn-return:hover { background: #fdf7ea !important; }
.rw-dp-btn-approve { background: var(--accent, #0d5c54) !important; color: white !important; border-radius: 6px; padding: 0 16px; height: 32px; }
.rw-dp-btn-approve:hover { background: #0a4a44 !important; }

.rw-dialog { min-width: 380px; }

/* ── Compliance panel ── */
.cov-panel { border-bottom: 1px solid var(--line, #ddd6c8); padding-bottom: 16px; margin-bottom: 16px; }
.cov-header { display: flex; align-items: center; gap: 6px; margin-bottom: 14px; }
.cov-title { font-family: 'IBM Plex Serif', serif; font-size: 16px; font-weight: 600; color: var(--ink, #1c1b18); flex: 1; }
.cov-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }
.cov-card { background: var(--card-bg); backdrop-filter: blur(8px); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; }
.cov-card-label { font-size: 10.5px; font-weight: 600; letter-spacing: 0.13em; text-transform: uppercase; color: var(--ink-3, #86827a); margin-bottom: 4px; }
.cov-card-value { font-family: 'IBM Plex Serif', serif; font-size: 28px; font-weight: 600; line-height: 1; margin-bottom: 8px; }
.cov-progress-wrap { margin-bottom: 8px; }
.cov-bar-bg { height: 6px; background: var(--line, #ddd6c8); border-radius: 3px; overflow: hidden; }
.cov-bar-fill { height: 100%; border-radius: 3px; transition: width 0.5s ease; }
.cov-breakdown { display: flex; flex-wrap: wrap; gap: 5px; }
.cov-pill { font-size: 11px; padding: 2px 7px; border-radius: 10px; }
.cov-pill--empty { background: #f1f0ec; color: #86827a; }
.cov-pill--draft { background: #fef3c7; color: #92400e; }
.cov-pill--defined { background: #dbeafe; color: #1e40af; }
.cov-pill--approved { background: #d1fae5; color: #065f46; }
.cov-pill--pending { background: #ede9fe; color: #5b21b6; }
.cov-meta { font-size: 11px; color: var(--ink-3, #86827a); }
.cov-chart-panel { margin-top: 16px; background: var(--card-bg); backdrop-filter: blur(8px); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; }
.cov-chart-label { font-size: 10.5px; font-weight: 600; letter-spacing: 0.13em; text-transform: uppercase; color: var(--ink-3, #86827a); margin-bottom: 10px; }
.cov-chart-wrap { max-width: 100%; height: 220px; }
.cov-backfill-btn { margin-top: 10px; display: inline-flex; align-items: center; font-size: 12px; font-weight: 600; color: var(--accent, #0d5c54); background: transparent; border: 1px solid var(--accent, #0d5c54); border-radius: 6px; padding: 4px 10px; cursor: pointer; }
.cov-backfill-btn:hover { background: rgba(13, 92, 84, 0.08); }

/* ── Backfill wizard ── */
.rw-backfill-card { min-width: 480px; max-width: 560px; }
.bf-section-label { display: flex; align-items: center; font-size: 12px; font-weight: 600; color: var(--ink, #1c1b18); margin-bottom: 8px; }
.bf-section-label--muted { color: var(--ink-2, #4a473f); }
.bf-empty { font-size: 12.5px; color: var(--ink-3, #86827a); padding: 4px 0 8px; }
.bf-list { display: flex; flex-direction: column; gap: 2px; }
.bf-list--muted { opacity: 0.85; }
.bf-row { display: flex; align-items: center; gap: 10px; padding: 5px 8px; border-radius: 6px; cursor: pointer; }
.bf-row:hover { background: var(--paper-2, #efeae0); }
.bf-row--muted { cursor: default; }
.bf-row--muted:hover { background: transparent; }
.bf-table { font-size: 12.5px; color: var(--ink, #1c1b18); font-weight: 600; }
.bf-subject { font-size: 12px; color: var(--accent, #0d5c54); font-weight: 600; }
.bf-vs { font-size: 11.5px; color: var(--ink-3, #86827a); }
.bf-margin { font-size: 11px; color: var(--ink-3, #86827a); margin-left: auto; }
.fade-enter-active, .fade-leave-active { transition: opacity 0.3s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>

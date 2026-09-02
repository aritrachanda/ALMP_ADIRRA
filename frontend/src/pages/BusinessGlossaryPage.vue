<template>
  <q-page class="glossary-v2 column no-wrap">
    <!-- title + tab bar (mirrors AssetWorkspace: title/meta on top, tab bar directly
         below it, left-aligned, above the content area) -->
    <div class="v2-topbar column no-wrap q-px-md q-py-sm">
      <div class="v2-title">Business Glossary</div>
      <div class="tab-bar q-mt-sm">
        <button class="tab-btn" :class="{ 'tab-btn--active': view === 'coverage' }" @click="view = 'coverage'">Coverage</button>
        <button class="tab-btn" :class="{ 'tab-btn--active': view === 'browse' }" @click="view = 'browse'">Browse</button>
        <button class="tab-btn" :class="{ 'tab-btn--active': view === 'review' }" @click="view = 'review'">
          Review
          <span v-if="store.reviewQueue.length" class="tab-badge">{{ store.reviewQueue.length }}</span>
        </button>
      </div>
    </div>

    <!-- ══ BROWSE ══ -->
    <div v-show="view === 'browse'" class="v2-browse row no-wrap col">
      <!-- left: search + facets + tree -->
      <div class="v2-left column no-wrap">
        <div class="q-pa-sm">
          <div class="row items-center q-mb-sm">
            <div class="rail-section-label q-mb-none">Terms</div>
            <q-space />
            <q-btn
              no-caps dense unelevated color="primary" icon="add" label="New Term"
              @click="openNewTermDialog()"
            />
          </div>
          <q-input
            v-model="searchText"
            dense outlined clearable
            placeholder="Search terms (title, domain, category, status…)"
            class="rail-search"
          >
            <template #prepend><q-icon name="search" size="18px" /></template>
          </q-input>
          <div class="rail-chips q-px-none q-mt-sm">
            <button
              v-for="s in ['draft', 'in_review', 'approved']" :key="s"
              class="rail-chip" :class="{ 'rail-chip--active': activeStatus === s }"
              @click="toggleStatus(s)"
            >{{ statusLabel(s) }}</button>
            <button
              class="rail-chip" :class="{ 'rail-chip--active': filterAI }"
              @click="filterAI = !filterAI"
            >AI-generated</button>
            <button
              class="rail-chip" :class="{ 'rail-chip--active': filterLinked }"
              @click="filterLinked = !filterLinked"
            >Has linkage</button>
          </div>
          <div class="text-caption text-grey-6 q-mt-xs">
            {{ filteredSummaries.length }} shown · {{ store.summaries.length }} in glossary
          </div>
        </div>
        <q-separator />
        <div class="v2-tree col scroll">
          <q-inner-loading :showing="store.loading" />
          <template v-for="row in visibleTreeRows" :key="row.key">
            <div
              v-if="row.kind === 'category'"
              class="v2-cat-row"
              @click="toggleCategory(row.key)"
            >
              <q-icon
                :name="collapsedCats.has(row.key) ? 'chevron_right' : 'expand_more'"
                size="14px" class="v2-cat-chevron"
              />
              {{ row.label }} <span class="v2-cat-count">{{ row.count }}</span>
            </div>
            <div
              v-else
              class="v2-term-row"
              :class="{ 'v2-term-active': store.selectedSlug === row.term!.id }"
              :style="{ paddingLeft: 12 + (row.depth || 1) * 14 + 'px' }"
              @click="store.selectTerm(row.term!.id)"
            >
              <q-icon v-if="(row.depth || 1) > 1" name="subdirectory_arrow_right" size="13px" class="text-grey-5 q-mr-xs" />
              <span class="v2-term-title">{{ row.label }}</span>
              <q-space />
              <span class="v2-term-pill">
                <StatusPill :status="row.term!.status || 'draft'" compact />
              </span>
            </div>
          </template>
          <div v-if="!store.loading && !filteredTreeRows.length" class="text-grey-6 q-pa-md text-center">
            Nothing matches those filters.
          </div>
        </div>
      </div>

      <!-- right: detail -->
      <div class="v2-detail col scroll">
        <q-inner-loading :showing="store.detailLoading" />
        <div v-if="!store.selectedTerm" class="v2-empty column items-center justify-center text-grey-5">
          <q-icon name="menu_book" size="40px" />
          <div class="q-mt-sm">Select a term to see its definition, linkages and history.</div>
        </div>
        <div v-else class="q-pa-lg">
          <div class="row items-center q-gutter-sm">
            <div class="v2-term-name">{{ store.selectedTerm.title }}</div>
            <StatusPill :status="store.selectedTerm.status || 'draft'" />
            <q-space />
            <ExportSyncMenu :term="store.selectedTerm" />
          </div>
          <div class="text-caption text-grey-7 q-mt-xs">
            {{ store.selectedTerm.domain || '—' }} · {{ store.selectedTerm.category || '—' }}
            &nbsp;·&nbsp; Steward {{ store.selectedTerm.steward || 'Not assigned' }}
          </div>

          <!-- reparent control (drag-to-reparent polish deferred; select-based here) -->
          <div class="row items-center q-gutter-sm q-mt-sm">
            <span class="text-caption text-grey-6">Parent:</span>
            <q-select
              dense outlined options-dense clearable emit-value map-options
              use-input input-debounce="0" hide-selected fill-input
              style="min-width: 260px"
              :model-value="currentParent"
              :options="filteredParentOptions"
              @filter="filterParentOptions"
              @update:model-value="onReparent"
            >
              <template #no-option>
                <q-item><q-item-section class="text-grey-6">No matching terms</q-item-section></q-item>
              </template>
            </q-select>
          </div>

          <div class="tab-bar q-mt-md">
            <button class="tab-btn" :class="{ 'tab-btn--active': tab === 'definition' }" @click="tab = 'definition'">Definition</button>
            <button class="tab-btn" :class="{ 'tab-btn--active': tab === 'linkages' }" @click="tab = 'linkages'">
              Linkages
              <span class="tab-badge">{{ linkedRefs.length }}</span>
            </button>
            <button class="tab-btn" :class="{ 'tab-btn--active': tab === 'history' }" @click="tab = 'history'">History</button>
          </div>

          <q-tab-panels v-model="tab" animated class="v2-panels">
            <!-- Definition -->
            <q-tab-panel name="definition" class="q-px-none">
              <!-- Business description -->
              <div class="panel-card block-card q-mb-md">
                <div class="block-bar">
                  <span class="block-bar-left">
                    <span class="block-bar-title">Business description</span>
                    <AiBadge :field="'business_description'" :term="store.selectedTerm" />
                  </span>
                  <span v-if="editingField !== 'business_description' && isTermEditable" class="block-bar-actions">
                    <button class="icon-btn" title="Edit" @click="startFieldEdit('business_description')"><q-icon name="edit" size="16px" /></button>
                  </span>
                </div>
                <div class="block-body q-pa-md">
                  <div v-if="editingField !== 'business_description'" class="desc-view">
                    <div class="desc-content">
                      <div v-if="store.selectedTerm.business_description" class="desc-text">{{ store.selectedTerm.business_description }}</div>
                      <div v-else class="desc-empty">Write a business-friendly description…</div>
                    </div>
                  </div>
                  <template v-else>
                    <q-input v-model="fieldEditValue" type="textarea" outlined dense autogrow :rows="3" class="desc-input" placeholder="Write a business-friendly description…" />
                    <div class="desc-actions q-mt-sm">
                      <button class="action-btn action-btn--primary" :disabled="savingField" @click="saveFieldEdit('business_description')">
                        <q-spinner-dots v-if="savingField" size="13px" class="q-mr-xs" /><q-icon v-else name="save" size="14px" class="q-mr-xs" />Save
                      </button>
                      <button class="action-btn action-btn--ai" :disabled="store.generating === 'business_description'" @click="generateFieldEdit('business_description')">
                        <q-spinner-dots v-if="store.generating === 'business_description'" size="13px" class="q-mr-xs" /><q-icon v-else name="auto_awesome" size="14px" class="q-mr-xs" />Draft with AI
                      </button>
                      <button class="action-btn action-btn--secondary" @click="cancelFieldEdit"><q-icon name="close" size="14px" class="q-mr-xs" />Cancel</button>
                    </div>
                  </template>
                </div>
              </div>

              <!-- Detailed description -->
              <div class="panel-card block-card q-mb-md">
                <div class="block-bar">
                  <span class="block-bar-left">
                    <span class="block-bar-title">Detailed description</span>
                    <AiBadge :field="'detailed_description'" :term="store.selectedTerm" />
                  </span>
                  <span v-if="editingField !== 'detailed_description' && isTermEditable" class="block-bar-actions">
                    <button class="icon-btn" title="Edit" @click="startFieldEdit('detailed_description')"><q-icon name="edit" size="16px" /></button>
                  </span>
                </div>
                <div class="block-body q-pa-md">
                  <div v-if="editingField !== 'detailed_description'" class="desc-view">
                    <div class="desc-content">
                      <div v-if="store.selectedTerm.detailed_description" class="desc-text">{{ store.selectedTerm.detailed_description }}</div>
                      <div v-else class="desc-empty">Write a detailed, technical description…</div>
                    </div>
                  </div>
                  <template v-else>
                    <q-input v-model="fieldEditValue" type="textarea" outlined dense autogrow :rows="3" class="desc-input" placeholder="Write a detailed, technical description…" />
                    <div class="desc-actions q-mt-sm">
                      <button class="action-btn action-btn--primary" :disabled="savingField" @click="saveFieldEdit('detailed_description')">
                        <q-spinner-dots v-if="savingField" size="13px" class="q-mr-xs" /><q-icon v-else name="save" size="14px" class="q-mr-xs" />Save
                      </button>
                      <button class="action-btn action-btn--ai" :disabled="store.generating === 'detailed_description'" @click="generateFieldEdit('detailed_description')">
                        <q-spinner-dots v-if="store.generating === 'detailed_description'" size="13px" class="q-mr-xs" /><q-icon v-else name="auto_awesome" size="14px" class="q-mr-xs" />Draft with AI
                      </button>
                      <button class="action-btn action-btn--secondary" @click="cancelFieldEdit"><q-icon name="close" size="14px" class="q-mr-xs" />Cancel</button>
                    </div>
                  </template>
                </div>
              </div>

              <!-- CRR3 / DPM 2.0 (attribute-driven) -->
              <div v-for="attr in store.attributesConfig" :key="attr.key" class="panel-card block-card q-mb-md">
                <div class="block-bar">
                  <span class="block-bar-left">
                    <span class="block-bar-title">{{ attr.label }}</span>
                    <span class="v2-attr-hint">{{ attr.hint }}</span>
                    <AiBadge :field="ATTR_FIELD[attr.key]" :term="store.selectedTerm" />
                  </span>
                  <span v-if="editingField !== ATTR_FIELD[attr.key] && isTermEditable" class="block-bar-actions">
                    <button class="icon-btn" title="Edit" @click="startFieldEdit(ATTR_FIELD[attr.key])"><q-icon name="edit" size="16px" /></button>
                  </span>
                </div>
                <div class="block-body q-pa-md">
                  <div v-if="editingField !== ATTR_FIELD[attr.key]" class="desc-view">
                    <div class="desc-content">
                      <div v-if="attrValue(attr.key)" class="desc-text">{{ attrValue(attr.key) }}</div>
                      <div v-else class="desc-empty">Not set — generate or write an interpretation…</div>
                    </div>
                  </div>
                  <template v-else>
                    <q-input v-model="fieldEditValue" type="textarea" outlined dense autogrow :rows="3" class="desc-input" />
                    <div class="desc-actions q-mt-sm">
                      <button class="action-btn action-btn--primary" :disabled="savingField" @click="saveFieldEdit(ATTR_FIELD[attr.key])">
                        <q-spinner-dots v-if="savingField" size="13px" class="q-mr-xs" /><q-icon v-else name="save" size="14px" class="q-mr-xs" />Save
                      </button>
                      <button class="action-btn action-btn--ai" :disabled="store.generating === attr.key" @click="generateFieldEdit(ATTR_FIELD[attr.key])">
                        <q-spinner-dots v-if="store.generating === attr.key" size="13px" class="q-mr-xs" /><q-icon v-else name="auto_awesome" size="14px" class="q-mr-xs" />Draft with AI
                      </button>
                      <button class="action-btn action-btn--secondary" @click="cancelFieldEdit"><q-icon name="close" size="14px" class="q-mr-xs" />Cancel</button>
                    </div>
                  </template>
                </div>
              </div>

              <!-- Synonyms -->
              <div class="panel-card block-card q-mb-md">
                <div class="block-bar">
                  <span class="block-bar-left">
                    <span class="block-bar-title">Synonyms</span>
                    <AiBadge :field="'synonyms'" :term="store.selectedTerm" />
                  </span>
                  <span v-if="editingField !== 'synonyms' && isTermEditable" class="block-bar-actions">
                    <button class="icon-btn" title="Edit" @click="startFieldEdit('synonyms')"><q-icon name="edit" size="16px" /></button>
                  </span>
                </div>
                <div class="block-body q-pa-md">
                  <div v-if="editingField !== 'synonyms'" class="desc-view">
                    <div class="desc-content">
                      <template v-if="(store.selectedTerm.synonyms || []).length">
                        <q-chip v-for="s in store.selectedTerm.synonyms" :key="s" dense outline color="primary" size="sm">{{ s }}</q-chip>
                      </template>
                      <div v-else class="desc-empty">Add synonyms this term is also known by…</div>
                    </div>
                  </div>
                  <template v-else>
                    <q-input v-model="fieldEditValue" outlined dense class="desc-input" hint="Comma-separated" />
                    <div class="desc-actions q-mt-sm">
                      <button class="action-btn action-btn--primary" :disabled="savingField" @click="saveFieldEdit('synonyms')">
                        <q-spinner-dots v-if="savingField" size="13px" class="q-mr-xs" /><q-icon v-else name="save" size="14px" class="q-mr-xs" />Save
                      </button>
                      <button class="action-btn action-btn--ai" :disabled="store.generating === 'synonyms'" @click="generateFieldEdit('synonyms')">
                        <q-spinner-dots v-if="store.generating === 'synonyms'" size="13px" class="q-mr-xs" /><q-icon v-else name="auto_awesome" size="14px" class="q-mr-xs" />Draft with AI
                      </button>
                      <button class="action-btn action-btn--secondary" @click="cancelFieldEdit"><q-icon name="close" size="14px" class="q-mr-xs" />Cancel</button>
                    </div>
                  </template>
                </div>
              </div>

              <!-- Tags -->
              <div class="panel-card block-card q-mb-md">
                <div class="block-bar">
                  <span class="block-bar-left">
                    <span class="block-bar-title">Tags</span>
                    <AiBadge :field="'tags'" :term="store.selectedTerm" />
                  </span>
                  <span v-if="editingField !== 'tags' && isTermEditable" class="block-bar-actions">
                    <button class="icon-btn" title="Edit" @click="startFieldEdit('tags')"><q-icon name="edit" size="16px" /></button>
                  </span>
                </div>
                <div class="block-body q-pa-md">
                  <div v-if="editingField !== 'tags'" class="desc-view">
                    <div class="desc-content">
                      <template v-if="(store.selectedTerm.tags || []).length">
                        <q-chip v-for="t in store.selectedTerm.tags" :key="t" dense color="grey-3" text-color="grey-8" size="sm">{{ t }}</q-chip>
                      </template>
                      <div v-else class="desc-empty">Add tags to help others find this term…</div>
                    </div>
                  </div>
                  <template v-else>
                    <q-input v-model="fieldEditValue" outlined dense class="desc-input" hint="Comma-separated" />
                    <div class="desc-actions q-mt-sm">
                      <button class="action-btn action-btn--primary" :disabled="savingField" @click="saveFieldEdit('tags')">
                        <q-spinner-dots v-if="savingField" size="13px" class="q-mr-xs" /><q-icon v-else name="save" size="14px" class="q-mr-xs" />Save
                      </button>
                      <button class="action-btn action-btn--ai" :disabled="store.generating === 'tags'" @click="generateFieldEdit('tags')">
                        <q-spinner-dots v-if="store.generating === 'tags'" size="13px" class="q-mr-xs" /><q-icon v-else name="auto_awesome" size="14px" class="q-mr-xs" />Draft with AI
                      </button>
                      <button class="action-btn action-btn--secondary" @click="cancelFieldEdit"><q-icon name="close" size="14px" class="q-mr-xs" />Cancel</button>
                    </div>
                  </template>
                </div>
              </div>
            </q-tab-panel>

            <!-- Linkages -->
            <q-tab-panel name="linkages" class="q-px-none">
              <div v-if="!linkedRefs.length" class="text-grey-6">No linked data objects.</div>
              <template v-else>
                <div class="v2-link-group-head">Source linkages <span class="v2-cat-count">{{ sourceLinkedRefs.length }}</span></div>
                <div v-if="!sourceLinkedRefs.length" class="text-grey-6 q-mb-md">No source-connection linkages.</div>
                <div
                  v-for="ref in sourceLinkedRefs" :key="ref.raw"
                  class="v2-link-row v2-link-row--clickable"
                  @click="openLinkage(ref)"
                >
                  <q-icon :name="granIcon(ref.gran)" size="15px" class="text-grey-6 q-mr-sm" />
                  <span class="v2-link-path">{{ ref.path }}</span>
                  <q-space />
                  <span class="text-caption text-grey-6">{{ ref.gran }} · {{ ref.dataset }}</span>
                  <q-icon name="open_in_new" size="13px" class="q-ml-sm text-grey-5" />
                </div>

                <div class="v2-link-group-head q-mt-md">Target linkages <span class="v2-cat-count">{{ targetLinkedRefs.length }}</span></div>
                <div v-if="!targetLinkedRefs.length" class="text-grey-6">No target/regulatory-model linkages.</div>
                <div
                  v-for="ref in targetLinkedRefs" :key="ref.raw"
                  class="v2-link-row"
                >
                  <q-icon :name="granIcon(ref.gran)" size="15px" class="text-grey-6 q-mr-sm" />
                  <span class="v2-link-path">{{ ref.path }}</span>
                  <q-space />
                  <span class="text-caption text-grey-6">{{ ref.gran }} · {{ ref.kind }}:{{ ref.dataset }}</span>
                  <q-tooltip anchor="top middle" self="bottom middle">
                    Target/regulatory-model elements can't be opened directly yet (tech debt).
                  </q-tooltip>
                </div>
              </template>
            </q-tab-panel>


            <!-- History -->
            <q-tab-panel name="history" class="q-px-none">
              <div v-if="store.history">
                <div class="v2-hist-label">Versions</div>
                <div v-for="v in store.history.versions" :key="v.version_no" class="v2-hist-row">
                  <span class="v2-vbadge" :class="{ serving: v.serving }">v{{ v.version_no }}</span>
                  <span class="text-body2">{{ v.authored_by || 'unknown' }}</span>
                  <span class="text-caption text-grey-6 q-ml-sm">{{ formatTs(v.authored_at) }}</span>
                  <q-badge v-if="v.serving" color="green-7" text-color="white" class="q-ml-sm" label="Serving DQ scoring" />
                </div>
                <div class="v2-hist-label q-mt-md">Lifecycle</div>
                <div v-for="(tr, i) in store.history.transitions" :key="i" class="v2-hist-row">
                  <q-icon name="arrow_forward" size="13px" class="text-grey-5 q-mr-xs" />
                  <span class="text-body2">{{ tr.from_status || '—' }} → {{ tr.to_status }}</span>
                  <span class="text-caption text-grey-6 q-ml-sm">{{ tr.actor || '' }} {{ formatTs(tr.occurred_at) }}</span>
                </div>
              </div>
            </q-tab-panel>
          </q-tab-panels>
        </div>
      </div>
    </div>

    <!-- ══ REVIEW ══ -->
    <div v-show="view === 'review'" class="v2-browse row no-wrap col">
      <!-- left: queue -->
      <div class="v2-left column no-wrap">
        <div class="q-pa-sm row items-center">
          <div class="text-subtitle2 text-weight-bold">Review queue</div>
          <q-space />
          <q-badge color="orange-7" :label="store.reviewQueue.length" />
        </div>
        <div class="text-caption text-grey-6 q-px-sm q-pb-xs">
          Draft, AI-drafted terms awaiting approval.<br>
          <b>J</b>/<b>K</b> move · <b>A</b> approve · <b>R</b> reject.
        </div>
        <q-separator />
        <div class="v2-tree col scroll">
          <q-inner-loading :showing="store.reviewLoading" />
          <div
            v-for="(item, i) in store.reviewQueue" :key="item.id"
            class="v2-term-row"
            :class="{ 'v2-term-active': i === reviewIndex }"
            @click="selectQueueItem(i)"
          >
            <span class="v2-term-title">{{ item.title }}</span>
            <q-space />
            <q-badge v-if="item.assigned_to" dense color="blue-2" text-color="blue-9" :label="item.assigned_to" />
          </div>
          <div v-if="!store.reviewLoading && !store.reviewQueue.length" class="text-grey-6 q-pa-md text-center">
            Queue is clear — no AI drafts awaiting review.
          </div>
        </div>
      </div>

      <!-- right: editor -->
      <div class="v2-detail col scroll">
        <q-inner-loading :showing="store.detailLoading || store.savingTerm" />
        <div v-if="!showEditor" class="v2-empty column items-center justify-center text-grey-5">
          <q-icon name="rate_review" size="40px" />
          <div class="q-mt-sm">Pick a term from the queue to review its AI draft, edit it, then approve or reject.</div>
        </div>
        <div v-else-if="store.selectedTerm" class="q-pa-lg">
          <AiErrorBanner :error="aiError" @dismiss="clearAiError" />
          <div class="row items-center q-gutter-sm">
            <div class="v2-term-name">{{ store.selectedTerm.title }}</div>
            <StatusPill :status="store.selectedTerm.status || 'draft'" />
            <span class="text-caption text-grey-6">{{ store.selectedTerm.domain || '—' }} · {{ store.selectedTerm.category || '—' }}</span>
          </div>

          <!-- reviewer + assignment + actions -->
          <div class="row items-center q-gutter-sm q-mt-md">
            <q-input v-model="reviewer" dense outlined placeholder="Reviewing as…" style="width: 170px">
              <template #prepend><q-icon name="badge" size="16px" /></template>
            </q-input>
            <q-input
              v-model="assignInput" dense outlined placeholder="Assign to…" style="width: 170px"
              @keyup.enter="assign"
            >
              <template #prepend><q-icon name="person_add" size="16px" /></template>
              <template #append>
                <q-btn dense flat round size="sm" icon="check" @click="assign">
                  <q-tooltip>Save assignment</q-tooltip>
                </q-btn>
              </template>
            </q-input>
            <q-space />
            <q-btn no-caps dense outline color="grey-8" icon="save" label="Save" :disable="!isDirty" @click="saveEdits" />
            <q-btn no-caps dense unelevated color="negative" icon="close" label="Reject (R)" @click="reject" />
            <q-btn no-caps dense unelevated color="positive" icon="check" label="Approve (A)" @click="approve" />
          </div>

          <q-separator class="q-my-md" />

          <!-- editable fields, AI draft vs reviewed -->
          <div v-for="f in EDIT_FIELDS" :key="f.key" class="v2-review-field">
            <div class="v2-section-head row items-center no-wrap">
              <span>{{ f.label }}</span>
              <AiBadge :field="f.key" :term="store.selectedTerm" class="q-ml-xs" />
              <q-space />
              <q-btn
                dense flat no-caps size="sm" color="orange-8" icon="auto_awesome" label="Regenerate"
                :loading="store.generating === f.gen" @click="regenerate(f)"
              />
            </div>
            <div class="row q-col-gutter-md items-stretch">
              <div class="col-6">
                <div class="v2-draft-label">AI draft</div>
                <div class="v2-draft-box">{{ aiDraft[f.key] || '—' }}</div>
              </div>
              <div class="col-6">
                <div class="v2-draft-label">Reviewed</div>
                <q-input
                  v-if="f.type === 'text'"
                  v-model="edited[f.key]" type="textarea" autogrow dense outlined
                />
                <q-input
                  v-else
                  v-model="edited[f.key]" dense outlined hint="comma-separated"
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ══ COVERAGE ══ -->
    <div v-show="view === 'coverage'" class="v2-coverage col scroll q-pa-lg">
      <template v-if="store.coverage">
        <div class="row q-col-gutter-md">
          <div v-for="kpi in kpis" :key="kpi.label" class="col-12 col-sm-6 col-md-3">
            <q-card flat bordered class="v2-kpi" :style="{ borderLeft: `3px solid ${kpi.color}` }">
              <div class="v2-kpi-label">{{ kpi.label }}</div>
              <div class="v2-kpi-value" :style="{ color: kpi.color }">{{ kpi.value }}<span class="v2-kpi-of">{{ kpi.of }}</span></div>
            </q-card>
          </div>
        </div>

        <q-card flat bordered class="q-mt-md q-pa-md">
          <div class="v2-section-head">Linkage granularity</div>
          <div class="text-caption text-grey-6 q-mb-sm">Table/dataset references counted as linkages in v1 are now separate from column-level coverage.</div>
          <div v-for="g in granularityBars" :key="g.k" class="row items-center q-gutter-sm q-mb-xs">
            <q-icon :name="granIcon(g.k)" size="15px" class="text-grey-7" />
            <span style="width: 60px" class="text-body2">{{ g.k }}</span>
            <q-linear-progress :value="g.frac" size="14px" color="blue-6" track-color="grey-3" style="flex: 1" rounded />
            <span style="width: 40px" class="text-right text-body2">{{ g.n }}</span>
          </div>
        </q-card>

        <q-card flat bordered class="q-mt-md q-pa-md">
          <div class="v2-section-head">Status distribution</div>
          <div class="row q-gutter-md q-mt-xs">
            <div v-for="(n, s) in store.coverage.by_status" :key="s" class="text-body2">
              <StatusPill :status="String(s)" compact /> <span class="text-grey-7">{{ n }}</span>
            </div>
          </div>
        </q-card>

        <q-card flat bordered class="q-mt-md q-pa-md">
          <div class="v2-section-head text-negative">Unresolved references (triage)</div>
          <div class="text-body2 q-mt-xs">
            <b>{{ store.coverage.triage_total }}</b> catalog references don't resolve to an onboarded asset.
            Must reach zero before v1 is retired.
          </div>
        </q-card>
      </template>
      <q-inner-loading :showing="!store.coverage">
        <StagedLoader :stages="coverageLoadStages" :completed="store.coverageProgress.completed" :active-detail="store.coverageProgress.detail" />
      </q-inner-loading>
    </div>

    <!-- ══ NEW TERM ══ -->
    <q-dialog v-model="showNewTermDialog">
      <q-card style="min-width: 480px; max-width: 560px">
        <q-card-section>
          <div class="text-h6">New Term</div>
          <div v-if="newTermLinkPrefill" class="text-caption text-grey-6 q-mt-xs">
            Will be linked to <span class="v2-link-path">{{ newTermLinkPrefill }}</span>
          </div>
        </q-card-section>
        <q-card-section class="q-gutter-sm">
          <q-input v-model="newTerm.title" dense outlined autofocus label="Title *" />
          <div v-if="duplicateTitleMatch" class="v2-dup-warning">
            <q-icon name="warning_amber" size="16px" class="q-mr-xs" />
            A term titled "{{ duplicateTitleMatch.title }}" already exists.
            <a href="#" class="v2-dup-link" @click.prevent="openExistingTerm(duplicateTitleMatch.id)">Open it instead</a>
          </div>
          <div class="row q-col-gutter-sm">
            <q-input v-model="newTerm.domain" dense outlined class="col" label="Domain" />
            <q-input v-model="newTerm.category" dense outlined class="col" label="Category" />
          </div>
          <q-input v-model="newTerm.steward" dense outlined label="Steward" />
          <q-input v-model="newTerm.business_description" dense outlined type="textarea" autogrow label="Business description" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancel" v-close-popup @click="cancelNewTermDialog" />
          <q-btn
            no-caps unelevated color="primary" label="Create"
            :disable="!newTerm.title.trim() || !!duplicateTitleMatch" :loading="creatingTerm"
            @click="submitNewTerm"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { Notify } from 'quasar';
import { useGlossaryV2Store, buildTreeRows } from 'src/stores/glossaryV2Store';
import { statusLabel } from 'src/utils/statusDisplay';
import StatusPill from 'src/components/StatusPill.vue';
import AiBadge from 'src/components/AiProvenanceBadge.vue';
import ExportSyncMenu from 'src/components/ExportSyncMenu.vue';
import AiErrorBanner from 'src/components/AiErrorBanner.vue';
import StagedLoader from 'src/components/StagedLoader.vue';
import { useAiError } from 'src/composables/useAiError';
import { upsertTerm as createV1Term } from 'src/api/glossary';
import type { GlossaryTerm, AIProvenance } from 'src/types';

const store = useGlossaryV2Store();
const route = useRoute();
const router = useRouter();

// Shared "AI action failed" banner for AI field generation (CRR3 / DPM / prose).
const { aiError, setAiError, clearAiError, aiErrorFrom } = useAiError();

const view = ref<'browse' | 'review' | 'coverage'>('browse');
const tab = ref<'definition' | 'linkages' | 'history'>('definition');
const coverageLoadStages = computed(() => [
  'Tallying glossary coverage…',
  'Checking catalog linkages…',
]);
const searchText = ref('');
const activeStatus = ref<string | null>(null);
const filterAI = ref(false);
const filterLinked = ref(false);

// ── category collapse (groups collapsed by default; auto-expanded while
// searching/filtering so matches aren't hidden behind a closed group) ──
const collapsedCats = ref<Set<string>>(new Set());
let catsSeeded = false;
watch(() => store.treeRows, (rows) => {
  if (catsSeeded) return;
  const cats = rows.filter((r) => r.kind === 'category').map((r) => r.key);
  if (cats.length) {
    collapsedCats.value = new Set(cats);
    catsSeeded = true;
  }
}, { immediate: true });

function toggleCategory(key: string) {
  const next = new Set(collapsedCats.value);
  if (next.has(key)) next.delete(key);
  else next.add(key);
  collapsedCats.value = next;
}

function clearAllFilters() {
  activeStatus.value = null;
  filterAI.value = false;
  filterLinked.value = false;
}

const isFiltering = computed(() =>
  !!(searchText.value || activeStatus.value || filterAI.value || filterLinked.value));

/** Live predictive filtering — entirely client-side against the already-loaded
 * summaries (matches the old Business Glossary's instant search), so there is no
 * network round-trip or debounce lag while typing. */
const filteredSummaries = computed(() => {
  const tokens = searchText.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
  return store.summaries.filter((s) => {
    if (activeStatus.value && s.status !== activeStatus.value) return false;
    if (filterAI.value && !s.ai_generated) return false;
    if (filterLinked.value && !s.has_linkage) return false;
    if (!tokens.length) return true;
    const haystack = `${s.title} ${s.domain} ${s.category} ${s.status}`.toLowerCase();
    return tokens.every((t) => haystack.includes(t));
  });
});
const filteredTreeRows = computed(() => buildTreeRows(filteredSummaries.value));

const visibleTreeRows = computed(() => {
  if (isFiltering.value) return filteredTreeRows.value;
  const rows: typeof filteredTreeRows.value = [];
  let hideUntilNextCategory = false;
  for (const row of filteredTreeRows.value) {
    if (row.kind === 'category') {
      hideUntilNextCategory = collapsedCats.value.has(row.key);
      rows.push(row);
    } else if (!hideUntilNextCategory) {
      rows.push(row);
    }
  }
  return rows;
});

const ATTR_FIELD: Record<string, 'CRR_context' | 'DPM_context'> = {
  crr3: 'CRR_context',
  dpm: 'DPM_context',
};

function attrValue(key: string): string {
  const field = ATTR_FIELD[key];
  return field ? (store.selectedTerm?.[field] || '') : '';
}

function toggleStatus(s: string) {
  activeStatus.value = activeStatus.value === s ? null : s;
}

// ── Definition tab: per-field inline edit (Browse view) ─────────────────────
// term field key currently being edited: business_description, detailed_description,
// CRR_context, DPM_context, synonyms, tags
const editingField = ref<string | null>(null);
const fieldEditValue = ref('');
const savingField = ref(false);
// tracks whether the current edit buffer is an untouched AI draft, so saving can
// mark/unmark ai_generated_fields + ai_provenance correctly (mirrors Review's buildPayload)
const genDraftKey = ref<string | null>(null);
const genDraftValue = ref('');
const genDraftProv = ref<AIProvenance | null>(null);

// Draft-only editing (mirrors AssetWorkspace's isLcEditable): frozen once in_review/approved.
const isTermEditable = computed(() => {
  const s = store.selectedTerm?.status;
  return s !== 'in_review' && s !== 'approved';
});

function fieldDisplayValue(key: string): string {
  const t = store.selectedTerm;
  if (!t) return '';
  const v = (t as unknown as Record<string, unknown>)[key];
  return Array.isArray(v) ? (v as string[]).join(', ') : ((v as string) ?? '');
}

function startFieldEdit(key: string) {
  editingField.value = key;
  fieldEditValue.value = fieldDisplayValue(key);
  genDraftKey.value = null;
  genDraftValue.value = '';
  genDraftProv.value = null;
}

function cancelFieldEdit() {
  editingField.value = null;
  fieldEditValue.value = '';
}

/** Backend generate-field keys differ from term field names for CRR3/DPM only. */
function genKeyFor(fieldKey: string): string {
  if (fieldKey === 'CRR_context') return 'crr3';
  if (fieldKey === 'DPM_context') return 'dpm';
  return fieldKey;
}

async function generateFieldEdit(fieldKey: string) {
  const t = store.selectedTerm;
  if (!t) return;
  clearAiError();
  try {
    const res = await store.generateField(t.id, genKeyFor(fieldKey));
    if (res.value == null) {
      setAiError(res.error ?? { summary: res.message || 'Generation unavailable.' });
      return;
    }
    const disp = Array.isArray(res.value) ? res.value.join(', ') : res.value;
    fieldEditValue.value = disp;
    genDraftKey.value = fieldKey;
    genDraftValue.value = disp;
    genDraftProv.value = res.provenance ?? null;
  } catch (e) {
    setAiError(aiErrorFrom(e, 'Generation failed.'));
  }
}

async function saveFieldEdit(fieldKey: string) {
  const t = store.selectedTerm;
  if (!t) return;
  savingField.value = true;
  try {
    const isList = fieldKey === 'synonyms' || fieldKey === 'tags';
    const value: string | string[] = isList
      ? fieldEditValue.value.split(',').map((s) => s.trim()).filter(Boolean)
      : fieldEditValue.value;
    const aiFields = new Set(t.ai_generated_fields || []);
    const prov: Record<string, AIProvenance> = { ...(t.ai_provenance || {}) };
    const generatedUnmodified = genDraftKey.value === fieldKey && fieldEditValue.value === genDraftValue.value && !!genDraftProv.value;
    if (generatedUnmodified) {
      aiFields.add(fieldKey);
      prov[fieldKey] = genDraftProv.value!;
    } else {
      aiFields.delete(fieldKey);
      delete prov[fieldKey];
    }
    await store.saveTerm(t.id, {
      [fieldKey]: value,
      ai_generated_fields: [...aiFields],
      ai_provenance: prov,
    } as unknown as Partial<GlossaryTerm>);
    editingField.value = null;
    Notify.create({ message: 'Saved.', color: 'positive', position: 'top', timeout: 1200 });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : 'Save failed';
    Notify.create({ message: msg, color: 'negative', position: 'top', timeout: 2600 });
  } finally {
    savingField.value = false;
  }
}

// ── reparent ──
const currentParent = computed(() => {
  const slug = store.selectedSlug;
  return store.summaries.find((s) => s.id === slug)?.parent ?? null;
});
const parentOptions = computed(() =>
  store.summaries
    .filter((s) => s.id !== store.selectedSlug)
    .map((s) => ({ label: s.title, value: s.id }))
    .sort((a, b) => a.label.localeCompare(b.label)),
);
const filteredParentOptions = ref<{ label: string; value: string }[]>([]);
watch(parentOptions, (opts) => { filteredParentOptions.value = opts; }, { immediate: true });
function filterParentOptions(val: string, update: (cb: () => void) => void) {
  update(() => {
    const needle = val.trim().toLowerCase();
    filteredParentOptions.value = needle
      ? parentOptions.value.filter((o) => o.label.toLowerCase().includes(needle))
      : parentOptions.value;
  });
}
async function onReparent(parent: string | null) {
  if (!store.selectedSlug) return;
  try {
    await store.reparentTerm(store.selectedSlug, parent);
    Notify.create({ message: 'Hierarchy updated.', color: 'positive', position: 'top', timeout: 1400 });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : 'Reparent failed';
    Notify.create({ message: msg, color: 'negative', position: 'top', timeout: 2600 });
  }
}

// ── new term dialog ──
const showNewTermDialog = ref(false);
const creatingTerm = ref(false);
const newTermLinkPrefill = ref<string | null>(null);
const newTerm = reactive({ title: '', domain: '', category: '', steward: '', business_description: '' });

function openNewTermDialog(link: string | null = null) {
  newTerm.title = '';
  newTerm.domain = '';
  newTerm.category = '';
  newTerm.steward = '';
  newTerm.business_description = '';
  newTermLinkPrefill.value = link;
  showNewTermDialog.value = true;
}

function cancelNewTermDialog() {
  newTermLinkPrefill.value = null;
}

// Case-insensitive exact-title collision check against the already-loaded term list —
// primary UX guard; the backend (agents/glossary_agent.py::add) enforces the same rule
// as a defense-in-depth safety net for any caller that bypasses this dialog.
const duplicateTitleMatch = computed(() => {
  const normalized = newTerm.title.trim().toLowerCase();
  if (!normalized) return null;
  return store.summaries.find((s) => s.title.trim().toLowerCase() === normalized) ?? null;
});

function openExistingTerm(id: string) {
  showNewTermDialog.value = false;
  newTermLinkPrefill.value = null;
  view.value = 'browse';
  void store.selectTerm(id);
}

async function submitNewTerm() {
  if (!newTerm.title.trim() || duplicateTitleMatch.value) return;
  creatingTerm.value = true;
  try {
    const saved = await createV1Term({
      title: newTerm.title.trim(),
      domain: newTerm.domain.trim(),
      category: newTerm.category.trim(),
      steward: newTerm.steward.trim(),
      business_description: newTerm.business_description.trim(),
      related_objects: newTermLinkPrefill.value ? [newTermLinkPrefill.value] : [],
    });
    showNewTermDialog.value = false;
    newTermLinkPrefill.value = null;
    await Promise.all([store.loadTree(), store.loadFacets(), store.loadCoverage()]);
    view.value = 'browse';
    await store.selectTerm(saved.id);
    Notify.create({ message: `Created "${saved.title}".`, color: 'positive', position: 'top', timeout: 1600 });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : 'Create failed';
    Notify.create({ message: msg, color: 'negative', position: 'top', timeout: 2600 });
  } finally {
    creatingTerm.value = false;
  }
}

// ── linkages parse ──
interface ParsedRef { raw: string; kind: string; dataset: string; gran: string; path: string }
const linkedRefs = computed<ParsedRef[]>(() =>
  (store.selectedTerm?.related_objects || []).map((raw) => {
    const parts = raw.split('|');
    if (parts.length !== 3) return { raw, kind: '', dataset: '', gran: 'concept', path: raw };
    const segs = parts[2].split('.').filter(Boolean);
    const gran = segs.length >= 3 ? 'column' : segs.length === 2 ? 'table' : 'dataset';
    return { raw, kind: parts[0], dataset: parts[1], gran, path: parts[2] };
  }),
);
function granIcon(g: string): string {
  return g === 'column' ? 'view_column' : g === 'table' ? 'table_chart' : g === 'dataset' ? 'storage' : 'link';
}
const sourceLinkedRefs = computed(() => linkedRefs.value.filter((r) => r.kind === 'source'));
const targetLinkedRefs = computed(() => linkedRefs.value.filter((r) => r.kind !== 'source'));

/** Source-kind linkages open the exact element on Asset Workspace's Interpretation tab
 * (its `/workspace?source=&schema=&table=&column=&tab=` deep-link contract). Target/
 * regulatory-model (BIRD/CRDM) linkages have no equivalent page yet — see tech-debt. */
function openLinkage(ref: ParsedRef) {
  if (ref.kind !== 'source') return;
  const segs = ref.path.split('.').filter(Boolean);
  const query: Record<string, string> = { source: ref.dataset };
  if (ref.gran === 'column' && segs.length >= 3) {
    query.schema = segs[0];
    query.table = segs[1];
    query.column = segs.slice(2).join('.');
    query.tab = 'interpretation';
  } else if (ref.gran === 'table' && segs.length === 2) {
    query.schema = segs[0];
    query.table = segs[1];
  }
  router.push({ path: '/workspace', query });
}
function formatTs(ts: string | null): string {
  if (!ts) return '';
  try { return new Date(ts).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }); }
  catch { return ''; }
}

// ── coverage view models ──
const kpis = computed(() => {
  const c = store.coverage;
  if (!c) return [];
  return [
    { label: 'Terms approved', value: c.approved, of: ` / ${c.terms_total}`, color: '#14543F' },
    { label: 'Column coverage', value: `${c.column_coverage_pct}%`, of: ` (${c.distinct_linked_source_columns}/${c.total_source_columns})`, color: '#1C5B9E' },
    { label: 'Triage', value: c.triage_total, of: ' refs', color: '#9C5D06' },
    { label: 'Needs revalidation', value: c.needs_revalidation, of: ' linkages', color: '#9E2F2A' },
  ];
});
const granularityBars = computed(() => {
  const c = store.coverage;
  if (!c) return [];
  const total = c.linkages_total || 1;
  return ['column', 'table', 'dataset'].map((k) => ({
    k, n: c.by_granularity[k] || 0, frac: (c.by_granularity[k] || 0) / total,
  }));
});

// ── review queue + inline editor (Phase 4c) ──────────────────────────────────
interface EditField { key: string; label: string; gen: string; type: 'text' | 'list' }
const EDIT_FIELDS: EditField[] = [
  { key: 'business_description', label: 'Business description', gen: 'business_description', type: 'text' },
  { key: 'detailed_description', label: 'Detailed description', gen: 'detailed_description', type: 'text' },
  { key: 'CRR_context', label: 'CRR context', gen: 'crr3', type: 'text' },
  { key: 'DPM_context', label: 'DPM context', gen: 'dpm', type: 'text' },
  { key: 'synonyms', label: 'Synonyms', gen: 'synonyms', type: 'list' },
  { key: 'tags', label: 'Tags', gen: 'tags', type: 'list' },
];

const reviewIndex = ref(-1);
const reviewer = ref('');
const assignInput = ref('');
const edited = reactive<Record<string, string>>({});   // reviewer-facing editable text
const aiDraft = reactive<Record<string, string>>({});   // AI draft display (updates on regenerate)
let originalRaw: Record<string, string | string[]> = {}; // stored values, for change detection
let genProv: Record<string, AIProvenance> = {};          // provenance from regenerated fields

const currentQueueSlug = computed(() => store.reviewQueue[reviewIndex.value]?.id ?? null);
const showEditor = computed(
  () => !!currentQueueSlug.value && store.selectedTerm?.id === currentQueueSlug.value,
);

function fieldRaw(t: GlossaryTerm, key: string): string | string[] {
  const v = (t as unknown as Record<string, unknown>)[key];
  if (Array.isArray(v)) return v as string[];
  return (v as string) ?? '';
}

function buildEditor() {
  const t = store.selectedTerm;
  if (!t) return;
  originalRaw = {};
  genProv = {};
  for (const f of EDIT_FIELDS) {
    const raw = fieldRaw(t, f.key);
    const disp = Array.isArray(raw) ? raw.join(', ') : raw;
    edited[f.key] = disp;
    aiDraft[f.key] = disp;
    originalRaw[f.key] = raw;
  }
  assignInput.value = store.reviewQueue[reviewIndex.value]?.assigned_to || '';
}

async function selectQueueItem(i: number) {
  reviewIndex.value = i;
  const slug = store.reviewQueue[i]?.id;
  if (!slug) return;
  await store.selectTerm(slug);
  buildEditor();
}

function advance() {
  const n = store.reviewQueue.length;
  if (!n) { reviewIndex.value = -1; return; }
  void selectQueueItem(Math.min(reviewIndex.value, n - 1));
}

function parseEdited(f: EditField): string | string[] {
  const v = edited[f.key] || '';
  return f.type === 'list' ? v.split(',').map((s) => s.trim()).filter(Boolean) : v;
}

const isDirty = computed(() => {
  if (!showEditor.value) return false;
  return EDIT_FIELDS.some(
    (f) => JSON.stringify(parseEdited(f)) !== JSON.stringify(originalRaw[f.key]),
  );
});

function notifyErr(e: unknown, fallback = 'Action failed') {
  const msg = e instanceof Error ? e.message : fallback;
  Notify.create({ message: msg, color: 'negative', position: 'top', timeout: 2600 });
}

async function regenerate(f: EditField) {
  const t = store.selectedTerm;
  if (!t) return;
  clearAiError();
  try {
    const res = await store.generateField(t.id, f.gen);
    if (res.value == null) {
      setAiError(res.error ?? { summary: res.message || 'Generation unavailable.' });
      return;
    }
    const disp = Array.isArray(res.value) ? res.value.join(', ') : res.value;
    aiDraft[f.key] = disp;
    edited[f.key] = disp;
    if (res.provenance) genProv[f.key] = res.provenance;
    Notify.create({ message: `Regenerated ${f.label.toLowerCase()}.`, color: 'positive', position: 'top', timeout: 1400 });
  } catch (e) {
    setAiError(aiErrorFrom(e, 'Generation failed.'));
  }
}

/** Merge edits into the full term, recomputing ai_generated_fields + provenance. */
function buildPayload(): { payload: GlossaryTerm; dirty: boolean } {
  const t = store.selectedTerm as GlossaryTerm;
  const aiFields = new Set(t.ai_generated_fields || []);
  const prov: Record<string, AIProvenance> = { ...(t.ai_provenance || {}) };
  const payload: GlossaryTerm = { ...t };
  let dirty = false;
  for (const f of EDIT_FIELDS) {
    const finalRaw = parseEdited(f);
    (payload as unknown as Record<string, unknown>)[f.key] = finalRaw;
    if (JSON.stringify(finalRaw) === JSON.stringify(originalRaw[f.key])) continue;
    dirty = true;
    const generatedUnmodified = !!genProv[f.key] && edited[f.key] === aiDraft[f.key];
    if (generatedUnmodified) {
      aiFields.add(f.key);
      prov[f.key] = genProv[f.key]!;
    } else {
      aiFields.delete(f.key);   // reviewer hand-authored — no longer AI
      delete prov[f.key];
    }
  }
  payload.ai_generated_fields = [...aiFields];
  payload.ai_provenance = prov;
  return { payload, dirty };
}

async function save(): Promise<boolean> {
  const t = store.selectedTerm;
  if (!t) return false;
  const { payload, dirty } = buildPayload();
  if (!dirty) return true;
  try {
    await store.saveTerm(t.id, payload);
    buildEditor();   // refresh baseline from persisted term
    return true;
  } catch (e) {
    notifyErr(e, 'Save failed');
    return false;
  }
}

async function saveEdits() {
  if (await save()) {
    Notify.create({ message: 'Edits saved.', color: 'positive', position: 'top', timeout: 1400 });
  }
}

async function approve() {
  const t = store.selectedTerm;
  if (!t || currentQueueSlug.value !== t.id) return;
  if (!(await save())) return;
  try {
    await store.confirmTerm(t.id, { decided_by: reviewer.value || undefined, decided_by_role: 'steward' });
    Notify.create({ message: `Approved “${t.title}”.`, color: 'positive', position: 'top', timeout: 1600 });
    advance();
  } catch (e) {
    notifyErr(e, 'Approve failed');
  }
}

async function reject() {
  const t = store.selectedTerm;
  if (!t || currentQueueSlug.value !== t.id) return;
  try {
    await store.rejectTerm(t.id, {
      decided_by: reviewer.value || undefined, decided_by_role: 'steward',
      reason: 'Rejected in bulk review',
    });
    Notify.create({ message: `Rejected “${t.title}”.`, color: 'warning', position: 'top', timeout: 1600 });
    advance();
  } catch (e) {
    notifyErr(e, 'Reject failed');
  }
}

async function assign() {
  const slug = currentQueueSlug.value;
  if (!slug) return;
  try {
    await store.assignReview(slug, assignInput.value || null);
    Notify.create({ message: 'Assignment updated.', color: 'positive', position: 'top', timeout: 1400 });
  } catch (e) {
    notifyErr(e, 'Assignment failed');
  }
}

function onKey(e: KeyboardEvent) {
  if (view.value !== 'review') return;
  const tag = (e.target as HTMLElement | null)?.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA') return;   // don't hijack editing
  const k = e.key.toLowerCase();
  if (k === 'j') { e.preventDefault(); if (reviewIndex.value < store.reviewQueue.length - 1) void selectQueueItem(reviewIndex.value + 1); }
  else if (k === 'k') { e.preventDefault(); if (reviewIndex.value > 0) void selectQueueItem(reviewIndex.value - 1); }
  else if (k === 'a') { e.preventDefault(); void approve(); }
  else if (k === 'r') { e.preventDefault(); void reject(); }
}

onMounted(async () => {
  window.addEventListener('keydown', onKey);

  // Deep-link support (e.g. Asset Workspace's "Create New Linkage" / "View linked term"):
  //   ?new=1[&link=<related_object ref>]  — open the New Term dialog, optionally prefilled
  //   ?term=<id>                          — select an existing term directly
  // Kick the term selection off up-front (parallel with the slower tree/facet loads) so a
  // deep-linked term opens immediately instead of appearing blank behind the whole page load.
  view.value = 'browse';
  if (route.query.new === '1') {
    openNewTermDialog(typeof route.query.link === 'string' ? route.query.link : null);
  } else if (typeof route.query.term === 'string' && route.query.term) {
    void store.selectTerm(route.query.term);
  }
  if (route.query.new || route.query.term || route.query.link) {
    void router.replace({ query: {} });
  }

  await Promise.all([
    store.loadTree(),
    store.loadFacets(),
    store.loadAttributesConfig(),
    store.loadCoverage(),
    store.loadReviewQueue(),
  ]);
});

onBeforeUnmount(() => window.removeEventListener('keydown', onKey));
</script>

<style scoped>
.glossary-v2 {
  height: 100%; min-height: 0;
  background: radial-gradient(ellipse 110% 55% at 50% 0%, #b8d4ec 0%, #d4e6f2 28%, #e8f0f7 50%, #f6f3ec 75%);
  /* Local token aliases mirror AssetWorkspace's `.wp` / ReferenceDataspace's `.rds-page`
     blocks so this page reuses the same visual language and responds to dark mode,
     instead of hardcoding its own hex palette. */
  --text: var(--adirra-ink);
  --text-2: var(--adirra-ink-2);
  --border: var(--adirra-line);
  --accent: var(--adirra-accent);
  --paper: var(--adirra-paper);
  --card-bg: var(--adirra-card);
}
.v2-topbar { border-bottom: 1px solid var(--border); background: var(--card-bg); flex: 0 0 auto; }
.v2-title { font-size: 18px; font-weight: 700; color: var(--text); }

/* ── Tab bar — mirrors AssetWorkspace's pill-style .tab-bar/.tab-btn ──── */
.tab-bar { display: flex; align-items: center; gap: 6px; }
.tab-btn {
  font-size: 12.5px;
  padding: 7px 14px;
  border: 1px solid rgba(13, 92, 84, 0.14);
  border-radius: 9px;
  background: linear-gradient(180deg, rgba(13, 92, 84, 0.09), rgba(13, 92, 84, 0.035));
  color: var(--text);
  cursor: pointer;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 5px;
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  transition: color .15s, background .15s, border-color .15s, box-shadow .15s;
}
.tab-btn:not(.tab-btn--active):hover {
  background: linear-gradient(180deg, rgba(13, 92, 84, 0.09), rgba(13, 92, 84, 0.035));
  border-color: #1c1b18;
}
.tab-btn--active {
  color: #fdfffe;
  background: linear-gradient(160deg, #16887c 0%, var(--accent) 55%, #0a4a43 100%);
  border-color: #0a4a43;
  font-weight: 700;
  box-shadow: 0 3px 10px -2px rgba(13, 92, 84, 0.45), inset 0 1px 0 rgba(255, 255, 255, 0.28);
}
.tab-badge {
  font-size: 9px;
  padding: 1px 4px;
  border-radius: 4px;
  background: #e0e0e0;
  color: #555;
  font-weight: 700;
}
.tab-btn--active .tab-badge { background: rgba(255, 255, 255, 0.25); color: #fdfffe; }
.v2-browse { min-height: 0; }
.v2-left { width: 320px; flex: 0 0 320px; border-right: 1px solid var(--border); background: #e8edf2; min-height: 0; }
.v2-tree { min-height: 0; position: relative; padding-bottom: 24px; }
.v2-detail { min-height: 0; position: relative; background: transparent; }
.v2-cat-row { display: flex; align-items: center; gap: 4px; font-size: 12px; font-weight: 700; color: var(--text-2); padding: 8px 12px 4px; text-transform: uppercase; letter-spacing: .04em; cursor: pointer; }
.v2-cat-row:hover { color: var(--text); }
.v2-cat-count { color: var(--text-2); font-weight: 500; }
/* Pill-card term rows — mirrors AssetWorkspace's rail-col-btn/rail-col-btn--active gradient */
.v2-term-row {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  margin: 3px 8px;
  border-radius: 10px;
  cursor: pointer;
  font-size: 13px;
  background: var(--card-bg);
  border: 1px solid var(--border);
  transition: background .12s, border-color .12s, box-shadow .12s;
}
.v2-term-row:hover {
  background: color-mix(in srgb, var(--accent) 6%, var(--card-bg));
  border-color: color-mix(in srgb, var(--accent) 30%, var(--border));
}
.v2-term-active {
  background: linear-gradient(160deg, #16887c 0%, var(--accent) 55%, #0a4a43 100%) !important;
  border-color: #0a4a43 !important;
  box-shadow: 0 3px 10px -2px rgba(13, 92, 84, 0.45), inset 0 1px 0 rgba(255, 255, 255, 0.28);
}
.v2-term-active .v2-term-title { color: #fdfffe; }
.v2-term-title { color: #3a3833; font-weight: 700; }
.v2-term-pill :deep(.status-pill) { min-height: 16px; padding: 0.06rem 0.4rem; font-size: 0.6rem; }
.v2-link-group-head { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: var(--text-2); margin-bottom: 6px; display: flex; align-items: center; gap: 8px; }
.v2-dup-warning { font-size: 12.5px; color: #9a3412; background: #ffedd5; border: 1px solid #fdba74; border-radius: 6px; padding: 6px 10px; display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
.v2-dup-link { color: #9a3412; font-weight: 700; text-decoration: underline; }

/* ── Rail-style search/chips/section-label — mirrors AssetWorkspace's rail ── */
.rail-section-label {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .10em;
  text-transform: uppercase;
  color: var(--text-2);
}
.rail-search :deep(.q-field__control) {
  height: 34px;
  font-size: 12.5px;
  background: var(--card-bg);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  border-radius: 10px;
  box-shadow: 0 1px 2px rgba(28, 27, 24, 0.06);
  transition: border-color .15s ease, box-shadow .15s ease, background .15s ease;
}
.rail-search :deep(.q-field__control)::before { border-color: var(--border) !important; border-radius: 10px; }
.rail-search:hover :deep(.q-field__control)::before { border-color: var(--accent) !important; }
.rail-search :deep(.q-icon) { color: var(--accent); opacity: .85; }
.rail-search :deep(.q-field--focused .q-field__control),
.rail-search :deep(.q-field--highlighted .q-field__control) {
  background: color-mix(in srgb, var(--accent) 10%, white) !important;
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 16%, transparent), 0 2px 6px rgba(13, 92, 84, 0.12);
}
.rail-search :deep(.q-field--focused .q-field__control::after),
.rail-search :deep(.q-field--highlighted .q-field__control::after) {
  border-color: var(--accent) !important; border-width: 1.5px !important; border-radius: 10px; box-shadow: none !important;
}
.rail-chips { display: flex; flex-wrap: wrap; gap: 5px; }
.rail-chip {
  font-size: 10.5px;
  font-weight: 600;
  height: 22px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: 11px;
  background: var(--card-bg);
  color: var(--text-2);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 5px;
  transition: background .12s, color .12s, border-color .12s;
}
.rail-chip--active { background: var(--accent); border-color: var(--accent); color: #fff; }

.v2-empty { height: 100%; gap: 8px; }
.v2-term-name { font-family: 'IBM Plex Serif', serif; font-size: 24px; font-weight: 600; color: var(--text); }
.v2-panels { background: transparent; }
.v2-section { margin: 14px 0; }
.v2-section-head { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: var(--text-2); margin-bottom: 5px; display: flex; align-items: center; gap: 8px; }
.v2-attr-hint { font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: var(--text-2); text-transform: none; letter-spacing: 0; }
.v2-section-body { font-size: 14px; line-height: 1.6; color: var(--text); white-space: pre-wrap; }
.v2-link-row { display: flex; align-items: center; padding: 8px 10px; border: 1px solid var(--border); border-radius: 6px; background: #fff; margin-bottom: 6px; }
.v2-link-row--clickable { cursor: pointer; transition: border-color .12s, background .12s; }
.v2-link-row--clickable:hover { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 7%, white); }
.v2-link-path { font-family: 'IBM Plex Mono', monospace; font-size: 12px; color: #14515f; }
.v2-hist-label { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: var(--text-2); margin-bottom: 6px; }
.v2-hist-row { display: flex; align-items: center; padding: 4px 0; }
.v2-vbadge { display: inline-grid; place-items: center; width: 30px; height: 20px; border-radius: 10px; font-size: 11px; font-weight: 700; background: #efebe2; color: var(--text-2); margin-right: 8px; }
.v2-vbadge.serving { background: #14543F; color: #fff; }
.v2-coverage { min-height: 0; position: relative; }
.v2-kpi { padding: 12px 14px; }
.v2-kpi-label { font-size: 11px; text-transform: uppercase; letter-spacing: .03em; color: var(--text-2); }
.v2-kpi-value { font-size: 26px; font-weight: 700; font-variant-numeric: tabular-nums; }
.v2-kpi-of { font-size: 12px; color: var(--text-2); font-weight: 400; margin-left: 4px; }
.v2-review-field { margin: 16px 0; }
.v2-draft-label { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: var(--text-2); margin-bottom: 4px; }
.v2-draft-box { font-size: 13px; line-height: 1.55; color: var(--text-2); white-space: pre-wrap; background: #efece4; border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; min-height: 40px; }
.v2-cat-chevron { color: var(--text-2); }

/* ── Editable field cards (Definition tab) — mirrors AssetWorkspace's
   panel-card, block-card, block-bar, desc-view/desc-text, action-btn pattern exactly ── */
.panel-card {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}
.block-card { padding: 0; overflow: hidden; }
.block-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 30px;
  padding: 5px 14px;
  background: linear-gradient(90deg, #0d5c5433, #0d5c5414);
  border-left: 3px solid var(--accent);
  border-bottom: 1px solid var(--border);
}
.block-bar-left { display: flex; align-items: center; gap: 8px; min-width: 0; flex: 1; flex-wrap: wrap; }
.block-bar-title { font-size: 13px; font-weight: 700; letter-spacing: .01em; color: var(--text); }
.block-bar-actions { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: #f5f3f0;
  color: var(--text-2);
  cursor: pointer;
  transition: background .12s, color .12s;
}
.icon-btn:hover { background: var(--accent); color: #fff; }
.desc-view { display: flex; gap: 12px; align-items: flex-start; }
.desc-content { flex: 1; }
.desc-text { font-size: 13px; line-height: 1.5; color: var(--text); white-space: pre-wrap; word-break: break-word; }
.desc-empty { font-size: 13px; color: var(--text-2); font-style: italic; }
.desc-input :deep(.q-field__control) { font-size: 13px; }
.desc-actions { display: flex; gap: 8px; }
.action-btn {
  display: flex;
  align-items: center;
  font-size: 12px;
  font-weight: 600;
  padding: 5px 12px;
  border-radius: 6px;
  border: 1px solid var(--border);
  cursor: pointer;
  transition: background .12s, opacity .12s;
}
.action-btn:disabled { opacity: .45; cursor: default; }
.action-btn--primary { background: var(--accent); color: #fff; border-color: var(--accent); }
.action-btn--primary:not(:disabled):hover { background: #0a4d46; }
.action-btn--ai { background: #f3f0fc; color: #8b5cf6; border-color: #c4b5fd; }
.action-btn--ai:not(:disabled):hover { background: #8b5cf6; color: #fff; }
.action-btn--secondary { background: #f5f3f0; color: var(--text); border-color: var(--border); }
.action-btn--secondary:not(:disabled):hover { background: #ede8e0; }
</style>

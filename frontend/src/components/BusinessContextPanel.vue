<template>
  <div class="biz-ctx-panel panel-card biz-ctx-blockcard">
    <!-- Section header row (accent bar) -->
    <div class="biz-ctx-header biz-ctx-bar">
      <span class="biz-ctx-bar-left">
        <span class="biz-ctx-title">Business Glossary Linkage</span>
        <template v-if="termRef">
          <span class="biz-ctx-term-state" :class="termStateClass">{{ termStateLabel }}</span>
        </template>
      </span>

      <!-- Expand / collapse the linked-term detail -->
      <button v-if="termRef" class="biz-ctx-toggle-btn biz-ctx-bar-toggle" @click="isExpanded = !isExpanded">
        {{ isExpanded ? 'Collapse' : 'Expand' }}
        <q-icon :name="isExpanded ? 'expand_less' : 'expand_more'" size="13px" />
      </button>

      <!-- Dropdown anchor -->
      <div class="biz-ctx-menu-wrap" ref="menuAnchorEl">
        <button class="biz-ctx-link-btn" @click="onLinkageButtonClick">
          <q-icon name="add_link" size="13px" class="q-mr-xs" />
          {{ termRef ? 'Edit Linkage' : 'Add Glossary Linkage' }}
          <q-icon v-if="!termRef" :name="menuOpen ? 'expand_less' : 'expand_more'" size="13px" class="q-ml-xs" />
        </button>

        <!-- Dropdown (shown for unlinked items only) — teleported to <body> so it
             floats above the panel card and can never be clipped by an ancestor's
             overflow:hidden or painted under a later sibling panel-card. -->
        <teleport to="body">
          <transition name="biz-ctx-drop">
            <div v-if="menuOpen && !termRef" ref="dropdownEl" class="biz-ctx-dropdown biz-ctx-dropdown--floating" :style="dropdownStyle">
              <button class="biz-ctx-drop-item" @click="doCreateNew">
                <q-icon name="add_circle_outline" size="14px" class="q-mr-sm" />
                <div>
                  <div class="biz-ctx-drop-label">Create New Linkage</div>
                  <div class="biz-ctx-drop-sub">Open the Glossary new-term form with this element pre-filled</div>
                </div>
              </button>
              <div class="biz-ctx-drop-divider" />
              <button class="biz-ctx-drop-item" @click="doMapExisting">
                <q-icon name="manage_search" size="14px" class="q-mr-sm" />
                <div>
                  <div class="biz-ctx-drop-label">Link to Existing Term</div>
                  <div class="biz-ctx-drop-sub">Search glossary terms and link this element inline</div>
                </div>
              </button>
            </div>
          </transition>
        </teleport>
      </div>

      <!-- Remove Linkage button — only shown when a term is linked -->
      <button v-if="termRef" class="biz-ctx-remove-btn" :disabled="removingLinkage" @click="promptRemoveLinkage" title="Remove Linkage">
        <q-spinner-dots v-if="removingLinkage" size="11px" />
        <q-icon v-else name="link_off" size="14px" />
      </button>
    </div>

    <div class="biz-ctx-content q-pa-md">
    <!-- Inline search panel (Map to Existing) -->
    <transition name="biz-ctx-slide">
      <div v-if="searchMode" class="biz-ctx-search-panel">
        <div class="biz-ctx-search-row">
          <q-icon name="search" size="14px" class="biz-ctx-search-icon" />
          <input
            ref="searchInputEl"
            v-model="searchQuery"
            class="biz-ctx-search-input"
            placeholder="Search glossary terms…"
            autocomplete="off"
            @input="onSearchInput"
          />
          <button class="biz-ctx-search-close" @click="cancelSearch">
            <q-icon name="close" size="13px" />
          </button>
        </div>

        <!-- Results -->
        <div v-if="searchLoading" class="biz-ctx-search-status">
          <q-spinner-dots size="13px" class="q-mr-xs" />Searching…
        </div>
        <div v-else-if="searchQuery.trim() && searchResults.length === 0" class="biz-ctx-search-status">
          No matching terms found.
        </div>
        <div v-else-if="searchResults.length" class="biz-ctx-search-results">
          <div
            v-for="term in searchResults"
            :key="term.id"
            class="biz-ctx-search-result"
          >
            <div class="biz-ctx-result-body">
              <span class="biz-ctx-result-title">{{ term.title }}</span>
              <span v-if="term.domain" class="biz-ctx-result-meta">{{ term.domain }}<template v-if="term.category"> / {{ term.category }}</template></span>
              <span v-if="term.business_description" class="biz-ctx-result-desc">{{ term.business_description }}</span>
            </div>
            <button
              class="biz-ctx-add-btn"
              :disabled="linkingTermId === term.id || term.id === termRef?.id"
              :title="term.id === termRef?.id ? 'Already linked' : '+Add'"
              @click="linkTerm(term)"
            >
              <q-spinner-dots v-if="linkingTermId === term.id" size="10px" class="q-mr-xs" />
              <q-icon v-else-if="term.id === termRef?.id" name="check" size="12px" class="q-mr-xs" />
              <q-icon v-else name="add" size="12px" class="q-mr-xs" />
              {{ linkingTermId === term.id ? 'Linking…' : term.id === termRef?.id ? 'Linked' : '+Add' }}
            </button>
          </div>
        </div>
      </div>
    </transition>

    <!-- Success / failure banner -->
    <transition name="biz-ctx-banner">
      <div v-if="banner" class="biz-ctx-banner" :class="`biz-ctx-banner--${banner.type}`">
        <q-icon :name="banner.type === 'success' ? 'check_circle' : banner.type === 'warn' ? 'warning_amber' : 'error_outline'" size="13px" class="q-mr-xs" />
        <span class="biz-ctx-banner-msg">{{ banner.msg }}</span>
        <template v-if="banner.type === 'warn'">
          <button class="biz-ctx-banner-action biz-ctx-banner-action--danger" @click="doRemoveLinkage">Yes, Remove</button>
          <button class="biz-ctx-banner-action" @click="banner = null">Cancel</button>
        </template>
        <button v-else-if="banner.type === 'success'" class="biz-ctx-refresh-btn" @click="emit('linkage-changed')">Refresh Linkage</button>
      </div>
    </transition>

    <!-- State (a): no linked term -->
    <div v-if="!termRef && !searchMode" class="biz-ctx-empty">
      <q-icon name="link_off" size="14px" class="q-mr-xs" />
      No linked glossary term yet.
    </div>

    <!-- States (b) & (c): term linked -->
    <template v-else-if="termRef">
      <div class="biz-ctx-term-strip q-mb-xs">
        <q-icon name="menu_book" size="13px" class="q-mr-xs biz-ctx-book-icon" />
        <router-link :to="{ name: 'business-glossary', query: { term: termRef.id } }" class="biz-ctx-term-title biz-ctx-term-link">{{ termRef.title }}</router-link>
      </div>

      <div class="biz-ctx-collapsible">
        <div class="biz-ctx-preview-row">
          <span class="biz-ctx-summary-preview">{{ termRef.business_description || 'No business description yet.' }}</span>
        </div>

        <div v-if="isExpanded" class="biz-ctx-body">
          <div class="biz-ctx-slice">
            <div class="biz-ctx-slice-label">Business description</div>
            <div class="biz-ctx-slice-value">{{ termRef.business_description || 'Not yet documented' }}</div>
          </div>
          <div class="biz-ctx-slice">
            <div class="biz-ctx-slice-label">Detailed description</div>
            <div class="biz-ctx-slice-value">{{ termRef.detailed_description || 'Not yet documented' }}</div>
          </div>
          <template v-if="fullTerm">
            <div class="biz-ctx-slice">
              <div class="biz-ctx-slice-label">CRR3 interpretation</div>
              <div class="biz-ctx-slice-value">{{ fullTerm.CRR_context || 'Not yet documented' }}</div>
            </div>
            <div class="biz-ctx-slice">
              <div class="biz-ctx-slice-label">DPM 2.0 interpretation</div>
              <div class="biz-ctx-slice-value">{{ fullTerm.DPM_context || 'Not yet documented' }}</div>
            </div>
            <div class="biz-ctx-slice">
              <div class="biz-ctx-slice-label">Synonyms</div>
              <div v-if="fullTerm.synonyms?.length" class="biz-ctx-slice-value">{{ fullTerm.synonyms.join(', ') }}</div>
              <div v-else class="biz-ctx-slice-value">Not yet documented</div>
            </div>
            <div class="biz-ctx-slice">
              <div class="biz-ctx-slice-label">Tags</div>
              <div v-if="fullTerm.tags?.length" class="biz-ctx-tags">
                <span v-for="tag in fullTerm.tags" :key="tag" class="biz-ctx-tag">{{ tag }}</span>
              </div>
              <div v-else class="biz-ctx-slice-value">Not yet documented</div>
            </div>
          </template>
          <div v-else-if="termLoading" class="biz-ctx-loading">
            <q-spinner-dots size="12px" class="q-mr-xs" />Loading term details…
          </div>
        </div>
      </div>
    </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue';
import { useRouter } from 'vue-router';
import { useGlossaryStore } from 'src/stores/glossaryStore';
import { upsertTerm, getGlossary, getTerm } from 'src/api/glossary';
import type { GlossaryTermRef } from 'src/api/element';
import type { GlossaryTerm } from 'src/types';

const props = defineProps<{
  termRef: GlossaryTermRef | null;
  source?: string;
  schema?: string;
  table?: string;
  column?: string;
}>();
const emit = defineEmits<{
  'report-wrong-mapping': [termId: string | undefined];
  'linkage-changed': [];
}>();

const router = useRouter();
const glossaryStore = useGlossaryStore();
const termLoading = ref(false);
const isExpanded = ref(false);

// ── Menu state ─────────────────────────────────────────────────────────────
const menuOpen = ref(false);
const menuAnchorEl = ref<HTMLElement | null>(null);
const dropdownEl = ref<HTMLElement | null>(null);
const dropdownStyle = ref<{ top: string; left: string }>({ top: '0px', left: '0px' });
const DROPDOWN_WIDTH = 280; // matches .biz-ctx-dropdown min-width

function closeMenu() { menuOpen.value = false; }

/** Compute a viewport-fixed position for the teleported dropdown, right-aligned
 *  under the anchor button and kept clear of the window edges. */
function positionDropdown() {
  const anchor = menuAnchorEl.value;
  if (!anchor) return;
  const rect = anchor.getBoundingClientRect();
  const left = Math.min(Math.max(8, rect.right - DROPDOWN_WIDTH), window.innerWidth - DROPDOWN_WIDTH - 8);
  dropdownStyle.value = { top: `${rect.bottom + 6}px`, left: `${left}px` };
}

function onOutsideInteraction(e: MouseEvent) {
  const target = e.target as Node;
  if (menuAnchorEl.value?.contains(target)) return;
  if (dropdownEl.value?.contains(target)) return;
  closeMenu();
}

watch(menuOpen, async (open) => {
  if (open) {
    await nextTick();
    positionDropdown();
    window.addEventListener('resize', positionDropdown);
    window.addEventListener('scroll', closeMenu, true);
    document.addEventListener('mousedown', onOutsideInteraction);
  } else {
    window.removeEventListener('resize', positionDropdown);
    window.removeEventListener('scroll', closeMenu, true);
    document.removeEventListener('mousedown', onOutsideInteraction);
  }
});

/** Button click: if term already linked, go directly to search (re-link flow).
 *  If no term linked, show the dropdown with both options. */
function onLinkageButtonClick() {
  if (props.termRef) {
    // Already linked — go straight to search so user can swap to a different term
    void doMapExisting();
  } else {
    menuOpen.value = !menuOpen.value;
  }
}

// ── Option (a): Create New ──────────────────────────────────────────────────
function doCreateNew() {
  closeMenu();
  let link: string | undefined;
  if (props.source && props.table && props.column) {
    const schemaTable = props.schema ? `${props.schema}.${props.table}` : props.table;
    link = `source|${props.source}|${schemaTable}.${props.column}`;
  }
  if (props.termRef) {
    void router.push({ name: 'business-glossary', query: { term: props.termRef.id } });
  } else {
    void router.push({ name: 'business-glossary', query: { new: '1', ...(link ? { link } : {}) } });
  }
}

// ── Option (b): Map to Existing ────────────────────────────────────────────
const searchMode = ref(false);
const searchQuery = ref('');
const searchResults = ref<GlossaryTerm[]>([]);
const searchLoading = ref(false);
const allTerms = ref<GlossaryTerm[]>([]);
const searchInputEl = ref<HTMLInputElement | null>(null);
const linkingTermId = ref<string | null>(null);
const banner = ref<{ msg: string; type: 'success' | 'error' | 'warn' } | null>(null);
let bannerTimer: ReturnType<typeof setTimeout> | null = null;

async function doMapExisting() {
  closeMenu();
  searchQuery.value = '';
  searchResults.value = [];
  searchMode.value = true;
  // Pre-load all terms once
  if (allTerms.value.length === 0) {
    searchLoading.value = true;
    try { allTerms.value = await getGlossary(); } catch { /* fallback to empty */ }
    finally { searchLoading.value = false; }
  }
  await nextTick();
  searchInputEl.value?.focus();
}

function onSearchInput() {
  const q = searchQuery.value.trim().toLowerCase();
  if (!q) { searchResults.value = []; return; }
  searchResults.value = allTerms.value.filter(t =>
    t.title.toLowerCase().includes(q) ||
    t.business_description?.toLowerCase().includes(q) ||
    t.domain?.toLowerCase().includes(q)
  ).slice(0, 8);
}

function cancelSearch() {
  searchMode.value = false;
  searchQuery.value = '';
  searchResults.value = [];
}

function showBanner(msg: string, type: 'success' | 'error' | 'warn') {
  banner.value = { msg, type };
  if (bannerTimer) clearTimeout(bannerTimer);
  if (type !== 'warn') bannerTimer = setTimeout(() => { banner.value = null; }, 5000);
}

async function linkTerm(term: GlossaryTerm) {
  if (!props.source || !props.table || !props.column) {
    showBanner('Element information is missing — cannot create linkage.', 'error');
    return;
  }
  linkingTermId.value = term.id;
  const schemaTable = props.schema ? `${props.schema}.${props.table}` : props.table;
  const newRef = `source|${props.source}|${schemaTable}.${props.column}`;
  const existingRefs = term.related_objects ?? [];
  if (existingRefs.includes(newRef)) {
    showBanner(`This element is already linked to "${term.title}".`, 'error');
    linkingTermId.value = null;
    return;
  }
  try {
    await upsertTerm({ ...term, related_objects: [...existingRefs, newRef] });
    await glossaryStore.loadGlossary();
    cancelSearch();
    showBanner(`Successfully linked to "${term.title}".`, 'success');
    emit('linkage-changed');
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : 'Unknown error';
    showBanner(`Failed to create linkage: ${msg}`, 'error');
  } finally {
    linkingTermId.value = null;
  }
}

const removingLinkage = ref(false);

function promptRemoveLinkage() {
  banner.value = {
    msg: `Remove linkage to "${props.termRef?.title}"? This cannot be undone.`,
    type: 'warn',
  };
  if (bannerTimer) clearTimeout(bannerTimer);
  // Don't auto-dismiss the confirmation
}

async function doRemoveLinkage() {
  if (!props.termRef || !props.source || !props.table || !props.column) return;
  removingLinkage.value = true;
  try {
    const term = fullTerm.value ?? await getTerm(props.termRef.id);
    const schemaTable = props.schema ? `${props.schema}.${props.table}` : props.table;
    const refToRemove = `source|${props.source}|${schemaTable}.${props.column}`;
    const updatedRefs = (term.related_objects ?? []).filter(r => r !== refToRemove);
    await upsertTerm({ ...term, related_objects: updatedRefs });
    await glossaryStore.loadGlossary();
    showBanner(`Linkage to "${term.title}" removed.`, 'success');
    emit('linkage-changed');
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : 'Unknown error';
    showBanner(`Failed to remove linkage: ${msg}`, 'error');
  } finally {
    removingLinkage.value = false;
  }
}


// ── Term detail state ──────────────────────────────────────────────────────
const fullTerm = computed(() => {
  const st = glossaryStore.selectedTerm;
  if (!st || !props.termRef || st.id !== props.termRef.id) return null;
  return st;
});

const termStateLabel = computed(() => props.termRef?.status?.trim() || 'State not set');
const termStateClass = computed(() => {
  const s = props.termRef?.status;
  if (!s || !s.trim()) return 'biz-ctx-state--unset';
  if (s === 'approved') return 'biz-ctx-state--ok';
  return 'biz-ctx-state--warn';
});

watch(() => props.termRef?.id, async (id) => {
  isExpanded.value = false;
  if (!id) return;
  termLoading.value = true;
  try { await glossaryStore.loadTerm(id); } finally { termLoading.value = false; }
}, { immediate: true });
</script>

<style scoped>
/* Raise stacking context above sibling panel-cards (backdrop-filter creates one per card) */
.biz-ctx-panel { position: relative; z-index: 1; }

/* Flush accent header bar (matches the other Interpretation decision blocks). */
.biz-ctx-blockcard { padding: 0; overflow: hidden; }
.biz-ctx-bar {
  height: 30px;
  padding: 0 14px;
  margin: 0;
  background: linear-gradient(90deg, #0d5c5433, #0d5c5414);
  border-left: 3px solid var(--accent, #0d5c54);
  border-bottom: 1px solid var(--border, #ddd6c8);
}
/* Compact the in-bar actions so the bar height matches the other blocks. */
.biz-ctx-bar .biz-ctx-link-btn { padding: 2px 9px; }
.biz-ctx-bar .biz-ctx-remove-btn { padding: 2px 6px; }
.biz-ctx-bar-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.biz-ctx-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.biz-ctx-title {
  flex: 0 0 auto;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: .01em;
  color: var(--text, #1c1b18);
}

.biz-ctx-menu-wrap {
  position: relative;
  flex-shrink: 0;
}

.biz-ctx-link-btn {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--accent, #0d5c54);
  background: var(--accent-light, #e6f2f0);
  border: 1px solid transparent;
  border-radius: 6px;
  padding: 4px 10px;
  cursor: pointer;
  white-space: nowrap;
  transition: filter .12s;
}
.biz-ctx-link-btn:hover { filter: brightness(.92); }

/* Dropdown — solid opaque background so it's always readable.
   Teleported to <body> (see template) and positioned via inline style
   computed from the anchor button's bounding rect, so it floats above every
   panel-card instead of being clipped by an ancestor's overflow:hidden or
   painted underneath a later sibling block-card's stacking context. */
.biz-ctx-dropdown--floating {
  position: fixed;
  z-index: 4000;
  min-width: 280px;
  background: #ffffff;
  border: 1px solid var(--border, #ddd6c8);
  border-radius: 10px;
  box-shadow: 0 8px 28px rgba(0,0,0,0.18);
  overflow: hidden;
}
.biz-ctx-drop-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  width: 100%;
  padding: 12px 14px;
  background: none;
  border: none;
  cursor: pointer;
  text-align: left;
  transition: background .12s;
  color: var(--text, #1c1b18);
}
.biz-ctx-remove-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: 1px solid var(--border, #ddd6c8);
  border-radius: 5px;
  padding: 4px 7px;
  cursor: pointer;
  color: var(--danger-col, #9e3326);
  flex-shrink: 0;
  transition: background .12s;
}
.biz-ctx-remove-btn:hover:not(:disabled) { background: #fdecea; }
.biz-ctx-remove-btn:disabled { opacity: .45; cursor: not-allowed; }

.biz-ctx-drop-item:hover { background: var(--accent-light, #e6f2f0); }
.biz-ctx-drop-label { font-size: 12.5px; font-weight: 600; }
.biz-ctx-drop-sub { font-size: 11px; color: var(--text-2, #86827a); margin-top: 2px; line-height: 1.4; }
.biz-ctx-drop-divider { height: 1px; background: var(--border, #ddd6c8); }

/* Search panel */
.biz-ctx-search-panel {
  background: var(--accent-light, #e6f2f0);
  border: 1px solid var(--border, #ddd6c8);
  border-radius: 8px;
  padding: 8px;
  margin-bottom: 10px;
}
.biz-ctx-search-row {
  display: flex;
  align-items: center;
  gap: 6px;
  background: #fff;
  border: 1px solid var(--border, #ddd6c8);
  border-radius: 6px;
  padding: 5px 8px;
}
.biz-ctx-search-icon { color: var(--text-2, #86827a); flex-shrink: 0; }
.biz-ctx-search-input {
  flex: 1;
  border: none;
  outline: none;
  font-size: 12.5px;
  background: transparent;
  color: var(--text, #1c1b18);
}
.biz-ctx-search-close {
  background: none; border: none; cursor: pointer;
  color: var(--text-2, #86827a); padding: 0; display: flex; align-items: center;
}
.biz-ctx-search-close:hover { color: var(--text, #1c1b18); }
.biz-ctx-search-status {
  font-size: 11.5px; color: var(--text-2, #86827a);
  padding: 8px 4px; display: flex; align-items: center;
}
.biz-ctx-search-results { margin-top: 6px; display: flex; flex-direction: column; gap: 4px; }
.biz-ctx-search-result {
  display: flex; align-items: center; gap: 10px;
  background: #fff; border: 1px solid var(--border, #ddd6c8);
  border-radius: 6px; padding: 8px 10px;
}
.biz-ctx-result-body { flex: 1; min-width: 0; }
.biz-ctx-result-title { font-size: 12.5px; font-weight: 600; color: var(--text, #1c1b18); display: block; }
.biz-ctx-result-meta { font-size: 10.5px; color: var(--text-2, #86827a); display: block; margin-top: 1px; }
.biz-ctx-result-desc {
  font-size: 11px; color: var(--text-2, #86827a);
  display: block; margin-top: 2px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 280px;
}
.biz-ctx-add-btn {
  display: inline-flex; align-items: center;
  font-size: 11.5px; font-weight: 700;
  color: var(--accent, #0d5c54);
  background: var(--accent-light, #e6f2f0);
  border: 1px solid transparent; border-radius: 5px;
  padding: 3px 9px; cursor: pointer; white-space: nowrap;
  transition: filter .12s; flex-shrink: 0;
}
.biz-ctx-add-btn:hover:not(:disabled) { filter: brightness(.92); }
.biz-ctx-add-btn:disabled { opacity: .5; cursor: not-allowed; }

/* Banner */
.biz-ctx-banner {
  display: flex; align-items: center;
  font-size: 12px; border-radius: 6px; padding: 7px 10px; margin-bottom: 8px;
}
.biz-ctx-banner--success { background: #e8f5e9; color: #2f6b3a; border: 1px solid #a8d5b0; }
.biz-ctx-banner--error   { background: #fdecea; color: #9e3326; border: 1px solid #f5b8b3; }
.biz-ctx-banner--warn    { background: #fff8e1; color: #7a5800; border: 1px solid #ffe082; }
.biz-ctx-banner-msg { flex: 1; }
.biz-ctx-banner-action {
  margin-left: 8px;
  font-size: 11.5px; font-weight: 700;
  background: none; border: 1px solid currentColor;
  border-radius: 4px; padding: 2px 9px; cursor: pointer; color: inherit; white-space: nowrap;
  flex-shrink: 0;
}
.biz-ctx-banner-action:hover { opacity: .75; }
.biz-ctx-banner-action--danger { background: #9e3326; color: #fff; border-color: #9e3326; }
.biz-ctx-banner-action--danger:hover { opacity: .85; }
.biz-ctx-refresh-btn {
  margin-left: auto;
  font-size: 11.5px;
  font-weight: 700;
  background: none;
  border: 1px solid currentColor;
  border-radius: 4px;
  padding: 2px 8px;
  cursor: pointer;
  color: inherit;
  white-space: nowrap;
  flex-shrink: 0;
}
.biz-ctx-refresh-btn:hover { opacity: .75; }

/* Transitions */
.biz-ctx-drop-enter-active, .biz-ctx-drop-leave-active { transition: opacity .12s, transform .12s; }
.biz-ctx-drop-enter-from, .biz-ctx-drop-leave-to { opacity: 0; transform: translateY(-6px); }
.biz-ctx-slide-enter-active, .biz-ctx-slide-leave-active { transition: opacity .15s, max-height .2s; overflow: hidden; max-height: 400px; }
.biz-ctx-slide-enter-from, .biz-ctx-slide-leave-to { opacity: 0; max-height: 0; }
.biz-ctx-banner-enter-active, .biz-ctx-banner-leave-active { transition: opacity .2s; }
.biz-ctx-banner-enter-from, .biz-ctx-banner-leave-to { opacity: 0; }

.biz-ctx-empty {
  font-size: 12px; color: var(--text-2, #86827a);
  display: flex; align-items: center; gap: 4px;
}
.biz-ctx-term-strip {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
}
.biz-ctx-book-icon { color: var(--accent, #0d5c54); }
.biz-ctx-term-title { font-size: 13px; font-weight: 600; color: var(--text, #1c1b18); }
.biz-ctx-term-link { color: var(--accent, #0d5c54); text-decoration: none; border-bottom: 1px solid transparent; transition: border-color .12s; }
.biz-ctx-term-link:hover { border-bottom-color: var(--accent, #0d5c54); }
.biz-ctx-term-state { font-size: 10.5px; font-weight: 700; border-radius: 4px; padding: 2px 6px; }
.biz-ctx-state--ok { background: #d4edda; color: #2f6b3a; }
.biz-ctx-state--warn { background: #fff3cd; color: #856404; }
.biz-ctx-state--unset { background: var(--border, #ddd6c8); color: var(--text-2, #86827a); }
.biz-ctx-last-updated { font-size: 10.5px; color: var(--text-2, #86827a); }
.biz-ctx-wrong-btn {
  font-size: 10.5px; color: var(--text-2, #86827a); background: none; border: none;
  cursor: pointer; padding: 0; text-decoration: underline; text-decoration-style: dotted;
}
.biz-ctx-wrong-btn:hover { color: var(--danger-col, #b91c1c); }
.biz-ctx-preview-row { display: flex; align-items: flex-start; gap: 8px; }
.biz-ctx-summary-preview { flex: 1; font-size: 13px; color: var(--text, #1c1b18); font-style: italic; }
.biz-ctx-toggle-btn { font-size: 11.5px; color: var(--accent, #0d5c54); background: none; border: none; cursor: pointer; padding: 0; white-space: nowrap; }
.biz-ctx-bar-toggle { display: inline-flex; align-items: center; gap: 2px; flex-shrink: 0; font-weight: 600; }
.biz-ctx-body { margin-top: 14px; display: flex; flex-direction: column; gap: 18px; }
.biz-ctx-slice { padding-bottom: 4px; border-bottom: 1px solid var(--border, #ede8e1); }
.biz-ctx-slice:last-child { border-bottom: none; padding-bottom: 0; }
.biz-ctx-slice-label { font-size: 10.5px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: var(--text-2, #86827a); margin-bottom: 2px; }
.biz-ctx-slice-value { font-size: 12.5px; color: var(--text, #1c1b18); }
.biz-ctx-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.biz-ctx-tag { font-size: 11px; padding: 2px 7px; border-radius: 4px; background: var(--accent-light, #e6f2f0); color: var(--accent, #0d5c54); }
.biz-ctx-loading { font-size: 12px; color: var(--text-2, #86827a); display: flex; align-items: center; }
</style>
  const ts = fullTerm.value?.last_updated;
  if (!ts) return 'Not recorded';
  return new Date(ts).toLocaleDateString(undefined, { dateStyle: 'medium' });
});

// Must be defined before the watches that reference it.
const isPartial = computed(() => {
  if (!props.termRef) return false;
  const ft = fullTerm.value;
  return (
    !props.termRef.business_description ||
    !props.termRef.detailed_description ||
    !ft?.CRR_context ||
    !ft?.DPM_context ||
    !ft?.synonyms?.length
  );
});

watch(
  () => props.termRef?.id,
  async (id) => {
    isExpanded.value = false;
    if (!id) return;
    termLoading.value = true;
    try {
      await glossaryStore.loadTerm(id);
    } finally {
      termLoading.value = false;
    }
  },
  { immediate: true },
);

// Auto-expand when the term is partial so the user sees what's missing.
watch(isPartial, (partial) => {
  if (partial) isExpanded.value = true;
}, { immediate: true });

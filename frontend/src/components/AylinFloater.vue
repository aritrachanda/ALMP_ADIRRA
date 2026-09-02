<template>
  <teleport to="body">
    <template v-if="!isAssistantHome">
      <!-- FAB -->
      <button
        class="assistant-fab"
        :class="{ 'is-dragging': fabDragging }"
        :style="fabStyle"
        :aria-label="`Open ${assistantName} assistant`"
        @pointerdown="onFabPointerDown"
        @pointermove="onFabPointerMove"
        @pointerup="onFabPointerUp"
        @click="onFabClick"
      >
        <span class="assistant-fab-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" width="26" height="26">
            <path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8"/>
          </svg>
        </span>
      </button>

      <!-- Backdrop -->
      <transition name="assistant-fade">
        <div v-if="drawerOpen" class="assistant-backdrop" @click="drawerOpen = false" />
      </transition>

      <!-- Drawer -->
      <transition name="assistant-slide">
        <div
          v-if="drawerOpen"
          ref="drawerEl"
          class="assistant-drawer"
          role="dialog"
          aria-modal="true"
          :aria-label="`${assistantName} assistant`"
          tabindex="-1"
          @keydown="onKeydown"
        >
          <!-- Header -->
          <div class="assistant-dhead">
            <div class="assistant-dava">
              <img
                v-if="personaStore.avatarUrl"
                :src="personaStore.avatarUrl"
                :alt="assistantName"
                class="assistant-dava-img"
              />
              <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" width="17" height="17">
                <path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8"/>
              </svg>
            </div>
            <div class="assistant-dhead-meta">
              <div class="assistant-dhead-name">{{ assistantName }}</div>
              <div class="assistant-dhead-ctx">{{ contextLabel }}</div>
            </div>
            <button class="assistant-dnew" @click="newChat" :disabled="store.loading" aria-label="New chat">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M12 5v14M5 12h14"/></svg>
              New Chat
            </button>
            <button class="assistant-dclose" @click="drawerOpen = false" :aria-label="`Close ${assistantName}`">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><path d="M18 6L6 18M6 6l12 12"/></svg>
            </button>
          </div>

          <!-- Messages -->
          <div class="assistant-dmsgs" ref="msgsEl">
            <div class="assistant-dmsgs-inner">
              <template v-if="store.activeConversation">
                <template v-for="(msg, i) in store.activeConversation.messages" :key="i">
                  <div v-if="msg.role === 'user'" class="assistant-dmsg assistant-dmsg--user">
                    {{ msg.content }}
                  </div>
                  <div v-else class="assistant-dmsg assistant-dmsg--assistant">
                    <div class="assistant-dmd" v-html="renderMarkdown(msg.content)" />
                    <template v-if="store.visualsByIndex[i]?.length">
                      <template v-for="(vis, vi) in store.visualsByIndex[i]" :key="vi">
                        <div v-if="vis.type === 'chart' && vis.spec && vis.data?.length" class="assistant-dchart">
                          <Bar v-if="vis.spec.chart_type === 'bar' || vis.spec.chart_type === 'histogram'" :data="toChartData(vis)" :options="chartOptions(vis)" :style="{ height: '200px' }" />
                          <Line v-else-if="vis.spec.chart_type === 'line'" :data="toChartData(vis)" :options="chartOptions(vis)" :style="{ height: '200px' }" />
                          <Pie v-else-if="vis.spec.chart_type === 'pie'" :data="toPieData(vis)" :options="pieOptions(vis)" :style="{ height: '200px' }" />
                          <Scatter v-else-if="vis.spec.chart_type === 'scatter'" :data="toChartData(vis)" :options="chartOptions(vis)" :style="{ height: '200px' }" />
                        </div>
                        <div v-else-if="vis.type === 'dataframe' && vis.data?.length" class="q-mt-xs">
                          <q-markup-table flat dense separator="horizontal" class="assistant-dtable">
                            <thead><tr><th v-for="col in (vis.columns ?? Object.keys(vis.data[0]))" :key="col" class="text-left">{{ col }}</th></tr></thead>
                            <tbody>
                              <tr v-for="(row, ri) in vis.data.slice(0, 20)" :key="ri">
                                <td v-for="col in (vis.columns ?? Object.keys(vis.data[0]))" :key="col">{{ row[col] }}</td>
                              </tr>
                            </tbody>
                          </q-markup-table>
                        </div>
                        <div v-else-if="vis.type === 'error'" class="assistant-dvis-error">{{ vis.message }}</div>
                      </template>
                    </template>
                  </div>
                </template>
              </template>
              <div v-else class="assistant-dmsg assistant-dmsg--assistant">
                <div class="assistant-dmd" v-html="renderMarkdown(openingMessage)" />
              </div>
              <div v-if="store.loading" class="assistant-dloading">
                <q-spinner-dots color="primary" size="22px" />
              </div>

              <!-- Transient backend/LLM failure — ephemeral, not saved to history. -->
              <div v-if="store.chatError" class="assistant-dmsg assistant-dmsg--assistant">
                <div class="assistant-derror">
                  <div class="assistant-derror-line">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" width="14" height="14"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/></svg>
                    <span>{{ store.chatError.summary }}</span>
                  </div>
                  <details v-if="store.chatError.detail" class="assistant-derror-details">
                    <summary>Technical details</summary>
                    <pre>{{ (store.chatError.status ? '[' + store.chatError.status + '] ' : '') + store.chatError.detail }}</pre>
                  </details>
                </div>
              </div>
            </div>
          </div>

          <!-- Input -->
          <div class="assistant-dinput-wrap">
            <div class="assistant-dinput-box">
              <q-input
                v-model="inputText"
                borderless
                :placeholder="`Ask ${assistantName}…`"
                class="assistant-dinput"
                autogrow
                @keyup.enter.exact="onSend"
              />
              <button
                v-if="store.loading"
                class="assistant-dstop"
                aria-label="Stop generation"
                @click="store.stopGeneration()"
              >
                <svg viewBox="0 0 24 24" fill="currentColor" width="14" height="14"><rect x="4" y="4" width="16" height="16" rx="2"/></svg>
              </button>
              <q-btn
                v-else
                flat round dense
                icon="send"
                size="sm"
                color="primary"
                @click="onSend"
              />
            </div>
            <div class="assistant-dinput-hint">Press <kbd>Esc</kbd> to close — your conversation is saved.</div>
          </div>
        </div>
      </transition>
    </template>
  </teleport>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { useAssistantChatStore } from 'src/stores/assistantChatStore';
import { useElementStore } from 'src/stores/elementStore';
import { usePersonaStore } from 'src/stores/personaStore';
import { useBirdKbStore } from 'src/stores/birdKbStore';
import { ASSISTANT_NAME } from 'src/config/assistant';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { Bar, Line, Pie, Scatter } from 'vue-chartjs';
import {
  Chart as ChartJS,
  CategoryScale, LinearScale, BarElement, LineElement,
  PointElement, ArcElement, Tooltip, Legend,
} from 'chart.js';
import type { ChatVisual } from 'src/api/discovery';

ChartJS.register(CategoryScale, LinearScale, BarElement, LineElement, PointElement, ArcElement, Tooltip, Legend);

const route = useRoute();
const store = useAssistantChatStore();
const elementStore = useElementStore();
const personaStore = usePersonaStore();
const birdKbStore = useBirdKbStore();

// Load persona once so name/avatar are fresh
onMounted(() => personaStore.loadPersona());

// Use persona name reactively; fall back to compile-time constant
const assistantName = computed(() => personaStore.name || ASSISTANT_NAME);

const drawerOpen = ref(false);
const inputText = ref('');
const drawerEl = ref<HTMLElement | null>(null);
const msgsEl = ref<HTMLElement | null>(null);

const isAssistantHome = computed(() => !!route.meta?.isAssistantHome);

const contextLabel = computed(() => {
  const el = elementStore.element;
  if (el) {
    const name = el.business_name || el.column;
    return `${name} — ${el.table}`;
  }
  const title = route.meta?.title;
  return typeof title === 'string' && title ? title : 'ADIRRA';
});

const openingMessage = computed(() => {
  const el = elementStore.element;
  const routeTitle = typeof route.meta?.title === 'string' ? route.meta.title : '';

  if (el) {
    const name = el.business_name || el.column;
    const table = el.table;
    return `Hi! I can see you're looking at **${name}** in *${table}*. I can explain what this element means, check its governance status, show how it maps to BIRD, or dig into the data — just ask.`;
  }

  const byPage: Record<string, string> = {
    'Asset Workspace': `Hi! You're in the Asset Workspace. I can explain elements, check governance and approval status, look at data profiles, or help draft definitions — what would you like to explore?`,
    'Business Glossary': `Hi! You're browsing the Business Glossary. I can help you find terms, explain or draft definitions, and show how terms link to physical data columns.`,
    'Data Catalog': `Hi! You're in the Data Catalog. I can search datasets, explore column metadata, check governance coverage, or explain what a dataset is used for.`,
    'Discovery': `Hi! You're in Smart Data Insights. I can run queries, create charts, surface data patterns, or cross-reference your findings with regulatory context.`,
    'Mapping': `Hi! You're on the Mapping page. I can explain BIRD mappings, review confidence scores, identify unmapped columns, or clarify what a target model concept means.`,
    'Dashboard': `Hi! You're on the Dashboard. I can explain any metric here, help you understand governance coverage, or suggest what to focus on next.`,
    'Audit Log': `Hi! You're in the Audit Log. I can help you find specific events, explain what an action means, or summarise recent governance activity.`,
    'Settings': `Hi! I can explain any configuration option here or help you understand what different settings do — just ask.`,
    'About': `Hi! You're on the About page. I can walk you through how ADIRRA works, explain what each module does, describe the AI agents behind the scenes, or answer any questions about the platform architecture — just ask.`,
    'Chat': `Hi! I can answer questions about your data, mappings, glossary, or anything ADIRRA-related. What's on your mind?`,
    'BIRD': `Hi! You're in the BIRD Knowledge Base. I can explain any entity, variable, domain, or transformation rule you're looking at — just ask. You can also ask me to navigate to a specific entity or layer.`,
    'Data Standards Glossary': `Hi! You're in the Data Standards Glossary. I can help you find terms, explain definitions, or show how terms link to physical data elements.`,
    'Reference Data': `Hi! You're in Reference Data. I can explain any code list, domain, or enumerated value you're viewing.`,
    'BIRD Mapping': `Hi! You're in the BIRD Mapping workspace. I can explain mapping concepts, review candidate target attributes, or help clarify what a BIRD LDM entity means.`,
    'Regulatory': `Hi! You're in the Regulatory Knowledge Base. I can help you find regulatory guidance or explain AnaCredit reporting requirements.`,
  };

  return byPage[routeTitle]
    ?? `Hi! I'm ${assistantName.value}, your AI assistant for ADIRRA. Ask me anything about your data, mappings, glossary, or this page.`;
});

async function newChat() {
  await store.createConversation();
  inputText.value = '';
  await nextTick();
  if (msgsEl.value) msgsEl.value.scrollTop = 0;
}

function buildContext(): string | undefined {
  const el = elementStore.element;
  const routeTitle = route.meta?.title;
  const pageLabel = typeof routeTitle === 'string' && routeTitle ? routeTitle : 'ADIRRA';
  const parts: string[] = [`The user is currently on the ${pageLabel} page.`];

  // BIRD KB context
  if (pageLabel === 'BIRD') {
    const ctx = birdKbStore.pageContext;
    const layerDesc: Record<string, string> = {
      LDM:  'Logical Data Model — canonical business concepts (primary mapping target)',
      ELDM: 'Extended LDM — enriched input layer',
      IL:   'Input Layer — WUDEN reshape from LDM',
      EIL:  'Extended Input Layer — DER derivations',
      ROL:  'Regulatory Output Layer — final AnaCredit output',
    };

    parts.push(
      'IMPORTANT: The user is in the BIRD Knowledge Base — a read-only structural REFERENCE MODEL ' +
      'for regulatory reporting (LDM / ELDM / IL / EIL / ROL). ' +
      'BIRD entities are business concepts defined by the ECB SMCube framework. ' +
      'They are NOT source database tables or schemas. ' +
      'When answering BIRD questions, use the search_bird_entity and get_bird_entity_detail tools — ' +
      'do NOT query source databases (E_INPUT, DWH, or any source schema) for BIRD entity answers.',
    );
    parts.push(`Active layer: ${ctx.layer} (${layerDesc[ctx.layer] ?? ctx.layer}).`);
    if (ctx.framework && ctx.framework !== 'All') {
      parts.push(`Framework filter: ${ctx.framework}.`);
    }

    if (ctx.entity_id) {
      parts.push(`The user is viewing BIRD entity '${ctx.entity_name}' (ID: ${ctx.entity_id}).`);
      // Include attribute summary if detail is loaded
      const detail = birdKbStore.entityDetail;
      if (detail) {
        if (detail.description) parts.push(`Entity description: ${detail.description}`);
        const keyFields = detail.attributes
          .filter((a) => a.role === 'D')
          .map((a) => `${a.variable_code} (${a.domain_name})`)
          .slice(0, 6).join(', ');
        const reportedVals = detail.attributes
          .filter((a) => a.role === 'O')
          .map((a) => `${a.variable_code} (${a.domain_name})`)
          .slice(0, 8).join(', ');
        const aCount = detail.attributes.filter((a) => a.role === 'A').length;
        if (keyFields) parts.push(`Key fields (D-role): ${keyFields}.`);
        if (reportedVals) parts.push(`Reported values (O-role): ${reportedVals}.`);
        if (aCount) parts.push(`Qualifiers (A-role): ${aCount} attributes.`);
      }
    } else if (ctx.group_name) {
      parts.push(`The user is browsing entity group '${ctx.group_name}'.`);
    } else {
      parts.push(`The user is browsing the ${ctx.layer} layer.`);
    }
    return parts.join(' ');
  }

  // BIRD Mapping workspace context (Regulatory Workspace module)
  if (pageLabel === 'BIRD Mapping') {
    parts.push('They are in the BIRD Mapping workspace, mapping source fields to BIRD LDM target attributes (Semantic Type deduction, steward review and approval).');
    return parts.join(' ');
  }

  // Element-level context (Asset Workspace — column selected)
  if (el) {
    const elementName = el.business_name || el.column;
    const datasetName = el.table;
    if (elementName && datasetName) {
      parts.push(`They are viewing element '${elementName}' (column: '${el.column}') in dataset '${datasetName}' from source '${el.source}'.`);
      if (el.lifecycle_state) parts.push(`Lifecycle state: ${el.lifecycle_state}.`);
      if (el.dq?.state === 'scored') parts.push(`Data quality: ${el.dq.dq_score} · ${el.dq.grade_label}.`);
      if (el.schema) parts.push(`Schema: ${el.schema}.`);
    }
    return parts.join(' ');
  }

  // Dataset-level context (Asset Workspace — dataset selected, no column)
  const overview = elementStore.datasetOverview;
  if (overview && pageLabel === 'Asset Workspace') {
    parts.push(`They are viewing the dataset '${overview.table_name}' in source '${overview.source}' (schema: ${overview.schema}).`);
    parts.push(`Dataset has ${overview.column_count} columns and ${overview.row_count?.toLocaleString() ?? '?'} rows.`);
    const gov = overview.governance_state;
    if (gov) {
      parts.push(`Governance state: ${gov.approved ?? 0} approved, ${gov.defined ?? 0} defined, ${gov.draft ?? 0} draft.`);
    }
    return parts.join(' ');
  }

  // Source-level context (Asset Workspace — source selected, no dataset)
  const srcInfo = elementStore.sourceInfo;
  if (srcInfo && pageLabel === 'Asset Workspace') {
    parts.push(`They are viewing source '${srcInfo.source}' which has ${srcInfo.table_count} datasets and ${srcInfo.column_count} columns.`);
    const gov = srcInfo.governance_state;
    if (gov) {
      parts.push(`Governance state: ${gov.approved ?? 0} approved, ${gov.defined ?? 0} defined, ${gov.draft ?? 0} draft.`);
    }
    return parts.join(' ');
  }

  return parts.join(' ');
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
  return {
    labels: rows.map(r => String(r[x] ?? '')),
    datasets: [{
      label: vis.spec?.title ?? y,
      data: rows.map(r => Number(r[y]) || 0),
      backgroundColor: PALETTE,
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
    datasets: [{ data: rows.map(r => Number(r[y]) || 0), backgroundColor: PALETTE }],
  };
}

function chartOptions(vis: ChatVisual) {
  return {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { display: false }, tooltip: { enabled: true } },
    scales: {
      x: { grid: { display: false }, title: { display: !!vis.spec?.x, text: vis.spec?.x ?? '' } },
      y: { beginAtZero: true, grid: { color: '#f0f0f0' }, title: { display: !!vis.spec?.y, text: vis.spec?.y ?? '' } },
    },
  };
}

function pieOptions(_vis: ChatVisual) {
  return {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { position: 'bottom' as const, labels: { boxWidth: 10 } }, tooltip: { enabled: true } },
  };
}

async function onSend() {
  const text = inputText.value.trim();
  if (!text || store.loading) return;
  inputText.value = '';
  await store.sendMessage(text, buildContext());
  await nextTick();
  scrollToBottom();
}

function scrollToBottom() {
  if (msgsEl.value) msgsEl.value.scrollTop = msgsEl.value.scrollHeight;
}

watch(() => store.activeConversation?.messages?.length, () => {
  nextTick(() => scrollToBottom());
});

watch(drawerOpen, (open) => {
  if (open) nextTick(() => drawerEl.value?.focus());
});

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') { drawerOpen.value = false; return; }
  if (e.key === 'Tab') {
    const focusable = drawerEl.value?.querySelectorAll<HTMLElement>(
      'button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])',
    );
    if (!focusable?.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }
}

// ── Draggable FAB ────────────────────────────────────────────────────
const FAB_SIZE = 56;
const FAB_MIN_MARGIN = 12;

// -1 = not yet pinned; CSS bottom/right defaults take effect
const fabX = ref(-1);
const fabY = ref(-1);
const fabDragging = ref(false);

// Drag gesture bookkeeping (no reactivity needed)
let _ds = { x: 0, y: 0, fx: 0, fy: 0 };

const fabStyle = computed(() =>
  fabX.value < 0
    ? {}
    : { position: 'fixed' as const, left: `${fabX.value}px`, top: `${fabY.value}px`, right: 'auto', bottom: 'auto' },
);

function _initFabPos() {
  if (fabX.value < 0) {
    // Materialise the CSS default (bottom-right) as concrete pixel coords
    fabX.value = window.innerWidth  - FAB_SIZE - 28;
    fabY.value = window.innerHeight - FAB_SIZE - 28;
  }
}

function onFabPointerDown(e: PointerEvent) {
  _initFabPos();
  _ds = { x: e.clientX, y: e.clientY, fx: fabX.value, fy: fabY.value };
  fabDragging.value = false;
  (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
}

function onFabPointerMove(e: PointerEvent) {
  if (!(e.currentTarget as HTMLElement).hasPointerCapture(e.pointerId)) return;
  const dx = e.clientX - _ds.x;
  const dy = e.clientY - _ds.y;
  if (!fabDragging.value && Math.hypot(dx, dy) < 5) return;
  fabDragging.value = true;
  e.preventDefault(); // prevent scroll on mobile while dragging
  const maxX = window.innerWidth  - FAB_SIZE - FAB_MIN_MARGIN;
  const maxY = window.innerHeight - FAB_SIZE - FAB_MIN_MARGIN;
  fabX.value = Math.max(FAB_MIN_MARGIN, Math.min(maxX, _ds.fx + dx));
  fabY.value = Math.max(50 + FAB_MIN_MARGIN, Math.min(maxY, _ds.fy + dy)); // 50 = navbar height
}

function onFabPointerUp(e: PointerEvent) {
  (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
  // Keep fabDragging true long enough for the click event (fires just after pointerup) to see it
  setTimeout(() => { fabDragging.value = false; }, 80);
}

function onFabClick() {
  if (fabDragging.value) return; // was a drag, not a tap
  drawerOpen.value = !drawerOpen.value;
}
</script>

<style scoped lang="scss">
.assistant-fab {
  position: fixed;
  bottom: 28px;
  right: 28px;
  z-index: 200;
  width: 56px;
  height: 56px;
  border-radius: 18px;
  border: none;
  cursor: grab;
  touch-action: none;  /* required: lets pointer-move fire without being swallowed by scroll */
  user-select: none;
  background: linear-gradient(135deg, #0d5c54, #0a4a44);
  box-shadow: 0 6px 28px -4px #0d5c5444;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  padding: 0;
  transition: transform 0.15s ease, box-shadow 0.15s ease;

  &:not(.is-dragging):hover {
    transform: scale(1.08);
    box-shadow: 0 10px 32px -4px #0d5c5466;
  }

  &.is-dragging {
    cursor: grabbing;
    transform: scale(1.06);
    box-shadow: 0 14px 40px -4px #0d5c5466;
    transition: none; /* no easing while user is actively moving it */
  }

  @media (max-width: 767px) {
    bottom: calc(56px + 16px);
    right: 16px;
  }
}

.assistant-fab-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
}

.assistant-backdrop {
  position: fixed;
  inset: 0;
  z-index: 201;
  background: rgba(0, 0, 0, 0.25);
}

.assistant-fade-enter-active, .assistant-fade-leave-active { transition: opacity 0.2s ease; }
.assistant-fade-enter-from, .assistant-fade-leave-to { opacity: 0; }

.assistant-drawer {
  position: fixed;
  top: 50px;
  right: 0;
  bottom: 0;
  z-index: 202;
  width: 420px;
  max-width: 100vw;
  background: var(--adirra-paper);
  border-left: 1px solid var(--adirra-line);
  box-shadow: -2px 0 20px -8px rgba(0, 0, 0, 0.3);
  display: flex;
  flex-direction: column;
  outline: none;

  @media (max-width: 767px) { width: 100vw; }
}

.assistant-slide-enter-active, .assistant-slide-leave-active { transition: transform 0.22s ease; }
.assistant-slide-enter-from, .assistant-slide-leave-to { transform: translateX(100%); }

.assistant-dhead {
  height: 60px;
  min-height: 60px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 14px;
  border-bottom: 1px solid var(--adirra-line);
  background: var(--adirra-card);
  flex-shrink: 0;
}

.assistant-dava {
  width: 32px;
  height: 32px;
  border-radius: 10px;
  background: linear-gradient(135deg, #0d5c54, #0a4a44);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: #fff;
  overflow: hidden;
}

.assistant-dava-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 10px;
}

.assistant-dhead-meta { flex: 1; min-width: 0; }

.assistant-dhead-name {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--adirra-ink);
  line-height: 1.2;
}

.assistant-dhead-ctx {
  font-size: 11px;
  color: var(--adirra-ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.3;
}

.assistant-dnew {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: none;
  border: 1px solid var(--adirra-line);
  border-radius: 6px;
  padding: 4px 9px;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--adirra-ink-2);
  cursor: pointer;
  flex-shrink: 0;
  transition: background 0.12s, color 0.12s;

  &:hover:not(:disabled) { background: var(--adirra-line); color: var(--adirra-ink); }
  &:disabled { opacity: .45; cursor: not-allowed; }
}

.assistant-dclose {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--adirra-ink-2);
  padding: 4px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background 0.12s;

  &:hover { background: var(--adirra-line); }
}

.assistant-dmsgs {
  flex: 1;
  overflow-y: auto;
  padding: 16px 14px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.assistant-dmsgs-inner {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.assistant-dmsg {
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 12.5px;
  line-height: 1.55;
  word-break: break-word;
}

.assistant-dmsg--assistant {
  background: var(--adirra-accent-soft);
  border: 1px solid var(--adirra-accent);
  color: var(--adirra-ink);
}

.assistant-dmsg--user {
  background: var(--adirra-card);
  border: 1px solid var(--adirra-line);
  color: var(--adirra-ink);
  align-self: flex-end;
  max-width: 85%;
}

.assistant-dempty {
  color: var(--adirra-ink-3);
  font-size: 13px;
  text-align: center;
  padding: 48px 0 0;
}

.assistant-dloading { display: flex; padding: 4px 0; }

.assistant-dvis-error { font-size: 11px; color: var(--adirra-danger); margin-top: 4px; }

.assistant-derror {
  border: 1px solid #f3c6c0;
  background: #fdf3f2;
  border-radius: 8px;
  padding: 8px 10px;
}
.assistant-derror-line {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 12.5px;
  color: #8a2c22;
  line-height: 1.4;
}
.assistant-derror-line svg { flex: 0 0 auto; margin-top: 1px; }
.assistant-derror-details { margin-top: 6px; }
.assistant-derror-details > summary {
  cursor: pointer;
  font-size: 11px;
  font-weight: 600;
  color: #a24b3f;
  user-select: none;
}
.assistant-derror-details > pre {
  margin: 6px 0 0;
  padding: 8px;
  background: #fff;
  border: 1px solid #f0d5d0;
  border-radius: 6px;
  font-size: 11px;
  color: #6b6862;
  white-space: pre-wrap;
  word-break: break-word;
}

.assistant-dchart {
  margin-top: 8px;
  background: white;
  border: 1px solid #eee;
  border-radius: 8px;
  padding: 8px;
}

.assistant-dtable { font-size: 11px; }

.assistant-dmd {
  :deep(p) { margin: 0 0 8px; &:last-child { margin-bottom: 0; } }
  :deep(ul), :deep(ol) { margin: 0 0 8px; padding-left: 20px; }
  :deep(li) { margin-bottom: 2px; }
  :deep(code) { background: var(--adirra-paper-2); padding: 1px 4px; border-radius: 3px; font-size: 11.5px; }
  :deep(pre) { background: var(--adirra-paper-2); border-radius: 6px; padding: 8px 10px; overflow-x: auto; margin: 0 0 8px; code { background: none; padding: 0; } }
  :deep(h1), :deep(h2), :deep(h3), :deep(h4) { margin: 10px 0 5px; color: var(--adirra-ink); font-size: 13px; }
  :deep(table) { border-collapse: collapse; margin: 0 0 8px; font-size: 11.5px; th, td { border: 1px solid var(--adirra-line); padding: 4px 8px; } th { background: var(--adirra-paper-2); font-weight: 600; } }
  :deep(blockquote) { border-left: 3px solid var(--adirra-accent); margin: 0 0 8px; padding: 2px 10px; color: var(--adirra-ink-2); }
  :deep(strong) { font-weight: 600; }
}

.assistant-dinput-wrap {
  padding: 10px 14px 16px;
  flex-shrink: 0;
  border-top: 1px solid var(--adirra-line);
  background: var(--adirra-card);
}

.assistant-dinput-box {
  border: 1px solid var(--adirra-accent);
  border-radius: 10px;
  background: var(--adirra-paper);
  padding: 6px 10px 8px;
  display: flex;
  align-items: flex-end;
  gap: 4px;
}

.assistant-dstop {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  border: none;
  background: var(--adirra-danger, #c0392b);
  color: #fff;
  cursor: pointer;
  flex-shrink: 0;
  transition: opacity .15s;
}
.assistant-dstop:hover { opacity: .85; }

.assistant-dinput-hint {
  margin-top: 7px;
  font-size: 10.5px;
  color: var(--adirra-ink-3);
  text-align: center;

  kbd {
    display: inline-block;
    font: inherit;
    font-size: 10px;
    font-weight: 600;
    color: var(--adirra-ink-2);
    background: var(--adirra-paper-2);
    border: 1px solid var(--adirra-line);
    border-radius: 4px;
    padding: 1px 5px;
    letter-spacing: 0.02em;
  }
}

.assistant-dinput {
  flex: 1;
  :deep(.q-field__control) { min-height: 22px; }
  :deep(.q-field__native) { font-size: 13px; color: var(--adirra-ink); padding: 0; }
}
</style>

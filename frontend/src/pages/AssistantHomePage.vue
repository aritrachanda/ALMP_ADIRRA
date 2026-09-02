<template>
  <q-page class="ahp-root">
    <!-- History rail -->
    <div class="ahp-rail" :class="{ 'ahp-rail--collapsed': railCollapsed }">
      <div class="ahp-rail-top">
        <button class="ahp-newbtn" @click="newChat">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="15" height="15"><path d="M12 5v14M5 12h14"/></svg>
          <span class="ahp-newbtn-label">New chat</span>
        </button>
        <button class="ahp-rail-toggle" :aria-label="railCollapsed ? 'Expand history' : 'Collapse history'" :title="railCollapsed ? 'Expand' : 'Collapse'" @click="railCollapsed = !railCollapsed">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="15" height="15"><path d="M15 18l-6-6 6-6"/></svg>
        </button>
      </div>

      <div v-if="!railCollapsed" class="ahp-hist-list">
        <template v-if="store.conversations.length">
          <div class="ahp-hist-sect">Recent</div>
          <div
            v-for="convo in store.conversations"
            :key="convo.id"
            class="ahp-hist-item"
            :class="{ 'ahp-hist-item--on': store.activeConversation?.id === convo.id }"
            @click="selectConvo(convo.id)"
          >
            <div class="ahp-hi-body">
              <div class="ahp-hi-title">{{ convo.title || 'Untitled' }}</div>
              <div class="ahp-hi-time">{{ relTime(convo.created_at) }}</div>
            </div>
            <button class="ahp-hi-del" aria-label="Delete conversation" title="Delete" @click.stop="store.removeConversation(convo.id)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13"><path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/></svg>
            </button>
          </div>
        </template>
        <div v-else class="ahp-hist-sect">No conversations yet</div>
      </div>
    </div>

    <!-- Main chat column -->
    <div class="ahp-main">
      <div class="ahp-scroll" ref="scrollEl">
        <div class="ahp-inner">

          <!-- Empty state: hero + orientation + caps + try -->
          <template v-if="!store.activeConversation">
            <!-- Hero -->
            <div class="ahp-hero">
              <div class="ahp-avatar">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" width="38" height="38">
                  <path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8"/>
                </svg>
              </div>
              <h1 class="ahp-hero-h1">Meet <em>{{ assistantName }}</em></h1>
              <div class="ahp-hero-intro" v-html="greetingHtml" />
              <button class="ahp-customize-link" @click="openPersonaSettings">
                Customize {{ assistantName }}
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
              </button>
            </div>

            <!-- Orientation banner -->
            <div class="ahp-starthere" @click="askAboutApp">
              <div class="ahp-ash-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="21" height="21"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>
              </div>
              <div class="ahp-ash-body">
                <div class="ahp-ash-title">New here? Let {{ assistantName }} show you around</div>
                <div class="ahp-ash-desc">Get a plain-language tour of what ADIRRA does, its modules, and how a typical workflow flows from data onboarding to a compliant submission.</div>
              </div>
              <div class="ahp-ash-cta">
                Explain the app
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
              </div>
            </div>

            <!-- Capability cards -->
            <div class="ahp-caps">
              <div v-for="card in capabilityCards" :key="card.title" class="ahp-cap" @click="card.action">
                <div class="ahp-cap-icon" :style="{ background: card.iconBg, color: card.iconColor }">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18" v-html="card.icon" />
                </div>
                <h3 class="ahp-cap-title">{{ card.title }}</h3>
                <p class="ahp-cap-desc">{{ card.desc }}</p>
                <span class="ahp-cap-link">
                  {{ card.link }}
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
                </span>
              </div>
            </div>

            <!-- Example prompts -->
            <div class="ahp-try">
              <div class="ahp-try-label">Example prompts</div>
              <div class="ahp-chips">
                <button
                  v-for="prompt in examplePrompts"
                  :key="prompt"
                  class="ahp-chip"
                  :disabled="store.loading"
                  @click="seedPrompt(prompt)"
                >{{ prompt }}</button>
              </div>
            </div>
          </template>

          <!-- Active conversation -->
          <template v-else>
            <!-- Back to landing -->
            <div class="ahp-back-row">
              <button class="ahp-back" @click="store.clearActiveConversation()">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M19 12H5M12 5l-7 7 7 7"/></svg>
                Home
              </button>
            </div>

            <div class="ahp-msgs">

              <template v-for="(msg, i) in store.activeConversation.messages" :key="i">
                <!-- Inject greeting bubble before the first assistant message -->
                <div v-if="msg.role === 'assistant' && store.activeConversation.messages.findIndex(m => m.role === 'assistant') === i" class="ahp-msg ahp-msg--assistant">
                  <div class="ahp-msg-ava">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" width="16" height="16">
                      <path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8"/>
                    </svg>
                  </div>
                  <div class="ahp-msg-body">
                    <div class="ahp-msg-sender">{{ assistantName }}</div>
                    <div class="ahp-msg-txt" v-html="chatWelcomeHtml" />
                  </div>
                </div>
                <div class="ahp-msg" :class="msg.role === 'user' ? 'ahp-msg--user' : 'ahp-msg--assistant'">
                  <div class="ahp-msg-ava">
                    <template v-if="msg.role === 'user'">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                    </template>
                    <template v-else>
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" width="16" height="16"><path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8"/></svg>
                    </template>
                  </div>
                  <div class="ahp-msg-body">
                    <div class="ahp-msg-sender">{{ msg.role === 'user' ? 'You' : assistantName }}</div>
                    <div class="ahp-msg-txt">
                      <template v-if="msg.role === 'user'">{{ msg.content }}</template>
                      <div v-else class="ahp-md" v-html="renderMarkdown(msg.content)" />
                    </div>
                    <!-- Charts / visuals -->
                    <template v-if="msg.role !== 'user' && store.visualsByIndex[i]?.length">
                      <template v-for="(vis, vi) in store.visualsByIndex[i]" :key="vi">
                        <div v-if="vis.type === 'chart' && vis.spec && vis.data?.length" class="ahp-chart">
                          <Bar v-if="vis.spec.chart_type === 'bar' || vis.spec.chart_type === 'histogram'" :data="toChartData(vis)" :options="chartOptions(vis)" :style="{ height: '200px' }" />
                          <Line v-else-if="vis.spec.chart_type === 'line'" :data="toChartData(vis)" :options="chartOptions(vis)" :style="{ height: '200px' }" />
                          <Pie v-else-if="vis.spec.chart_type === 'pie'" :data="toPieData(vis)" :options="pieOptions(vis)" :style="{ height: '200px' }" />
                          <Scatter v-else-if="vis.spec.chart_type === 'scatter'" :data="toChartData(vis)" :options="chartOptions(vis)" :style="{ height: '200px' }" />
                        </div>
                        <div v-else-if="vis.type === 'dataframe' && vis.data?.length" class="q-mt-xs">
                          <q-markup-table flat dense separator="horizontal" class="ahp-table">
                            <thead><tr><th v-for="col in (vis.columns ?? Object.keys(vis.data[0]))" :key="col" class="text-left">{{ col }}</th></tr></thead>
                            <tbody>
                              <tr v-for="(row, ri) in vis.data.slice(0, 20)" :key="ri">
                                <td v-for="col in (vis.columns ?? Object.keys(vis.data[0]))" :key="col">{{ row[col] }}</td>
                              </tr>
                            </tbody>
                          </q-markup-table>
                        </div>
                        <div v-else-if="vis.type === 'error'" class="ahp-vis-error">{{ vis.message }}</div>
                      </template>
                    </template>
                  </div>
                </div>
              </template>

              <!-- Optimistic pending user message (shown before API responds) -->
              <div v-if="pendingUserMsg && !store.activeConversation?.messages?.some(m => m.role === 'user')" class="ahp-msg ahp-msg--user">
                <div class="ahp-msg-ava">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                </div>
                <div class="ahp-msg-body">
                  <div class="ahp-msg-sender">You</div>
                  <div class="ahp-msg-txt">{{ pendingUserMsg }}</div>
                </div>
              </div>

              <!-- Contextual quick links (shown after first completed response) -->
              <div v-if="quickLinks.length" class="ahp-quick-links">
                <div class="ahp-ql-label">Continue exploring</div>
                <div class="ahp-chips">
                  <button v-for="link in quickLinks" :key="link.label" class="ahp-chip" @click="link.action()">
                    {{ link.label }}
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="11" height="11"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
                  </button>
                </div>
              </div>

              <!-- Greeting during first exchange (before any assistant message arrives) —
                   delayed a beat so the typing animation plays first, not instantly. -->
              <div v-if="store.loading && showGreetingBubble && !store.activeConversation?.messages?.some(m => m.role === 'assistant')" class="ahp-msg ahp-msg--assistant">
                <div class="ahp-msg-ava">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" width="16" height="16"><path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8"/></svg>
                </div>
                <div class="ahp-msg-body">
                  <div class="ahp-msg-sender">{{ assistantName }}</div>
                  <div class="ahp-msg-txt" v-html="chatWelcomeHtml" />
                </div>
              </div>

              <div v-if="store.loading" class="ahp-msg ahp-msg--assistant">
                <div class="ahp-msg-ava">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" width="16" height="16"><path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8"/></svg>
                </div>
                <div class="ahp-msg-body">
                  <div class="ahp-msg-sender">{{ assistantName }}</div>
                  <div class="ahp-typing">
                    <span class="ahp-tdot" /><span class="ahp-tdot" /><span class="ahp-tdot" />
                  </div>
                </div>
              </div>

              <!-- Transient backend/LLM failure — ephemeral, not saved to history. -->
              <div v-if="store.chatError" class="ahp-msg ahp-msg--assistant">
                <div class="ahp-msg-ava ahp-msg-ava--err">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" width="16" height="16"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/></svg>
                </div>
                <div class="ahp-msg-body">
                  <div class="ahp-msg-sender">{{ assistantName }}</div>
                  <div class="ahp-chat-error">
                    <div class="ahp-chat-error-line">{{ store.chatError.summary }}</div>
                    <details v-if="store.chatError.detail" class="ahp-chat-error-details">
                      <summary>Technical details</summary>
                      <pre>{{ (store.chatError.status ? '[' + store.chatError.status + '] ' : '') + store.chatError.detail }}</pre>
                    </details>
                  </div>
                </div>
              </div>
            </div>
          </template>

        </div>
      </div>

      <!-- Pinned input bar -->
      <div class="ahp-inputwrap">
        <div class="ahp-inputinner">
          <input
            id="ahp-chat-input"
            ref="inputEl"
            v-model="inputText"
            class="ahp-input"
            :placeholder="`Ask ${assistantName} anything about your data…`"
            autocomplete="off"
            :disabled="store.loading"
            @keyup.enter.exact="onSend"
          />
          <button
            v-if="store.loading"
            class="ahp-stop"
            aria-label="Stop generation"
            @click="store.stopGeneration()"
          >
            <svg viewBox="0 0 24 24" fill="currentColor" width="14" height="14"><rect x="4" y="4" width="16" height="16" rx="2"/></svg>
          </button>
          <button
            v-else
            class="ahp-send"
            :aria-label="`Send message to ${assistantName}`"
            :disabled="!inputText.trim()"
            @click="onSend"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><path d="M22 2L11 13"/><path d="M22 2L15 22l-4-9-9-4z"/></svg>
          </button>
        </div>
      </div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { useAssistantChatStore } from 'src/stores/assistantChatStore';
import { usePersonaStore } from 'src/stores/personaStore';
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

const _personaStore = usePersonaStore();
onMounted(() => _personaStore.loadPersona());
const assistantName = computed(() => _personaStore.name || ASSISTANT_NAME);

const store = useAssistantChatStore();
const router = useRouter();

const railCollapsed = ref(true);
const inputText = ref('');
const scrollEl = ref<HTMLElement | null>(null);
const inputEl = ref<HTMLInputElement | null>(null);
const pendingUserMsg = ref<string | null>(null);

// The canned greeting line ('On it! ...') is deliberately held back for a beat so the
// typing-dot animation reads as "thinking" first, instead of both appearing at once.
const GREETING_DELAY_MS = 1800;
const showGreetingBubble = ref(false);
let greetingTimer: ReturnType<typeof setTimeout> | null = null;

const greetingHtml = computed(() => `Hello! I'm <b>${assistantName.value}</b>, your AI assistant across the data governance lifecycle. I'm connected to all modules — Catalog, Glossary, Insights, and Mapping. I can answer questions about your data, draft definitions, explain BIRD mappings, and show contextual visualisations right here in the conversation.<br><br>Try one of the prompts below, or ask me anything.`);

function topicGreeting(userText: string): string {
  const t = userText.toLowerCase();
  if (/glossar|term|definition|meaning/.test(t))
    return 'Happy to help with your glossary question! Let me look that up for you.';
  if (/map|bird|crdm|corep|finrep|regulat|submiss/.test(t))
    return 'Great question about data mapping! Looking into the details for you now.';
  if (/catalog|asset|dataset|column|table|schema|field/.test(t))
    return 'Sure — let me explore the data catalog and find what you need.';
  if (/insight|visuali|chart|graph|distribut|statistic|analytic/.test(t))
    return 'Happy to dig into the data insights! Pulling that together now.';
  if (/explain|what is|how does|what does|tell me|show me|describe/.test(t))
    return 'Great question — let me explain that for you right away.';
  if (/how many|count|total|number of|list/.test(t))
    return 'On it! Let me work that out for you.';
  return 'On it! Give me a moment to look that up.';
}

const chatWelcomeHtml = computed(() => {
  const text = store.activeConversation?.messages.find(m => m.role === 'user')?.content
    ?? pendingUserMsg.value
    ?? '';
  if (text) return topicGreeting(text);
  return `Hi! I'm <b>${assistantName.value}</b>. Ask me anything about your data.`;
});

// computed (not a plain array) so the assistant-name interpolations below
// stay correct if persona.yaml loads asynchronously after this component's
// initial setup (loadPersona() runs in onMounted, i.e. after this would
// otherwise have been evaluated once with the not-yet-loaded fallback name).
const capabilityCards = computed(() => [
  {
    icon: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    iconBg: 'var(--adirra-accent-soft)', iconColor: 'var(--adirra-accent)',
    title: 'Asset Workspace',
    desc: 'Your home for exploring datasets — profiles, definitions, semantic types and the lifecycle of every data element from ingestion through to release.',
    link: 'Explore the workspace',
    action: () => router.push('/workspace'),
  },
  {
    icon: '<path d="M4 4v15a1 1 0 001 1h14V6a2 2 0 00-2-2H6a2 2 0 00-2 0z"/><path d="M4 19a2 2 0 012-2h13"/>',
    iconBg: 'var(--adirra-reviewed-soft)', iconColor: 'var(--adirra-reviewed)',
    title: 'Business Glossary',
    desc: 'Explore business terms and their meanings, and see how each concept links down to the physical elements that carry it across your sources.',
    link: 'See how it works',
    action: () => seedPrompt('How does the Business Glossary link terms to physical elements?'),
  },
  {
    icon: '<path d="M12 2l7 4v6c0 5-3.5 8.5-7 10-3.5-1.5-7-5-7-10V6z"/><path d="M9 12l2 2 4-4"/>',
    iconBg: 'var(--adirra-released-soft)', iconColor: 'var(--adirra-released)',
    title: 'Data Quality Insights',
    desc: 'See how ADIRRA scores completeness, uniqueness and validity for every element — understand what drives a DQ grade, spot at-risk datasets, and see how findings feed governance decisions.',
    link: `Ask ${assistantName.value}`,
    action: () => seedPrompt('How is data quality scored and what drives an element\'s DQ grade?'),
  },
  {
    icon: '<path d="M5 12h14M13 6l6 6-6 6"/>',
    iconBg: 'var(--adirra-draft-soft)', iconColor: 'var(--adirra-draft)',
    title: 'BIRD Knowledge Base',
    desc: 'Explore BIRD regulatory concepts, attribute definitions, and validation rules — ask how any data element maps to the BIRD model and what is needed to make it eligible.',
    link: 'Explore BIRD',
    action: () => seedPrompt('What is the BIRD model and how do my datasets map to it?'),
  },
]);

const quickLinks = computed(() => {
  const msgs = store.activeConversation?.messages;
  if (!msgs || msgs.length < 2 || store.loading) return [];
  const text = msgs.map(m => m.content).join(' ').toLowerCase();
  const links: Array<{ label: string; action: () => void }> = [];
  if (/glossar|term|definition/.test(text))
    links.push({ label: 'Open Business Glossary', action: () => router.push({ name: 'business-glossary' }) });
  if (/asset|catalog|dataset|column|table|schema/.test(text))
    links.push({ label: 'Browse Asset Workspace', action: () => router.push('/workspace') });
  if (/map|bird|crdm|corep|finrep/.test(text))
    links.push({ label: 'Explore Data Mapping', action: () => router.push('/workspace/mapping') });
  return links.slice(0, 3);
});


const examplePrompts = [
  'What is ADIRRA and how do I use it?',
  'What is the governance state of my datasets?',
  'Which columns still need definitions or glossary links?',
  'What BIRD attributes do my datasets map to?',
];

function relTime(ts: string | number | undefined): string {
  if (!ts) return '';
  const d = Date.now() - new Date(ts).getTime();
  const m = Math.floor(d / 60000);
  const h = Math.floor(d / 3600000);
  const days = Math.floor(d / 86400000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  if (h < 24) return `${h}h ago`;
  if (days < 7) return `${days}d ago`;
  return new Date(ts).toLocaleDateString();
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

function scrollToBottom() {
  if (scrollEl.value) scrollEl.value.scrollTop = scrollEl.value.scrollHeight;
}

async function selectConvo(id: string) {
  await store.selectConversation(id);
  await nextTick();
  scrollToBottom();
}

function newChat() {
  store.clearActiveConversation();
  inputText.value = '';
  nextTick(() => inputEl.value?.focus());
}

function seedPrompt(text: string) {
  inputText.value = text;
  nextTick(() => inputEl.value?.focus());
}

function askAboutApp() {
  void onSendText('What is ADIRRA and how do I use it?');
}

function openPersonaSettings() {
  void router.push({ path: '/system/settings', query: { tab: 'ai-persona' } });
}

async function onSendText(text: string) {
  if (!text || store.loading) return;
  inputText.value = '';
  pendingUserMsg.value = text;
  showGreetingBubble.value = false;
  if (greetingTimer) clearTimeout(greetingTimer);
  greetingTimer = setTimeout(() => { showGreetingBubble.value = true; }, GREETING_DELAY_MS);
  const context = `The user is on the ADIRRA Home page (${assistantName.value} assistant home). They have full access to Asset Workspace, Business Glossary, Smart Data Insights, Data Mapping, Dashboard, and Audit Log.`;
  await store.sendMessage(text, context);
  if (greetingTimer) { clearTimeout(greetingTimer); greetingTimer = null; }
  showGreetingBubble.value = false;
  pendingUserMsg.value = null;
  await nextTick();
  scrollToBottom();
}

async function onSend() {
  const text = inputText.value.trim();
  await onSendText(text);
}

watch(() => store.activeConversation?.messages?.length, () => {
  nextTick(() => scrollToBottom());
});

onMounted(async () => {
  if (scrollEl.value) scrollEl.value.scrollTop = 0;
  await store.loadConversations();
  inputEl.value?.focus();
});
</script>

<style scoped lang="scss">
.ahp-root {
  display: flex;
  flex-direction: row;
  height: calc(100vh - 50px); /* 50px = q-toolbar default height */
  min-height: 0 !important;   /* override Quasar's inline min-height */
  overflow: hidden;
  background: var(--adirra-paper);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* History rail */
.ahp-rail {
  flex: 0 0 260px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: linear-gradient(180deg, #c2d8ea 0%, #d0e2ee 25%, #deeaf2 50%, #e8edf0 75%, #efeae0 100%);
  border-right: 1px solid var(--adirra-line);
  transition: flex-basis 0.22s ease;

  &--collapsed {
    flex-basis: 58px;
  }
}

.ahp-rail-top {
  padding: 14px 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  border-bottom: 1px solid var(--adirra-line);
  flex-shrink: 0;
}

.ahp-newbtn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  font: inherit;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--adirra-accent);
  background: var(--adirra-card);
  border: 1px solid var(--adirra-accent);
  border-radius: 9px;
  padding: 9px 12px;
  cursor: pointer;
  transition: background 0.12s;
  white-space: nowrap;
  overflow: hidden;

  &:hover { background: var(--adirra-accent-soft); }

  .ahp-rail--collapsed & {
    padding: 9px 0;
  }
}

.ahp-newbtn-label {
  .ahp-rail--collapsed & { display: none; }
}

.ahp-rail-toggle {
  width: 34px;
  height: 34px;
  flex: 0 0 auto;
  border-radius: 8px;
  border: 1px solid var(--adirra-line);
  background: var(--adirra-card);
  color: var(--adirra-ink-2);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: border-color 0.12s, color 0.12s;

  svg { transition: transform 0.22s; }

  &:hover { border-color: var(--adirra-accent); color: var(--adirra-accent); }

  .ahp-rail--collapsed & svg { transform: rotate(180deg); }
}

.ahp-hist-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.ahp-hist-sect {
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--adirra-ink-3);
  font-weight: 600;
  padding: 10px 10px 6px;
}

.ahp-hist-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 10px;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 2px;
  transition: background 0.12s;

  &:hover { background: var(--adirra-accent-soft); }

  &--on {
    background: var(--adirra-accent-soft);
    box-shadow: inset 3px 0 0 var(--adirra-accent);
  }

  &:hover .ahp-hi-del { opacity: 1; }
}

.ahp-hi-body { flex: 1; min-width: 0; }

.ahp-hi-title {
  font-size: 12.5px;
  font-weight: 500;
  color: var(--adirra-ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ahp-hi-time {
  font-size: 10.5px;
  color: var(--adirra-ink-3);
  margin-top: 1px;
}

.ahp-hi-del {
  opacity: 0;
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  color: var(--adirra-ink-3);
  cursor: pointer;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  transition: background 0.12s, color 0.12s, opacity 0.12s;

  &:hover { background: var(--adirra-danger-soft); color: var(--adirra-danger); }
}

/* Main chat column */
.ahp-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
  background: radial-gradient(ellipse 110% 55% at 50% 0%, #b8d4ec 0%, #d4e6f2 28%, #e8f0f7 50%, #f6f3ec 75%);
}

.ahp-scroll {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.ahp-inner {
  width: 100%;
  max-width: 820px;
  margin: 0 auto;
  padding: 0 32px;
  display: flex;
  flex-direction: column;
  flex: 1;
}

/* Hero */
.ahp-hero {
  padding: 18px 0 20px;
  text-align: center;
}

.ahp-avatar {
  width: 72px;
  height: 72px;
  border-radius: 22px;
  background: linear-gradient(135deg, #0d5c54, #0a4a44);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 6px;
  box-shadow: 0 6px 24px -6px #0d5c5444;
  color: #fff;
}

.ahp-hero-h1 {
  font-family: 'IBM Plex Serif', serif;
  font-size: 30px;
  font-weight: 600;
  letter-spacing: -0.02em;
  margin-bottom: 4px;
  color: var(--adirra-ink);

  em { color: var(--adirra-accent); font-style: normal; }
}

.ahp-hero-sub {
  font-size: 14.5px;
  color: var(--adirra-ink-2);
  max-width: 560px;
  margin: 0 auto 6px;
  line-height: 1.6;
}

.ahp-hero-sub2 {
  font-size: 12px;
  color: var(--adirra-ink-3);
  max-width: 480px;
  margin: 0 auto;
  line-height: 1.6;
}

/* Orientation banner */
.ahp-starthere {
  display: flex;
  align-items: center;
  gap: 15px;
  padding: 16px 18px;
  margin-bottom: 22px;
  border-radius: 14px;
  cursor: pointer;
  background: linear-gradient(135deg, var(--adirra-accent-soft), transparent);
  border: 1px solid var(--adirra-accent);
  transition: box-shadow 0.15s, transform 0.1s;

  &:hover {
    box-shadow: 0 4px 18px -5px #0d5c5433;
    transform: translateY(-1px);
  }

  @media (max-width: 680px) {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }
}

.ahp-ash-icon {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background: linear-gradient(135deg, #0d5c54, #0a4a44);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
}

.ahp-ash-body { flex: 1; min-width: 0; }

.ahp-ash-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--adirra-ink);
  margin-bottom: 3px;
}

.ahp-ash-desc {
  font-size: 12px;
  color: var(--adirra-ink-2);
  line-height: 1.5;
}

.ahp-ash-cta {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--adirra-accent);
  white-space: nowrap;

  svg { transition: transform 0.15s; }
  .ahp-starthere:hover & svg { transform: translateX(3px); }
}

/* Capability cards */
.ahp-caps {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  padding: 0 0 26px;

  @media (max-width: 900px) { grid-template-columns: repeat(2, 1fr); }
}

.ahp-cap {
  display: flex;
  flex-direction: column;
  background: var(--adirra-card);
  border: 1px solid var(--adirra-line);
  border-radius: 14px;
  padding: 16px 15px;
  box-shadow: var(--adirra-shadow);
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s, transform 0.1s;

  &:hover {
    border-color: var(--adirra-accent);
    box-shadow: 0 4px 16px -4px #0d5c5422;
    transform: translateY(-1px);

    .ahp-cap-link svg { transform: translateX(2px); }
  }
}

.ahp-cap-icon {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 11px;
  flex-shrink: 0;
}

.ahp-cap-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 5px;
  color: var(--adirra-ink);
}

.ahp-cap-desc {
  font-size: 11.5px;
  color: var(--adirra-ink-2);
  line-height: 1.5;
  margin-bottom: 11px;
  flex: 1;
}

.ahp-cap-link {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--adirra-accent);
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: auto;

  svg { transition: transform 0.15s; }
}

/* Example prompts */
.ahp-try {
  padding: 4px 0 20px;
}

.ahp-try-label {
  font-size: 10.5px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--adirra-ink-3);
  font-weight: 600;
  margin-bottom: 9px;
}

.ahp-chips {
  display: flex;
  gap: 7px;
  flex-wrap: wrap;
}

.ahp-chip {
  font: inherit;
  font-size: 12px;
  font-weight: 500;
  color: var(--adirra-accent);
  background: var(--adirra-card);
  border: 1px solid var(--adirra-line);
  border-radius: 20px;
  padding: 7px 14px;
  cursor: pointer;
  transition: border-color 0.12s, background 0.12s, color 0.12s;
  box-shadow: var(--adirra-shadow);

  &:hover { border-color: var(--adirra-accent); background: var(--adirra-accent-soft); color: var(--adirra-ink); }
  &:disabled { opacity: 0.4; cursor: not-allowed; }
}

/* Messages */
.ahp-msgs {
  padding: 24px 0 10px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  flex: 1;
}

.ahp-msg {
  display: flex;
  gap: 12px;
  animation: ahp-fade 0.25s ease;
}

@keyframes ahp-fade {
  from { opacity: 0; transform: translateY(5px); }
  to { opacity: 1; transform: none; }
}

.ahp-msg-ava {
  width: 30px;
  height: 30px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  margin-top: 2px;

  .ahp-msg--user & { background: var(--adirra-paper-2); color: var(--adirra-ink-2); }
  .ahp-msg--assistant & { background: linear-gradient(135deg, #0d5c54, #0a4a44); color: #fff; }
}

.ahp-msg-body { flex: 1; min-width: 0; }

.ahp-msg-sender {
  font-size: 11px;
  font-weight: 600;
  color: var(--adirra-ink-3);
  margin-bottom: 4px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.ahp-msg-txt {
  font-size: 13.5px;
  color: var(--adirra-ink);
  line-height: 1.6;
  background: var(--adirra-card);
  border: 1px solid var(--adirra-line);
  border-radius: 10px;
  padding: 11px 13px;
  word-break: break-word;

  .ahp-msg--assistant & {
    background: var(--adirra-accent-soft);
    border-color: var(--adirra-accent);
  }
}

.ahp-md {
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

/* Typing indicator */
.ahp-typing {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 4px 0;
}

.ahp-tdot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--adirra-accent);
  animation: ahp-blink 1.2s infinite;
  display: block;

  &:nth-child(2) { animation-delay: 0.2s; }
  &:nth-child(3) { animation-delay: 0.4s; }
}

@keyframes ahp-blink {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 1; }
}

/* Charts */
.ahp-chart {
  margin-top: 8px;
  background: white;
  border: 1px solid #eee;
  border-radius: 8px;
  padding: 8px;
}

.ahp-table { font-size: 11px; }
.ahp-vis-error { font-size: 11px; color: var(--adirra-danger); margin-top: 4px; }

.ahp-msg-ava--err { background: #fdecea; color: var(--adirra-danger); }
.ahp-chat-error {
  border: 1px solid #f3c6c0;
  background: #fdf3f2;
  border-radius: 8px;
  padding: 8px 10px;
}
.ahp-chat-error-line { font-size: 13px; color: #8a2c22; line-height: 1.4; }
.ahp-chat-error-details { margin-top: 6px; }
.ahp-chat-error-details > summary {
  cursor: pointer;
  font-size: 11px;
  font-weight: 600;
  color: #a24b3f;
  user-select: none;
}
.ahp-chat-error-details > pre {
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

/* Input bar */
.ahp-inputwrap {
  flex: 0 0 auto;
  border-top: 1px solid var(--adirra-line);
  background: rgba(246, 243, 236, 0.85);
  backdrop-filter: blur(10px);
}

.ahp-inputinner {
  max-width: 820px;
  margin: 0 auto;
  padding: 14px 32px;
  display: flex;
  align-items: center;
  gap: 10px;
}

.ahp-input {
  flex: 1;
  font: inherit;
  font-size: 13.5px;
  padding: 11px 15px;
  border: 1px solid var(--adirra-line);
  border-radius: 11px;
  background: var(--adirra-paper);
  color: var(--adirra-ink);
  outline: none;
  transition: border-color 0.12s, box-shadow 0.12s;

  &::placeholder { color: var(--adirra-ink-3); }

  &:focus {
    border-color: var(--adirra-accent);
    box-shadow: 0 0 0 3px var(--adirra-accent-soft);
    background: var(--adirra-card);
  }

  &:disabled { opacity: 0.6; cursor: not-allowed; }
}

.ahp-send {
  width: 40px;
  height: 40px;
  border-radius: 11px;
  border: none;
  background: linear-gradient(135deg, #0d5c54, #0a4a44);
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  transition: filter 0.12s;

  &:hover:not(:disabled) { filter: brightness(1.12); }
  &:disabled { opacity: 0.4; cursor: not-allowed; filter: none; }
}
.ahp-back-row {
  padding: 16px 0 4px;
}

.ahp-back {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  color: var(--adirra-ink-3);
  background: none;
  border: none;
  cursor: pointer;
  padding: 5px 8px;
  border-radius: 7px;
  transition: background 0.12s, color 0.12s;

  &:hover {
    background: var(--adirra-accent-soft);
    color: var(--adirra-accent);
  }
}

.ahp-hero-intro {
  font-size: 13.5px;
  color: var(--adirra-ink-2);
  max-width: 720px;
  margin: 4px auto 0;
  line-height: 1.65;
  text-align: center;

  :deep(b) { color: var(--adirra-ink); font-weight: 600; }
}

.ahp-customize-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: 10px;
  padding: 0;
  border: none;
  background: none;
  font: inherit;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--adirra-accent);
  cursor: pointer;

  svg { transition: transform 0.15s; }
  &:hover svg { transform: translateX(2px); }
}

/* Quick links */
.ahp-quick-links {
  padding: 6px 0 4px;
}

.ahp-ql-label {
  font-size: 10.5px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--adirra-ink-3);
  font-weight: 600;
  margin-bottom: 8px;
}

.ahp-stop {
  width: 40px;
  height: 40px;
  border-radius: 11px;
  border: 1px solid var(--adirra-line);
  background: var(--adirra-card);
  color: var(--adirra-danger);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  transition: background 0.12s, border-color 0.12s;

  &:hover { background: var(--adirra-danger-soft); border-color: var(--adirra-danger); }
}

</style>

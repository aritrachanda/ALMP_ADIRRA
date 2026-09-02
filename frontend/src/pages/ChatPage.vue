<template>
  <q-page class="q-pa-sm" style="display: flex; height: calc(100vh - 50px); gap: 4px;">
    <!-- Previous conversations panel -->
    <div class="conversations-panel">
      <div class="conversations-header">
        <span class="conversations-title">Previous conversations</span>
        <q-icon name="chevron_left" size="18px" color="grey-7" class="cursor-pointer" />
      </div>

      <div class="q-px-sm q-pb-sm">
        <q-input
          v-model="searchQuery"
          dense
          outlined
          placeholder="Search"
          class="search-input"
        >
          <template #append>
            <q-icon name="search" size="16px" color="grey-6" />
          </template>
        </q-input>
      </div>

      <div class="conversations-list">
        <div
          v-for="c in filteredConversations"
          :key="c.id"
          :class="['conversation-item', { 'conversation-item--active': chatStore.activeConversation?.id === c.id }]"
          @click="chatStore.selectConversation(c.id)"
        >
          <span class="conversation-item-title">{{ c.title }}</span>
          <q-btn
            flat round dense
            icon="delete"
            size="xs"
            color="grey-5"
            class="conversation-delete-btn"
            @click.stop="chatStore.removeConversation(c.id)"
          />
        </div>
      </div>
    </div>

    <!-- Chat area -->
    <div class="chat-panel">
      <!-- Action bar -->
      <div class="chat-action-bar">
        <q-btn
          flat dense no-caps
          icon="add"
          label="New conversation"
          class="new-convo-btn"
          @click="onNewConversation"
        />
      </div>

      <!-- Hero state when no active conversation -->
      <div v-if="!chatStore.activeConversation" class="hero-state col column items-center justify-center">
        <q-icon name="chat" size="64px" color="grey-4" class="q-mb-md" />
        <div class="text-h5 text-grey-8 q-mb-lg">How can I help you?</div>
        <div class="row q-gutter-sm">
          <q-chip
            v-for="suggestion in suggestions"
            :key="suggestion"
            clickable
            outline
            color="primary"
            text-color="primary"
            @click="onSuggestionClick(suggestion)"
          >
            {{ suggestion }}
          </q-chip>
        </div>
      </div>

      <!-- Active conversation -->
      <template v-else>
        <!-- Conversation title -->
        <div class="chat-title">
          {{ chatStore.activeConversation.title || 'New conversation' }}
        </div>

        <!-- Messages -->
        <div class="chat-messages" ref="messagesContainer">
          <div class="chat-messages-inner">
            <template
              v-for="(msg, i) in chatStore.activeConversation.messages"
              :key="i"
            >
              <!-- User message -->
              <div v-if="msg.role === 'user'" class="user-message-row">
                <div class="user-bubble">{{ msg.content }}</div>
              </div>

              <!-- Assistant message -->
              <div v-else class="assistant-message">
                <div class="assistant-text" v-html="renderMarkdown(msg.content)" />
                <!-- Charts attached to this message -->
                <template v-if="chatStore.visualsByIndex[i]?.length">
                  <template v-for="(vis, vi) in chatStore.visualsByIndex[i]" :key="vi">
                    <div v-if="vis.type === 'chart' && vis.spec && vis.data?.length" class="chart-wrapper q-mt-sm">
                      <Bar v-if="vis.spec.chart_type === 'bar' || vis.spec.chart_type === 'histogram'" :data="toChartData(vis)" :options="chartOptions(vis)" :style="{height: '260px'}" />
                      <Line v-else-if="vis.spec.chart_type === 'line'" :data="toChartData(vis)" :options="chartOptions(vis)" :style="{height: '260px'}" />
                      <Pie v-else-if="vis.spec.chart_type === 'pie'" :data="toPieData(vis)" :options="pieOptions(vis)" :style="{height: '260px'}" />
                      <Scatter v-else-if="vis.spec.chart_type === 'scatter'" :data="toChartData(vis)" :options="chartOptions(vis)" :style="{height: '260px'}" />
                    </div>
                    <div v-else-if="vis.type === 'dataframe' && vis.data?.length" class="q-mt-sm">
                      <q-markup-table flat dense separator="horizontal" class="data-table">
                        <thead><tr><th v-for="col in (vis.columns ?? Object.keys(vis.data[0]))" :key="col" class="text-left">{{ col }}</th></tr></thead>
                        <tbody>
                          <tr v-for="(row, ri) in vis.data.slice(0, 50)" :key="ri">
                            <td v-for="col in (vis.columns ?? Object.keys(vis.data[0]))" :key="col" class="text-caption">{{ row[col] }}</td>
                          </tr>
                        </tbody>
                      </q-markup-table>
                    </div>
                    <div v-else-if="vis.type === 'error'" class="text-caption text-negative q-mt-xs">{{ vis.message }}</div>
                  </template>
                </template>
              </div>
            </template>

            <div v-if="chatStore.loading" class="q-pa-md">
              <q-spinner-dots color="primary" size="32px" />
            </div>
          </div>
        </div>
      </template>

      <!-- Chat input (always visible) -->
      <div class="chat-input-wrapper">
        <div class="chat-input-box">
          <q-input
            v-model="messageInput"
            borderless
            placeholder="Type a message..."
            class="chat-input"
            autogrow
            @keyup.enter.exact="onSend"
          />
          <div class="chat-input-actions">
            <q-icon name="add" size="16px" color="grey-7" class="cursor-pointer" />
            <q-space />
            <q-btn
              flat round dense
              icon="send"
              size="sm"
              color="primary"
              @click="onSend"
              :loading="chatStore.loading"
            />
          </div>
        </div>
      </div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick, watch } from 'vue';
import { useChatStore } from 'src/stores/chatStore';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { Bar, Line, Pie, Scatter } from 'vue-chartjs';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  ArcElement,
  Tooltip,
  Legend,
} from 'chart.js';
import type { ChatVisual } from 'src/api/discovery';

ChartJS.register(CategoryScale, LinearScale, BarElement, LineElement, PointElement, ArcElement, Tooltip, Legend);

const chatStore = useChatStore();
const searchQuery = ref('');
const messageInput = ref('');
const messagesContainer = ref<HTMLElement | null>(null);

const suggestions = [
  'What tables are in my banking dataset?',
  'Explain the BIRD data model',
  'Help me map counterparties',
  'What is credit quality step?',
];

const filteredConversations = computed(() => {
  const q = searchQuery.value.toLowerCase();
  if (!q) return chatStore.conversations;
  return chatStore.conversations.filter(c => c.title.toLowerCase().includes(q));
});

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
      x: { grid: { display: false }, title: { display: true, text: vis.spec?.x ?? '' } },
      y: { beginAtZero: true, grid: { color: '#f0f0f0' }, title: { display: true, text: vis.spec?.y ?? '' } },
    },
  };
}

function pieOptions(_vis: ChatVisual) {
  return {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { position: 'bottom' as const, labels: { boxWidth: 10 } }, tooltip: { enabled: true } },
  };
}

async function onNewConversation() {
  await chatStore.createConversation();
}

async function onSuggestionClick(text: string) {
  const convo = await chatStore.createConversation();
  if (convo) {
    messageInput.value = text;
    await onSend();
  }
}

async function onSend() {
  const text = messageInput.value.trim();
  if (!text) return;
  messageInput.value = '';
  await chatStore.sendMessage(text);
  await nextTick();
  scrollToBottom();
}

function scrollToBottom() {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight;
  }
}

watch(() => chatStore.activeConversation?.messages?.length, () => {
  nextTick(() => scrollToBottom());
});

onMounted(() => {
  chatStore.loadConversations();
});
</script>

<style scoped lang="scss">
.conversations-panel {
  width: 280px;
  min-width: 280px;
  background: #fdfdfd;
  border-radius: 10px 10px 0 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.conversations-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 8px 12px 16px;
}

.conversations-title {
  font-weight: 700;
  font-size: 14px;
  color: #2b2a31;
}

.search-input {
  :deep(.q-field__control) {
    border-radius: 5px;
    border-color: #0d4da1;
    height: 28px;
    min-height: 28px;
  }
  :deep(.q-field__native) {
    font-size: 14px;
    padding: 0 8px;
    color: #2b2a31;
  }
}

.conversations-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 8px;
}

.conversation-item {
  display: flex;
  align-items: center;
  padding: 4px;
  border-radius: 4px;
  cursor: pointer;
  margin-bottom: 2px;

  &:hover {
    background: #f0f0f0;
  }

  &--active {
    background: #e9f3ff;
  }
}

.conversation-item-title {
  flex: 1;
  font-size: 14px;
  color: #2b2a31;
  line-height: 18px;
  letter-spacing: -0.08px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conversation-delete-btn {
  opacity: 0;
  .conversation-item:hover & {
    opacity: 1;
  }
}

.chat-panel {
  flex: 1;
  background: #fdfdfd;
  border-radius: 10px 10px 0 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

.chat-title {
  font-weight: 700;
  font-size: 20px;
  color: #2b2a31;
  letter-spacing: -0.08px;
  padding: 12px 20px 8px 28px;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 0 28px 20px 28px;
}

.chat-messages-inner {
  max-width: 100%;
  display: flex;
  flex-direction: column;
  gap: 24px;
  justify-content: flex-end;
  min-height: 100%;
  padding-bottom: 24px;
}

.user-message-row {
  display: flex;
  justify-content: flex-end;
  padding-top: 12px;
  padding-bottom: 8px;
}

.user-bubble {
  background: #e9f3ff;
  color: #000;
  font-weight: 500;
  font-size: 16px;
  line-height: normal;
  padding: 8px 12px;
  border-radius: 5px 5px 0 5px;
  max-width: 70%;
  word-break: break-word;
}

.assistant-message {
  max-width: 600px;
  padding: 12px;
}

.assistant-text {
  font-size: 16px;
  color: #2b2a31;
  line-height: normal;
  letter-spacing: -0.08px;

  :deep(p) {
    margin: 0 0 12px 0;
    &:last-child {
      margin-bottom: 0;
    }
  }

  :deep(ul), :deep(ol) {
    margin: 0 0 12px 0;
    padding-left: 24px;
  }

  :deep(li) {
    margin-bottom: 4px;
  }

  :deep(code) {
    background: #f0f0f0;
    padding: 1px 4px;
    border-radius: 3px;
    font-size: 14px;
  }

  :deep(pre) {
    background: #f5f5f5;
    border-radius: 6px;
    padding: 12px;
    overflow-x: auto;
    margin: 0 0 12px 0;

    code {
      background: none;
      padding: 0;
    }
  }

  :deep(h1), :deep(h2), :deep(h3), :deep(h4) {
    margin: 16px 0 8px 0;
    color: #2b2a31;
  }

  :deep(table) {
    border-collapse: collapse;
    margin: 0 0 12px 0;

    th, td {
      border: 1px solid #ddd;
      padding: 6px 10px;
      text-align: left;
    }
    th {
      background: #f5f5f5;
      font-weight: 600;
    }
  }

  :deep(blockquote) {
    border-left: 3px solid #0d4da1;
    margin: 0 0 12px 0;
    padding: 4px 12px;
    color: #555;
  }

  :deep(strong) {
    font-weight: 600;
  }
}

.chart-wrapper {
  background: white;
  border: 1px solid #eee;
  border-radius: 8px;
  padding: 12px;
  max-width: 500px;
}

.data-table {
  max-width: 600px;
  font-size: 12px;

  th {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    color: #94a3b8;
  }
}

.chat-action-bar {
  display: flex;
  align-items: center;
  padding: 4px 20px 12px 20px;
}

.new-convo-btn {
  background: rgba(13, 77, 161, 0.25);
  border-radius: 10px;
  color: #fefefe;
  font-size: 16px;
  padding: 4px 16px 4px 8px;
  letter-spacing: -0.08px;
}

.hero-state {
  flex: 1;
}

.chat-input-wrapper {
  padding: 0 28px 20px 28px;
}

.chat-input-box {
  border: 0.4px solid #0d4da1;
  border-radius: 10px;
  background: #fdfdfd;
  padding: 8px 16px 12px 16px;
  display: flex;
  flex-direction: column;
}

.chat-input {
  :deep(.q-field__control) {
    min-height: 24px;
  }
  :deep(.q-field__native) {
    font-size: 16px;
    color: #2b2a31;
    padding: 0;
  }
}

.chat-input-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
</style>

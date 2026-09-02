import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { ConversationSummary, Conversation } from 'src/types';
import type { ChatVisual } from 'src/api/discovery';
import type { ChatError } from 'src/api/chat';
import * as api from 'src/api/chat';

// NOTE: conversations are loaded from the backend API.
// localStorage persistence is a mock-level stand-in; in production this
// is replaced entirely by the backend conversation store.
export const useAssistantChatStore = defineStore('assistantChat', () => {
  const conversations = ref<ConversationSummary[]>([]);
  const activeConversation = ref<Conversation | null>(null);
  const loading = ref(false);
  const visualsByIndex = ref<Record<number, ChatVisual[]>>({});
  // Transient (not persisted) — a failed turn's friendly error, cleared on the next action.
  const chatError = ref<ChatError | null>(null);
  let _abort: AbortController | null = null;

  async function loadConversations() {
    try {
      conversations.value = await api.listConversations();
    } catch (e) {
      console.error('assistantChat loadConversations failed:', e);
    }
  }

  async function createConversation() {
    const convo = await api.createConversation();
    await loadConversations();
    activeConversation.value = convo;
    chatError.value = null;
    return convo;
  }

  async function selectConversation(id: string) {
    activeConversation.value = await api.getConversation(id);
    visualsByIndex.value = {};
    chatError.value = null;
  }

  function clearActiveConversation() {
    activeConversation.value = null;
    visualsByIndex.value = {};
    chatError.value = null;
  }

  function stopGeneration() {
    _abort?.abort();
    _abort = null;
    loading.value = false;
  }

  async function sendMessage(content: string, context?: string) {
    if (!activeConversation.value) {
      await createConversation();
    }
    if (!activeConversation.value) return;
    _abort = new AbortController();
    loading.value = true;
    chatError.value = null;

    // Optimistically show the user message immediately so the UI updates
    // before the API round-trip completes.
    activeConversation.value = {
      ...activeConversation.value,
      messages: [
        ...activeConversation.value.messages,
        { role: 'user', content },
      ],
    };

    try {
      const result = await api.sendMessage(activeConversation.value.id, content, context, _abort.signal);
      if (result.error) {
        // Keep the optimistic user message; surface the failure transiently.
        chatError.value = result.error;
        return;
      }
      const visuals = result.visuals ?? [];
      activeConversation.value = result;
      if (visuals.length) {
        const lastIdx = result.messages.length - 1;
        visualsByIndex.value[lastIdx] = visuals;
      }
      await loadConversations();
    } catch (e: unknown) {
      if (e instanceof Error && e.name === 'AbortError') return;
      console.error('assistantChat sendMessage failed:', e);
      chatError.value = {
        summary: "I couldn't reach the server. Check that the backend is running.",
        detail: e instanceof Error ? e.message : String(e),
      };
    } finally {
      _abort = null;
      loading.value = false;
    }
  }

  async function removeConversation(id: string) {
    await api.deleteConversation(id);
    if (activeConversation.value?.id === id) clearActiveConversation();
    await loadConversations();
  }

  return {
    conversations, activeConversation, loading, visualsByIndex, chatError,
    loadConversations, createConversation, selectConversation,
    clearActiveConversation, sendMessage, stopGeneration, removeConversation,
  };
});

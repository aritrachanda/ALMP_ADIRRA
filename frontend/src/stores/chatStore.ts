import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { ConversationSummary, Conversation } from 'src/types';
import type { ChatVisual } from 'src/api/discovery';
import type { ChatError } from 'src/api/chat';
import * as api from 'src/api/chat';

export const useChatStore = defineStore('chat', () => {
  const conversations = ref<ConversationSummary[]>([]);
  const activeConversation = ref<Conversation | null>(null);
  const loading = ref(false);
  /** Visuals keyed by message index within the active conversation */
  const visualsByIndex = ref<Record<number, ChatVisual[]>>({});
  // Transient (not persisted) chat failure, cleared on the next action.
  const chatError = ref<ChatError | null>(null);

  async function loadConversations() {
    try {
      conversations.value = await api.listConversations();
    } catch (e) {
      console.error('chat loadConversations failed:', e);
    }
  }

  async function createConversation() {
    const convo = await api.createConversation();
    await loadConversations();
    activeConversation.value = convo;
    return convo;
  }

  async function selectConversation(id: string) {
    activeConversation.value = await api.getConversation(id);
    visualsByIndex.value = {};
    chatError.value = null;
  }

  async function sendMessage(content: string, context?: string) {
    if (!activeConversation.value) {
      await createConversation();
    }
    if (!activeConversation.value) return;
    loading.value = true;
    chatError.value = null;
    try {
      const result = await api.sendMessage(activeConversation.value.id, content, context);
      if (result.error) {
        chatError.value = result.error;
        return;
      }
      const visuals = result.visuals ?? [];
      activeConversation.value = result;
      // Attach visuals to the last assistant message index
      if (visuals.length) {
        const lastIdx = result.messages.length - 1;
        visualsByIndex.value[lastIdx] = visuals;
      }
      await loadConversations();
    } catch (e) {
      console.error('sendMessage failed:', e);
      chatError.value = {
        summary: "I couldn't reach the server. Check that the backend is running.",
        detail: e instanceof Error ? e.message : String(e),
      };
    } finally {
      loading.value = false;
    }
  }

  async function removeConversation(id: string) {
    await api.deleteConversation(id);
    if (activeConversation.value?.id === id) activeConversation.value = null;
    await loadConversations();
  }

  return {
    conversations, activeConversation, loading, visualsByIndex, chatError,
    loadConversations, createConversation, selectConversation, sendMessage, removeConversation,
  };
});

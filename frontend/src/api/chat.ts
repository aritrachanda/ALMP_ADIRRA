import { apiFetch, apiPost, apiDelete } from './client';
import type { ConversationSummary, Conversation } from 'src/types';
import type { ChatVisual } from 'src/api/discovery';

/** Provider-agnostic chat failure surfaced by the backend (ephemeral — not saved to history). */
export interface ChatError {
  summary: string;
  detail?: string;
  status?: number | null;
}

export async function listConversations(): Promise<ConversationSummary[]> {
  return apiFetch('/api/chat/conversations');
}

export async function createConversation(): Promise<Conversation> {
  return apiPost('/api/chat/conversations', {});
}

export async function getConversation(id: string): Promise<Conversation> {
  return apiFetch(`/api/chat/conversations/${id}`);
}

export async function sendMessage(id: string, content: string, context?: string, signal?: AbortSignal): Promise<Conversation & { visuals?: ChatVisual[]; error?: ChatError }> {
  return apiPost(`/api/chat/conversations/${id}/messages`, { content, ...(context ? { context } : {}) }, signal);
}

export async function deleteConversation(id: string): Promise<{ status: string }> {
  return apiDelete(`/api/chat/conversations/${id}`);
}

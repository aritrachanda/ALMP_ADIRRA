import { ref } from 'vue';

/** Structured AI failure payload — mirrors the backend `{summary, detail, status}`
 *  shape (api/llm_errors.py) so one banner can render every non-chat LLM failure. */
export interface AiError {
  summary: string;
  detail?: string | null;
  status?: number | null;
}

/** Per-page holder for the current AI failure plus helpers to set it from either a
 *  backend `{error}` payload or a thrown exception. Chat has its own surface — this is
 *  for the non-chat LLM features (AI drafts, glossary generate, semantic resolve, mapping). */
export function useAiError() {
  const aiError = ref<AiError | null>(null);

  function setAiError(err: AiError | null): void {
    aiError.value = err ?? null;
  }

  function clearAiError(): void {
    aiError.value = null;
  }

  /** Normalise a backend `{summary,...}` payload OR a thrown value into an `AiError`. */
  function aiErrorFrom(source: unknown, fallbackSummary = 'The AI request failed.'): AiError {
    if (source && typeof source === 'object' && 'summary' in source) {
      const e = source as AiError;
      return { summary: e.summary || fallbackSummary, detail: e.detail, status: e.status };
    }
    if (source instanceof Error) {
      return { summary: fallbackSummary, detail: source.message };
    }
    return { summary: fallbackSummary, detail: source != null ? String(source) : undefined };
  }

  return { aiError, setAiError, clearAiError, aiErrorFrom };
}

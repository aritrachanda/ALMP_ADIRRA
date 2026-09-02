// SSE reader using fetch + ReadableStream for POST endpoints
import type { SSEEvent } from 'src/types';

export async function* readSSE(url: string, body: object, signal?: AbortSignal): AsyncGenerator<SSEEvent> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok) {
    throw new Error(`SSE request failed: ${res.status} ${res.statusText}`);
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let currentEvent = '';
  let currentData = '';

  while (true) {
    if (signal?.aborted) break;
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    for (const line of lines) {
      if (line.startsWith('event: ')) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith('data: ')) {
        currentData = line.slice(6);
      } else if (line === '') {
        if (currentEvent && currentData) {
          try {
            yield { event: currentEvent, data: JSON.parse(currentData) };
          } catch {
            // skip malformed JSON
          }
        }
        currentEvent = '';
        currentData = '';
      }
    }
  }

  // Flush any remaining event after stream ends
  if (currentEvent && currentData) {
    try {
      yield { event: currentEvent, data: JSON.parse(currentData) };
    } catch {
      // skip malformed JSON
    }
  }
}

/**
 * Drive a StagedLoader honestly from a backend stream that reports only real
 * checkpoints: `progress` events (`{completed: n}`) advance the stage count,
 * `detail` events (`{text, index?, total?}`) update live sub-progress text within
 * the current stage — `fraction` (index/total, when both are present) lets the
 * caller move the progress bar smoothly within a stage, not just at stage
 * boundaries — and the final `done` event carries the real result payload. Never
 * fabricates a stage — every callback fires only because the backend emitted it.
 */
export async function fetchWithRealProgress<T>(
  url: string,
  onProgress: (completed: number) => void,
  onDetail: (text: string, fraction?: number, total?: number) => void,
  signal?: AbortSignal,
): Promise<T> {
  let result: T | undefined;
  for await (const evt of readSSE(url, {}, signal)) {
    const data = evt.data as unknown as { completed?: number; text?: string; index?: number; total?: number; status?: number; detail?: string };
    if (evt.event === 'progress' && typeof data.completed === 'number') {
      onProgress(data.completed);
    } else if (evt.event === 'detail' && typeof data.text === 'string') {
      const fraction = (typeof data.index === 'number' && typeof data.total === 'number' && data.total > 0)
        ? data.index / data.total
        : undefined;
      onDetail(data.text, fraction, data.total);
    } else if (evt.event === 'done') {
      result = evt.data as unknown as T;
    } else if (evt.event === 'error') {
      throw new Error(data.detail || `Stream failed (${data.status ?? 'unknown error'})`);
    }
  }
  if (result === undefined) throw new Error('Stream ended without a result');
  return result;
}

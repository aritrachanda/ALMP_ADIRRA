/**
 * fetchWithRealProgress — error-event handling (2026-08-17).
 *
 * Root cause of a real hang: a backend stream that crashed mid-way used to just
 * end the connection with no final event, leaving the caller waiting forever.
 * The backend now always emits a clean "error" event on failure — this proves
 * the frontend consumer surfaces it as a rejected promise instead of silently
 * finishing with `result === undefined`. Drives the REAL `readSSE` parser via a
 * mocked `fetch` (not a spy on the module's own export — `readSSE` is called as
 * a same-module reference inside `fetchWithRealProgress`, which ESM spies can't
 * intercept), so this exercises the actual SSE line-parsing too.
 */
import { describe, it, expect, vi } from 'vitest';

import { fetchWithRealProgress } from '../src/api/sse';

function sseResponse(body: string): Response {
  const bytes = new TextEncoder().encode(body);
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(bytes);
      controller.close();
    },
  });
  return new Response(stream, { status: 200 });
}

describe('fetchWithRealProgress', () => {
  it('throws using the error event detail/status when the backend reports a failure', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => sseResponse(
      'event: progress\ndata: {"completed":1}\n\n' +
      'event: error\ndata: {"status":404,"detail":"Table \'*\' not found in \'ALM Bank\'"}\n\n'
    )));

    await expect(fetchWithRealProgress('/api/element/x/y/z/stream', () => {}, () => {}))
      .rejects.toThrow("Table '*' not found in 'ALM Bank'");

    vi.unstubAllGlobals();
  });

  it('still resolves normally on progress/detail/done', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => sseResponse(
      'event: progress\ndata: {"completed":1}\n\n' +
      'event: done\ndata: {"ok":true}\n\n'
    )));

    const result = await fetchWithRealProgress<{ ok: boolean }>('/api/element/x/y/z/stream', () => {}, () => {});
    expect(result).toEqual({ ok: true });

    vi.unstubAllGlobals();
  });
});


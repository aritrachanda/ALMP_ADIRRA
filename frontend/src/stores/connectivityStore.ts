// Tracks whether the backend (FastAPI) is actually reachable, independent of whatever page
// is currently mounted — the frontend (Vite) dev server can serve pages perfectly fine even
// when the backend hasn't been started yet, which otherwise looks like a silent hang/failure.
import { defineStore } from 'pinia';
import { ref } from 'vue';

const POLL_INTERVAL_MS = 10_000;

export const useConnectivityStore = defineStore('connectivity', () => {
  // Assume disconnected until the first check proves otherwise — the banner shows immediately
  // on load rather than waiting for a check to fail first.
  const backendUp = ref(false);
  let timer: ReturnType<typeof setInterval> | null = null;

  async function checkNow(): Promise<void> {
    try {
      const res = await fetch('/api/health');
      backendUp.value = res.ok;
    } catch {
      backendUp.value = false;
    }
  }

  function startPolling(): void {
    if (timer) return;
    void checkNow();
    timer = setInterval(() => { void checkNow(); }, POLL_INTERVAL_MS);
  }

  function stopPolling(): void {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
  }

  return { backendUp, checkNow, startPolling, stopPolling };
});

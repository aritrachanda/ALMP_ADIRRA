/**
 * User preference storage.
 *
 * Browser-local today. This module is deliberately the ONLY place that knows
 * where preferences live, so moving to server-side per-user preferences later
 * is a change to these four functions rather than a hunt through the codebase.
 */

const PREFIX = 'adm-pref:';

function key(name: string): string {
  return `${PREFIX}${name}`;
}

export function getPreference<T>(name: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key(name));
    return raw == null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

export function setPreference<T>(name: string, value: T): void {
  try {
    localStorage.setItem(key(name), JSON.stringify(value));
  } catch {
    // Storage unavailable or full — preferences simply don't persist.
  }
}

export function clearPreference(name: string): void {
  try {
    localStorage.removeItem(key(name));
  } catch {
    // ignore
  }
}

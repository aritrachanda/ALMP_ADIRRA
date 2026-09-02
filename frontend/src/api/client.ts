// Base fetch wrapper with error handling

export class ApiError extends Error {
  status: number;
  statusText: string;

  constructor(response: Response, detail?: string) {
    super(detail || `API Error: ${response.status} ${response.statusText}`);
    this.status = response.status;
    this.statusText = response.statusText;
  }
}

export async function apiFetch<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    // Surface FastAPI's HTTPException `detail` (e.g. "A term titled 'X' already exists.")
    // instead of a generic "API Error: 400 Bad Request" — most callers just show err.message.
    let detail: string | undefined;
    try {
      const body: unknown = await res.json();
      if (body && typeof body === 'object' && typeof (body as { detail?: unknown }).detail === 'string') {
        detail = (body as { detail: string }).detail;
      }
    } catch {
      // response body wasn't JSON — fall back to the generic message
    }
    throw new ApiError(res, detail);
  }
  return res.json();
}

export async function apiPost<T>(url: string, body: unknown, signal?: AbortSignal): Promise<T> {
  return apiFetch<T>(url, {
    method: 'POST',
    body: JSON.stringify(body),
    signal,
  });
}

export async function apiPut<T>(url: string, body: unknown): Promise<T> {
  return apiFetch<T>(url, {
    method: 'PUT',
    body: JSON.stringify(body),
  });
}

export async function apiPatch<T>(url: string, body: unknown): Promise<T> {
  return apiFetch<T>(url, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export async function apiDelete<T>(url: string): Promise<T> {
  return apiFetch<T>(url, { method: 'DELETE' });
}

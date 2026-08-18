import { get } from 'svelte/store';
import { authRequired, authStore, toastStore } from '../stores/appStore';

export interface FetchOptions extends RequestInit {
  silent?: boolean;
}

/**
 * Error class for non-2xx responses. Carries the HTTP status and the
 * parsed response body (when the server sent one) so callers can branch
 * on ``err.status`` / ``err.data`` without casting through ``any``.
 */
export class FetchError extends Error {
  readonly status: number;
  readonly data: unknown;

  constructor(message: string, status: number, data: unknown) {
    super(message);
    this.name = 'FetchError';
    this.status = status;
    this.data = data;
  }
}

/**
 * Type guard for {@link FetchError}. Equivalent to ``err instanceof
 * FetchError`` but usable in ``catch`` blocks that type the caught
 * value as ``unknown``.
 */
export function isFetchError(err: unknown): err is FetchError {
  return err instanceof FetchError;
}

function readHeaderValue(headers: RequestInit['headers'], key: string): string | undefined {
  if (!headers) return undefined;
  if (typeof Headers !== 'undefined' && headers instanceof Headers) {
    return headers.get(key) ?? undefined;
  }
  if (Array.isArray(headers)) {
    for (const [k, v] of headers) {
      if (k.toLowerCase() === key.toLowerCase()) return v;
    }
    return undefined;
  }
  const record = headers as Record<string, string>;
  return record[key] ?? record[key.toLowerCase()];
}

function pickBearerForUrl(url: string, auth: { ocr?: string; translation?: string; transcription?: string; global?: string }): string | undefined {
  if (url.includes('/api/process') || url.includes('/api/ocr') || url.includes('/api/text') || url.includes('/api/export') || url.includes('/api/jobs')) {
    return auth.ocr || auth.global;
  }
  if (url.includes('/api/translate')) return auth.translation || auth.global;
  if (url.includes('/api/transcribe')) return auth.transcription || auth.global;
  return auth.global;
}

function flattenHeaders(initHeaders: RequestInit['headers']): Record<string, string> {
  const headers: Record<string, string> = {};
  if (!initHeaders) return headers;
  if (typeof Headers !== 'undefined' && initHeaders instanceof Headers) {
    initHeaders.forEach((v, k) => { headers[k] = v; });
  } else if (Array.isArray(initHeaders)) {
    for (const [k, v] of initHeaders) headers[k] = v;
  } else {
    Object.assign(headers, initHeaders);
  }
  return headers;
}

function extractErrorMessage(data: unknown, status: number): string {
  if (data && typeof data === 'object' && 'detail' in data) {
    const detail = (data as { detail: unknown }).detail;
    if (typeof detail === 'string') return detail;
  }
  if (data && typeof data === 'object' && 'error' in data) {
    const err = (data as { error: unknown }).error;
    if (typeof err === 'string') return err;
  }
  return `Request failed with status ${status}`;
}

async function parseResponseBody(res: Response): Promise<unknown> {
  const contentType = res.headers?.get ? res.headers.get('content-type') : null;
  if (contentType && contentType.includes('application/json')) {
    return res.json();
  }
  if (typeof res.json === 'function') {
    try {
      return await res.json();
    } catch {
      if (typeof res.text === 'function') return res.text();
    }
  }
  if (typeof res.text === 'function') return res.text();
  return null;
}

export async function fetchApi<T = unknown>(path: string, options: FetchOptions = {}): Promise<T> {
  const { silent = false, ...init } = options;

  let url = path;
  if (!url.startsWith('http://') && !url.startsWith('https://')) {
    if (!url.startsWith('/api')) {
      url = `/api${url.startsWith('/') ? '' : '/'}${url}`;
    }
  }

  const auth = get(authStore) || {};
  const token = pickBearerForUrl(url, auth);

  const headers = flattenHeaders(init.headers);
  if (token && !headers['Authorization'] && !headers['authorization']) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  if (init.body && !(init.body instanceof FormData) && !headers['Content-Type'] && !headers['content-type']) {
    headers['Content-Type'] = 'application/json';
  }

  try {
    const res = await fetch(url, { ...init, headers });
    const data: unknown = await parseResponseBody(res);

    if (!res.ok) {
      const errorMessage = extractErrorMessage(data, res.status);
      // F3.3 audit fix: a 401 means the configured bearer token is
      // missing or wrong. Flip the persistent ``authRequired`` flag
      // so the global banner can link the user to the Settings
      // auth tab. We intentionally suppress the toast on 401 so
      // the user is not spammed with a fresh error toast on every
      // poll (TabRibbon health, JobHistory load, model refresh) —
      // the banner is the persistent indicator.
      if (res.status === 401) {
        authRequired.set(true);
      } else if (!silent) {
        toastStore.pushToast('error', errorMessage);
      }
      throw new FetchError(errorMessage, res.status, data);
    }

    return data as T;
  } catch (err: unknown) {
    if (!isFetchError(err) && !silent) {
      const message = err instanceof Error ? err.message : String(err);
      toastStore.pushToast('error', message || 'Network error');
    }
    throw err;
  }
}

export async function fetchFile(path: string, options: FetchOptions = {}): Promise<Blob> {
  let url = path;
  if (!url.startsWith('http://') && !url.startsWith('https://')) {
    if (!url.startsWith('/api')) {
      url = `/api${url.startsWith('/') ? '' : '/'}${url}`;
    }
  }

  // Resolve the bearer the same way as fetchApi: per-route token when the
  // path targets a known service group, else auth.global. The caller can
  // still override with an explicit Authorization header in options.
  const auth = get(authStore) || {};
  const token = pickBearerForUrl(url, auth);
  const headers = flattenHeaders(options.headers);
  if (token && !headers['Authorization'] && !headers['authorization']) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(url, { ...options, headers });
  if (!res.ok) {
    throw new FetchError(`File download failed: ${res.statusText}`, res.status, null);
  }
  return res.blob();
}

/**
 * Variant of ``fetchApi`` that returns both the parsed body and the
 * response headers as a plain object. Used by endpoints whose response
 * carries side-channel metadata in headers (e.g. ``X-Document-Trust``).
 *
 * For binary endpoints the ``body`` is the raw ``Blob`` so callers can
 * still trigger a download or read it as needed.
 */
export async function fetchApiWithHeaders<T = unknown>(
  path: string,
  options: FetchOptions = {}
): Promise<{ body: T; headers: Record<string, string> }> {
  const { silent = false, ...init } = options;

  let url = path;
  if (!url.startsWith('http://') && !url.startsWith('https://')) {
    if (!url.startsWith('/api')) {
      url = `/api${url.startsWith('/') ? '' : '/'}${url}`;
    }
  }

  const auth = get(authStore) || {};
  const token = pickBearerForUrl(url, auth);

  const headers = flattenHeaders(init.headers);
  if (token && !headers['Authorization'] && !headers['authorization']) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  if (init.body && !(init.body instanceof FormData) && !headers['Content-Type'] && !headers['content-type']) {
    headers['Content-Type'] = 'application/json';
  }

  const res = await fetch(url, { ...init, headers });

  const responseHeaders: Record<string, string> = {};
  res.headers.forEach((value, key) => {
    responseHeaders[key.toLowerCase()] = value;
  });

  const contentType = responseHeaders['content-type'] || '';
  let body: T;
  if (contentType.includes('application/json')) {
    body = (await res.json()) as T;
  } else if (typeof res.blob === 'function') {
    body = (await res.blob()) as T;
  } else {
    body = null as T;
  }

  if (!res.ok) {
    const errorMessage = extractErrorMessage(body, res.status);
    // F3.3 audit fix: same 401 branch as ``fetchApi`` — set the
    // persistent ``authRequired`` flag and suppress the toast so
    // the banner is the single source of truth.
    if (res.status === 401) {
      authRequired.set(true);
    } else if (!silent) {
      toastStore.pushToast('error', errorMessage);
    }
    throw new FetchError(errorMessage, res.status, body);
  }

  return { body, headers: responseHeaders };
}

// Re-exported for callers that read ``err.status`` / ``err.data``
// without an explicit type guard.
export { readHeaderValue };

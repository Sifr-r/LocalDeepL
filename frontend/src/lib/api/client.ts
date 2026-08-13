import { get } from 'svelte/store';
import { authStore, toastStore } from '../stores/appStore';

export interface FetchOptions extends RequestInit {
  silent?: boolean;
}

export async function fetchApi<T = any>(path: string, options: FetchOptions = {}): Promise<T> {
  const { silent = false, ...init } = options;

  let url = path;
  if (!url.startsWith('http://') && !url.startsWith('https://')) {
    if (!url.startsWith('/api')) {
      url = `/api${url.startsWith('/') ? '' : '/'}${url}`;
    }
  }

  const auth = get(authStore) || {};
  let token: string | undefined;

  if (url.includes('/api/process') || url.includes('/api/ocr')) {
    token = auth.ocr || auth.global;
  } else if (url.includes('/api/translate')) {
    token = auth.translation || auth.global;
  } else if (url.includes('/api/transcribe')) {
    token = auth.transcription || auth.global;
  } else {
    token = auth.global;
  }

  const headers: Record<string, string> = {};
  if (init.headers) {
    if (typeof Headers !== 'undefined' && init.headers instanceof Headers) {
      init.headers.forEach((v, k) => { headers[k] = v; });
    } else if (Array.isArray(init.headers)) {
      init.headers.forEach(([k, v]) => { headers[k] = v; });
    } else {
      Object.assign(headers, init.headers);
    }
  }

  if (token && !headers['Authorization'] && !headers['authorization']) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  if (init.body && !(init.body instanceof FormData) && !headers['Content-Type'] && !headers['content-type']) {
    headers['Content-Type'] = 'application/json';
  }

  try {
    const res = await fetch(url, { ...init, headers });
    let data: any = null;

    const contentType = res.headers?.get ? res.headers.get('content-type') : null;
    if (contentType && contentType.includes('application/json')) {
      data = await res.json();
    } else if (typeof res.json === 'function') {
      try {
        data = await res.json();
      } catch {
        if (typeof res.text === 'function') {
          data = await res.text();
        }
      }
    } else if (typeof res.text === 'function') {
      data = await res.text();
    }

    if (!res.ok) {
      const errorMessage =
        (typeof data === 'object' && data !== null ? data.detail || data.error : null) ||
        `Request failed with status ${res.status}`;
      
      if (!silent) {
        toastStore.pushToast('error', errorMessage);
      }
      const err = new Error(errorMessage) as any;
      err.status = res.status;
      err.data = data;
      throw err;
    }

    return data as T;
  } catch (err: any) {
    if (!silent && !err.status) {
      toastStore.pushToast('error', err.message || 'Network error');
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

  const auth = get(authStore) || {};
  const token = auth.global;
  const headers: Record<string, string> = {};
  if (options.headers) {
    if (typeof Headers !== 'undefined' && options.headers instanceof Headers) {
      options.headers.forEach((v, k) => { headers[k] = v; });
    } else if (Array.isArray(options.headers)) {
      options.headers.forEach(([k, v]) => { headers[k] = v; });
    } else {
      Object.assign(headers, options.headers);
    }
  }
  if (token && !headers['Authorization'] && !headers['authorization']) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(url, { ...options, headers });
  if (!res.ok) {
    throw new Error(`File download failed: ${res.statusText}`);
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
export async function fetchApiWithHeaders<T = any>(
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
  let token: string | undefined;

  if (url.includes('/api/process') || url.includes('/api/ocr')) {
    token = auth.ocr || auth.global;
  } else if (url.includes('/api/translate')) {
    token = auth.translation || auth.global;
  } else if (url.includes('/api/transcribe')) {
    token = auth.transcription || auth.global;
  } else {
    token = auth.global;
  }

  const headers: Record<string, string> = {};
  if (init.headers) {
    if (typeof Headers !== 'undefined' && init.headers instanceof Headers) {
      init.headers.forEach((v, k) => { headers[k] = v; });
    } else if (Array.isArray(init.headers)) {
      init.headers.forEach(([k, v]) => { headers[k] = v; });
    } else {
      Object.assign(headers, init.headers);
    }
  }

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
  let body: any = null;
  if (contentType.includes('application/json')) {
    body = await res.json();
  } else if (typeof res.blob === 'function') {
    body = await res.blob();
  }

  if (!res.ok) {
    const errorMessage =
      (typeof body === 'object' && body !== null ? body.detail || body.error : null) ||
      `Request failed with status ${res.status}`;

    if (!silent) {
      toastStore.pushToast('error', errorMessage);
    }
    const err = new Error(errorMessage) as any;
    err.status = res.status;
    err.data = body;
    throw err;
  }

  return { body, headers: responseHeaders };
}

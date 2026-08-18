import { describe, it, expect, vi, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import { fetchApi, fetchApiWithHeaders } from '../lib/api/client';
import { authRequired, authStore, toastStore } from '../lib/stores/appStore';

describe('fetchApi client', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    authStore.set({});
    authRequired.set(false);
  });

  it('attaches Authorization header when authStore contains global token', async () => {
    authStore.set({ global: 'secret-bearer-token' });

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ status: 'ok' })
    } as Response);

    await fetchApi('/config');

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/config',
      expect.objectContaining({
        headers: expect.objectContaining({
          'Authorization': 'Bearer secret-bearer-token'
        })
      })
    );
  });

  it('attaches OCR token for /process endpoints when configured', async () => {
    authStore.set({ global: 'global-tok', ocr: 'ocr-tok' });

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ status: 'ok' })
    } as Response);

    await fetchApi('/process/status/123');

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/process/status/123',
      expect.objectContaining({
        headers: expect.objectContaining({
          'Authorization': 'Bearer ocr-tok'
        })
      })
    );
  });

  it('attaches OCR token for /jobs endpoints (async OCR result download)', async () => {
    authStore.set({ global: 'global-tok', ocr: 'ocr-tok' });

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ status: 'ok' })
    } as Response);

    await fetchApi('/jobs/abc/result');

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/jobs/abc/result',
      expect.objectContaining({
        headers: expect.objectContaining({
          'Authorization': 'Bearer ocr-tok'
        })
      })
    );
  });

  it('attaches OCR token for /process/async (submit endpoint)', async () => {
    authStore.set({ global: 'global-tok', ocr: 'ocr-tok' });

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 202,
      json: async () => ({ job_id: 'job-1', status: 'pending' })
    } as Response);

    await fetchApi('/process/async', { method: 'POST', body: new FormData() });

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/process/async',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          'Authorization': 'Bearer ocr-tok'
        })
      })
    );
  });
});

describe('F3.3 audit fix: 401 handling', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    authStore.set({});
    authRequired.set(false);
  });

  it('flips authRequired flag and suppresses the toast on a 401', async () => {
    // The F3.3 audit fix: a 401 from the server means the configured
    // bearer token is missing or wrong. We set the persistent
    // ``authRequired`` flag so the global banner can deep-link the
    // user to the Settings auth tab, and we suppress the per-error
    // toast (which would otherwise spam on every poll).
    const pushToast = vi.spyOn(toastStore, 'pushToast');

    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ detail: 'Unauthorized' })
    } as Response);

    await expect(fetchApi('/config')).rejects.toThrow();

    expect(get(authRequired)).toBe(true);
    expect(pushToast).not.toHaveBeenCalled();
  });

  it('still toasts on non-401 errors (e.g. 500)', async () => {
    const pushToast = vi.spyOn(toastStore, 'pushToast');

    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({ detail: 'Internal Server Error' })
    } as Response);

    await expect(fetchApi('/config')).rejects.toThrow();

    expect(get(authRequired)).toBe(false);
    // 500 is not a 401, so the regular error path fires and the
    // server's `detail` ("Internal Server Error") is shown in the
    // toast. The 401 branch is bypassed.
    expect(pushToast).toHaveBeenCalledWith(
      'error',
      'Internal Server Error'
    );
  });

  it('flips authRequired flag on 401 in fetchApiWithHeaders too', async () => {
    // The header-bearing variant of fetchApi is used for endpoints
    // whose response carries side-channel metadata (X-Document-Trust
    // etc.). Same 401 handling applies.
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      headers: { forEach: () => {} } as unknown as Headers,
      json: async () => ({ detail: 'Unauthorized' })
    } as Response);

    await expect(fetchApiWithHeaders('/config')).rejects.toThrow();

    expect(get(authRequired)).toBe(true);
  });
});

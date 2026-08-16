import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fetchApi } from '../lib/api/client';
import { authStore } from '../lib/stores/appStore';

describe('fetchApi client', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    authStore.set({});
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

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { artifactsApi } from '../lib/api/endpoints';
import { authStore } from '../lib/stores/appStore';

describe('artifactsApi.getText / getExport auth', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    authStore.set({});
  });

  it('getText uses bearer header and drops the ?token= query string', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      blob: async () => new Blob(['hello'])
    } as Response);

    await artifactsApi.getText('id', 'tok-123');

    const fetchMock = global.fetch as ReturnType<typeof vi.fn>;
    const [calledUrl, calledInit] = fetchMock.mock.calls[0] as [string, RequestInit];

    // No query string at all — the token is carried by the Authorization header.
    expect(calledUrl).toBe('/api/text/id');
    expect(String(calledUrl)).not.toMatch(/token=/);

    const headers = (calledInit.headers ?? {}) as Record<string, string>;
    expect(headers['Authorization']).toBe('Bearer tok-123');
  });

  it('getExport uses bearer header and drops the ?token= query string', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      blob: async () => new Blob(['pdf-bytes'])
    } as Response);

    await artifactsApi.getExport('id', 'tok-456');

    const fetchMock = global.fetch as ReturnType<typeof vi.fn>;
    const [calledUrl, calledInit] = fetchMock.mock.calls[0] as [string, RequestInit];

    expect(calledUrl).toBe('/api/export/id');
    expect(String(calledUrl)).not.toMatch(/token=/);

    const headers = (calledInit.headers ?? {}) as Record<string, string>;
    expect(headers['Authorization']).toBe('Bearer tok-456');
  });

  it('fetchFile falls back to auth.ocr for /text when no explicit Authorization is passed', async () => {
    authStore.set({ global: 'global-tok', ocr: 'ocr-tok' });

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      blob: async () => new Blob(['x'])
    } as Response);

    const { fetchFile } = await import('../lib/api/client');
    await fetchFile('/text/some-id');

    const fetchMock = global.fetch as ReturnType<typeof vi.fn>;
    const [calledUrl, calledInit] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(calledUrl).toBe('/api/text/some-id');
    const headers = (calledInit.headers ?? {}) as Record<string, string>;
    expect(headers['Authorization']).toBe('Bearer ocr-tok');
  });
});

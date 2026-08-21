import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { transcribe } from '../transcriptionService';

/**
 * Service-level tests for `transcriptionService.ts`. The wrapper is a
 * single `POST /api/transcribe` (multipart) call — the tests assert
 * URL forwarding, method, and signal propagation.
 */

const okResponse = (): Response =>
  new Response(JSON.stringify({ text: 'hello', segments: [] }), {
    status: 200,
    headers: { 'content-type': 'application/json' }
  });

describe('transcriptionService', () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchSpy = vi.fn().mockResolvedValue(okResponse());
    vi.stubGlobal('fetch', fetchSpy);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('transcribe POSTs to /api/transcribe', async () => {
    const form = new FormData();
    form.append('audio', new File(['binary'], 'rec.wav', { type: 'audio/wav' }));
    await transcribe(form);
    const [url, init] = fetchSpy.mock.calls[0] ?? [];
    expect(url).toContain('/api/transcribe');
    expect(init.method).toBe('POST');
    // The wrapper passes the FormData through as the body (not JSON).
    expect(init.body).toBe(form);
  });

  it('transcribe forwards the AbortSignal to fetch', async () => {
    const ctrl = new AbortController();
    const form = new FormData();
    form.append('audio', new File(['binary'], 'rec.wav', { type: 'audio/wav' }));
    await transcribe(form, { signal: ctrl.signal });
    expect(fetchSpy.mock.calls[0]?.[1]?.signal).toBe(ctrl.signal);
  });
});

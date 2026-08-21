import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { cancel, clear, list } from '../jobsService';

/**
 * Service-level tests for `jobsService.ts`. Three wrappers:
 *   - list   → GET    /api/jobs
 *   - clear  → DELETE /api/jobs
 *   - cancel → POST   /api/jobs/{jobId}/cancel
 */

const jsonResponse = (body: unknown): Response =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' }
  });

describe('jobsService', () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchSpy = vi.fn().mockResolvedValue(jsonResponse([]));
    vi.stubGlobal('fetch', fetchSpy);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('list GETs /api/jobs', async () => {
    await list();
    const [url, init] = fetchSpy.mock.calls[0] ?? [];
    expect(url).toContain('/api/jobs');
    expect(url).not.toContain('/cancel');
    expect(init.method ?? 'GET').toBe('GET');
  });

  it('clear DELETEs /api/jobs', async () => {
    await clear();
    const [url, init] = fetchSpy.mock.calls[0] ?? [];
    expect(url).toContain('/api/jobs');
    expect(init.method).toBe('DELETE');
  });

  it('cancel POSTs to /api/jobs/{jobId}/cancel', async () => {
    await cancel('job-1');
    const [url, init] = fetchSpy.mock.calls[0] ?? [];
    expect(url).toContain('/api/jobs/job-1/cancel');
    expect(init.method).toBe('POST');
  });

  it.each([
    ['list', (signal: AbortSignal) => list({ signal })],
    ['clear', (signal: AbortSignal) => clear({ signal })],
    ['cancel', (signal: AbortSignal) => cancel('job-1', { signal })]
  ])('%s forwards the AbortSignal to fetch', async (_name, call) => {
    const ctrl = new AbortController();
    await call(ctrl.signal);
    expect(fetchSpy.mock.calls[0]?.[1]?.signal).toBe(ctrl.signal);
  });
});

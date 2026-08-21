import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import {
  getTranslationStatus,
  translate,
  translateAsync,
  translateNllb
} from '../translationService';

/**
 * Service-level tests for `translationService.ts`. The wrappers here
 * are thin pass-throughs to `endpoints.translationApi`, so the tests
 * focus on:
 *   - The forwarded `signal` reaches the underlying `fetch` call.
 *   - The URL paths match the expected FastAPI routes.
 *   - Method/JSON body shape on POSTs.
 *
 * The full `client.ts` plumbing (auth header injection, content-type,
 * toast suppression) is exercised by `endpoints.fetchOptions.test.ts`
 * and the `WorkstationView` integration test.
 */

const okResponse = (body: unknown = {}): Response =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' }
  });

describe('translationService', () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchSpy = vi.fn().mockResolvedValue(okResponse({}));
    vi.stubGlobal('fetch', fetchSpy);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('translate forwards the call to POST /api/translate', async () => {
    await translate({ text: 'hi', target_language: 'es' });
    const [url, init] = fetchSpy.mock.calls[0] ?? [];
    expect(url).toContain('/api/translate');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toMatchObject({
      text: 'hi',
      target_language: 'es'
    });
  });

  it.each([
    [
      'translate',
      (signal: AbortSignal) => translate({ text: 'hi', target_language: 'es' }, { signal })
    ],
    [
      'translateAsync',
      (signal: AbortSignal) =>
        translateAsync(
          { text: 'long', target_language: 'fr' },
          { signal }
        )
    ],
    [
      'getTranslationStatus',
      (signal: AbortSignal) => getTranslationStatus('job-1', { signal })
    ],
    [
      'translateNllb',
      (signal: AbortSignal) =>
        translateNllb({ text: 'hello', target_language: 'es' }, { signal })
    ]
  ])('%s forwards the AbortSignal to fetch', async (_name, call) => {
    const ctrl = new AbortController();
    await call(ctrl.signal);
    expect(fetchSpy.mock.calls[0]?.[1]?.signal).toBe(ctrl.signal);
  });

  it('translateAsync posts to /api/translate/async', async () => {
    await translateAsync({ text: 'long document', target_language: 'fr' });
    const [url, init] = fetchSpy.mock.calls[0] ?? [];
    expect(url).toContain('/api/translate/async');
    expect(init.method).toBe('POST');
  });

  it('translateNllb posts to /api/translate/nllb', async () => {
    await translateNllb({ text: 'hello world', target_language: 'es' });
    const [url, init] = fetchSpy.mock.calls[0] ?? [];
    expect(url).toContain('/api/translate/nllb');
    expect(url).not.toContain('/async');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toMatchObject({
      text: 'hello world',
      target_language: 'es'
    });
  });

  it('getTranslationStatus GETs /api/translate/status/{id}', async () => {
    await getTranslationStatus('job-42');
    const [url, init] = fetchSpy.mock.calls[0] ?? [];
    expect(url).toContain('/api/translate/status/job-42');
    // GET is the fetch default; the underlying wrapper omits method.
    expect(init.method ?? 'GET').toBe('GET');
  });
});

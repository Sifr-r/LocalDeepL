/**
 * FE-10: every endpoints.ts wrapper accepts an optional trailing
 * ``FetchOptions`` parameter and forwards ``signal`` through to the
 * underlying ``fetchApi`` / ``fetchApiWithHeaders`` / ``fetchFile``
 * call. These tests pin that contract by stubbing ``global.fetch`` and
 * inspecting the ``RequestInit.signal`` argument for a representative
 * slice of wrappers — enough to catch any wrapper that forgets to
 * merge the signal through.
 *
 * Companion file: ``frontend/src/lib/api/fetchOptions.ts``.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  configApi,
  ocrApi,
  translationApi,
  transcriptionApi,
  glossaryApi,
  jobsApi,
  providersApi,
  artifactsApi,
  extractionApi,
  getConfig,
  updateConfig,
  getProviders,
  getProviderDetails,
  getProviderModels,
  processOcr,
  getOcrStatus,
  processOcrAsync,
  getOcrResult,
  exportDocument,
  exportDocx
} from '../endpoints';
import { createAbortController } from '../fetchOptions';

type FetchMock = ReturnType<typeof vi.fn>;

/**
 * Build a Response-shaped object for both JSON endpoints and the
 * binary ``/jobs/:id/result`` and ``/text/:id`` artifact endpoints.
 * ``Response.json`` throws when the body isn't JSON, so a
 * catch-and-fall-back ``text()`` keeps the mock usable for both
 * shapes.
 */
function mockResponse(body: unknown = {}, status = 200): Response {
  const isObject = body !== null && typeof body === 'object';
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? 'OK' : 'Mock',
    headers: {
      get: (_key: string) => null,
      forEach: (_cb: (value: string, key: string) => void) => {
        /* no-op */
      }
    } as unknown as Headers,
    json: async () => (isObject ? body : {}),
    text: async () => (typeof body === 'string' ? body : JSON.stringify(body)),
    blob: async () => new Blob([typeof body === 'string' ? body : JSON.stringify(body)])
  } as unknown as Response;
}

let fetchSpy: FetchMock;

beforeEach(() => {
  fetchSpy = vi.fn().mockResolvedValue(mockResponse({ ok: true }));
  global.fetch = fetchSpy as unknown as typeof fetch;
  // Some wrappers read authStore indirectly via fetchApi's bearer
  // resolution; clearing it keeps the assertion surface small.
});

afterEach(() => {
  vi.restoreAllMocks();
});

/** Pull the ``RequestInit`` argument off the most recent fetch call. */
function lastInit(): RequestInit | undefined {
  const call = fetchSpy.mock.calls.at(-1);
  return call?.[1] as RequestInit | undefined;
}

describe('createAbortController (fetchOptions helper)', () => {
  it('returns a fresh AbortController on every call', () => {
    const a = createAbortController();
    const b = createAbortController();
    expect(a).toBeInstanceOf(AbortController);
    expect(b).toBeInstanceOf(AbortController);
    expect(a).not.toBe(b);
    expect(a.signal).not.toBe(b.signal);
    expect(a.signal.aborted).toBe(false);
  });
});

describe('namespace wrappers forward FetchOptions.signal', () => {
  it.each([
    [
      'configApi.get',
      () => configApi.get({ signal: new AbortController().signal })
    ],
    [
      'configApi.update',
      () => configApi.update({} as never, { signal: new AbortController().signal })
    ],
    [
      'ocrApi.process',
      () => ocrApi.process(new FormData(), { signal: new AbortController().signal })
    ],
    [
      'ocrApi.processAsync',
      () => ocrApi.processAsync(new FormData(), { signal: new AbortController().signal })
    ],
    [
      'ocrApi.getStatus',
      () => ocrApi.getStatus('job-1', { signal: new AbortController().signal })
    ],
    [
      'ocrApi.getResult',
      () => ocrApi.getResult('job-1', 'tok-1', { signal: new AbortController().signal })
    ],
    [
      'ocrApi.cancel',
      () => ocrApi.cancel('job-1', { signal: new AbortController().signal })
    ],
    [
      'translationApi.translate',
      () =>
        translationApi.translate(
          { text: 'x', target_lang: 'en' } as never,
          { signal: new AbortController().signal }
        )
    ],
    [
      'translationApi.translateAsync',
      () =>
        translationApi.translateAsync(
          { text: 'x', target_lang: 'en' } as never,
          { signal: new AbortController().signal }
        )
    ],
    [
      'translationApi.getStatus',
      () => translationApi.getStatus('job-1', { signal: new AbortController().signal })
    ],
    [
      'transcriptionApi.transcribe',
      () =>
        transcriptionApi.transcribe(new FormData(), { signal: new AbortController().signal })
    ],
    [
      'glossaryApi.getLibraries',
      () => glossaryApi.getLibraries({ signal: new AbortController().signal })
    ],
    [
      'glossaryApi.getEntries',
      () => glossaryApi.getEntries('lib-1', { signal: new AbortController().signal })
    ],
    [
      'glossaryApi.getMerged',
      () => glossaryApi.getMerged({ signal: new AbortController().signal })
    ],
    [
      'glossaryApi.getPreview',
      () => glossaryApi.getPreview({ signal: new AbortController().signal })
    ],
    [
      'glossaryApi.toggle',
      () => glossaryApi.toggle('lib-1', true, { signal: new AbortController().signal })
    ],
    [
      'glossaryApi.delete',
      () => glossaryApi.delete('lib-1', { signal: new AbortController().signal })
    ],
    [
      'glossaryApi.reorder',
      () =>
        glossaryApi.reorder(['lib-1', 'lib-2'], { signal: new AbortController().signal })
    ],
    [
      'glossaryApi.importFile',
      () =>
        glossaryApi.importFile(new FormData(), { signal: new AbortController().signal })
    ],
    [
      'glossaryApi.importUrl',
      () =>
        glossaryApi.importUrl('https://example.com/x.tbx', 'tbx', 'name', {
          signal: new AbortController().signal
        })
    ],
    [
      'jobsApi.list',
      () => jobsApi.list({ signal: new AbortController().signal })
    ],
    [
      'jobsApi.clear',
      () => jobsApi.clear({ signal: new AbortController().signal })
    ],
    [
      'jobsApi.cancel',
      () => jobsApi.cancel('job-1', { signal: new AbortController().signal })
    ],
    [
      'providersApi.list',
      () => providersApi.list({ signal: new AbortController().signal })
    ],
    [
      'providersApi.get',
      () => providersApi.get('openai', { signal: new AbortController().signal })
    ],
    [
      'providersApi.models',
      () => providersApi.models('openai', { signal: new AbortController().signal })
    ],
    [
      'artifactsApi.getText',
      () =>
        artifactsApi.getText('art-1', 'tok-1', { signal: new AbortController().signal })
    ],
    [
      'artifactsApi.getTextAsString',
      () =>
        artifactsApi.getTextAsString('art-1', 'tok-1', {
          signal: new AbortController().signal
        })
    ],
    [
      'artifactsApi.getExport',
      () =>
        artifactsApi.getExport('art-1', 'tok-1', { signal: new AbortController().signal })
    ],
    [
      'extractionApi.extract',
      () =>
        extractionApi.extract(
          { text: 'x' } as never,
          { signal: new AbortController().signal }
        )
    ]
  ])('%s forwards the AbortSignal to fetch', async (_name, call) => {
    await call();
    expect(lastInit()?.signal).toBeDefined();
    expect(lastInit()?.signal).toBeInstanceOf(AbortSignal);
  });
});

describe('free-function wrappers forward FetchOptions.signal', () => {
  it.each([
    ['getConfig', () => getConfig({ signal: new AbortController().signal })],
    [
      'updateConfig',
      () => updateConfig({}, { signal: new AbortController().signal })
    ],
    ['getProviders', () => getProviders({ signal: new AbortController().signal })],
    [
      'getProviderDetails',
      () => getProviderDetails('openai', { signal: new AbortController().signal })
    ],
    [
      'getProviderModels',
      () => getProviderModels('openai', { signal: new AbortController().signal })
    ],
    [
      'processOcr',
      () => processOcr(new FormData(), { signal: new AbortController().signal })
    ],
    [
      'getOcrStatus',
      () => getOcrStatus('job-1', { signal: new AbortController().signal })
    ],
    [
      'processOcrAsync',
      () => processOcrAsync(new FormData(), { signal: new AbortController().signal })
    ],
    [
      'getOcrResult',
      () => getOcrResult('job-1', 'tok-1', { signal: new AbortController().signal })
    ],
    [
      'exportDocument',
      () =>
        exportDocument(
          { text_artifact_id: 'art-1', text_artifact_token: 'tok-1' },
          { signal: new AbortController().signal }
        )
    ],
    [
      'exportDocx',
      () => exportDocx({ text: 'x' }, { signal: new AbortController().signal })
    ]
  ])('%s forwards the AbortSignal to fetch', async (_name, call) => {
    await call();
    expect(lastInit()?.signal).toBeDefined();
    expect(lastInit()?.signal).toBeInstanceOf(AbortSignal);
  });
});

describe('AbortController actually aborts the request', () => {
  it('fires the AbortError when the controller aborts mid-flight', async () => {
    // Drive the abort through ``fetchApi`` (via configApi.get) so the
    // production abort-detection path is exercised — ``fetchApi``
    // re-throws DOMException with ``name === 'AbortError'`` without
    // surfacing a toast.
    const ctrl = new AbortController();
    // Simulate a fetch that throws when aborted (mirrors real browsers).
    fetchSpy.mockImplementationOnce(((_url: string, init?: RequestInit) => {
      return new Promise((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => {
          const err = new Error('aborted');
          (err as Error & { name: string }).name = 'AbortError';
          reject(err);
        });
      });
    }) as unknown as typeof fetch);

    const promise = configApi.get({ signal: ctrl.signal });
    ctrl.abort();
    await expect(promise).rejects.toThrow();
  });
});

describe('wrappers tolerate missing FetchOptions', () => {
  it('configApi.get() without options still hits fetch', async () => {
    await configApi.get();
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    // When options is omitted we deliberately pass ``signal: undefined``
    // — the underlying fetch sees no live signal, which is the correct
    // "no cancellation" semantic.
    expect(lastInit()?.signal).toBeUndefined();
  });

  it('jobsApi.cancel(jobId) without options still hits fetch', async () => {
    await jobsApi.cancel('job-1');
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(lastInit()?.signal).toBeUndefined();
  });

  it('getConfig() without options still hits fetch', async () => {
    await getConfig();
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(lastInit()?.signal).toBeUndefined();
  });
});

describe('FetchOptions — signal forwarding', () => {
  it('forwards the exact AbortSignal instance the caller passes in', async () => {
    // The wrapper must not consume the signal — passing the caller's
    // own controller lets the caller abort independently of the call.
    const ctrl = new AbortController();
    await configApi.get({ signal: ctrl.signal });
    expect(lastInit()?.signal).toBe(ctrl.signal);
  });

  it('omits signal when options is provided but signal is undefined', async () => {
    await configApi.get({});
    expect(lastInit()?.signal).toBeUndefined();
  });
});

import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import {
  extract,
  exportBlocktree,
  exportDocx,
  exportDocxTree,
  exportDocument,
  exportHtml
} from '../extractionService';

/**
 * Service-level tests for `extractionService.ts`. The wrappers fan out
 * to three endpoints (`/api/extract`, `/api/export/document`,
 * `/api/export/docx`); each test pins URL + method + forwarded signal.
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

const okBlob = (body = '%PDF-1.4'): Response =>
  new Response(body, {
    status: 200,
    headers: {
      'content-type':
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    }
  });

describe('extractionService', () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchSpy = vi.fn().mockResolvedValue(okResponse({}));
    vi.stubGlobal('fetch', fetchSpy);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('extract posts to /api/extract', async () => {
    // ``ExtractionTemplate`` is a string union — not an object.
    await extract({ text: 'invoice body', template: 'invoice' });
    const [url, init] = fetchSpy.mock.calls[0] ?? [];
    expect(url).toContain('/api/extract');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toMatchObject({
      text: 'invoice body'
    });
  });

  it('exportDocument posts to /api/export/document', async () => {
    await exportDocument({
      text_artifact_id: 'art-1',
      text_artifact_token: 'tok-1',
      export_format: 'markdown'
    });
    const [url, init] = fetchSpy.mock.calls[0] ?? [];
    expect(url).toContain('/api/export/document');
    expect(init.method).toBe('POST');
  });

  it('exportDocx posts to /api/export/docx and returns a Blob', async () => {
    fetchSpy.mockResolvedValueOnce(okBlob());
    const blob = await exportDocx({ text: 'plain text' });
    const [url, init] = fetchSpy.mock.calls[0] ?? [];
    expect(url).toContain('/api/export/docx');
    expect(init.method).toBe('POST');
    expect(blob).toBeInstanceOf(Blob);
  });

  it('exportHtml posts to /api/export/html and returns a Blob', async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response('<html></html>', {
        status: 200,
        headers: { 'content-type': 'text/html' }
      })
    );
    const blob = await exportHtml({ text_artifact_id: 'a', text_artifact_token: 't' });
    const [url, init] = fetchSpy.mock.calls[0] ?? [];
    expect(url).toContain('/api/export/html');
    expect(url).not.toContain('/docx');
    expect(init.method).toBe('POST');
    expect(blob).toBeInstanceOf(Blob);
  });

  it('exportDocxTree posts to /api/export/docx-tree and returns a Blob', async () => {
    fetchSpy.mockResolvedValueOnce(okBlob());
    const blob = await exportDocxTree({ text_artifact_id: 'a', text_artifact_token: 't' });
    const [url, init] = fetchSpy.mock.calls[0] ?? [];
    expect(url).toContain('/api/export/docx-tree');
    expect(init.method).toBe('POST');
    expect(blob).toBeInstanceOf(Blob);
  });

  it('exportBlocktree posts to /api/export/blocktree and parses the JSON response', async () => {
    fetchSpy.mockResolvedValueOnce(okResponse({ blocks: [{ id: 'b1' }] }));
    const res = await exportBlocktree({ text_artifact_id: 'a', text_artifact_token: 't' });
    const [url, init] = fetchSpy.mock.calls[0] ?? [];
    expect(url).toContain('/api/export/blocktree');
    expect(init.method).toBe('POST');
    expect(res).toEqual({ blocks: [{ id: 'b1' }] });
  });

  // Parametrized signal-forwarding test — covers every wrapper so a
  // refactor that drops a wrapper (or forgets to thread `signal`)
  // fails the test for that wrapper specifically.
  it.each([
    ['extract', (signal: AbortSignal) => extract({ text: 'x' }, { signal })],
    [
      'exportDocument',
      (signal: AbortSignal) =>
        exportDocument(
          { text_artifact_id: 'a', text_artifact_token: 't' },
          { signal }
        )
    ],
    ['exportDocx', (signal: AbortSignal) => exportDocx({ text: 'x' }, { signal })],
    [
      'exportHtml',
      (signal: AbortSignal) =>
        exportHtml({ text_artifact_id: 'a', text_artifact_token: 't' }, { signal })
    ],
    [
      'exportDocxTree',
      (signal: AbortSignal) =>
        exportDocxTree({ text_artifact_id: 'a', text_artifact_token: 't' }, { signal })
    ],
    [
      'exportBlocktree',
      (signal: AbortSignal) =>
        exportBlocktree({ text_artifact_id: 'a', text_artifact_token: 't' }, { signal })
    ]
  ])('%s forwards the AbortSignal to fetch', async (_name, call) => {
    const ctrl = new AbortController();
    await call(ctrl.signal);
    expect(fetchSpy.mock.calls[0]?.[1]?.signal).toBe(ctrl.signal);
  });
});

import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { extract, exportDocument, exportDocx } from '../extractionService';

/**
 * Service-level tests for `extractionService.ts`. The wrappers fan out
 * to three endpoints (`/api/extract`, `/api/export/document`,
 * `/api/export/docx`); each test pins URL + method + forwarded signal.
 */

const okResponse = (body: unknown = {}): Response =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' }
  });

const okBlob = (body = '%PDF-1.4'): Response =>
  new Response(body, {
    status: 200,
    headers: { 'content-type': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' }
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

  it('extract forwards the signal', async () => {
    const ctrl = new AbortController();
    await extract({ text: 'x' }, { signal: ctrl.signal });
    const init = fetchSpy.mock.calls[0]?.[1] as RequestInit;
    expect(init.signal).toBe(ctrl.signal);
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
});

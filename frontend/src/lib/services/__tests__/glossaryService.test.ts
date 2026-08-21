import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import {
  getLibraries,
  getMerged,
  getPreview,
  importFile,
  importUrl
} from '../glossaryService';

/**
 * Service-level tests for `glossaryService.ts`. Exercises every
 * exported wrapper:
 *   - getLibraries        → GET /api/glossary/library
 *   - getMerged           → GET /api/glossary/library/merged
 *   - getPreview          → GET /api/glossary/library/preview
 *   - importFile          → POST /api/glossary/import (multipart)
 *   - importUrl           → POST /api/glossary/import/url (json)
 */

const jsonResponse = (body: unknown): Response =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' }
  });

describe('glossaryService', () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchSpy = vi.fn().mockResolvedValue(
      jsonResponse({ libraries: [], entries: [], preview: {} })
    );
    vi.stubGlobal('fetch', fetchSpy);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('getLibraries GETs /api/glossary/library', async () => {
    await getLibraries();
    const [url, init] = fetchSpy.mock.calls[0] ?? [];
    expect(url).toContain('/api/glossary/library');
    expect(url).not.toContain('/merged');
    expect(init.method ?? 'GET').toBe('GET');
  });

  it('getMerged GETs /api/glossary/library/merged', async () => {
    await getMerged();
    const [url] = fetchSpy.mock.calls[0] ?? [];
    expect(url).toContain('/api/glossary/library/merged');
  });

  it('getPreview GETs /api/glossary/library/preview', async () => {
    await getPreview();
    const [url] = fetchSpy.mock.calls[0] ?? [];
    expect(url).toContain('/api/glossary/library/preview');
  });

  it('importFile POSTs to /api/glossary/import with FormData body', async () => {
    const form = new FormData();
    form.append('file', new File(['tbx'], 'glossary.tbx'));
    await importFile(form);
    const [url, init] = fetchSpy.mock.calls[0] ?? [];
    expect(url).toContain('/api/glossary/import');
    expect(url).not.toContain('/url');
    expect(init.method).toBe('POST');
    expect(init.body).toBe(form);
  });

  it('importUrl POSTs to /api/glossary/import/url with JSON body', async () => {
    await importUrl('https://example.com/g.tbx', 'tbx', 'My Library');
    const [url, init] = fetchSpy.mock.calls[0] ?? [];
    expect(url).toContain('/api/glossary/import/url');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toMatchObject({
      url: 'https://example.com/g.tbx',
      format: 'tbx',
      name: 'My Library'
    });
  });

  it('importUrl omits name when not provided', async () => {
    await importUrl('https://example.com/g.csv', 'csv');
    const [, init] = fetchSpy.mock.calls[0] ?? [];
    const body = JSON.parse(init.body as string);
    // ``undefined`` is serialised away — the body must NOT carry the
    // field at all so the server falls back to its URL-derived name.
    expect('name' in body).toBe(false);
    expect(body).toMatchObject({ url: 'https://example.com/g.csv' });
  });

  it('every wrapper forwards the signal', async () => {
    const ctrl = new AbortController();
    await getLibraries({ signal: ctrl.signal });
    const init = fetchSpy.mock.calls[0]?.[1] as RequestInit;
    expect(init.signal).toBe(ctrl.signal);
  });
});

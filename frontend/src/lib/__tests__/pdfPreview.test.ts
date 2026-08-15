import { describe, it, expect, vi, beforeEach } from 'vitest';
import { get } from 'svelte/store';

// ``pdfjs-dist`` is mocked at the module level so the store can run
// inside the jsdom test environment without booting a real worker.
// The mock must be declared before importing the store, which in turn
// must happen before the suite body executes.
vi.mock('pdfjs-dist', () => {
  const fakePage = {
    getViewport: () => ({ width: 800, height: 1131 }),
    render: () => ({ promise: Promise.resolve() }),
    cleanup: () => undefined
  };
  const fakeDoc = {
    numPages: 3,
    getPage: async () => fakePage,
    destroy: async () => undefined
  };
  return {
    GlobalWorkerOptions: { workerSrc: '' },
    getDocument: () => ({ promise: Promise.resolve(fakeDoc) }),
    version: 'test-stub'
  };
});

import { pdfPreview } from '../stores/pdfPreview';

function makeFile(name: string, type: string): File {
  return new File(['hello'], name, { type });
}

describe('pdfPreview store', () => {
  beforeEach(() => {
    pdfPreview.clear();
  });

  it('starts with no preview bound', () => {
    const state = get(pdfPreview);
    expect(state.blobUrl).toBeNull();
    expect(state.pageCount).toBe(0);
    expect(state.fileName).toBeNull();
  });

  it('binds a PDF file, resolves page count from PDF.js, and revokes the prior blob URL', async () => {
    const firstBlobUrl = get(pdfPreview).blobUrl;
    await pdfPreview.loadFile(makeFile('a.pdf', 'application/pdf'));
    const afterFirst = get(pdfPreview);
    expect(afterFirst.source).toBe('file');
    expect(afterFirst.fileName).toBe('a.pdf');
    expect(afterFirst.isPdf).toBe(true);
    expect(afterFirst.pageCount).toBe(3);
    expect(afterFirst.blobUrl).not.toBeNull();
    expect(firstBlobUrl).toBeNull();

    const secondLoad = pdfPreview.loadFile(makeFile('b.pdf', 'application/pdf'));
    await secondLoad;
    const afterSecond = get(pdfPreview);
    // A fresh blob URL should have replaced the first one.
    expect(afterSecond.blobUrl).not.toBeNull();
    expect(afterSecond.blobUrl).not.toBe(afterFirst.blobUrl);
  });

  it('treats a PNG upload as a single-page image preview', async () => {
    await pdfPreview.loadFile(makeFile('page.png', 'image/png'));
    const state = get(pdfPreview);
    expect(state.isPdf).toBe(false);
    expect(state.pageCount).toBe(1);
  });

  it('captures the OCR response blob separately so the export modal can download it', async () => {
    const ocrBlob = new Blob(['%PDF-1.4 fake'], { type: 'application/pdf' });
    await pdfPreview.loadResponse(ocrBlob, 'doc.ocr.pdf');
    const state = get(pdfPreview);
    expect(state.responseBlobUrl).not.toBeNull();
    expect(state.responseFileName).toBe('doc.ocr.pdf');
    expect(state.source).toBe('response');
    // The response is also the active preview.
    expect(state.fileName).toBe('doc.ocr.pdf');
  });

  it('keeps the response blob URL across a file clear so the export modal keeps working', async () => {
    const ocrBlob = new Blob(['%PDF-1.4 fake'], { type: 'application/pdf' });
    await pdfPreview.loadResponse(ocrBlob, 'doc.ocr.pdf');
    const responseBefore = get(pdfPreview).responseBlobUrl;
    pdfPreview.clear();
    const after = get(pdfPreview);
    expect(after.blobUrl).toBeNull();
    expect(after.responseBlobUrl).toBe(responseBefore);
  });

  it('clamps setPage to the [1, pageCount] range', async () => {
    await pdfPreview.loadFile(makeFile('a.pdf', 'application/pdf'));
    pdfPreview.setPage(0);
    expect(get(pdfPreview).currentPage).toBe(1);
    pdfPreview.setPage(99);
    expect(get(pdfPreview).currentPage).toBe(3);
    pdfPreview.setPage(2);
    expect(get(pdfPreview).currentPage).toBe(2);
  });

  it('paints a page onto a target canvas', async () => {
    await pdfPreview.loadFile(makeFile('a.pdf', 'application/pdf'));
    const canvas = document.createElement('canvas');
    await pdfPreview.renderPage(canvas, 1.0);
    // The mock viewport is 800x1131, so the canvas should be sized to match.
    expect(canvas.width).toBe(800);
    expect(canvas.height).toBe(1131);
  });
});

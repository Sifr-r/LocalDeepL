/**
 * PDF / image preview store.
 *
 * Owns the lifecycle of the blob URL + PDF.js document proxy used by the
 * workstation canvas. Components subscribe to the store to know whether
 * a preview is available and to which page they should render; they call
 * :meth:`renderPage` to paint a specific page onto a target ``<canvas>``.
 *
 * The store deliberately hides the PDF.js types from components — the
 * canvas only needs the resolved page count, the current page index, and
 * a paint method. Importing ``pdfjs-dist`` from a component pulls in
 * the worker chunk; isolating that import in this file keeps the bundle
 * surface narrow and lets unit tests mock the render path entirely.
 */

import { writable, get, type Readable, type Writable } from 'svelte/store';

// PDF.js 4+ ships ESM-only and expects a worker URL at runtime. Vite resolves
// the ``?url`` import to the asset's hashed URL so the worker loads from the
// same origin the app is served from.
import * as pdfjsLib from 'pdfjs-dist';
import workerSrc from 'pdfjs-dist/build/pdf.worker.min.mjs?url';

import type {
  PDFDocumentProxy,
  PDFPageProxy
} from 'pdfjs-dist/types/src/display/api';

let workerConfigured = false;
function ensureWorker(): void {
  if (workerConfigured) return;
  pdfjsLib.GlobalWorkerOptions.workerSrc = workerSrc;
  workerConfigured = true;
}

export type PreviewSource = 'file' | 'response' | null;

export interface PdfPreviewState {
  /** What the preview is currently showing. ``null`` when no file is loaded. */
  source: PreviewSource;
  /** Display name of the active file (uploaded or OCR result). */
  fileName: string | null;
  /** Object URL pointing at the active blob (uploaded file, OCR'd PDF, or image). */
  blobUrl: string | null;
  /** ``true`` for PDF sources, ``false`` for single-page image inputs. */
  isPdf: boolean;
  /** Number of pages in the preview. ``1`` for images. */
  pageCount: number;
  /** 1-indexed current page. */
  currentPage: number;
  /** Bumped whenever the source changes so async renders can drop stale results. */
  version: number;
  /**
   * Latest OCR result — the searchable PDF returned by ``/api/process``.
   * Kept on the store so :file:`ExportModal.svelte` can download it
   * without re-fetching. ``null`` until the first successful run.
   */
  responseBlobUrl: string | null;
  responseFileName: string | null;
}

const initialState: PdfPreviewState = {
  source: null,
  fileName: null,
  blobUrl: null,
  isPdf: false,
  pageCount: 0,
  currentPage: 1,
  version: 0,
  responseBlobUrl: null,
  responseFileName: null
};

interface PdfPreviewStore extends Readable<PdfPreviewState> {
  /**
   * Load a freshly selected user file (PDF or image). Creates the
   * underlying object URL and resolves the page count via PDF.js. Safe
   * to call repeatedly — the previous blob URL and document are
   * released before the new one is bound.
   */
  loadFile(file: File): Promise<void>;
  /**
   * Bind the OCR response PDF returned by ``/api/process``. Keeps a
   * separate ``responseBlobUrl`` so the export modal can download the
   * result even if the user later swaps the file input.
   */
  loadResponse(blob: Blob, fileName: string): Promise<void>;
  /** Switch the active page (1-indexed). */
  setPage(page: number): void;
  /**
   * Paint the current page onto a target ``<canvas>`` at the given CSS
   * scale. Resolves once the next animation frame is committed. Returns
   * early (without throwing) when the preview has been disposed or the
   * page index has moved on — the ``version`` token guards against
   * late paints from a superseded render.
   */
  renderPage(canvas: HTMLCanvasElement, scale?: number): Promise<void>;
  /** Release object URLs, drop the PDF doc, reset to initial state. */
  clear(): void;
}

function isPdfLike(file: Blob): boolean {
  const type = (file.type || '').toLowerCase();
  if (type === 'application/pdf' || type === 'application/x-pdf') return true;
  // Some browsers / OSes hand us an empty MIME for PDFs.
  if (type === '' && file instanceof File) {
    return file.name.toLowerCase().endsWith('.pdf');
  }
  return false;
}

function createPdfPreviewStore(): PdfPreviewStore {
  const state: Writable<PdfPreviewState> = writable({ ...initialState });
  let pdfDoc: PDFDocumentProxy | null = null;
  let activeVersion = 0;

  function resetTransient(): void {
    pdfDoc = null;
    activeVersion += 1;
  }

  async function loadFromBlob(blob: Blob, fileName: string, source: PreviewSource): Promise<void> {
    ensureWorker();
    const prev = get(state);
    if (prev.blobUrl) {
      try { URL.revokeObjectURL(prev.blobUrl); } catch { /* ignore */ }
    }
    resetTransient();
    const blobUrl = URL.createObjectURL(blob);
    const isPdf = isPdfLike(blob);
    let pageCount = 1;
    if (isPdf) {
      try {
        const task = pdfjsLib.getDocument({ url: blobUrl });
        const doc = await task.promise;
        pdfDoc = doc;
        pageCount = doc.numPages;
      } catch (err) {
        // PDF.js failed to parse — surface a single-page placeholder so the
        // user still sees something rather than a blank canvas. The export
        // path can still use the responseBlobUrl when it exists.
        console.warn('pdfPreview: PDF.js failed to parse blob', err);
        try { URL.revokeObjectURL(blobUrl); } catch { /* ignore */ }
        state.set({ ...initialState });
        return;
      }
    }
    activeVersion += 1;
    state.set({
      source,
      fileName,
      blobUrl,
      isPdf,
      pageCount,
      currentPage: 1,
      version: activeVersion,
      // Preserve any previously-captured response PDF when binding the file.
      responseBlobUrl: prev.responseBlobUrl,
      responseFileName: prev.responseFileName
    });
  }

  function setPage(page: number): void {
    state.update((curr) => {
      if (curr.pageCount === 0) return curr;
      const next = Math.max(1, Math.min(curr.pageCount, Math.floor(page)));
      if (next === curr.currentPage) return curr;
      // Bump the version so any in-flight render for the old page aborts.
      activeVersion += 1;
      return { ...curr, currentPage: next, version: activeVersion };
    });
  }

  async function renderPage(canvas: HTMLCanvasElement, scale = 1.25): Promise<void> {
    const curr = get(state);
    if (!curr.blobUrl) return;
    if (!curr.isPdf) {
      // Image preview: hand the <img> element over to the caller via canvas
      // drawImage so the layout stays consistent (the canvas is the
      // single rendering surface in the workstation viewer).
      const img = new Image();
      img.crossOrigin = 'anonymous';
      img.src = curr.blobUrl;
      await new Promise<void>((resolve, reject) => {
        img.onload = () => resolve();
        img.onerror = () => reject(new Error('Failed to load image preview'));
      });
      if (get(state).version !== curr.version) return;
      canvas.width = Math.round(img.naturalWidth * scale);
      canvas.height = Math.round(img.naturalHeight * scale);
      const ctx = canvas.getContext('2d');
      if (ctx) ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      return;
    }
    if (!pdfDoc) return;
    const myVersion = curr.version;
    const page: PDFPageProxy = await pdfDoc.getPage(curr.currentPage);
    if (get(state).version !== myVersion) return;
    const viewport = page.getViewport({ scale });
    const dpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1;
    canvas.width = Math.round(viewport.width * dpr);
    canvas.height = Math.round(viewport.height * dpr);
    // Only the logical width is pinned; height stays ``auto`` (via the
    // canvas element's ``h-auto max-w-full`` classes) so a container
    // narrower than the logical size shrinks the page proportionally
    // instead of squashing it against a fixed pixel height.
    canvas.style.width = `${Math.round(viewport.width)}px`;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const transform = dpr !== 1 ? [dpr, 0, 0, dpr, 0, 0] : undefined;
    // ``canvas`` is the field PDF.js's public typings now require; the
    // ``canvasContext`` alias is kept for forward-compat with older
    // worker builds that still read from it. The cast is contained here
    // because the public type drifts between minor versions.
    const renderParams = { canvas, canvasContext: ctx, viewport, transform } as unknown as Parameters<typeof page.render>[0];
    await page.render(renderParams).promise;
    if (get(state).version !== myVersion) return;
  }

  function clear(): void {
    const curr = get(state);
    if (curr.blobUrl) {
      try { URL.revokeObjectURL(curr.blobUrl); } catch { /* ignore */ }
    }
    // Preserve the OCR response across clears so the export modal keeps
    // working even when the user removes the original upload.
    state.set({ ...initialState, responseBlobUrl: curr.responseBlobUrl, responseFileName: curr.responseFileName });
    resetTransient();
  }

  async function loadFile(file: File): Promise<void> {
    await loadFromBlob(file, file.name, 'file');
  }

  async function loadResponse(blob: Blob, fileName: string): Promise<void> {
    const prev = get(state);
    if (prev.responseBlobUrl) {
      try { URL.revokeObjectURL(prev.responseBlobUrl); } catch { /* ignore */ }
    }
    const responseBlobUrl = URL.createObjectURL(blob);
    state.update((curr) => ({
      ...curr,
      responseBlobUrl,
      responseFileName: fileName
    }));
    // Also swap the active preview to the response PDF so the user sees
    // the OCR result instead of the original file.
    await loadFromBlob(blob, fileName, 'response');
  }

  return {
    subscribe: state.subscribe,
    loadFile,
    loadResponse,
    setPage,
    renderPage,
    clear
  };
}

export const pdfPreview = createPdfPreviewStore();

export type { PdfPreviewStore };

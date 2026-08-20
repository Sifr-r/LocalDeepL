<script lang="ts">
  /**
   * Lightweight PDF.js preview pane used in the metadata panel.
   *
   * Renders every page of the bound blob URL onto a small canvas and
   * stacks the canvases vertically so the user can scroll through the
   * structured OCR result without leaving the workstation. The
   * implementation is intentionally minimal: PDF.js paints each page
   * once at a fixed ``preview-scale``; no zoom, no text-layer selection.
   *
   * The Svelte action ``paintPage`` owns the per-page canvas lifecycle:
   * it allocates the canvas, paints into it, and tears it down on
   * unmount. This keeps the component declarative — no
   * ``bind:this``-into-array gymnastics, no manual ``appendChild``.
   */
  import { onDestroy, tick } from 'svelte';
  import * as pdfjsLib from 'pdfjs-dist';
  import workerSrc from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
  import { humanizeApiError } from '$lib/utils/error';
  import type {
    PDFDocumentProxy,
    PDFPageProxy
  } from 'pdfjs-dist/types/src/display/api';

  export let blobUrl: string;
  /** Visual scale relative to the PDF's native pixel dimensions. */
  export let previewScale: number = 0.6;

  let numPages = 0;
  let errorMessage: string | null = null;
  let loading = true;
  let doc: PDFDocumentProxy | null = null;
  // Each ``paintPage`` action registers a destructor; the cancellation
  // set lets the parent render loop stop an in-flight paint mid-stream
  // when the user changes the source PDF. The set is never read from a
  // Svelte-reactive context — a plain ``Set`` is the right tool, and
  // the ``prefer-svelte-reactivity`` rule is locally disabled to
  // silence the false positive.
  // eslint-disable-next-line svelte/prefer-svelte-reactivity
  const pendingCancels: Set<() => void> = new Set();
  // Bumped on every ``blobUrl`` / ``previewScale`` change so any
  // in-flight paints know to abort.
  let renderEpoch = 0;

  pdfjsLib.GlobalWorkerOptions.workerSrc = workerSrc;

  type PagePaint = (host: HTMLDivElement) => {
    update?: (params: { doc: PDFDocumentProxy; pageNumber: number; scale: number }) => void;
    destroy?: () => void;
  };

  function paintPage(node: HTMLDivElement, initial: { doc: PDFDocumentProxy; pageNumber: number; scale: number }): ReturnType<PagePaint> {
    const canvas = document.createElement('canvas');
    canvas.className = 'block w-full h-auto';
    node.replaceChildren(canvas);

    let cancelled = false;
    pendingCancels.add(() => { cancelled = true; });

    async function paint(target: { doc: PDFDocumentProxy; pageNumber: number; scale: number }): Promise<void> {
      let page: PDFPageProxy | undefined;
      try {
        page = await target.doc.getPage(target.pageNumber);
        if (cancelled) {
          return;
        }
        const viewport = page.getViewport({ scale: target.scale });
        canvas.width = Math.round(viewport.width);
        canvas.height = Math.round(viewport.height);
        const ctx = canvas.getContext('2d');
        if (!ctx) {
          throw new Error('2D canvas context unavailable');
        }
        const renderParams = {
          canvas,
          canvasContext: ctx,
          viewport
        } as unknown as Parameters<typeof page.render>[0];
        await page.render(renderParams).promise;
      } catch (err) {
        if (cancelled) return;
        // Cancellation is expected when the user switches source.
        const name = (err as { name?: string } | null)?.name;
        if (name === 'RenderingCancelledException') return;
        throw err;
      } finally {
        if (page) {
          try {
            page.cleanup();
          } catch {
            /* ignore */
          }
        }
      }
    }

    void paint(initial);

    return {
      update(next) {
        if (cancelled) return;
        void paint(next);
      },
      destroy() {
        cancelled = true;
        node.replaceChildren();
      }
    };
  }

  async function loadAndBind(): Promise<void> {
    const epoch = ++renderEpoch;
    errorMessage = null;
    numPages = 0;
    loading = true;
    // Cancel any in-flight paints from the previous source.
    pendingCancels.forEach((fn) => fn());
    pendingCancels.clear();
    if (doc) {
      try { await doc.cleanup(); } catch { /* ignore */ }
      try { await (doc as { destroy?: () => Promise<void> | void }).destroy?.(); } catch { /* ignore */ }
      doc = null;
    }
    try {
      const task = pdfjsLib.getDocument({ url: blobUrl });
      const next = await task.promise;
      if (epoch !== renderEpoch) {
        try { await next.cleanup(); } catch { /* ignore */ }
        try { await (next as { destroy?: () => Promise<void> | void }).destroy?.(); } catch { /* ignore */ }
        return;
      }
      doc = next;
      numPages = next.numPages;
      // Let Svelte mount the page placeholders before paints start.
      await tick();
      if (epoch !== renderEpoch) return;
      loading = false;
    } catch (err) {
      if (epoch !== renderEpoch) return;
      const name = (err as { name?: string } | null)?.name;
      if (name === 'RenderingCancelledException') return;
      errorMessage = humanizeApiError(err);
      loading = false;
    }
  }

  $: if (blobUrl) {
    void loadAndBind();
  }

  onDestroy(() => {
    pendingCancels.forEach((fn) => fn());
    pendingCancels.clear();
    if (doc) {
      try { void doc.cleanup(); } catch { /* ignore */ }
      try { void (doc as { destroy?: () => Promise<void> | void }).destroy?.(); } catch { /* ignore */ }
      doc = null;
    }
  });
</script>

<div class="space-y-2">
  {#if loading && numPages === 0}
    <p class="text-[11px] font-mono text-foreground-muted italic">Rendering OCR pages…</p>
  {/if}
  {#if errorMessage}
    <p class="text-[11px] font-mono text-danger">Preview error: {errorMessage}</p>
  {/if}
  {#if doc && numPages > 0}
    {#each Array.from({ length: numPages }, (_, i) => i + 1) as pageNumber (pageNumber)}
      <div class="border border-border rounded-sm overflow-hidden bg-card-raised">
        <div
          class="block w-full h-auto"
          use:paintPage={{ doc, pageNumber, scale: previewScale }}
        ></div>
        <div class="px-2 py-0.5 text-[10px] font-mono text-foreground-muted border-t border-border bg-card">
          Page {pageNumber}
        </div>
      </div>
    {/each}
  {/if}
</div>

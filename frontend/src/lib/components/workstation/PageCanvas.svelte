<script lang="ts">
  import { documentStore, jobStore } from '../../stores/appStore';
  import { pdfPreview } from '../../stores/pdfPreview';
  import Card from '../ui/Card.svelte';
  import type { BBoxItem } from '../../types/api';

  // ``pages`` is kept for legacy code paths (text-artifact page split, etc.)
  // and for the streamed bbox grouping below.
  $: pages = ($documentStore.pages || []) as { text?: string; image_url?: string }[];
  $: currentPageIndex = $documentStore.selectedPageIndex || 0;
  $: legacyPage = pages[currentPageIndex] || null;
  $: streamedBoxes = ($documentStore.bboxes || []).filter((b) => b.page === currentPageIndex);
  $: totalPages = $pdfPreview.pageCount || $documentStore.pageCount || 0;
  // The preview is the single source of truth for "is there something to
  // show". Falling back to streamed bboxes keeps the canvas responsive
  // during the first few hundred ms after a run starts (before the
  // response PDF lands).
  $: hasDocument = $pdfPreview.blobUrl !== null || streamedBoxes.length > 0;
  $: completedPages = $jobStore.completedPages || [];

  let canvasContainer: HTMLDivElement;
  let renderCanvas: HTMLCanvasElement;
  let renderToken = 0;
  let renderError: string | null = null;

  // Re-render the active page whenever the preview state (source, page,
  // version) changes. ``renderToken`` guards against overlapping renders
  // when navigation happens faster than PDF.js can paint. The
  // ``$pdfPreview`` read inside the reactive block keeps the rule live.
  $: if (renderCanvas && $pdfPreview.blobUrl) {
    void repaint();
  }

  async function repaint(): Promise<void> {
    const myToken = ++renderToken;
    renderError = null;
    try {
      await pdfPreview.renderPage(renderCanvas, 1.5);
      if (myToken !== renderToken) return;
    } catch (err: unknown) {
      if (myToken !== renderToken) return;
      const message = err instanceof Error ? err.message : String(err);
      renderError = message || 'Preview render failed';
    }
  }

  function gotoPage(direction: -1 | 1): void {
    const next = currentPageIndex + direction + 1; // 1-indexed
    pdfPreview.setPage(next);
    documentStore.update((d) => ({ ...d, selectedPageIndex: Math.max(0, next - 1) }));
  }

  function prevPage() {
    if (currentPageIndex > 0) gotoPage(-1);
  }
  function nextPage() {
    if (currentPageIndex < totalPages - 1) gotoPage(1);
  }

  function boxStyle(box: BBoxItem): string {
    const [x0, y0, x1, y1] = box.bbox;
    const left = Math.max(0, Math.min(1, x0)) * 100;
    const top = Math.max(0, Math.min(1, y0)) * 100;
    const width = Math.max(0, Math.min(1, x1) - Math.max(0, x0)) * 100;
    const height = Math.max(0, Math.min(1, y1) - Math.max(0, y0)) * 100;
    return `left: ${left}%; top: ${top}%; width: ${width}%; height: ${height}%;`;
  }

  function confidenceLabel(box: BBoxItem): string {
    return box.confidence == null ? '—' : `${Math.round(box.confidence * 100)}%`;
  }
</script>

<Card padding="none" className="flex-1 flex flex-col min-h-0 overflow-hidden">
  <!-- Toolbar -->
  <div class="h-11 px-4 flex items-center justify-between border-b border-border bg-card-raised shrink-0">
    <div class="flex items-center gap-2 min-w-0">
      <span class="text-sm font-display font-semibold text-foreground">Document viewer</span>
      {#if $pdfPreview.fileName}
        <span class="text-xs text-foreground-muted truncate" title={$pdfPreview.fileName}>
          · {$pdfPreview.fileName}
        </span>
      {:else if $documentStore.filename}
        <span class="text-xs text-foreground-muted truncate" title={$documentStore.filename}>
          · {$documentStore.filename}
        </span>
      {/if}
      {#if $pdfPreview.source === 'response'}
        <span class="text-[10px] font-mono uppercase tracking-wide text-brand">OCR result</span>
      {/if}
    </div>

    {#if totalPages > 0}
      <div class="flex items-center gap-1 text-xs font-mono text-foreground-muted">
        <button
          type="button"
          class="h-7 w-7 inline-flex items-center justify-center rounded-md text-foreground-muted hover:text-foreground hover:bg-muted disabled:opacity-40 transition-colors"
          disabled={currentPageIndex === 0}
          aria-label="Previous page"
          title="Previous page"
          on:click={prevPage}
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <span class="px-2">
          Page {currentPageIndex + 1} of {totalPages}
          {#if completedPages.includes(currentPageIndex)}
            <span class="text-success" title="Page OCR complete">✓</span>
          {/if}
        </span>
        <button
          type="button"
          class="h-7 w-7 inline-flex items-center justify-center rounded-md text-foreground-muted hover:text-foreground hover:bg-muted disabled:opacity-40 transition-colors"
          disabled={currentPageIndex >= totalPages - 1}
          aria-label="Next page"
          title="Next page"
          on:click={nextPage}
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
          </svg>
        </button>
      </div>
    {/if}
  </div>

  <!-- Canvas — auto-margin centering (m-auto on the child) instead of
       items-center so an oversized page stays scrollable from its top
       edge instead of overflowing into unreachable space. -->
  <div
    bind:this={canvasContainer}
    class="flex-1 relative flex p-6 overflow-auto bg-spatial-grid min-h-[400px]"
  >
    {#if hasDocument}
      <div class="relative m-auto inline-block border border-border shadow-2xl rounded-md overflow-hidden bg-card">
        {#if $pdfPreview.blobUrl}
          <canvas
            bind:this={renderCanvas}
            class="block max-w-full h-auto"
            data-page={$pdfPreview.currentPage}
          ></canvas>
        {:else if legacyPage?.image_url}
          <img
            src={String(legacyPage.image_url)}
            alt="Page {currentPageIndex + 1}"
            class="block max-w-full h-auto"
          />
        {/if}

        <!-- Streamed block overlays (normalized 0..1 → %) -->
        {#each streamedBoxes as box (box.block_id)}
          <div
            class={[
              'absolute border-2 transition-colors cursor-pointer group',
              box.revised
                ? 'border-success bg-success/10 hover:bg-success/20'
                : 'border-brand bg-brand/10 hover:border-success hover:bg-success/20'
            ].join(' ')}
            style={boxStyle(box)}
            role="region"
            aria-label="Text block {box.block + 1} on page {box.page + 1}"
          >
            <div class="opacity-0 group-hover:opacity-100 transition-opacity absolute -top-6 left-0 bg-card text-foreground border border-border font-mono text-[10px] px-1.5 py-0.5 rounded shadow pointer-events-none whitespace-nowrap z-20 max-w-[320px] truncate">
              {box.revised ? 'revised · ' : ''}{confidenceLabel(box)} · {box.text}
            </div>
          </div>
        {/each}

        {#if renderError}
          <!-- Promoted to a top banner (was an 11px footer band that
               was easy to miss). Keeps the error attached to the
               document, not the empty state. -->
          <div class="absolute top-0 inset-x-0 z-10 px-3 py-2 bg-danger/15 border-b border-danger/30 text-danger text-xs font-mono flex items-start gap-2 backdrop-blur-sm">
            <svg class="w-3.5 h-3.5 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div class="min-w-0">
              <p class="font-semibold">Preview failed</p>
              <p class="opacity-80 truncate" title={renderError}>{renderError}</p>
            </div>
          </div>
        {/if}
      </div>
    {:else if renderError}
      <!-- Error empty state: a non-PDF upload (or a corrupt PDF) lands
           here because `hasDocument` flips back to false when the canvas
           never produces a render. Without this branch the user only
           sees the generic "No document loaded" copy. -->
      <div class="m-auto flex flex-col items-center justify-center gap-3 text-center max-w-sm">
        <div class="w-16 h-16 rounded-full bg-danger/15 border border-danger/30 flex items-center justify-center">
          <svg class="w-7 h-7 text-danger" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <div class="space-y-1">
          <p class="text-sm font-display font-semibold text-foreground">Couldn’t render this file</p>
          <p class="text-xs text-foreground-muted font-mono break-words">{renderError}</p>
        </div>
      </div>
    {:else}
      <!-- Empty state -->
      <div class="m-auto flex flex-col items-center justify-center gap-3 text-center text-foreground-muted">
        <div class="w-16 h-16 rounded-full bg-card border border-border flex items-center justify-center">
          <svg class="w-7 h-7 text-foreground-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        </div>
        <div class="space-y-1">
          <p class="text-sm font-display font-semibold text-foreground">No document loaded</p>
          <p class="text-xs font-mono text-foreground-muted">Upload a file on the left panel — recognized text blocks stream in live during processing</p>
        </div>
      </div>
    {/if}
  </div>
</Card>

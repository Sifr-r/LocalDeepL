<script lang="ts">
  import { documentStore } from '../../stores/appStore';
  import Card from '../ui/Card.svelte';
  import type { BoundingBox, PageResult } from '../../types/api';

  $: currentPageIndex = ($documentStore as any).selectedPageIndex || 0;
  $: pages = ($documentStore as any).pages || [];
  $: currentPage = (pages.length > currentPageIndex ? pages[currentPageIndex] : null) as PageResult | null;
  $: boxes = (currentPage?.boxes || []) as BoundingBox[];

  let canvasContainer: HTMLDivElement;
  let hoveredBox: BoundingBox | null = null;

  function prevPage() {
    if (currentPageIndex > 0) {
      documentStore.update((d: any) => ({ ...d, selectedPageIndex: currentPageIndex - 1 }));
    }
  }

  function nextPage() {
    if (currentPageIndex < pages.length - 1) {
      documentStore.update((d: any) => ({ ...d, selectedPageIndex: currentPageIndex + 1 }));
    }
  }
</script>

<Card padding="none" className="flex-1 flex flex-col min-h-0 overflow-hidden">
  <!-- Toolbar -->
  <div class="h-11 px-4 flex items-center justify-between border-b border-border bg-card-raised shrink-0">
    <div class="flex items-center gap-2 min-w-0">
      <span class="text-sm font-display font-semibold text-foreground">Document viewer</span>
      {#if ($documentStore as any).filename}
        <span class="text-xs text-foreground-muted truncate" title={($documentStore as any).filename}>
          · {($documentStore as any).filename}
        </span>
      {/if}
    </div>

    {#if pages.length > 0}
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
        <span class="px-2">Page {currentPageIndex + 1} of {pages.length}</span>
        <button
          type="button"
          class="h-7 w-7 inline-flex items-center justify-center rounded-md text-foreground-muted hover:text-foreground hover:bg-muted disabled:opacity-40 transition-colors"
          disabled={currentPageIndex >= pages.length - 1}
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

  <!-- Canvas -->
  <div
    bind:this={canvasContainer}
    class="flex-1 relative flex items-center justify-center p-6 overflow-auto bg-spatial-grid min-h-[400px]"
  >
    {#if currentPage}
      <div class="relative max-w-full max-h-full border border-border shadow-2xl rounded-md overflow-hidden bg-card">
        {#if currentPage.image_url}
          <img
            src={String(currentPage.image_url)}
            alt="Page {currentPage.page_number || 1}"
            class="max-w-full h-auto block select-none"
          />
        {:else}
          <!-- Empty document page mock for when image hasn't loaded yet -->
          <div class="w-[600px] h-[800px] flex flex-col p-8 space-y-4 bg-card-raised">
            <div class="w-1/3 h-4 bg-muted rounded"></div>
            <div class="w-full h-2 bg-muted rounded"></div>
            <div class="w-full h-2 bg-muted rounded"></div>
            <div class="w-4/5 h-2 bg-muted rounded"></div>
            <div class="w-full h-32 bg-card rounded border border-dashed border-border"></div>
          </div>
        {/if}

        <!-- Bounding box overlays -->
        {#each boxes as box, idx}
          <div
            class="absolute border-2 border-brand bg-brand/10 hover:border-success hover:bg-success/20 transition-colors cursor-pointer group"
            style="left: {box.x}px; top: {box.y}px; width: {box.width}px; height: {box.height}px;"
            on:mouseenter={() => (hoveredBox = box)}
            on:mouseleave={() => (hoveredBox = null)}
            role="region"
            aria-label="Bounding box {idx + 1}"
          >
            <div class="opacity-0 group-hover:opacity-100 transition-opacity absolute -top-6 left-0 bg-card text-foreground border border-border font-mono text-[10px] px-1.5 py-0.5 rounded shadow pointer-events-none whitespace-nowrap z-20">
              {box.label || `Box #${idx + 1}`} · {Math.round((box.confidence || 0.95) * 100)}%
            </div>
          </div>
        {/each}
      </div>
    {:else}
      <!-- Empty state -->
      <div class="flex flex-col items-center justify-center gap-3 text-center text-foreground-muted">
        <div class="w-16 h-16 rounded-full bg-card border border-border flex items-center justify-center">
          <svg class="w-7 h-7 text-foreground-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        </div>
        <div class="space-y-1">
          <p class="text-sm font-display font-semibold text-foreground">No document loaded</p>
          <p class="text-xs font-mono text-foreground-muted">Upload a file on the left panel to preview page rendering</p>
        </div>
      </div>
    {/if}
  </div>
</Card>

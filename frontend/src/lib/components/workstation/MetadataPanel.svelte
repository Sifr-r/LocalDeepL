<script lang="ts">
  import { documentStore, exportModalOpen, jobStore } from '../../stores/appStore';
  import { pdfPreview } from '../../stores/pdfPreview';
  import Card from '../ui/Card.svelte';
  import SectionHeader from '../ui/SectionHeader.svelte';
  import Badge, { type BadgeVariant } from '../ui/Badge.svelte';
  import Button from '../ui/Button.svelte';
  import SegmentedControl from '../ui/SegmentedControl.svelte';
  import PdfMiniViewer from './PdfMiniViewer.svelte';

  $: currentPageIndex = $documentStore.selectedPageIndex || 0;
  $: pages = $documentStore.pages || [];
  $: currentPage = pages[currentPageIndex] || null;
  $: streamedBoxes = $documentStore.bboxes || [];
  $: totalPages = Math.max(pages.length, $documentStore.pageCount || 0);

  // Live confidence: average the streamed block confidences when present,
  // then the job quality summary, then the response summary. Audit P2-10:
  // before any real result exists every source is null and the panel
  // renders "—" instead of a fake "Overall confidence 100%".
  $: scoredBoxes = streamedBoxes.filter((b) => b.confidence != null);
  $: streamedAvg = scoredBoxes.length
    ? scoredBoxes.reduce((sum, b) => sum + (b.confidence as number), 0) / scoredBoxes.length
    : null;
  $: confidenceSource =
    streamedAvg ??
    $documentStore.confidenceSummary?.average ??
    $jobStore.qualitySummary?.avg_confidence ??
    $documentStore.confidence ??
    null;
  $: confidencePercent = Math.round((confidenceSource ?? 0) * 100);

  $: confidenceLevel = (confidenceSource == null
    ? 'neutral'
    : confidencePercent >= 90
    ? 'success'
    : confidencePercent >= 70
    ? 'warning'
    : 'danger') as BadgeVariant;

  // The most recent page a streamed block landed on — drives "Active page"
  // during a run (block_complete frames) instead of the user's selection.
  $: lastStreamedPage = streamedBoxes.length
    ? Math.max(...streamedBoxes.map((b) => b.page))
    : null;
  $: activePageLabel =
    lastStreamedPage != null
      ? String(lastStreamedPage + 1)
      : totalPages > 0
      ? String(currentPageIndex + 1)
      : '—';

  // Extracted text: prefer server page text; fall back to the live
  // streamed blocks grouped by page so the panel fills in during a run.
  $: streamedText = streamedBoxes
    .slice()
    .sort((a, b) => a.page - b.page || a.block - b.block)
    .map((b) => b.text)
    .join('\n');

  // The default preview is the OCR'd PDF (preserves structure like-for-like).
  // The legacy per-page text view stays available behind a toggle for users
  // who want the raw recognized text.
  let previewMode: 'pdf' | 'text' = 'pdf';
  $: hasResponsePdf = $pdfPreview.responseBlobUrl !== null;
  $: effectivePreviewMode = hasResponsePdf ? previewMode : 'text';
</script>

<Card padding="md" class="flex-1 flex flex-col gap-5 overflow-y-auto">
  <SectionHeader title="Document metadata" />

  <!-- Confidence summary -->
  <div class="surface-inset p-3 space-y-2">
    <div class="flex items-center justify-between">
      <span class="text-xs text-foreground-muted">Overall confidence</span>
      <Badge variant={confidenceLevel} size="md" dot>
        {confidenceSource != null ? `${confidencePercent}%` : '—'}
      </Badge>
    </div>
    <div class="w-full h-1.5 rounded-full bg-muted overflow-hidden">
      <div
        class={[
          'h-full transition-all duration-300',
          confidenceLevel === 'success' ? 'bg-success' :
          confidenceLevel === 'warning' ? 'bg-warning' :
          confidenceLevel === 'danger' ? 'bg-danger' : 'bg-foreground-muted'
        ].join(' ')}
        style="width: {confidenceSource != null ? confidencePercent : 0}%;"
      ></div>
    </div>
  </div>

  <!-- Pipeline stats -->
  <div>
    <p class="form-label">Pipeline stats</p>
    <div class="surface-inset p-3 space-y-1.5 font-mono text-xs">
      <div class="flex justify-between">
        <span class="text-foreground-muted">Total pages</span>
        <span class="text-foreground">{totalPages || '—'}</span>
      </div>
      <div class="flex justify-between">
        <span class="text-foreground-muted">Active page</span>
        <span class="text-foreground">{activePageLabel}</span>
      </div>
      <div class="flex justify-between">
        <span class="text-foreground-muted">Blocks streamed</span>
        <span class="text-foreground">{streamedBoxes.length || '—'}</span>
      </div>
      <div class="flex justify-between gap-2">
        <span class="text-foreground-muted shrink-0">Artifact ID</span>
        <span class="text-brand truncate" title={$documentStore.textArtifactId || $documentStore.textArtifacts?.[0]?.id || 'N/A'}>
          {$documentStore.textArtifactId || $documentStore.textArtifacts?.[0]?.id || 'N/A'}
        </span>
      </div>
    </div>
  </div>

  <!-- Extracted text preview -->
  <div class="flex-1 flex flex-col min-h-0">
    <div class="flex items-center justify-between mb-1.5">
      <p class="form-label !mb-0">Extracted content</p>
      {#if hasResponsePdf}
        <SegmentedControl
          bind:value={previewMode}
          ariaLabel="Preview mode"
          options={[
            { value: 'pdf', label: 'OCR PDF', title: 'Render the OCR\u2019d PDF (preserves the original layout)' },
            { value: 'text', label: 'Text', title: 'Show the raw recognized text' }
          ]}
        />
      {/if}
    </div>
    <!-- Bounded scroll box: the OCR PDF mini viewer stacks every page,
         which would otherwise stretch the metadata column (and, via the
         grid's items-stretch, the whole workstation) to thousands of px. -->
    <div class="flex-1 surface-inset p-3 overflow-y-auto min-h-[160px] max-h-[520px]">
      {#if effectivePreviewMode === 'pdf' && $pdfPreview.responseBlobUrl}
        <PdfMiniViewer blobUrl={$pdfPreview.responseBlobUrl} previewScale={0.6} />
      {:else if currentPage?.text}
        <pre class="font-mono text-xs text-foreground whitespace-pre-wrap leading-relaxed">{currentPage.text}</pre>
      {:else if pages.length > 0}
        <pre class="font-mono text-xs text-foreground whitespace-pre-wrap leading-relaxed">{pages.map((p) => p.text).join('\n\n--- Page Break ---\n\n')}</pre>
      {:else if streamedText}
        <pre class="font-mono text-xs text-foreground whitespace-pre-wrap leading-relaxed">{streamedText}</pre>
      {:else}
        <p class="text-foreground-muted italic text-xs">No extracted content available. Upload and process a document to view results.</p>
      {/if}
    </div>
  </div>

  <Button
    variant="outline"
    fullWidth
    disabled={!$documentStore.textArtifactId}
    title={$documentStore.textArtifactId ? 'Download OCR outputs' : 'Process a document first'}
    on:click={() => exportModalOpen.set(true)}
  >
    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
    </svg>
    <span>Export results…</span>
  </Button>
</Card>

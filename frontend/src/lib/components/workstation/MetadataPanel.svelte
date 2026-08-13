<script lang="ts">
  import { documentStore, exportModalOpen } from '../../stores/appStore';
  import Card from '../ui/Card.svelte';
  import SectionHeader from '../ui/SectionHeader.svelte';
  import Badge, { type BadgeVariant } from '../ui/Badge.svelte';
  import Button from '../ui/Button.svelte';

  $: currentPageIndex = $documentStore.selectedPageIndex || 0;
  $: pages = $documentStore.pages || [];
  $: currentPage = pages[currentPageIndex] || null;
  $: confidencePercent = Math.round(($documentStore.confidenceSummary?.average || $documentStore.confidence || 0.92) * 100);

  $: confidenceLevel = (confidencePercent >= 90 ? 'success' : confidencePercent >= 70 ? 'warning' : 'danger') as BadgeVariant;
</script>

<Card padding="md" class="flex-1 flex flex-col gap-5 overflow-y-auto">
  <SectionHeader title="Document metadata" />

  <!-- Confidence summary -->
  <div class="surface-inset p-3 space-y-2">
    <div class="flex items-center justify-between">
      <span class="text-xs text-foreground-muted">Overall confidence</span>
      <Badge variant={confidenceLevel} size="md" dot>
        {confidencePercent}%
      </Badge>
    </div>
    <div class="w-full h-1.5 rounded-full bg-muted overflow-hidden">
      <div
        class={[
          'h-full transition-all duration-300',
          confidenceLevel === 'success' ? 'bg-success' :
          confidenceLevel === 'warning' ? 'bg-warning' : 'bg-danger'
        ].join(' ')}
        style="width: {confidencePercent}%;"
      ></div>
    </div>
  </div>

  <!-- Pipeline stats -->
  <div>
    <p class="form-label">Pipeline stats</p>
    <div class="surface-inset p-3 space-y-1.5 font-mono text-xs">
      <div class="flex justify-between">
        <span class="text-foreground-muted">Total pages</span>
        <span class="text-foreground">{pages.length}</span>
      </div>
      <div class="flex justify-between">
        <span class="text-foreground-muted">Active page</span>
        <span class="text-foreground">{pages.length > 0 ? currentPageIndex + 1 : '—'}</span>
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
    <p class="form-label">Extracted text preview</p>
    <div class="flex-1 surface-inset p-3 overflow-y-auto font-mono text-xs text-foreground whitespace-pre-wrap leading-relaxed min-h-[160px]">
      {#if currentPage?.text}
        {currentPage.text}
      {:else if pages.length > 0}
        {pages.map((p) => p.text).join('\n\n--- Page Break ---\n\n')}
      {:else}
        <span class="text-foreground-muted italic">No extracted text available. Upload and process a document to view results.</span>
      {/if}
    </div>
  </div>

  <Button
    variant="primary"
    fullWidth
    on:click={() => exportModalOpen.set(true)}
  >
    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
    </svg>
    <span>Export results…</span>
  </Button>
</Card>

<script lang="ts">
  import { activeTab, documentStore, configStore, pushToast } from '$lib/stores/appStore';
  import { fetchApi, fetchFile } from '$lib/api/client';
  import type { ExtractionRequest } from '$lib/types/api';
  import Card from '../ui/Card.svelte';
  import Button from '../ui/Button.svelte';
  import Badge from '../ui/Badge.svelte';
  import SectionHeader from '../ui/SectionHeader.svelte';
  import SegmentedControl from '../ui/SegmentedControl.svelte';

  type Template = 'invoice' | 'resume' | 'academic' | 'custom';
  let selectedTemplate: Template = 'invoice';
  let customSchemaJson = '{\n  "invoice_number": "string",\n  "total_amount": "number",\n  "date": "string",\n  "line_items": "array"\n}';
  let inputText = '';
  let selectedArtifactId = '';
  let selectedArtifactToken = '';
  let isExtracting = false;
  let extractedData: Record<string, unknown> | null = null;

  $: if ($documentStore.textArtifactId) {
    selectedArtifactId = $documentStore.textArtifactId;
    selectedArtifactToken = $documentStore.textArtifactToken || '';
  }

  const templates: { value: Template; label: string }[] = [
    { value: 'invoice', label: 'Invoice' },
    { value: 'resume', label: 'Resume' },
    { value: 'academic', label: 'Academic' },
    { value: 'custom', label: 'Custom schema' }
  ];

  function downloadBlob(blob: Blob, name: string) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  async function handleExtract() {
    if (!inputText.trim() && !selectedArtifactId) {
      pushToast('warning', 'Provide source text or select a document artifact for extraction.', 3000);
      return;
    }

    isExtracting = true;
    extractedData = null;

    try {
      const payload: ExtractionRequest = {
        template: selectedTemplate,
        custom_prompt: selectedTemplate === 'custom' ? customSchemaJson : undefined,
        text: inputText || undefined,
        model: $configStore.model,
        api_base: $configStore.api_base,
      };

      const res = await fetchApi<{ extracted_data: Record<string, unknown> }>('/extract', {
        method: 'POST',
        body: JSON.stringify(payload),
      });

      extractedData = res.extracted_data;
      pushToast('success', 'Structured data extraction completed!', 3000);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      pushToast('error', message || 'Extraction failed', 4000);
    } finally {
      isExtracting = false;
    }
  }

  async function downloadExport(format: 'markdown' | 'docx' | 'html' | 'blocktree') {
    if (!selectedArtifactId || !selectedArtifactToken) {
      pushToast('warning', 'Export requires an active text artifact ID and token.', 3000);
      return;
    }

    try {
      const payload = {
        text_artifact_id: selectedArtifactId,
        text_artifact_token: selectedArtifactToken,
      };

      pushToast('info', `Generating ${format.toUpperCase()} export...`, 2000);

      if (format === 'html') {
        const blob = await fetchFile('/export/html', {
          method: 'POST',
          body: JSON.stringify(payload),
          headers: { 'Content-Type': 'application/json' },
        });
        downloadBlob(blob, `export-${selectedArtifactId}.html`);
        pushToast('success', 'HTML export downloaded.', 3000);
      } else if (format === 'docx') {
        const blob = await fetchFile('/export/docx-tree', {
          method: 'POST',
          body: JSON.stringify(payload),
          headers: { 'Content-Type': 'application/json' },
        });
        downloadBlob(blob, `export-${selectedArtifactId}.docx`);
        pushToast('success', 'DOCX export downloaded.', 3000);
      } else if (format === 'blocktree') {
        const res = await fetchApi<unknown>('/export/blocktree', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        const blob = new Blob([JSON.stringify(res, null, 2)], { type: 'application/json' });
        downloadBlob(blob, `blocktree-${selectedArtifactId}.json`);
        pushToast('success', 'BlockTree export downloaded.', 3000);
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      pushToast('error', message || 'Export failed', 4000);
    }
  }
</script>

<section id="view-extraction" data-view="extraction" hidden={$activeTab !== 'extraction'} class="flex-1 flex flex-col min-h-0 p-6 space-y-6">
  <!-- Header -->
  <header class="flex flex-col lg:flex-row lg:items-end justify-between border-b border-border pb-4 gap-3">
    <div class="space-y-1.5 min-w-0">
      <div class="flex items-center gap-2.5 flex-wrap">
        <h2 class="text-2xl font-semibold font-display text-foreground">Structured information extraction</h2>
        <Badge variant="brand" size="md">JSON Schema / AST</Badge>
      </div>
      <p class="text-xs text-foreground-muted">Extract structured entities and key-value fields from OCR document trees</p>
    </div>

    <!-- Template selector -->
    <SegmentedControl
      bind:value={selectedTemplate}
      ariaLabel="Extraction template"
      options={templates}
    />
  </header>

  <!-- Dual pane -->
  <div class="grid grid-cols-1 lg:grid-cols-2 gap-5 flex-1 min-h-0">
    <!-- Left: Input -->
    <Card padding="md" class="flex flex-col gap-4 min-h-[400px]">
      <SectionHeader title="Input text / document artifact" divider={false}>
        <svelte:fragment slot="action">
          {#if selectedArtifactId}
            <Badge variant="brand" size="sm" title={selectedArtifactId}>
              {selectedArtifactId.slice(0, 12)}…
            </Badge>
          {/if}
        </svelte:fragment>
      </SectionHeader>

      <textarea
        bind:value={inputText}
        placeholder="Paste text to extract structured data from, or leave empty if a document artifact is bound..."
        class="flex-1 w-full surface-inset rounded-md p-3 text-sm font-mono text-foreground placeholder:text-foreground-subtle focus:outline-none focus:ring-2 focus:ring-brand/20 resize-none leading-relaxed min-h-[160px]"
      ></textarea>

      {#if selectedTemplate === 'custom'}
        <div class="space-y-2 pt-3 border-t border-border">
          <label for="custom-schema" class="form-label">Custom JSON schema</label>
          <textarea
            id="custom-schema"
            bind:value={customSchemaJson}
            rows="4"
            class="w-full surface-inset rounded-md p-2.5 text-sm font-mono text-success focus:outline-none focus:ring-2 focus:ring-brand/20 resize-none"
          ></textarea>
        </div>
      {/if}

      <Button variant="primary" fullWidth loading={isExtracting} on:click={handleExtract}>
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
        </svg>
        <span>{isExtracting ? 'Extracting…' : 'Run structured extraction'}</span>
      </Button>
    </Card>

    <!-- Right: Output -->
    <Card padding="md" class="flex flex-col gap-4 min-h-[400px]">
      <SectionHeader title="Extracted output AST" divider={false}>
        <svelte:fragment slot="action">
          <div class="flex items-center gap-1.5">
            <Button size="sm" variant="ghost" on:click={() => downloadExport('html')}>
              .HTML
            </Button>
            <Button size="sm" variant="ghost" on:click={() => downloadExport('docx')}>
              .DOCX
            </Button>
            <Button size="sm" variant="ghost" on:click={() => downloadExport('blocktree')}>
              BlockTree
            </Button>
          </div>
        </svelte:fragment>
      </SectionHeader>

      <div class="flex-1 surface-inset rounded-md p-3 font-mono text-xs overflow-y-auto leading-relaxed min-h-[160px]">
        {#if isExtracting}
          <div class="h-full flex items-center justify-center text-brand animate-pulse">
            Extracting structured schema fields…
          </div>
        {:else if extractedData}
          <pre class="text-success whitespace-pre-wrap">{JSON.stringify(extractedData, null, 2)}</pre>
        {:else}
          <div class="h-full flex items-center justify-center text-foreground-subtle italic">
            Extracted JSON schema structure will appear here…
          </div>
        {/if}
      </div>
    </Card>
  </div>
</section>

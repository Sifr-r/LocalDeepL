<script lang="ts">
  import { exportModalOpen, documentStore, toastStore } from '../../stores/appStore';
  import { pdfPreview } from '../../stores/pdfPreview';
  import { exportDocument, exportDocx } from '../../api/endpoints';
  import Modal from '../ui/Modal.svelte';
  import Button from '../ui/Button.svelte';
  import Badge, { type BadgeVariant } from '../ui/Badge.svelte';

  type ExportFormat = 'txt' | 'pdf' | 'markdown' | 'json' | 'docx';

  const formats: { value: ExportFormat; label: string; description: string; tag: string; tagVariant?: BadgeVariant }[] = [
    {
      value: 'txt',
      label: 'Plain text',
      description: 'Clean unformatted raw text',
      tag: 'TXT',
      tagVariant: 'neutral'
    },
    {
      value: 'pdf',
      label: 'Searchable PDF',
      description: 'Original layout with embedded text layer — like-for-like output',
      tag: 'PDF',
      tagVariant: 'brand'
    },
    {
      value: 'markdown',
      label: 'Markdown',
      description: 'Formatted markdown with headers and tables',
      tag: 'MD',
      tagVariant: 'brand'
    },
    {
      value: 'json',
      label: 'Structured JSON',
      description: 'Full block hierarchy with bounding boxes',
      tag: 'JSON',
      tagVariant: 'success'
    },
    {
      value: 'docx',
      label: 'Word document',
      description: 'Editable Microsoft Word document',
      tag: 'DOCX',
      tagVariant: 'brand'
    }
  ];

  function closeModal() {
    exportModalOpen.set(false);
  }

  // ``exportDocument`` returns whatever shape the server shipped, which
  // is a string for text / markdown exports and an object envelope
  // (``{ artifact_id, token, format }``) for JSON exports. Normalize
  // both into a string so the download path doesn't care.
  function extractExportString(body: unknown, key: string): string {
    if (typeof body === 'string') return body;
    if (body && typeof body === 'object' && key in body) {
      const value = (body as Record<string, unknown>)[key];
      if (typeof value === 'string') return value;
    }
    return '';
  }

  async function handleExport(format: ExportFormat) {
    try {
      const artifactId: string | null = $documentStore.textArtifactId ?? $documentStore.textArtifact?.id ?? null;
      const filename: string = $documentStore.filename ?? 'export_result';

      if (format === 'txt') {
        const pages: Array<{ text?: string }> = ($documentStore.pages || []);
        const textContent = pages.map((p) => p.text ?? '').join('\n\n');
        downloadBlob(new Blob([textContent], { type: 'text/plain;charset=utf-8' }), `${filename}.txt`);
      } else if (format === 'markdown') {
        const res = await exportDocument({ text_artifact_id: artifactId ?? undefined, format: 'markdown', filename });
        const content = extractExportString(res, 'content');
        downloadBlob(new Blob([content], { type: 'text/markdown;charset=utf-8' }), `${filename}.md`);
      } else if (format === 'json') {
        const res = await exportDocument({ text_artifact_id: artifactId ?? undefined, format: 'json', filename });
        const jsonStr = typeof res === 'string' ? res : JSON.stringify(res, null, 2);
        downloadBlob(new Blob([jsonStr], { type: 'application/json' }), `${filename}.json`);
      } else if (format === 'docx') {
        await exportDocx({ text_artifact_id: artifactId ?? undefined, filename });
        toastStore.pushToast('success', 'DOCX generated successfully');
      } else if (format === 'pdf') {
        // The PDF returned by ``/api/process`` is already the structured,
        // like-for-like output: the original page images with a text layer
        // baked in. We capture the blob in :file:`pdfPreview` so the user
        // can download it without re-issuing the OCR request.
        const blobUrl = $pdfPreview.responseBlobUrl;
        if (!blobUrl) {
          toastStore.pushToast(
            'warning',
            'Run OCR on a document first — the searchable PDF is the OCR response.'
          );
          return;
        }
        const a = document.createElement('a');
        a.href = blobUrl;
        a.download = $pdfPreview.responseFileName || `${filename}.ocr.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        toastStore.pushToast('success', 'Searchable PDF downloaded');
      }

      closeModal();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      toastStore.pushToast('error', `Export failed: ${message}`);
    }
  }

  function downloadBlob(blob: Blob, name: string) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    a.click();
    URL.revokeObjectURL(url);
  }
</script>

<Modal
  open={$exportModalOpen}
  on:close={() => exportModalOpen.set(false)}
  title="Export document"
  description="Select an output format"
  maxWidth="md"
>
  <div class="space-y-2">
    {#each formats as fmt (fmt.value)}
      <button
        type="button"
        class="w-full p-3 rounded-md bg-card-raised hover:bg-muted border border-border hover:border-border-strong flex items-center justify-between text-left transition-colors group focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        on:click={() => handleExport(fmt.value)}
      >
        <div class="min-w-0">
          <p class="text-sm font-medium text-foreground group-hover:text-brand transition-colors">{fmt.label}</p>
          <p class="text-xs text-foreground-muted mt-0.5">{fmt.description}</p>
        </div>
        <Badge variant={fmt.tagVariant ?? 'neutral'} size="sm" class="shrink-0 ml-3">
          {fmt.tag}
        </Badge>
      </button>
    {/each}
  </div>

  <svelte:fragment slot="footer">
    <Button variant="secondary" on:click={closeModal}>
      Cancel
    </Button>
  </svelte:fragment>
</Modal>

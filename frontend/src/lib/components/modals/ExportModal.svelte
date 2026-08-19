<script lang="ts">
  import { exportModalOpen, documentStore, toastStore } from '../../stores/appStore';
  import { pdfPreview } from '../../stores/pdfPreview';
  import { exportDocument, exportDocx, artifactsApi } from '../../api/endpoints';
  import {
    aggregateMarkdownFromBboxes,
    aggregateTextFromBboxes,
  } from '../../utils/exportAggregation';
  import { downloadBlob, downloadUrl } from '../../utils/download';
  import Modal from '../ui/Modal.svelte';
  import Button from '../ui/Button.svelte';
  import Badge, { type BadgeVariant } from '../ui/Badge.svelte';
  import type { BBoxItem } from '../../types/api';

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

  async function handleExport(format: ExportFormat) {
    try {
      const artifactId: string | null = $documentStore.textArtifactId ?? $documentStore.textArtifact?.id ?? null;
      const artifactToken: string | null = $documentStore.textArtifactToken ?? $documentStore.textArtifact?.token ?? null;
      const filename: string = $documentStore.filename ?? 'export_result';
      const bboxes: BBoxItem[] = $documentStore.bboxes ?? [];

      if (format === 'txt') {
        const textContent = aggregateTextFromBboxes(bboxes);
        downloadBlob(new Blob([textContent], { type: 'text/plain;charset=utf-8' }), `${filename}.txt`);
      } else if (format === 'markdown') {
        if (!artifactId || !artifactToken) {
          toastStore.pushToast('error', 'Document text artifact not available for export');
          return;
        }
        const exportHandle = await exportDocument({
          text_artifact_id: artifactId,
          text_artifact_token: artifactToken,
          export_format: 'markdown'
        });
        const blob = await artifactsApi.getExport(exportHandle.artifact_id, exportHandle.token);
        downloadBlob(blob, `${filename}.md`);
      } else if (format === 'json') {
        if (!artifactId || !artifactToken) {
          toastStore.pushToast('error', 'Document text artifact not available for export');
          return;
        }
        const exportHandle = await exportDocument({
          text_artifact_id: artifactId,
          text_artifact_token: artifactToken,
          export_format: 'json'
        });
        const blob = await artifactsApi.getExport(exportHandle.artifact_id, exportHandle.token);
        downloadBlob(blob, `${filename}.json`);
      } else if (format === 'docx') {
        const markdownText = aggregateMarkdownFromBboxes(bboxes);
        const blob = await exportDocx({ text: markdownText });
        downloadBlob(blob, `${filename}.docx`);
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
        downloadUrl(blobUrl, $pdfPreview.responseFileName || `${filename}.ocr.pdf`);
        toastStore.pushToast('success', 'Searchable PDF downloaded');
      }

      closeModal();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      toastStore.pushToast('error', `Export failed: ${message}`);
    }
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

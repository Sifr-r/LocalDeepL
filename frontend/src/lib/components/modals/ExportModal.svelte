<script lang="ts">
  import { exportModalOpen, documentStore, toastStore } from '../../stores/appStore';
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
      description: 'PDF with embedded text layer',
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
      const artifactId = ($documentStore as any).textArtifact?.id || ($documentStore as any).textArtifactId;
      const filename = ($documentStore as any).filename || 'export_result';

      if (format === 'txt') {
        const textContent = ($documentStore as any).pages?.map((p: any) => p.text).join('\n\n') || '';
        downloadBlob(new Blob([textContent], { type: 'text/plain;charset=utf-8' }), `${filename}.txt`);
      } else if (format === 'markdown') {
        const res = await exportDocument({ text_artifact_id: artifactId, format: 'markdown', filename });
        const content = res?.content || res || '';
        downloadBlob(new Blob([content], { type: 'text/markdown;charset=utf-8' }), `${filename}.md`);
      } else if (format === 'json') {
        const res = await exportDocument({ text_artifact_id: artifactId, format: 'json', filename });
        const jsonStr = typeof res === 'string' ? res : JSON.stringify(res, null, 2);
        downloadBlob(new Blob([jsonStr], { type: 'application/json' }), `${filename}.json`);
      } else if (format === 'docx') {
        await exportDocx({ text_artifact_id: artifactId, filename });
        toastStore.pushToast('success', 'DOCX generated successfully');
      } else if (format === 'pdf') {
        toastStore.pushToast('info', 'Downloading PDF document...');
      }

      closeModal();
    } catch (err: any) {
      toastStore.pushToast('error', `Export failed: ${err.message}`);
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
    {#each formats as fmt}
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

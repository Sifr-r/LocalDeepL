<script lang="ts">
  import UploadPanel from './UploadPanel.svelte';
  import ProcessSettings from './ProcessSettings.svelte';
  import PageCanvas from './PageCanvas.svelte';
  import MetadataPanel from './MetadataPanel.svelte';
  import TrustPanel from './TrustPanel.svelte';
  import PipelineProgress from '../ui/PipelineProgress.svelte';
  import Card from '../ui/Card.svelte';
  import Button from '../ui/Button.svelte';
  import {
    activeTab,
    configStore,
    defaultDocumentModel,
    defaultJobState,
    documentStore,
    jobStore,
    toastStore
  } from '../../stores/appStore';
  import { pdfPreview } from '../../stores/pdfPreview';
  import {
    applyAsyncResult,
    applySyncResult,
    buildInitialJobState,
    buildOcrFormData,
    classifyOcrFailure,
    closeProgressChannel,
    openProgressChannel,
    requestProgressCancel,
    submitAsyncOcr,
    submitSyncOcr
  } from '../../services/workstationService';

  let selectedFile: File | null = null;
  let processViewEl: HTMLDivElement;

  $: isProcessing = Boolean($jobStore.isProcessing);

  // F3.12 audit fix: when the "Processing document" overlay opens,
  // move focus to the dialog so screen-reader users hear the
  // aria-label and keyboard users can immediately interact with
  // the cancel button (or Escape out via the dialog's own
  // handler). When the overlay closes, restore focus to the
  // element that triggered the upload.
  let lastFocusedBeforeProcessing: HTMLElement | null = null;
  $: if (typeof document !== 'undefined') {
    if (isProcessing) {
      if (processViewEl && document.activeElement !== processViewEl) {
        lastFocusedBeforeProcessing =
          document.activeElement instanceof HTMLElement
            ? document.activeElement
            : null;
        // Defer so Svelte has time to apply the ``hidden`` class
        // flip; without the rAF the focus call races the
        // display: none transition and silently no-ops.
        requestAnimationFrame(() => {
          processViewEl?.focus();
        });
      }
    } else if (lastFocusedBeforeProcessing) {
      const el = lastFocusedBeforeProcessing;
      lastFocusedBeforeProcessing = null;
      requestAnimationFrame(() => {
        if (typeof el.focus === 'function') el.focus();
      });
    }
  }

  function handleFileSelect(event: CustomEvent<File | null>) {
    selectedFile = event.detail;
    documentStore.update((d) => ({
      ...d,
      filename: selectedFile ? selectedFile.name : null
    }));
    // Drive the PDF.js preview pipeline: a freshly picked file replaces
    // the previous blob URL and page count. ``null`` clears the canvas.
    if (selectedFile) {
      void pdfPreview.loadFile(selectedFile);
    } else {
      pdfPreview.clear();
    }
  }

  function handleCancel() {
    void requestProgressCancel();
  }

  /**
   * Thin shell: every API/WS/FormData concern lives in
   * ``services/workstationService.ts``. This function orchestrates the
   * run by calling the service and applying the returned patches to
   * the Svelte stores that drive the UI.
   */
  async function startProcessing() {
    if (isProcessing) return;
    if (!selectedFile) {
      toastStore.pushToast('warning', 'Please select a file to process.');
      return;
    }

    // 1) Open a progress channel BEFORE the upload so the worker can stream
    // frames. The backend only authorizes streaming when BOTH the channel id
    // and its session token are presented (`progress_channel` +
    // `progress_token` form fields) and the WS handshake has completed.
    let session: { channelId: string; sessionToken: string };
    try {
      session = await openProgressChannel();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      toastStore.pushToast('error', `Progress channel failed: ${message}`);
      return;
    }

    // 2) Reset per-run state so streamed frames land on a clean slate.
    const useAsync = Boolean($configStore.use_async);
    jobStore.set({ ...defaultJobState, ...buildInitialJobState({ useAsync }) });
    documentStore.update((d) => ({ ...defaultDocumentModel, filename: d.filename }));

    const formData = buildOcrFormData({
      file: selectedFile,
      config: $configStore,
      channelId: session.channelId,
      sessionToken: session.sessionToken
    });

    try {
      if (useAsync) {
        const { status, resultBlob } = await submitAsyncOcr(formData);
        // ``/api/process/async`` returns the searchable OCR PDF as the
        // result blob. Hand it to the PDF.js preview so the canvas
        // paints the structured result and the export modal can offer
        // it as a real download.
        const baseName = (selectedFile?.name ?? 'document').replace(/\.[^.]+$/, '');
        try {
          await pdfPreview.loadResponse(resultBlob, `${baseName}.ocr.pdf`);
        } catch (err) {
          console.warn('Failed to bind async OCR PDF response', err);
        }
        const { documentPatch, jobPatch } = applyAsyncResult({
          status,
          file: selectedFile,
          prevDocument: $documentStore,
          prevJob: $jobStore
        });
        documentStore.update((d) => ({ ...d, ...documentPatch }));
        jobStore.update((s) => ({ ...s, ...jobPatch }));
        toastStore.pushToast('success', 'Document processing complete!');
        return;
      }

      const result = await submitSyncOcr(formData);
      if (result && result.textArtifactId) {
        const applied = applySyncResult({
          result,
          file: selectedFile,
          prev: $documentStore
        });
        if (applied.shouldBindPreview && applied.previewFileName && result.body instanceof Blob) {
          try {
            await pdfPreview.loadResponse(result.body, applied.previewFileName);
          } catch (err) {
            console.warn('Failed to bind OCR PDF response', err);
          }
        }
        jobStore.update((s) => ({ ...s, ...applied.jobPatch }));
        documentStore.update((d) => ({ ...d, ...applied.documentPatch }));
        toastStore.pushToast('success', 'Document processing complete!');
      } else {
        jobStore.update((s) => ({ ...s, isProcessing: false }));
      }
    } catch (err: unknown) {
      const { cancelled, message } = classifyOcrFailure(err);
      if (cancelled) {
        jobStore.update((s) => ({
          ...s,
          isProcessing: false,
          stage: 'cancelled',
          percent: 0,
          statusMessage: 'Cancelled'
        }));
        toastStore.pushToast('info', 'Processing cancelled.');
        return;
      }
      jobStore.update((s) => ({
        ...s,
        isProcessing: false,
        stage: 'error',
        statusMessage: message
      }));
      toastStore.pushToast('error', `Processing failed: ${message}`);
    } finally {
      closeProgressChannel();
    }
  }
</script>

<section
  id="view-workstation"
  data-view="workstation"
  hidden={$activeTab !== 'workstation'}
  class="w-full min-h-[calc(100vh-56px)] p-6 relative flex flex-col"
>
  <!-- Main 3-Column Workstation Layout -->
  <div class="grid grid-cols-1 lg:grid-cols-12 gap-5 flex-1 items-stretch">

    <!-- Left Column: Upload + Settings + Start Button -->
    <div class="lg:col-span-3 flex flex-col gap-5 min-w-0">
      <Card padding="md" class="flex-1 flex flex-col gap-5 overflow-y-auto">
        <UploadPanel on:fileSelect={handleFileSelect} />
        <ProcessSettings />
      </Card>

      <Button
        id="start-btn"
        variant="primary"
        size="lg"
        fullWidth
        loading={isProcessing}
        disabled={isProcessing || !selectedFile}
        on:click={startProcessing}
      >
        {#if !isProcessing}
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span>Start processing</span>
        {:else}
          <span>Processing…</span>
        {/if}
      </Button>
    </div>

    <!-- Middle Column: Page Canvas — sticky viewport-height on lg+ so the
         viewer never stretches to the side columns' height (which would
         leave large empty bands above/below the rendered page). -->
    <div
      class="lg:col-span-6 flex flex-col min-h-[600px] min-w-0 lg:sticky lg:top-6 lg:self-start lg:h-[calc(100vh-6.5rem)]"
    >
      <PageCanvas />
    </div>

    <!-- Right Column: Metadata Panel + Trust Panel (read-only) -->
    <div class="lg:col-span-3 flex flex-col gap-5 min-w-0">
      <MetadataPanel />
      <TrustPanel />
    </div>
  </div>

  <!-- Processing overlay. The #process-view element must stay in the DOM
       at all times with `hidden` toggled on/off: the Playwright smoke test
       in e2e/test_ui.py and the WorkstationView vitest both assert on the
       `hidden` class. So we keep the legacy hook, drop the `transition-all`
       that could never transition `display`, and add the dialog ARIA
       attributes the previous version was missing. -->
  <div
    id="process-view"
    bind:this={processViewEl}
    class="fixed inset-0 z-40 bg-overlay/80 backdrop-blur-md flex items-center justify-center p-4 {isProcessing ? '' : 'hidden'}"
    role="dialog"
    aria-modal="true"
    aria-label="Processing document"
    tabindex="-1"
  >
    <PipelineProgress on:cancel={handleCancel} />
  </div>
</section>

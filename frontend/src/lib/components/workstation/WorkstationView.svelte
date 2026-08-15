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
    toastStore,
    websocketStore
  } from '../../stores/appStore';
  import { pdfPreview } from '../../stores/pdfPreview';
  import { processOcr } from '../../api/endpoints';
  import { isFetchError } from '../../api/client';
  import type { PageResult } from '../../types/api';

  // Legacy JSON responses still carry ``pages`` / ``confidence`` in the
  // body. The modern OCR endpoint returns a PDF blob instead, so the
  // helpers fall back to ``undefined`` (and the document store keeps
  // its prior values).
  function extractPages(body: unknown): PageResult[] | undefined {
    if (!body || typeof body !== 'object') return undefined;
    const candidate = (body as { pages?: unknown }).pages;
    if (!Array.isArray(candidate)) return undefined;
    return candidate as PageResult[];
  }
  function extractConfidence(body: unknown): number | undefined {
    if (!body || typeof body !== 'object') return undefined;
    const value = (body as { confidence?: unknown }).confidence;
    return typeof value === 'number' ? value : undefined;
  }

  let selectedFile: File | null = null;
  let processViewEl: HTMLDivElement;

  $: isProcessing = Boolean($jobStore.isProcessing);

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
    void websocketStore.requestCancel();
  }

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
    let channelId: string;
    let sessionToken: string;
    try {
      const session = await websocketStore.connect();
      channelId = session.channelId;
      sessionToken = session.sessionToken;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      toastStore.pushToast('error', `Progress channel failed: ${message}`);
      return;
    }

    // 2) Reset per-run state so streamed frames land on a clean slate.
    jobStore.set({
      ...defaultJobState,
      isProcessing: true,
      percent: 2,
      stage: 'init',
      statusMessage: 'Uploading document…'
    });
    documentStore.update((d) => ({
      ...defaultDocumentModel,
      filename: d.filename
    }));

    try {
      const cfg = $configStore;
      const formData = new FormData();
      formData.append('file', selectedFile);
      formData.append('progress_channel', channelId);
      formData.append('progress_token', sessionToken);
      if (cfg.pipeline_mode) formData.append('pipeline_mode', cfg.pipeline_mode);
      if (cfg.dense_mode) formData.append('dense_mode', cfg.dense_mode);
      if (cfg.spellcheck) formData.append('spellcheck', cfg.spellcheck);
      if (cfg.document_processors?.length) {
        formData.append('document_processors', cfg.document_processors.join(','));
      }
      // The individual preprocessing toggles only take effect when the
      // master flag is on — derive it so the UI toggles are honest.
      const preprocessFields = [
        'orientation_detection',
        'deskew',
        'denoise',
        'normalize_contrast',
        'crop_cleanup'
      ] as const;
      const anyPreprocess = preprocessFields.some((f) => Boolean(cfg[f]));
      formData.append('preprocess_pages', String(cfg.preprocess_pages || anyPreprocess));
      for (const field of preprocessFields) {
        formData.append(field, String(Boolean(cfg[field])));
      }

      const result = await processOcr(formData);

      if (result && result.textArtifactId) {
        jobStore.update((s) => ({
          ...s,
          activeJobId: result.textArtifactId,
          percent: 100,
          stage: 'complete',
          statusMessage: 'Done',
          isProcessing: false
        }));

        // ``/api/process`` returns a binary PDF (the searchable OCR
        // output) as the response body. Hand it to the PDF.js preview
        // store so the canvas paints the structured result and the
        // export modal can offer it as a real download instead of a stub.
        if (result.body instanceof Blob && result.body.size > 0) {
          const baseName = selectedFile?.name?.replace(/\.[^.]+$/, '') || 'document';
          try {
            await pdfPreview.loadResponse(result.body, `${baseName}.ocr.pdf`);
          } catch (err) {
            console.warn('Failed to bind OCR PDF response', err);
          }
        }

        documentStore.update((d) => ({
          ...d,
          filename: selectedFile ? selectedFile.name : d.filename,
          // Legacy JSON paths may still include a ``pages`` array; the
          // modern OCR endpoint returns a PDF blob instead and we let
          // the streamed WebSocket frames populate pageCount.
          pages: extractPages(result.body) ?? d.pages,
          textArtifact: result.textArtifactId
            ? { id: result.textArtifactId, token: result.textArtifactToken ?? '' }
            : null,
          textArtifactId: result.textArtifactId,
          textArtifactToken: result.textArtifactToken,
          confidence: extractConfidence(result.body) ?? d.confidence,
          // Phase 2.18 — surface trust summary in the document store so
          // the TrustPanel can render it. ``null`` when the trust layer
          // was off (X-Document-Trust header absent).
          trustSummary: result.trustSummary
        }));

        toastStore.pushToast('success', 'Document processing complete!');
      } else {
        jobStore.update((s) => ({ ...s, isProcessing: false }));
      }
    } catch (err: unknown) {
      if (isFetchError(err) && err.status === 503) {
        const body = (err.data ?? {}) as { cancelled?: boolean };
        if (body.cancelled) {
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
      }
      const message = err instanceof Error ? err.message : 'Processing failed';
      jobStore.update((s) => ({
        ...s,
        isProcessing: false,
        stage: 'error',
        statusMessage: message
      }));
      toastStore.pushToast('error', `Processing failed: ${message}`);
    } finally {
      websocketStore.disconnect();
    }
  }
</script>

<section
  id="view-workstation"
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

  <!-- Legacy Overlay Container #process-view (kept for CSS/Playwright hooks) -->
  <div
    id="process-view"
    bind:this={processViewEl}
    class="fixed inset-0 z-40 bg-overlay/80 backdrop-blur-md flex items-center justify-center p-4 transition-all duration-300 {isProcessing ? '' : 'hidden'}"
  >
    <PipelineProgress on:cancel={handleCancel} />
  </div>
</section>

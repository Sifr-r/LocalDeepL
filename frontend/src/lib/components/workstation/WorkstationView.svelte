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
    configStore,
    documentStore,
    jobStore,
    toastStore,
    websocketStore
  } from '../../stores/appStore';
  import { processOcr } from '../../api/endpoints';

  let selectedFile: File | null = null;
  let processViewEl: HTMLDivElement;
  let activeChannelId: string | null = null;

  $: isProcessing = Boolean($jobStore.activeJobId && $jobStore.percent > 0 && $jobStore.percent < 100);

  function handleFileSelect(event: CustomEvent<File>) {
    selectedFile = event.detail;
    documentStore.update((d) => ({
      ...d,
      filename: selectedFile ? selectedFile.name : null
    }));
  }

  async function startProcessing() {
    if (!selectedFile) {
      toastStore.pushToast('warning', 'Please select a file to process.');
      return;
    }

    // 1) Open a progress channel BEFORE the upload so the worker can stream frames.
    let channelId: string;
    try {
      const session = await websocketStore.connect();
      channelId = session.channelId;
      activeChannelId = channelId;
    } catch (err: any) {
      toastStore.pushToast('error', `Progress channel failed: ${err?.message ?? err}`);
      return;
    }

    // Set processing state
    jobStore.update((s) => ({
      ...s,
      isProcessing: true,
      percent: 5,
      stage: 'detection'
    }));

    try {
      const formData = new FormData();
      formData.append('file', selectedFile);
      formData.append('channel_id', channelId);
      if ($configStore.pipeline_mode) formData.append('pipeline_mode', $configStore.pipeline_mode);
      if ($configStore.dense_mode) formData.append('dense_mode', $configStore.dense_mode);
      if ($configStore.spellcheck) formData.append('spellcheck', $configStore.spellcheck);

      const result = await processOcr(formData);

      if (result && result.textArtifactId) {
        jobStore.update((s) => ({
          ...s,
          activeJobId: result.textArtifactId,
          percent: 100,
          stage: 'complete',
          isProcessing: false
        }));

        documentStore.update((d) => ({
          ...d,
          jobId: result.textArtifactId,
          filename: selectedFile ? selectedFile.name : d.filename,
          pages: (result.body && result.body.pages) || [],
          textArtifact: result.textArtifactId
            ? { id: result.textArtifactId, token: result.textArtifactToken ?? '' }
            : null,
          textArtifactId: result.textArtifactId,
          textArtifactToken: result.textArtifactToken,
          confidence: (result.body && result.body.confidence) || 0.95,
          // Phase 2.18 — surface trust summary in the document store so
          // the TrustPanel can render it. ``null`` when the trust layer
          // was off (X-Document-Trust header absent).
          trustSummary: result.trustSummary
        }));

        toastStore.pushToast('success', 'Document processing complete!');
      } else {
        jobStore.update((s) => ({ ...s, isProcessing: false }));
      }
    } catch (err: any) {
      jobStore.update((s) => ({ ...s, isProcessing: false, stage: 'error' }));
      toastStore.pushToast('error', `Processing failed: ${err.message}`);
    }
  }
</script>

<section id="view-workstation" class="w-full min-h-[calc(100vh-56px)] p-6 relative flex flex-col">
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

    <!-- Middle Column: Page Canvas -->
    <div class="lg:col-span-6 flex flex-col min-h-[600px] min-w-0">
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
    <PipelineProgress />
  </div>
</section>

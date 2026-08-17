<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { configStore, toastStore } from '../../stores/appStore';
  import SectionHeader from '../ui/SectionHeader.svelte';

  const dispatch = createEventDispatcher<{ fileSelect: File | null }>();

  let selectedFile: File | null = null;
  let isDragging = false;

  function handleFileChange(event: Event) {
    const input = event.target as HTMLInputElement;
    if (input.files && input.files[0]) {
      validateAndDispatch(input.files[0]);
    }
  }

  function handleDrop(event: DragEvent) {
    event.preventDefault();
    isDragging = false;
    if (event.dataTransfer?.files && event.dataTransfer.files[0]) {
      validateAndDispatch(event.dataTransfer.files[0]);
    }
  }

  function handleDragOver(event: DragEvent) {
    event.preventDefault();
    isDragging = true;
  }

  function handleDragLeave(event: DragEvent) {
    event.preventDefault();
    isDragging = false;
  }

  function validateAndDispatch(file: File) {
    const maxBytes = maxUploadBytes;
    if (file.size > maxBytes) {
      const maxMb = Math.round(maxBytes / (1024 * 1024));
      toastStore.pushToast('error', `File size exceeds ${maxMb}MB limit.`);
      return;
    }
    selectedFile = file;
    dispatch('fileSelect', file);
  }

  function clearFile() {
    selectedFile = null;
    dispatch('fileSelect', null as File | null);
  }

  function handleKeyDown(e: KeyboardEvent) {
    if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') {
      e.preventDefault();
      document.getElementById('file-input')?.click();
    }
  }

  // Hint mirrors the server cap from /api/config — the old hard-coded
  // "up to 50 MB" contradicted the configured limit (audit P3).
  $: maxUploadBytes = $configStore.security?.max_upload_bytes || 52428800;
  $: maxUploadMb = Math.round(maxUploadBytes / (1024 * 1024));
</script>

<div>
  <SectionHeader title="Upload" description={`PDF, PNG, JPG, AVIF, TIFF — up to ${maxUploadMb} MB.`} />

  <div
    class={[
      'rounded-md border-2 border-dashed transition-colors duration-150 p-6 text-center',
      'flex flex-col items-center justify-center gap-3 cursor-pointer',
      'focus-within:ring-2 focus-within:ring-brand/20',
      isDragging
        ? 'border-brand bg-brand/10'
        : selectedFile
        ? 'border-success/50 bg-success/5'
        : 'border-border hover:border-brand bg-card'
    ].join(' ')}
    on:dragover={handleDragOver}
    on:dragleave={handleDragLeave}
    on:drop={handleDrop}
    on:click={() => document.getElementById('file-input')?.click()}
    on:keydown={handleKeyDown}
    role="button"
    tabindex="0"
    aria-label={selectedFile ? 'Replace uploaded file' : 'Upload a document'}
  >
    <input
      type="file"
      id="file-input"
      class="hidden"
      accept=".pdf,.png,.jpg,.jpeg,.avif,.webp,.tiff"
      on:change={handleFileChange}
    />

    <div
      class={[
        'w-11 h-11 rounded-full flex items-center justify-center',
        selectedFile ? 'bg-success/15 text-success' : 'bg-muted text-foreground-muted'
      ].join(' ')}
    >
      {#if selectedFile}
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      {:else}
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
        </svg>
      {/if}
    </div>

    <div class="space-y-1 min-w-0 w-full">
      {#if selectedFile}
        <p class="text-sm font-medium text-foreground truncate" title={selectedFile.name}>
          {selectedFile.name}
        </p>
        <p class="text-xs text-foreground-muted font-mono">
          {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB
        </p>
      {:else}
        <p class="text-sm font-medium text-foreground">
          {isDragging ? 'Drop to upload' : 'Drop document or click to browse'}
        </p>
        <p class="text-xs text-foreground-muted font-mono">PDF, PNG, JPG, AVIF, TIFF</p>
      {/if}
    </div>
  </div>

  {#if selectedFile}
    <div class="mt-2 flex justify-end">
      <button
        type="button"
        on:click={clearFile}
        class="text-xs text-foreground-muted hover:text-danger transition-colors focus:outline-none focus-visible:underline"
      >
        Remove file
      </button>
    </div>
  {/if}
</div>

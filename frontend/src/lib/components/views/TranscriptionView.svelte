<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { activeTab, refreshModels, pushToast } from '$lib/stores/appStore';
  import { fetchApi } from '$lib/api/client';
  import {
    transcriptionResult,
    isTranscribing,
    activeSegmentId,
    audioCurrentTime,
  } from '$lib/stores/transcriptionStore';
  import type { TranscriptionJobResponse, TranscriptionSegment } from '$lib/types/api';
  import { downloadBlob } from '$lib/utils/download';
  import Card from '../ui/Card.svelte';
  import Button from '../ui/Button.svelte';
  import Input from '../ui/Input.svelte';
  import Select from '../ui/Select.svelte';
  import Badge from '../ui/Badge.svelte';
  import SectionHeader from '../ui/SectionHeader.svelte';

  let selectedAudioFile: File | null = null;
  let audioInput: HTMLInputElement;
  let audioElement: HTMLAudioElement;
  let audioUrl: string | null = null;

  // Configuration options
  let engine = 'api';
  let model = 'whisper-1';
  let language = '';
  let prompt = '';
  let temperature = 0.0;

  onMount(() => {
    refreshModels('transcription');
  });

  // F3.4 audit fix: revoke the object URL on component unmount.
  // The previous code revoked only when the user picked a new file,
  // so navigating away while an audio preview was active leaked
  // the Blob URL until the page session ended. Each leaked URL
  // holds the entire decoded audio in memory (a 5-minute WAV
  // is ~50MB; a 30-minute interview can be 300MB+).
  onDestroy(() => {
    if (audioUrl) {
      URL.revokeObjectURL(audioUrl);
      audioUrl = null;
    }
  });

  function handleAudioFileChange(e: Event) {
    const input = e.target as HTMLInputElement;
    if (input.files && input.files[0]) {
      selectedAudioFile = input.files[0];
      if (audioUrl) URL.revokeObjectURL(audioUrl);
      audioUrl = URL.createObjectURL(selectedAudioFile);
    }
  }

  async function handleTranscribe() {
    if (!selectedAudioFile) {
      pushToast('warning', 'Please select an audio file to transcribe.', 3000);
      return;
    }

    isTranscribing.set(true);
    transcriptionResult.set(null);

    try {
      const formData = new FormData();
      formData.append('file', selectedAudioFile);
      formData.append('engine', engine);
      formData.append('model', model);
      if (language) formData.append('language', language);
      if (prompt) formData.append('prompt', prompt);
      formData.append('temperature', temperature.toString());

      const res = await fetchApi<TranscriptionJobResponse>('/transcribe', {
        method: 'POST',
        body: formData,
      });

      transcriptionResult.set(res);
      pushToast('success', `Transcription complete: ${res.segments.length} segments extracted`, 4000);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      pushToast('error', message || 'Transcription failed', 4000);
    } finally {
      isTranscribing.set(false);
    }
  }

  function seekToSegment(segment: TranscriptionSegment) {
    activeSegmentId.set(segment.id ?? null);
    if (audioElement) {
      audioElement.currentTime = segment.start ?? 0;
      audioElement.play();
    }
  }

  function downloadAsText() {
    if (!$transcriptionResult) return;
    const blob = new Blob([$transcriptionResult.text], { type: 'text/plain;charset=utf-8' });
    downloadBlob(blob, `${$transcriptionResult.filename || 'transcript'}.txt`);
  }

  function downloadAsSrt() {
    if (!$transcriptionResult) return;
    let srt = '';
    $transcriptionResult.segments.forEach((seg, i) => {
      const start = formatSrtTime(seg.start ?? 0);
      const end = formatSrtTime(seg.end ?? 0);
      srt += `${i + 1}\n${start} --> ${end}\n${seg.text.trim()}\n\n`;
    });
    const blob = new Blob([srt], { type: 'text/plain;charset=utf-8' });
    downloadBlob(blob, `${$transcriptionResult.filename || 'transcript'}.srt`);
  }

  function formatSrtTime(sec: number): string {
    const pad = (n: number, z = 2) => ('00' + Math.floor(n)).slice(-z);
    const hrs = Math.floor(sec / 3600);
    const mins = Math.floor((sec % 3600) / 60);
    const secs = sec % 60;
    const ms = Math.floor((secs - Math.floor(secs)) * 1000);
    return `${pad(hrs)}:${pad(mins)}:${pad(secs)},${pad(ms, 3)}`;
  }

  const engineOptions = [
    { value: 'api', label: 'OpenAI / Remote API' },
    { value: 'faster-whisper', label: 'Faster-Whisper (Local)' }
  ];
</script>

<section id="view-transcription" data-view="transcription" hidden={$activeTab !== 'transcription'} class="flex-1 flex flex-col min-h-0 p-6 space-y-6">
  <!-- Header -->
  <header class="flex flex-col lg:flex-row lg:items-end justify-between border-b border-border pb-4 gap-3">
    <div class="space-y-1.5 min-w-0">
      <div class="flex items-center gap-2.5 flex-wrap">
        <h2 class="text-2xl font-semibold font-display text-foreground">Voice & audio transcription</h2>
        <Badge variant="brand" size="md">Whisper / Faster-Whisper</Badge>
      </div>
      <p class="text-xs text-foreground-muted">Transcribe speech to text with precise segment timestamps and multi-language support</p>
    </div>

    <!-- Header controls -->
    <div class="flex items-center gap-2 flex-wrap">
      <Select
        id="transcription-engine-select"
        label="Engine"
        options={engineOptions}
        bind:value={engine}
      />
      <Input
        id="transcription-model-input"
        label="Model"
        type="text"
        bind:value={model}
        placeholder="whisper-1"
      />
    </div>
  </header>

  <!-- Dual column layout -->
  <div class="grid grid-cols-1 lg:grid-cols-3 gap-5 flex-1 min-h-0">
    <!-- Left: Audio file + controls -->
    <Card padding="md" class="flex flex-col gap-4">
      <SectionHeader title="Audio file" divider={false} />

      <label for="audio-file-input" class="sr-only">Upload audio file</label>
      <input
        id="audio-file-input"
        aria-label="Upload audio file"
        type="file"
        bind:this={audioInput}
        on:change={handleAudioFileChange}
        accept="audio/*,.mp3,.wav,.m4a,.flac,.ogg,.webm"
        class="block w-full text-foreground-muted surface-inset p-2 rounded-md border border-border file:mr-3 file:py-1.5 file:px-3 file:rounded file:border-0 file:text-xs file:font-medium file:bg-brand file:text-brand-foreground hover:file:bg-brand-600 cursor-pointer"
      />

      {#if selectedAudioFile}
        <div class="p-3 surface-inset rounded-md space-y-2 border-brand/30 border">
          <div class="text-sm font-display font-semibold text-brand truncate">{selectedAudioFile.name}</div>
          {#if audioUrl}
            <audio
              bind:this={audioElement}
              src={audioUrl}
              controls
              class="w-full h-9 focus:outline-none"
              on:timeupdate={() => {
                if (audioElement) audioCurrentTime.set(audioElement.currentTime);
              }}
            ></audio>
          {/if}
        </div>
      {/if}

      <div class="space-y-3 pt-3 border-t border-border">
        <Input
          id="transcription-language"
          label="Language (ISO code, e.g. en, fr, de)"
          type="text"
          bind:value={language}
          placeholder="Auto-detect if empty"
          hint="Leave empty for automatic language detection"
        />

        <div>
          <label for="transcription-prompt" class="form-label">Prompt / glossary context</label>
          <textarea
            id="transcription-prompt"
            bind:value={prompt}
            rows="2"
            placeholder="Optional vocabulary or style prompt..."
            class="w-full surface-inset rounded-md p-2 text-sm text-foreground placeholder:text-foreground-subtle focus:outline-none focus:ring-2 focus:ring-brand/20 resize-none"
          ></textarea>
        </div>
      </div>

      <div class="mt-auto">
        <Button
          variant="primary"
          fullWidth
          size="lg"
          loading={$isTranscribing}
          disabled={!selectedAudioFile}
          on:click={handleTranscribe}
        >
          {#if $isTranscribing}
            <span>Transcribing…</span>
          {:else}
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-14 0M12 19v3m-4 0h8M12 14a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
            </svg>
            <span>Start transcription</span>
          {/if}
        </Button>
      </div>
    </Card>

    <!-- Right: Segments list -->
    <Card padding="md" class="lg:col-span-2 flex flex-col gap-3 min-h-0 overflow-hidden">
      <SectionHeader title="Transcription segments" divider={false}>
        <svelte:fragment slot="action">
          {#if $transcriptionResult}
            <div class="flex items-center gap-2">
              <Button size="sm" variant="ghost" on:click={downloadAsText}>
                Export .TXT
              </Button>
              <Button size="sm" variant="outline" on:click={downloadAsSrt}>
                Export .SRT
              </Button>
            </div>
          {/if}
        </svelte:fragment>
      </SectionHeader>

      <div class="flex-1 overflow-y-auto space-y-2 pr-1">
        {#if $isTranscribing}
          <div role="status" aria-live="polite" class="h-full flex flex-col items-center justify-center space-y-3 text-xs text-brand animate-pulse">
            <div class="w-8 h-8 border-[3px] border-brand border-t-transparent rounded-full animate-spin"></div>
            <div>Processing voice audio stream…</div>
          </div>
        {:else if $transcriptionResult && $transcriptionResult.segments.length > 0}
          {#each $transcriptionResult.segments as segment (segment.id ?? `${segment.start}-${segment.end}-${segment.text}`)}
            {@const segStart = segment.start ?? 0}
            {@const segEnd = segment.end ?? 0}
            {@const isActive = $activeSegmentId === segment.id || ($audioCurrentTime >= segStart && $audioCurrentTime <= segEnd)}
            <button
              type="button"
              on:click={() => seekToSegment(segment)}
              aria-label="Play segment from {segStart.toFixed(1)} to {segEnd.toFixed(1)} seconds"
              class={[
                'w-full p-3 rounded-md border text-sm transition-colors text-left',
                'flex items-start gap-3 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand',
                isActive
                  ? 'bg-brand/15 border-brand/50 text-foreground'
                  : 'bg-card-raised border-border text-foreground hover:border-border-strong'
              ].join(' ')}
            >
              <span class={[
                'px-2 py-1 rounded font-mono text-[10px] shrink-0',
                isActive ? 'bg-brand text-brand-foreground' : 'bg-card text-brand border border-border'
              ].join(' ')}>
                {segStart.toFixed(1)}s – {segEnd.toFixed(1)}s
              </span>
              <p class="leading-relaxed font-body">{segment.text}</p>
            </button>
          {/each}
        {:else}
          <div class="h-full flex items-center justify-center text-foreground-muted text-sm italic">
            Upload an audio file and click "Start transcription" to view segment timings and text.
          </div>
        {/if}
      </div>
    </Card>
  </div>
</section>

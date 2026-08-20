<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { activeTab, documentStore, configStore, modelStore, refreshModels, pushToast } from '$lib/stores/appStore';
  import { fetchApi } from '$lib/api/client';
  import { artifactsApi } from '$lib/api/endpoints';
  import { bindArtifactToText } from '$lib/utils/artifactBinding';
  import { reportError } from '$lib/utils/error';
  import type { TranslationRequest, TreeTranslationRequest } from '$lib/types/api';
  import Card from '../ui/Card.svelte';
  import Button from '../ui/Button.svelte';
  import Badge from '../ui/Badge.svelte';
  import Select from '../ui/Select.svelte';
  import Toggle from '../ui/Toggle.svelte';
  import SectionHeader from '../ui/SectionHeader.svelte';

  let sourceText = '';
  let selectedArtifactId = '';
  let selectedArtifactToken = '';
  let targetLanguage = 'French';
  let promptTemplate = 'Translate the following text accurately while maintaining context and terminology.';
  let targetModel = '';
  let isTranslating = false;
  let translatedOutput = '';
  let asyncJobId: string | null = null;
  let asyncStatus = '';
  let useNllb = false;
  let useTree = false;
  let pollTimer: ReturnType<typeof setInterval> | null = null;

  const languages = [
    'French', 'Spanish', 'German', 'Italian', 'Portuguese',
    'Japanese', 'Chinese (Simplified)', 'Korean', 'Russian', 'Arabic', 'Dutch'
  ];

  function clearPolling() {
    if (pollTimer !== null) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  onMount(() => {
    refreshModels('translation');
  });

  onDestroy(() => {
    clearPolling();
  });

  // F3.9 audit fix: previously this was a one-way sync — when
  // ``$documentStore.textArtifactId`` was truthy, the local state
  // was updated, but a transition to falsy (e.g. the user clears
  // the artifact selection, or switches to a different document
  // that has no text artifact) was silently ignored. A subsequent
  // translation request would then re-send the stale id and the
  // server would 422. The fix lives in
  // ``$lib/utils/artifactBinding#bindArtifactToText`` — both views
  // subscribe to the same derived store and the F3.9 clear-on-falsy
  // invariant is enforced in one place.
  const artifact = bindArtifactToText(documentStore);
  $: selectedArtifactId = $artifact.id;
  $: selectedArtifactToken = $artifact.token;
  $: if ($artifact.id && !sourceText.trim() && $documentStore.pages?.length > 0) {
    sourceText = $documentStore.pages.map((p) => p.text || '').filter(Boolean).join('\n\n');
  }

  async function handleSyncTranslate() {
    if (!sourceText.trim() && !selectedArtifactId) {
      pushToast('warning', 'Provide source text or select a document text artifact.', 3000);
      return;
    }

    isTranslating = true;
    translatedOutput = '';
    try {
      if (!sourceText.trim() && selectedArtifactId) {
        if ($documentStore.textArtifactId === selectedArtifactId && $documentStore.pages?.length > 0) {
          sourceText = $documentStore.pages.map((p) => p.text || '').filter(Boolean).join('\n\n');
        }
        if (!sourceText.trim()) {
          try {
            sourceText = await artifactsApi.getTextAsString(
              selectedArtifactId,
              selectedArtifactToken
            );
          } catch (err) {
            console.warn('Failed to fetch artifact text for translation', err);
          }
        }
      }

      if (useNllb) {
        if (!sourceText.trim()) {
          pushToast('warning', 'Source text is empty. Provide text or select a valid document artifact.', 3000);
          isTranslating = false;
          return;
        }
        const res = await fetchApi<{ translated_text: string }>('/translate/nllb', {
          method: 'POST',
          body: JSON.stringify({
            text: sourceText,
            target_language: targetLanguage,
          }),
        });
        translatedOutput = res.translated_text;
        pushToast('success', 'NLLB fast translation complete.', 3000);
      } else if (useTree && selectedArtifactId) {
        const payload: TreeTranslationRequest = {
          text_artifact_id: selectedArtifactId,
          text_artifact_token: selectedArtifactToken,
          target_language: targetLanguage,
          prompt_template: promptTemplate,
          model: targetModel || $configStore.translation_model || $configStore.model,
          api_base: $configStore.translation_api_base || $configStore.api_base,
        };
        const res = await fetchApi<unknown>('/translate/tree', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        translatedOutput = JSON.stringify(res, null, 2);
        pushToast('success', 'Tree translation complete.', 3000);
      } else {
        const payload: TranslationRequest = {
          text: sourceText || undefined,
          text_artifact_id: selectedArtifactId || undefined,
          text_artifact_token: selectedArtifactToken || undefined,
          target_language: targetLanguage,
          prompt_template: promptTemplate,
          model: targetModel || $configStore.translation_model || $configStore.model,
          api_base: $configStore.translation_api_base || $configStore.api_base,
        };
        const res = await fetchApi<{ translated_text: string }>('/translate', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        translatedOutput = res.translated_text;
        pushToast('success', 'Translation complete.', 3000);
      }
    } catch (err: unknown) {
      reportError(err, 'Translation failed');
    } finally {
      isTranslating = false;
    }
  }

  async function handleAsyncTranslate() {
    if (!selectedArtifactId) {
      pushToast('warning', 'Async tree translation requires a valid text artifact ID.', 4000);
      return;
    }

    clearPolling();
    isTranslating = true;
    asyncJobId = null;
    asyncStatus = 'Queuing async translation job...';
    try {
      const payload = {
        text_artifact_id: selectedArtifactId,
        text_artifact_token: selectedArtifactToken,
        target_language: targetLanguage,
        prompt_template: promptTemplate,
      };
      const res = await fetchApi<{ job_id: string; status: string }>('/translate/async', {
        method: 'POST',
        body: JSON.stringify(payload),
      });

      asyncJobId = res.job_id;
      asyncStatus = `Job queued: ${res.job_id}. Polling status...`;
      pushToast('info', `Async job queued: ${res.job_id}`, 3000);
      pollAsyncStatus(asyncJobId);
    } catch (err: unknown) {
      const message = reportError(err, 'Async translation failed');
      asyncStatus = `Async queue error: ${message}`;
      isTranslating = false;
    }
  }

  async function pollAsyncStatus(jobId: string) {
    clearPolling();
    pollTimer = setInterval(async () => {
      try {
        const res = await fetchApi<{ state?: string; status?: string; result?: unknown; error?: string }>(`/translate/status/${jobId}`, { silent: true });
        asyncStatus = `Status: ${res.state || res.status}`;
        if (res.state === 'SUCCESS') {
          clearPolling();
          isTranslating = false;
          translatedOutput = typeof res.result === 'string' ? res.result : JSON.stringify(res.result, null, 2);
          pushToast('success', 'Async translation job completed!', 4000);
        } else if (res.state === 'FAILURE' || res.error) {
          clearPolling();
          isTranslating = false;
          pushToast('error', res.error || 'Async job failed', 4000);
        }
      } catch {
        clearPolling();
        isTranslating = false;
      }
    }, 2000);
  }
</script>

<section id="view-translation" data-view="translation" hidden={$activeTab !== 'translation'} class="flex-1 flex flex-col min-h-0 p-6 space-y-6">
  <!-- Header -->
  <header class="flex flex-col lg:flex-row lg:items-end justify-between border-b border-border pb-4 gap-3">
    <div class="space-y-1.5 min-w-0">
      <div class="flex items-center gap-2.5 flex-wrap">
        <h2 class="text-2xl font-semibold font-display text-foreground">Neural translation engine</h2>
        <Badge variant="brand" size="md">LangGraph / NLLB</Badge>
      </div>
      <p class="text-xs text-foreground-muted">Context-aware document translation with term preservation</p>
    </div>

    <!-- Controls bar -->
    <div class="flex items-center gap-2 flex-wrap">
      <Select
        id="translation-target-language"
        label="Target language"
        options={languages.map(l => ({ value: l, label: l }))}
        bind:value={targetLanguage}
      />
      <div class="flex items-end gap-1">
        <Select
          id="translation-model-select"
          label="Model"
          options={[
            { value: '', label: `Default: ${$configStore.translation_model || $configStore.model || 'auto'}` },
            ...$modelStore.translation.map(m => ({ value: m, label: m }))
          ]}
          value={targetModel}
          on:change={(e) => targetModel = (e.target as HTMLSelectElement).value}
        />
        <Button size="sm" variant="ghost" on:click={() => refreshModels('translation')} title="Refresh model list">
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
        </Button>
      </div>
    </div>
  </header>

  <!-- Options bar -->
  <div class="surface-inset p-3 rounded-md flex items-center justify-between gap-4 flex-wrap">
    <div class="flex items-center gap-4">
      <Toggle
        id="toggle-nllb"
        label="Use NLLB fast engine"
        bind:checked={useNllb}
      />
      <Toggle
        id="toggle-tree"
        label="Tree-aware translation"
        bind:checked={useTree}
      />
    </div>

    {#if selectedArtifactId}
      <div class="flex items-center gap-2 text-xs">
        <span class="text-foreground-muted">Artifact bound:</span>
        <Badge variant="brand" size="sm" title={selectedArtifactId}>
          {selectedArtifactId.slice(0, 16)}…
        </Badge>
        <button
          type="button"
          on:click={() => { selectedArtifactId = ''; selectedArtifactToken = ''; }}
          class="text-xs text-foreground-muted hover:text-danger transition-colors"
        >
          Clear
        </button>
      </div>
    {/if}
  </div>

  <!-- Dual pane -->
  <div class="grid grid-cols-1 lg:grid-cols-2 gap-5 flex-1 min-h-0">
    <!-- Source -->
    <Card padding="md" className="flex flex-col gap-3 min-h-[400px]">
      <SectionHeader title="Source input" divider={false}>
        <svelte:fragment slot="action">
          {#if selectedArtifactId}
            <button
              type="button"
              on:click={() => { selectedArtifactId = ''; selectedArtifactToken = ''; }}
              class="text-xs text-foreground-muted hover:text-danger transition-colors"
            >
              Clear artifact binding
            </button>
          {/if}
        </svelte:fragment>
      </SectionHeader>

      <label for="translation-source-text" class="sr-only">Source text to translate</label>
      <textarea
        id="translation-source-text"
        aria-label="Source text to translate"
        bind:value={sourceText}
        placeholder="Paste text to translate here, or process a document in the OCR workstation to bind its text artifact..."
        class="flex-1 w-full surface-inset rounded-md p-3 text-sm font-mono text-foreground placeholder:text-foreground-subtle focus:outline-none focus:ring-2 focus:ring-brand/20 resize-none leading-relaxed min-h-[160px]"
      ></textarea>

      <div class="flex items-center gap-2 pt-2">
        <Button
          variant="primary"
          fullWidth
          loading={isTranslating}
          on:click={handleSyncTranslate}
        >
          {isTranslating ? 'Translating…' : 'Translate (sync)'}
        </Button>
        <Button
          variant="secondary"
          disabled={isTranslating || !selectedArtifactId}
          on:click={handleAsyncTranslate}
          title="Queue background Celery task for full artifact tree translation"
        >
          Async
        </Button>
      </div>
    </Card>

    <!-- Target -->
    <Card padding="md" className="flex flex-col gap-3 min-h-[400px]">
      <SectionHeader title={`Translated output (${targetLanguage})`} divider={false}>
        <svelte:fragment slot="action">
          {#if isTranslating}
            <span role="status" aria-live="polite" class="flex items-center gap-1.5 text-[11px] font-mono text-warning">
              <span class="relative flex h-1.5 w-1.5">
                <span class="absolute inline-flex h-full w-full rounded-full bg-warning opacity-60 animate-ping"></span>
                <span class="relative inline-flex rounded-full h-1.5 w-1.5 bg-warning"></span>
              </span>
              Processing
            </span>
          {/if}
        </svelte:fragment>
      </SectionHeader>

      {#if asyncStatus}
        <div role="status" aria-live="polite" class="p-2.5 surface-inset rounded-md text-xs font-mono text-foreground-muted">
          {asyncStatus}
        </div>
      {/if}

      <div class="flex-1 surface-inset rounded-md p-3 font-mono text-sm text-foreground overflow-y-auto leading-relaxed whitespace-pre-wrap min-h-[160px]">
        {#if translatedOutput}
          {translatedOutput}
        {:else}
          <div class="h-full flex items-center justify-center text-foreground-subtle italic">
            Translated output will appear here…
          </div>
        {/if}
      </div>
    </Card>
  </div>
</section>

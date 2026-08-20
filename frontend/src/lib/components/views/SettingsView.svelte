<script lang="ts">
  import { onMount } from 'svelte';
  import { activeTab, configStore, modelStore, refreshModels, authStore, pushToast } from '$lib/stores/appStore';
  import { openProviderModal } from '$lib/stores/providerModalStore';
  import { fetchApi } from '$lib/api/client';
  import Card from '../ui/Card.svelte';
  import Button from '../ui/Button.svelte';
  import Input from '../ui/Input.svelte';
  import Select from '../ui/Select.svelte';
  import Toggle from '../ui/Toggle.svelte';
  import SectionHeader from '../ui/SectionHeader.svelte';
  import Badge from '../ui/Badge.svelte';

  type Namespace = 'ocr' | 'translation' | 'transcription' | 'auth';
  const namespaceOrder: Namespace[] = ['ocr', 'translation', 'transcription', 'auth'];
  let activeNamespace: Namespace = 'ocr';
  let isSaving = false;

  // F3.13 audit fix: roving-tabindex keyboard handling for the
  // WAI-ARIA tablist. Arrow Left/Right move focus through the
  // tabs in source order; Home/End jump to the first/last. The
  // focus ring stays on the active tab when navigating, matching
  // the WAI-ARIA Authoring Practices tablist example.
  function handleTabKeydown(e: KeyboardEvent, currentId: string) {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight' && e.key !== 'Home' && e.key !== 'End') {
      return;
    }
    e.preventDefault();
    const idx = namespaceOrder.indexOf(currentId as Namespace);
    if (idx < 0) return;
    let next = idx;
    if (e.key === 'ArrowLeft') next = (idx - 1 + namespaceOrder.length) % namespaceOrder.length;
    else if (e.key === 'ArrowRight') next = (idx + 1) % namespaceOrder.length;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = namespaceOrder.length - 1;
    activeNamespace = namespaceOrder[next];
    // Move focus to the newly-active tab so screen readers
    // announce the new selection and the focus ring follows.
    requestAnimationFrame(() => {
      const btn = document.getElementById(`settings-tab-${namespaceOrder[next]}`);
      if (btn) btn.focus();
    });
  }

  // Document processor chips options — mirrors the backend
  // DocumentProcessorName enum and the workstation's ProcessSettings
  // list (audit P3: the previous labels were made-up names whose ids
  // the API rejects with a 422).
  const availableProcessors = [
    { id: 'reading_order', label: 'Reading order' },
    { id: 'quality_analysis', label: 'Quality analysis' },
    { id: 'structure_analysis', label: 'Structure analysis' },
    { id: 'section_analysis', label: 'Section analysis' },
    { id: 'layout_enrichment', label: 'Layout enrichment' },
    { id: 'table_extraction', label: 'Table extraction' },
  ];

  let maxUploadMb = 0;
  $: maxUploadMb = Math.round(($configStore.security?.max_upload_bytes || 0) / (1024 * 1024));

  onMount(() => {
    refreshModels('ocr');
    refreshModels('translation');
    refreshModels('transcription');
  });

  async function saveConfig() {
    isSaving = true;
    try {
      if (activeNamespace === 'ocr') {
        const payload = {
          ocr_api_base: $configStore.ocr_api_base || $configStore.api_base,
          ocr_api_key: $configStore.ocr_api_key || $configStore.api_key,
          ocr_model: $configStore.ocr_model || $configStore.model,
          document_processors: $configStore.document_processors || [],
        };
        await fetchApi('/config/ocr', { method: 'POST', body: JSON.stringify(payload) });
        pushToast('success', 'OCR namespace settings saved.', 3000);
      } else if (activeNamespace === 'translation') {
        const payload = {
          translation_api_base: $configStore.translation_api_base || $configStore.api_base,
          translation_api_key: $configStore.translation_api_key || $configStore.api_key,
          translation_model: $configStore.translation_model || $configStore.model,
          sliding_window_words: $configStore.sliding_window_words,
          dual_translate: $configStore.dual_translate,
        };
        await fetchApi('/config/translation', { method: 'POST', body: JSON.stringify(payload) });
        pushToast('success', 'Translation namespace settings saved.', 3000);
      } else if (activeNamespace === 'transcription') {
        const payload = {
          api_base: $configStore.transcription_api_base,
          transcription_api_key: $configStore.transcription_api_key,
          model: $configStore.transcription_model,
          engine: $configStore.transcription_engine,
          language: $configStore.transcription_language,
          prompt: $configStore.transcription_prompt,
          temperature: typeof $configStore.transcription_temperature === 'number'
            ? $configStore.transcription_temperature
            : (parseFloat(String($configStore.transcription_temperature)) || 0.0),
        };
        await fetchApi('/config/transcription', { method: 'POST', body: JSON.stringify(payload) });
        pushToast('success', 'Transcription namespace settings saved.', 3000);
      } else if (activeNamespace === 'auth') {
        await fetchApi('/config/ocr/auth', { method: 'POST', body: JSON.stringify({ auth_token: $authStore.ocr || null }) });
        await fetchApi('/config/translation/auth', { method: 'POST', body: JSON.stringify({ auth_token: $authStore.translation || null }) });
        pushToast('success', 'Server authentication tokens saved.', 3000);
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      pushToast('error', message || 'Save failed', 4000);
    } finally {
      isSaving = false;
    }
  }

  function toggleProcessor(processorId: string) {
    configStore.update((cfg) => {
      const current = cfg.document_processors || [];
      const updated = current.includes(processorId)
        ? current.filter((p) => p !== processorId)
        : [...current, processorId];
      return { ...cfg, document_processors: updated };
    });
  }
</script>

<section id="view-settings" data-view="settings" hidden={$activeTab !== 'settings'} class="flex-1 flex flex-col min-h-0 p-6 space-y-6">
  <!-- Header -->
  <header class="flex flex-col lg:flex-row lg:items-end justify-between border-b border-border pb-4 gap-3">
    <div class="space-y-1.5 min-w-0">
      <h2 class="text-2xl font-semibold font-display text-foreground">System configuration & settings</h2>
      <p class="text-xs text-foreground-muted">Configure LLM endpoints, credentials, processor plugins, and authentication</p>
    </div>

    <div class="flex items-center gap-2">
      <Button variant="secondary" on:click={() => openProviderModal(activeNamespace === 'auth' ? 'general' : activeNamespace)}>
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        <span>Browse provider presets</span>
      </Button>

      <Button variant="primary" loading={isSaving} on:click={saveConfig}>
        {isSaving ? 'Saving…' : 'Save settings'}
      </Button>
    </div>
  </header>

  <!-- Tabs bar -->
  <!-- F3.13 audit fix: WAI-ARIA tablist pattern. Previously the tabs
       were bare ``<button>`` elements with no list semantics, no
       role="tab" / role="tablist", no aria-selected, and no arrow-key
       roving. Screen readers announced them as four independent
       buttons; keyboard users had to Tab through every other
       interactive element on the page to reach the next tab. The
       fix: ``role="tablist"`` on the container, ``role="tab"`` +
       ``aria-selected`` + ``aria-controls`` on each button, and a
       roving tabindex (only the selected tab is in the tab order;
       arrow keys move focus through the others). -->
  <div
    class="flex items-center gap-1 border-b border-border -mb-px"
    role="tablist"
    aria-label="Settings namespace"
  >
    {#each [
      { id: 'ocr', label: 'OCR namespace' },
      { id: 'translation', label: 'Translation namespace' },
      { id: 'transcription', label: 'Transcription namespace' },
      { id: 'auth', label: 'Server auth tokens' }
    ] as tab (tab.id)}
      <button
        type="button"
        role="tab"
        id={`settings-tab-${tab.id}`}
        aria-selected={activeNamespace === tab.id}
        aria-controls={`settings-tabpanel-${tab.id}`}
        tabindex={activeNamespace === tab.id ? 0 : -1}
        on:click={() => activeNamespace = tab.id as Namespace}
        on:keydown={(e) => handleTabKeydown(e, tab.id)}
        class={[
          'h-9 px-4 text-xs font-medium font-body transition-colors',
          'border-b-2 -mb-px',
          'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand',
          activeNamespace === tab.id
            ? 'border-brand text-brand'
            : 'border-transparent text-foreground-muted hover:text-foreground hover:border-border-strong'
        ].join(' ')}
      >
        {tab.label}
      </button>
    {/each}
  </div>

  <!-- Tab content -->
  <div class="flex-1 overflow-y-auto pr-1">
    {#if activeNamespace === 'ocr'}
      <div id="settings-tabpanel-ocr" role="tabpanel" tabindex="0" aria-labelledby="settings-tab-ocr">
        <Card padding="lg" class="max-w-3xl space-y-6">
          <SectionHeader title="OCR LLM backend settings" description="Endpoints, model, and processor plugins used by the OCR pipeline." />

          <div class="space-y-4">
            <Input
              id="ocr-api-base"
              label="OCR API base URL"
              type="text"
              bind:value={$configStore.ocr_api_base}
              placeholder={$configStore.api_base || 'http://localhost:1234/v1'}
            />
            <Input
              id="ocr-api-key"
              label="OCR API key"
              type="password"
              bind:value={$configStore.ocr_api_key}
              placeholder="lm-studio / masked"
              hint="Stored server-side. Never sent to the browser."
            />

            <div>
              <div class="flex items-center justify-between mb-1.5">
                <label for="ocr-model" class="form-label mb-0">OCR model ID</label>
                <button type="button" on:click={() => refreshModels('ocr')} class="text-xs text-brand hover:underline">
                  Refresh models
                </button>
              </div>
              <div class="flex gap-2">
                <Input
                  id="ocr-model"
                  type="text"
                  bind:value={$configStore.ocr_model}
                  placeholder="allenai/olmocr-2-7b"
                  class="flex-1 font-mono"
                />
                <Select
                  label=""
                  ariaLabel="Pick OCR model from the server list"
                  options={[
                    { value: '', label: '(Select model)' },
                    ...$modelStore.ocr.map(m => ({ value: m, label: m }))
                  ]}
                  on:change={(e) => {
                    const v = (e.target as HTMLSelectElement).value;
                    if (v) configStore.update((c) => ({ ...c, ocr_model: v }));
                  }}
                />
              </div>
            </div>

            <!-- Document Processor Chips -->
            <div class="pt-4 border-t border-border space-y-3">
              <p class="form-label">Document processors</p>
              <p class="text-xs text-foreground-muted">
                Select local post-OCR processors to run automatically before PDF generation.
              </p>
              <div class="flex flex-wrap gap-2 pt-1">
                {#each availableProcessors as proc (proc.id)}
                  {@const active = ($configStore.document_processors || []).includes(proc.id)}
                  <button
                    type="button"
                    on:click={() => toggleProcessor(proc.id)}
                    class={[
                      'px-3 py-1.5 text-xs font-medium rounded-md border transition-all flex items-center gap-1.5',
                      active
                        ? 'bg-brand/10 border-brand text-brand shadow-sm'
                        : 'bg-surface-alt border-border text-foreground-muted hover:border-border-strong hover:text-foreground'
                    ].join(' ')}
                  >
                    {#if active}
                      <svg class="w-3.5 h-3.5 text-brand" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                      </svg>
                    {/if}
                    <span>{proc.label}</span>
                  </button>
                {/each}
              </div>
            </div>
          </div>
        </Card>
      </div>

    {:else if activeNamespace === 'translation'}
      <div id="settings-tabpanel-translation" role="tabpanel" tabindex="0" aria-labelledby="settings-tab-translation">
        <Card padding="lg" class="max-w-3xl space-y-6">
          <SectionHeader title="Translation backend settings" description="Endpoints and parameters used by the translation pipeline." />

          <div class="space-y-4">
            <Input
              id="translation-api-base"
              label="Translation API base URL"
              type="text"
              bind:value={$configStore.translation_api_base}
              placeholder={$configStore.api_base || 'https://api.openai.com/v1'}
            />
            <Input
              id="translation-api-key"
              label="Translation API key"
              type="password"
              bind:value={$configStore.translation_api_key}
              placeholder="sk-... / masked"
              hint="Stored server-side. Never sent to the browser."
            />

            <div>
              <div class="flex items-center justify-between mb-1.5">
                <label for="translation-model" class="form-label mb-0">Translation model ID</label>
                <button type="button" on:click={() => refreshModels('translation')} class="text-xs text-brand hover:underline">
                  Refresh models
                </button>
              </div>
              <div class="flex gap-2">
                <Input
                  id="translation-model"
                  type="text"
                  bind:value={$configStore.translation_model}
                  placeholder="gpt-4o-mini"
                  class="flex-1 font-mono"
                />
                <Select
                  label=""
                  ariaLabel="Pick translation model from the server list"
                  options={[
                    { value: '', label: '(Select model)' },
                    ...$modelStore.translation.map(m => ({ value: m, label: m }))
                  ]}
                  on:change={(e) => {
                    const v = (e.target as HTMLSelectElement).value;
                    if (v) configStore.update((c) => ({ ...c, translation_model: v }));
                  }}
                />
              </div>
            </div>

            <div class="pt-4 border-t border-border space-y-4">
              <Toggle
                id="dual-translate"
                label="Enable secondary LLM dual verification"
                description="Cross-check translations with a second model for higher accuracy"
                bind:checked={$configStore.dual_translate}
              />
            </div>
          </div>
        </Card>
      </div>

    {:else if activeNamespace === 'transcription'}
      <div id="settings-tabpanel-transcription" role="tabpanel" tabindex="0" aria-labelledby="settings-tab-transcription">
        <Card padding="lg" class="max-w-3xl space-y-6">
          <SectionHeader title="Voice transcription settings" description="Whisper-compatible backend and prompt tuning." />

          <div class="space-y-4">
            <Input
              id="transcription-api-base"
              label="Transcription API base URL"
              type="text"
              bind:value={$configStore.transcription_api_base}
              placeholder="https://api.openai.com/v1"
            />
            <Input
              id="transcription-api-key"
              label="Transcription API key"
              type="password"
              bind:value={$configStore.transcription_api_key}
              placeholder="sk-..."
            />

            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Select
                id="transcription-engine"
                label="Engine type"
                options={[
                  { value: 'api', label: 'OpenAI / Remote API' },
                  { value: 'faster-whisper', label: 'Local Faster-Whisper' }
                ]}
                value={$configStore.transcription_engine}
                on:change={(e) => {
                  const v = (e.target as HTMLSelectElement).value;
                  configStore.update((c) => ({ ...c, transcription_engine: v }));
                }}
              />
              <div class="space-y-1.5">
                <label class="form-label" for="transcription-model">Model name</label>
                <div class="flex gap-2">
                  <Input
                    id="transcription-model"
                    label=""
                    type="text"
                    bind:value={$configStore.transcription_model}
                    placeholder="whisper-1"
                    class="flex-1 font-mono"
                  />
                  <Select
                    label=""
                    ariaLabel="Pick transcription model from the server list"
                    options={[
                      { value: '', label: '(Select model)' },
                      ...$modelStore.transcription.map(m => ({ value: m, label: m }))
                    ]}
                    on:change={(e) => {
                      const v = (e.target as HTMLSelectElement).value;
                      if (v) configStore.update((c) => ({ ...c, transcription_model: v }));
                    }}
                  />
                </div>
              </div>
            </div>
          </div>
        </Card>
      </div>

    {:else if activeNamespace === 'auth'}
      <div id="settings-tabpanel-auth" role="tabpanel" tabindex="0" aria-labelledby="settings-tab-auth">
        <Card padding="lg" class="max-w-3xl space-y-6">
          <SectionHeader title="Server authentication & bearer tokens" description="OMNISCRIBE_AUTH_TOKEN and per-service overrides." />

          <div class="space-y-4">
            <Input
              id="auth-global"
              label="Global bearer auth token (OMNISCRIBE_AUTH_TOKEN)"
              type="password"
              bind:value={$authStore.global}
              placeholder="Enter global bearer token…"
            />
            <Input
              id="auth-ocr"
              label="OCR per-service override token (OMNISCRIBE_OCR_AUTH_TOKEN)"
              type="password"
              bind:value={$authStore.ocr}
              placeholder="Leave empty to use global token"
            />
            <Input
              id="auth-translation"
              label="Translation per-service override token (OMNISCRIBE_TRANSLATION_AUTH_TOKEN)"
              type="password"
              bind:value={$authStore.translation}
              placeholder="Leave empty to use global token"
            />
            <Input
              id="auth-transcription"
              label="Transcription per-service override token (OMNISCRIBE_TRANSCRIPTION_AUTH_TOKEN)"
              type="password"
              bind:value={$authStore.transcription}
              placeholder="Leave empty to use global token"
            />

            <div class="pt-4 border-t border-border surface-inset p-3 space-y-1 rounded-md">
              <p class="text-sm font-display font-semibold text-foreground">Upload limits & environment</p>
              <div class="flex items-center gap-2 text-xs text-foreground-muted">
                <span>Max upload cap:</span>
                <Badge variant="success" size="sm">{maxUploadMb} MB</Badge>
                <span class="font-mono text-foreground-subtle">({$configStore.security?.max_upload_bytes || 0} bytes)</span>
              </div>
            </div>
          </div>
        </Card>
      </div>
    {/if}
  </div>
</section>

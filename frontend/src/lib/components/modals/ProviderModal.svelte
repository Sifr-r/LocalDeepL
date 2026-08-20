<script lang="ts">
  import {
    isProviderModalOpen,
    providerTargetNamespace,
    closeProviderModal
  } from '../../stores/providerModalStore';
  import {
    configStore,
    toastStore,
    updateOcrNamespace,
    updateTranslationNamespace,
    updateTranscriptionNamespace,
  } from '../../stores/appStore';
  import { fetchApi } from '../../api/client';
  import { getProviders, getProviderModels, type ProviderModelsResponse } from '../../api/endpoints';
  import type { ProviderPreset } from '../../types/api';
  import Modal from '../ui/Modal.svelte';
  import Button from '../ui/Button.svelte';
  import Badge from '../ui/Badge.svelte';

  /**
   * Per-provider live-model state. Mirrors the lifecycle the modal drives:
   *
   *   idle    → no fetch attempted yet
   *   loading → fetch in flight
   *   ok      → live models returned (may be empty if the provider has no
   *             models in the account, e.g. an unprovisioned key)
   *   error   → fetch failed; the static `models` list is shown as a
   *             fallback so the modal is never empty for a real provider
   */
  type ModelState = 'idle' | 'loading' | 'ok' | 'error';

  interface ProviderModelEntry {
    state: ModelState;
    models: string[];
    error: string | null;
  }

  /** Concurrency cap for the auto-load fan-out. Keeps the backend polite
   * when 50+ providers are queried on modal open. */
  const MAX_CONCURRENT_FETCHES = 12;

  /** Placeholder URL fragments the static catalog ships with. The auto-load
   * will always fail for these (the server can't construct a valid request
   * URL with `<...>` in it), so we skip the network round-trip and just
   * show the static preset list. This also avoids a swarm of 5-second
   * timeouts on every modal open. */
  const PLACEHOLDER_URL_NEEDLES = ['<resource>', '<account_id>', '{workspaceid}'];

  let providers: ProviderPreset[] = [];
  let loading = false;
  let error: string | null = null;

  /** Per-provider live-model state, keyed by provider id. Cleared on modal
   * close so each open does a fresh batch (live data is the point). */
  let modelState: Record<string, ProviderModelEntry> = {};
  /** Provider ids currently being fetched — drives the global "Loading
   * models…" indicator in the modal header. */
  let fetchingIds: Set<string> = new Set();
  /** Provider ids whose model list the user has expanded inline. */
  let expandedIds: Set<string> = new Set();

  async function loadCatalog() {
    loading = true;
    error = null;
    try {
      providers = await getProviders();
    } catch (err: unknown) {
      error = err instanceof Error ? err.message : 'Failed to fetch provider presets';
      providers = [];
    } finally {
      loading = false;
    }
    // Kick off the live model fan-out after the catalog is in hand.
    autoLoadAllModels();
  }

  /** Small inline async pool — no new dependency. Pulls one job off
   * `queue` at a time as workers free up, capped at `limit` parallel
   * in-flight tasks. Returns when the queue is drained. */
  async function runWithLimit<T>(
    items: T[],
    limit: number,
    worker: (item: T) => Promise<void>
  ): Promise<void> {
    let next = 0;
    const runners: Array<Promise<void>> = [];
    const launch = async (): Promise<void> => {
      while (true) {
        const idx = next++;
        if (idx >= items.length) return;
        await worker(items[idx]);
      }
    };
    const cap = Math.max(1, Math.min(limit, items.length));
    for (let i = 0; i < cap; i++) {
      runners.push(launch());
    }
    await Promise.all(runners);
  }

  function isPlaceholderUrl(url: string | null | undefined): boolean {
    if (!url) return true;
    const lower = url.toLowerCase();
    return PLACEHOLDER_URL_NEEDLES.some((needle) => lower.includes(needle));
  }

  async function loadModelsForProvider(p: ProviderPreset, opts: { force?: boolean } = {}): Promise<void> {
    if (!opts.force) {
      const existing = modelState[p.id];
      if (existing && (existing.state === 'loading' || existing.state === 'ok')) {
        return;
      }
    }
    const apiBase = p.api_base || p.recommended_base_url;
    if (isPlaceholderUrl(apiBase)) {
      // Skip the network round-trip entirely — the URL is a template
      // the user hasn't filled in. Surface the static list as the only
      // option.
      modelState = {
        ...modelState,
        [p.id]: {
          state: 'error',
          models: [],
          error: 'Configure the URL first to load live models.'
        }
      };
      return;
    }
    fetchingIds.add(p.id);
    fetchingIds = new Set(fetchingIds);
    modelState = {
      ...modelState,
      [p.id]: { state: 'loading', models: modelState[p.id]?.models ?? [], error: null }
    };
    try {
      const res: ProviderModelsResponse = await getProviderModels(p.id);
      // The server returns a static fallback list when the live fetch
      // fails; surface that to the user with a non-blocking error badge.
      const hasError = !!res.error && res.models.length === 0;
      modelState = {
        ...modelState,
        [p.id]: {
          state: hasError ? 'error' : 'ok',
          models: res.models ?? [],
          error: res.error ?? null
        }
      };
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load models';
      modelState = {
        ...modelState,
        [p.id]: { state: 'error', models: modelState[p.id]?.models ?? [], error: message }
      };
    } finally {
      fetchingIds.delete(p.id);
      fetchingIds = new Set(fetchingIds);
    }
  }

  async function autoLoadAllModels(): Promise<void> {
    if (providers.length === 0) return;
    await runWithLimit(providers, MAX_CONCURRENT_FETCHES, async (p) => {
      await loadModelsForProvider(p);
    });
  }

  function toggleExpanded(id: string): void {
    const next = new Set(expandedIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    expandedIds = next;
  }

  function refreshOne(p: ProviderPreset, event: Event): void {
    event.stopPropagation();
    void loadModelsForProvider(p, { force: true });
  }

  function refreshAll(): void {
    void autoLoadAllModels();
  }

  // Reactive trigger: any time the modal transitions to open, reload the
  // catalog and fan out the model fetches. On close, drop the per-modal
  // state so the next open starts fresh.
  let lastOpen = false;
  $: if ($isProviderModalOpen && !lastOpen) {
    lastOpen = true;
    modelState = {};
    expandedIds = new Set();
    void loadCatalog();
  } else if (!$isProviderModalOpen && lastOpen) {
    lastOpen = false;
  }

  function closeModal() {
    closeProviderModal();
  }

  async function applyPreset(provider: ProviderPreset, modelOverride?: string) {
    const target = $providerTargetNamespace;
    const base = provider.api_base || provider.recommended_base_url;
    const model = modelOverride ?? provider.default_model;

    configStore.update((cfg) => {
      if (target === 'ocr') {
        return {
          ...cfg,
          ocr_api_base: base,
          ocr_model: model,
          ocr_provider: provider.id,
        };
      } else if (target === 'translation') {
        return {
          ...cfg,
          translation_api_base: base,
          translation_model: model,
          translation_provider: provider.id,
        };
      } else if (target === 'transcription') {
        return {
          ...cfg,
          transcription_api_base: base,
          transcription_model: model,
        };
      } else {
        return {
          ...cfg,
          api_base: base,
          model: model,
        };
      }
    });

    try {
      await fetchApi('/providers/active', {
        method: 'POST',
        body: JSON.stringify({
          provider_id: provider.id,
          model: model || undefined,
        }),
      });

      if (target === 'ocr') {
        await updateOcrNamespace({
          ocr_api_base: base,
          ocr_model: model,
          ocr_provider: provider.id,
        });
      } else if (target === 'translation') {
        await updateTranslationNamespace({
          translation_api_base: base,
          translation_model: model,
          translation_provider: provider.id,
        });
      } else if (target === 'transcription') {
        await updateTranscriptionNamespace({
          transcription_api_base: base,
          transcription_model: model,
        });
      }
      toastStore.pushToast('success', `Applied and saved preset: ${provider.name} (${target})`);
    } catch (err: unknown) {
      toastStore.pushToast('success', `Applied preset: ${provider.name} (${target})`);
    }

    closeModal();
  }

  function applyWithModel(provider: ProviderPreset, model: string) {
    void applyPreset(provider, model);
  }
</script>

<Modal
  open={$isProviderModalOpen}
  on:close={closeModal}
  title="LLM provider catalog"
  description="Select a preset to populate API base and model configuration"
  maxWidth="xl"
>
  <div class="space-y-3">
    <div class="flex items-center justify-between text-xs text-foreground-muted">
      <span>
        {#if providers.length > 0}
          {providers.length} provider{providers.length === 1 ? '' : 's'} · {fetchingIds.size} loading models
        {:else if loading}
          Loading catalog…
        {/if}
      </span>
      <button
        type="button"
        class="text-brand hover:underline disabled:opacity-50 disabled:cursor-not-allowed"
        on:click={refreshAll}
        disabled={providers.length === 0 || fetchingIds.size > 0}
        data-testid="refresh-all-models"
      >
        Refresh all models
      </button>
    </div>

    {#if loading}
      <div class="py-12 flex flex-col items-center justify-center gap-3 text-foreground-muted">
        <div class="w-6 h-6 border-2 border-brand border-t-transparent rounded-full animate-spin"></div>
        <span class="text-xs text-foreground-muted">Loading provider catalog…</span>
      </div>
    {:else if error}
      <div class="p-4 rounded-md bg-danger/10 border border-danger/30 text-danger text-xs font-mono">
        {error}
      </div>
    {:else if providers.length === 0}
      <div class="py-8 text-center text-xs text-foreground-muted">
        No provider presets available.
      </div>
    {:else}
      {#each providers as provider (provider.id)}
        {@const entry = modelState[provider.id]}
        {@const isExpanded = expandedIds.has(provider.id)}
        {@const isFetching = fetchingIds.has(provider.id)}
        <div class="p-4 surface-inset rounded-md space-y-2 group" data-testid="provider-card" data-provider-id={provider.id}>
          <div class="flex items-center justify-between gap-4">
            <div class="space-y-1.5 min-w-0 flex-1">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="font-display font-semibold text-sm text-foreground group-hover:text-brand transition-colors">
                  {provider.name}
                </span>
                {#if provider.requires_key}
                  <Badge variant="warning" size="sm">Requires API key</Badge>
                {:else}
                  <Badge variant="success" size="sm" dot>Local / no key</Badge>
                {/if}
                {#if isFetching}
                  <Badge variant="info" size="sm">Loading models…</Badge>
                {/if}
              </div>
              {#if provider.description}
                <p class="text-xs text-foreground-muted">{provider.description}</p>
              {/if}
              <div class="font-mono text-[10px] text-foreground-subtle space-x-3">
                <span>Base: <span class="text-foreground">{provider.api_base || provider.recommended_base_url}</span></span>
                <span>Model: <span class="text-foreground">{provider.default_model}</span></span>
              </div>
            </div>

            <div class="flex items-center gap-2 shrink-0">
              <button
                type="button"
                class="text-xs text-brand hover:underline disabled:opacity-50"
                on:click={(e) => refreshOne(provider, e)}
                disabled={isFetching}
                aria-label={`Refresh models for ${provider.name}`}
                data-testid="provider-refresh"
              >
                Refresh
              </button>
              <Button
                variant="primary"
                size="sm"
                on:click={() => applyPreset(provider)}
              >
                Use preset
              </Button>
            </div>
          </div>

          <!-- Live model list. Default: collapsed to a single status line so
               the modal stays scannable with 50+ providers. -->
          <div class="border-t border-border-subtle pt-2" data-testid="provider-models-section">
            {#if !entry || entry.state === 'idle'}
              <div class="text-[11px] text-foreground-subtle italic">Models not yet loaded</div>
            {:else if entry.state === 'loading' && entry.models.length === 0}
              <div class="flex items-center gap-2 text-[11px] text-foreground-muted">
                <span class="w-3 h-3 border-2 border-brand border-t-transparent rounded-full animate-spin"></span>
                <span>Loading live models…</span>
              </div>
            {:else if entry.state === 'error' && entry.models.length === 0}
              <div class="space-y-1">
                <div class="text-[11px] text-foreground-subtle italic" data-testid="provider-models-error">
                  {#if entry.error}
                    {entry.error}
                  {:else}
                    Could not reach provider — no models available.
                  {/if}
                </div>
                {#if (provider.default_model)}
                  <div class="font-mono text-[10px] text-foreground-subtle">
                    Static fallback: <span class="text-foreground">{provider.default_model}</span>
                  </div>
                {/if}
              </div>
            {:else}
              {@const models = entry.models}
              <button
                type="button"
                class="flex items-center gap-2 text-[11px] text-foreground-muted hover:text-foreground"
                on:click={() => toggleExpanded(provider.id)}
                aria-expanded={isExpanded}
                data-testid="provider-models-toggle"
              >
                <span class="font-mono text-foreground">{models.length}</span>
                <span>model{models.length === 1 ? '' : 's'} available</span>
                {#if entry.state === 'error' && entry.error}
                  <span class="text-foreground-subtle" data-testid="provider-models-stale">· static fallback ({entry.error})</span>
                {/if}
                <span class="text-foreground-subtle">{isExpanded ? '▾' : '▸'}</span>
              </button>
              {#if isExpanded}
                <ul class="mt-2 max-h-48 overflow-y-auto space-y-0.5 pl-2 border-l border-border-subtle" data-testid="provider-models-list">
                  {#each models as m (m)}
                    <li class="flex items-center gap-2 group/item">
                      <span class="font-mono text-[11px] text-foreground-muted flex-1 truncate" title={m}>
                        {m}
                      </span>
                      <button
                        type="button"
                        class="opacity-0 group-hover/item:opacity-100 text-[10px] text-brand hover:underline"
                        on:click={() => applyWithModel(provider, m)}
                        title={`Use ${m} as the ${$providerTargetNamespace} model`}
                      >
                        Use
                      </button>
                    </li>
                  {/each}
                </ul>
              {/if}
            {/if}
          </div>
        </div>
      {/each}
    {/if}
  </div>

  <svelte:fragment slot="footer">
    <Button variant="secondary" on:click={closeModal}>
      Close
    </Button>
  </svelte:fragment>
</Modal>

<script lang="ts">
  import {
    isProviderModalOpen,
    providerTargetNamespace,
    closeProviderModal
  } from '../../stores/providerModalStore';
  import { configStore, toastStore } from '../../stores/appStore';
  import { getProviders } from '../../api/endpoints';
  import type { ProviderPreset } from '../../types/api';
  import Modal from '../ui/Modal.svelte';
  import Button from '../ui/Button.svelte';
  import Badge from '../ui/Badge.svelte';

  let providers: ProviderPreset[] = [];
  let loading = false;
  let error: string | null = null;

  async function loadCatalog() {
    loading = true;
    error = null;
    try {
      providers = await getProviders();
    } catch (err: unknown) {
      error = err instanceof Error ? err.message : 'Failed to fetch provider presets';
    } finally {
      loading = false;
    }
  }

  $: if ($isProviderModalOpen) {
    loadCatalog();
  }

  function closeModal() {
    closeProviderModal();
  }

  function applyPreset(provider: ProviderPreset) {
    const target = $providerTargetNamespace;
    const base = provider.api_base || provider.recommended_base_url;
    const model = provider.default_model;

    configStore.update((cfg) => {
      if (target === 'ocr') {
        return {
          ...cfg,
          ocr_api_base: base,
          ocr_model: model,
        };
      } else if (target === 'translation') {
        return {
          ...cfg,
          translation_api_base: base,
          translation_model: model,
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
    toastStore.pushToast('success', `Applied preset: ${provider.name} (${target})`);
    closeModal();
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
        <div class="p-4 surface-inset rounded-md flex items-center justify-between gap-4 group">
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
            </div>
            {#if provider.description}
              <p class="text-xs text-foreground-muted">{provider.description}</p>
            {/if}
            <div class="font-mono text-[10px] text-foreground-subtle space-x-3">
              <span>Base: <span class="text-foreground">{provider.api_base || provider.recommended_base_url}</span></span>
              <span>Model: <span class="text-foreground">{provider.default_model}</span></span>
            </div>
          </div>

          <Button
            variant="primary"
            size="sm"
            on:click={() => applyPreset(provider)}
          >
            Use preset
          </Button>
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

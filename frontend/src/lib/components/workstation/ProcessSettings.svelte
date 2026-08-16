<script lang="ts">
  import { configStore } from '../../stores/appStore';
  import type { PipelineMode, DenseMode, SpellcheckMode, DocumentProcessorName } from '../../types/api';
  import SectionHeader from '../ui/SectionHeader.svelte';
  import Select from '../ui/Select.svelte';
  import Toggle from '../ui/Toggle.svelte';

  const pipelineModes = [
    { value: 'hybrid', label: 'Hybrid (OCR + VLM)' },
    { value: 'grounded', label: 'Grounded BBox' },
    { value: 'grounded_native', label: 'Grounded Native' }
  ];

  const denseModes = [
    { value: 'auto', label: 'Auto' },
    { value: 'on', label: 'On' },
    { value: 'off', label: 'Off' }
  ];

  // Mirrors the backend SpellcheckMode enum (dictionary languages).
  const spellcheckModes = [
    { value: 'none', label: 'None' },
    { value: 'en-US', label: 'English (US)' },
    { value: 'ar', label: 'Arabic' },
    { value: 'de', label: 'German' },
    { value: 'es', label: 'Spanish' },
    { value: 'fr', label: 'French' }
  ];

  // Mirrors the backend DocumentProcessorName enum — invalid names are
  // rejected by /api/process, so only real processors are offered here.
  const availableProcessors: { value: DocumentProcessorName; label: string }[] = [
    { value: 'reading_order', label: 'Reading order' },
    { value: 'quality_analysis', label: 'Quality analysis' },
    { value: 'structure_analysis', label: 'Structure analysis' },
    { value: 'section_analysis', label: 'Section analysis' },
    { value: 'layout_enrichment', label: 'Layout enrichment' },
    { value: 'table_extraction', label: 'Table extraction' }
  ];

  function toggleProcessor(processor: string) {
    configStore.update((cfg) => {
      const current = cfg.document_processors || [];
      const updated = current.includes(processor)
        ? current.filter((p) => p !== processor)
        : [...current, processor];
      return { ...cfg, document_processors: updated };
    });
  }

  function togglePreprocessor(field: 'orientation_detection' | 'deskew' | 'denoise' | 'normalize_contrast' | 'crop_cleanup') {
    configStore.update((cfg) => ({ ...cfg, [field]: !cfg[field] }));
  }

  $: preprocessors = {
    orientation_detection: $configStore.orientation_detection ?? true,
    deskew: $configStore.deskew ?? true,
    denoise: $configStore.denoise ?? false,
    normalize_contrast: $configStore.normalize_contrast ?? true,
    crop_cleanup: $configStore.crop_cleanup ?? false
  };
</script>

<div class="space-y-5">
  <SectionHeader title="Pipeline settings" />

  <div class="space-y-4">
    <Select
      id="pipeline-mode-select"
      label="Pipeline mode"
      options={pipelineModes}
      value={$configStore.pipeline_mode || 'hybrid'}
      on:change={(e) => configStore.update((c) => ({ ...c, pipeline_mode: (e.target as HTMLSelectElement).value as PipelineMode }))}
    />

    <div class="grid grid-cols-2 gap-3">
      <Select
        id="dense-mode-select"
        label="Dense mode"
        options={denseModes}
        value={$configStore.dense_mode || 'auto'}
        on:change={(e) => configStore.update((c) => ({ ...c, dense_mode: (e.target as HTMLSelectElement).value as DenseMode }))}
      />
      <Select
        id="spellcheck-select"
        label="Spellcheck"
        options={spellcheckModes}
        value={$configStore.spellcheck || 'none'}
        on:change={(e) => configStore.update((c) => ({ ...c, spellcheck: (e.target as HTMLSelectElement).value as SpellcheckMode }))}
      />
    </div>
  </div>

  <div>
    <p class="form-label">Document processors</p>
    <div id="doc-processors-list" class="flex flex-wrap gap-2">
      {#each availableProcessors as proc (proc.value)}
        {@const active = ($configStore.document_processors || []).includes(proc.value)}
        <button
          type="button"
          on:click={() => toggleProcessor(proc.value)}
          class={[
            'inline-flex items-center gap-1.5 h-8 px-3 rounded-md text-xs font-medium',
            'border transition-colors',
            'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1 focus-visible:ring-offset-card',
            active
              ? 'bg-brand/15 border-brand/40 text-brand'
              : 'bg-card border-border text-foreground-muted hover:text-foreground hover:border-border-strong'
          ].join(' ')}
        >
          {#if active}
            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7" />
            </svg>
          {/if}
          <span>{proc.label}</span>
        </button>
      {/each}
    </div>
  </div>

  <div>
    <p class="form-label">Image preprocessing</p>
    <div id="preprocessors-group" class="surface-inset p-3 space-y-1">
      <Toggle
        id="toggle-orientation"
        label="Orientation detection"
        checked={preprocessors.orientation_detection}
        on:click={() => togglePreprocessor('orientation_detection')}
      />
      <Toggle
        id="toggle-deskew"
        label="Deskew image"
        checked={preprocessors.deskew}
        on:click={() => togglePreprocessor('deskew')}
      />
      <Toggle
        id="toggle-denoise"
        label="Denoise"
        checked={preprocessors.denoise}
        on:click={() => togglePreprocessor('denoise')}
      />
      <Toggle
        id="toggle-normalize"
        label="Normalize contrast"
        checked={preprocessors.normalize_contrast}
        on:click={() => togglePreprocessor('normalize_contrast')}
      />
      <Toggle
        id="toggle-crop"
        label="Crop cleanup"
        description="Trim borders before OCR"
        checked={preprocessors.crop_cleanup}
        on:click={() => togglePreprocessor('crop_cleanup')}
      />
    </div>
  </div>

  <div>
    <p class="form-label">Submission</p>
    <div id="submission-group" class="surface-inset p-3">
      <Toggle
        id="toggle-async"
        label="Async processing"
        description="Submit to /api/process/async and poll for the result. Long jobs no longer block the upload response; the result PDF is fetched when the worker finishes."
        checked={Boolean($configStore.use_async)}
        on:click={() => configStore.update((c) => ({ ...c, use_async: !c.use_async }))}
      />
    </div>
  </div>
</div>

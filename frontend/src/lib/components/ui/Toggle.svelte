<script lang="ts">
  /**
   * Toggle — design system primitive.
   *
   * Switch component for boolean preprocessor / option toggles.
   * Replaces the native checkbox + label pattern currently used
   * in ProcessSettings.svelte.
   *
   *   <Toggle bind:checked={preprocessors.denoise} label="Denoise" />
   *   <Toggle bind:checked={value} label="..." description="Helper text" />
   */
  export let id: string = `toggle-${Math.random().toString(36).slice(2, 9)}`;
  export let label: string;
  export let description: string = '';
  export let checked: boolean = false;
  export let disabled: boolean = false;
</script>

<label
  for={id}
  class="flex items-center justify-between gap-3 py-1.5 cursor-pointer select-none
         hover:text-foreground transition-colors
         {disabled ? 'opacity-50 cursor-not-allowed' : ''}"
>
  <div class="min-w-0">
    <span class="text-sm text-foreground">{label}</span>
    {#if description}
      <p class="text-xs text-foreground-muted mt-0.5">{description}</p>
    {/if}
  </div>

  <button
    {id}
    type="button"
    role="switch"
    aria-checked={checked}
    aria-label={label}
    {disabled}
    on:click={() => !disabled && (checked = !checked)}
    class={[
      'relative inline-flex h-5 w-9 shrink-0 items-center rounded-full',
      'transition-colors duration-150',
      'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-background',
      checked ? 'bg-brand' : 'bg-muted'
    ].join(' ')}
  >
    <span
      class={[
        'inline-block h-4 w-4 transform rounded-full bg-white shadow-sm',
        'transition-transform duration-150',
        checked ? 'translate-x-[18px]' : 'translate-x-0.5'
      ].join(' ')}
    ></span>
  </button>
</label>

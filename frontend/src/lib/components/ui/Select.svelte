<script lang="ts">
  /**
   * Select — design system primitive.
   *
   * Thin wrapper over native <select>. Same label/hint/error
   * contract as Input. Options are passed as a `options` array
   * of { value, label } pairs, or via the <option> default slot
   * for more flexibility.
   */
  export let id: string = `select-${Math.random().toString(36).slice(2, 9)}`;
  export let value: string = '';
  export let label = '';
  export let hint = '';
  export let error: string = '';
  export let disabled = false;
  export let fullWidth = true;
  export let options: Array<{ value: string; label: string }> | null = null;

  $: hasOptions = Array.isArray(options) && options.length > 0;
</script>

<div class={fullWidth ? 'w-full' : ''}>
  {#if label}
    <label for={id} class="form-label">{label}</label>
  {/if}
  <div class="relative">
    <select
      {id}
      {disabled}
      bind:value
      on:change
      on:blur
      on:focus
      class={[
        'w-full h-9 pl-3 pr-9 rounded-md text-sm font-body appearance-none',
        'bg-card text-foreground',
        'border transition-colors',
        'focus:outline-none focus:ring-2 focus:ring-brand/20',
        error
          ? 'border-danger focus:border-danger focus:ring-danger/20'
          : 'border-input focus:border-brand',
        disabled && 'opacity-50 cursor-not-allowed'
      ].filter(Boolean).join(' ')}
    >
      {#if hasOptions}
        {#each options as opt (opt.value)}
          <option value={opt.value}>{opt.label}</option>
        {/each}
      {:else}
        <slot />
      {/if}
    </select>
    <svg
      class="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-foreground-muted"
      viewBox="0 0 20 20"
      fill="none"
      aria-hidden="true"
    >
      <path d="M5.5 8L10 12.5L14.5 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
    </svg>
  </div>
  {#if error}
    <p class="mt-1 text-xs text-danger">{error}</p>
  {:else if hint}
    <p class="mt-1 text-xs text-foreground-muted">{hint}</p>
  {/if}
</div>

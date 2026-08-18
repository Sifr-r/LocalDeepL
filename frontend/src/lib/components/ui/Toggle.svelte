<script lang="ts">
  /**
   * Toggle — design system primitive.
   *
   * Switch component for boolean preprocessor / option toggles.
   * Built on a real ``<input type="checkbox">`` so the browser
   * handles click / keyboard / screen-reader semantics natively
   * (and ``bind:checked`` works without a custom event bridge).
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

  <!--
    The visible switch is a styled <span>; the actual form control is
    a visually-hidden <input type="checkbox">. This avoids the label /
    button overlap that the audit flagged (clicking the label used to
    re-fire the button's click handler) and gives screen readers a
    real checkbox semantics instead of role="switch" on a <button>.
  -->
  <span class="relative inline-flex h-5 w-9 shrink-0 items-center">
    <input
      {id}
      type="checkbox"
      role="switch"
      bind:checked
      {disabled}
      aria-label={label}
      class="peer absolute inset-0 z-10 opacity-0 cursor-pointer
             focus:outline-none focus-visible:opacity-100 focus-visible:ring-2
             focus-visible:ring-brand focus-visible:ring-offset-2
             focus-visible:ring-offset-background
             disabled:cursor-not-allowed"
    />
    <span
      aria-hidden="true"
      class={[
        'pointer-events-none absolute inset-0 inline-block rounded-full',
        'transition-colors duration-150',
        checked ? 'bg-brand' : 'bg-muted'
      ].join(' ')}
    ></span>
    <span
      aria-hidden="true"
      class={[
        'pointer-events-none absolute left-0.5 top-0.5 inline-block h-4 w-4',
        'transform rounded-full bg-white shadow-sm',
        'transition-transform duration-150',
        checked ? 'translate-x-4' : 'translate-x-0'
      ].join(' ')}
    ></span>
  </span>
</label>

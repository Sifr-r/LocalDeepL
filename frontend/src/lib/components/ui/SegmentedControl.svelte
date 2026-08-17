<script lang="ts" generics="T extends string">
  /**
   * SegmentedControl — single-select pill-style button group.
   *
   * Used for sub-navigation, template selection, and view-mode
   * toggles where exactly one option is active at a time.
   *
   *   <SegmentedControl
   *     bind:value={activeTabMode}
   *     ariaLabel="Sub-view"
   *     options={[
   *       { value: 'library', label: 'Library list' },
   *       { value: 'entries', label: 'Entries view' },
   *     ]}
   *   />
   *
   * NOT for top-level navigation: use the TabRibbon for primary
   * tabs (it ships `role="tablist"` + roving tabindex + arrow-key
   * handling). NOT for true form input: use a `<select>` or a
   * radio group wrapped in a `<fieldset>` for that.
   *
   * `ariaLabel` is required (no visible label is rendered).
   */
  type Option = { value: T; label: string; title?: string };

  export let value: T;
  export let options: Option[];
  export let ariaLabel: string = '';
  // Optional utility-class passthrough (Card / Input have the same
  // pattern) so a call site can swap the surface (e.g. to a border
  // + raised background for the smaller metadata-panel variant).
  let customClass: string = '';
  export { customClass as class };
</script>

<div
  role="group"
  aria-label={ariaLabel || undefined}
  class={[
    'inline-flex items-center gap-1 surface-inset p-1 rounded-md',
    customClass
  ].filter(Boolean).join(' ')}
>
  {#each options as opt (opt.value)}
    <button
      type="button"
      on:click={() => (value = opt.value)}
      title={opt.title}
      aria-pressed={value === opt.value}
      class={[
        'h-7 px-3 rounded text-xs font-medium font-body transition-colors',
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1 focus-visible:ring-offset-card',
        value === opt.value
          ? 'bg-brand text-brand-foreground shadow-sm'
          : 'text-foreground-muted hover:text-foreground'
      ].join(' ')}
    >
      {opt.label}
    </button>
  {/each}
</div>

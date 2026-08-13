<script lang="ts">
  /**
   * Button — design system primitive.
   *
   * Variants:
   *   primary   brand fill, white text  — single hero action per view
   *   secondary surface-2 fill, normal text + border  — paired actions
   *   ghost     transparent, muted text  — tertiary / icon buttons
   *   danger    danger-tinted, danger text  — destructive
   *   outline   transparent fill, brand border + text  — call-to-action that
   *            shouldn't compete with the primary action
   *
   * Sizes:
   *   sm  h-8  text-xs  px-3
   *   md  h-9  text-sm  px-4  (default)
   *   lg  h-11 text-sm  px-5  (hero / "Start Processing")
   *
   * Pass `loading` to swap label for a spinner; pass `icon` to render
   * a leading icon (use a snippet in the slot for that — not yet
   * supported here; components that need an icon can pass via children).
   */
  export let variant: 'primary' | 'secondary' | 'ghost' | 'danger' | 'outline' = 'primary';
  export let size: 'sm' | 'md' | 'lg' = 'md';
  export let type: 'button' | 'submit' | 'reset' = 'button';
  export let disabled = false;
  export let loading = false;
  export let fullWidth = false;
  export let id = '';
  export let title = '';
  export let ariaLabel: string = '';

  $: variantClass = {
    primary: 'bg-brand-500 text-brand-foreground hover:bg-brand-600 active:bg-brand-700 shadow-sm disabled:bg-brand-500/50',
    secondary: 'bg-card-raised text-foreground border border-border hover:bg-muted disabled:opacity-50',
    ghost: 'bg-transparent text-foreground-muted hover:bg-muted hover:text-foreground disabled:opacity-50',
    danger: 'bg-danger/15 text-danger border border-danger/30 hover:bg-danger hover:text-white disabled:opacity-50',
    outline: 'bg-transparent text-brand border border-brand/40 hover:bg-brand/10 disabled:opacity-50'
  }[variant];

  $: sizeClass = {
    sm: 'h-8 px-3 text-xs',
    md: 'h-9 px-4 text-sm',
    lg: 'h-11 px-5 text-sm'
  }[size];
</script>

<button
  {id}
  {type}
  {title}
  {disabled}
  aria-label={ariaLabel || undefined}
  on:click
  on:mouseenter
  on:mouseleave
  class={[
    'inline-flex items-center justify-center gap-2',
    'rounded-md font-medium font-body',
    'transition-colors duration-150',
    'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-background',
    'disabled:cursor-not-allowed',
    fullWidth && 'w-full',
    variantClass,
    sizeClass
  ].filter(Boolean).join(' ')}
>
  {#if loading}
    <span class="inline-block w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin" aria-hidden="true"></span>
  {/if}
  <slot />
</button>

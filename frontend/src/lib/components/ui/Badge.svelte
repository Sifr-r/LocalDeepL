<script context="module" lang="ts">
  export type BadgeVariant = 'neutral' | 'brand' | 'success' | 'warning' | 'danger' | 'info';
</script>

<script lang="ts">
  /**
   * Badge — design system primitive.
   *
   * Small pill used for status, counts, and tags.
   * Variants map to the semantic color tokens.
   *
   *   neutral   muted, default
   *   brand     primary accent
   *   success   completion, confidence high
   *   warning   processing, caution
   *   danger    failure, destructive
   *   info      informational
   */
  export let variant: BadgeVariant = 'neutral';
  export let size: 'sm' | 'md' = 'sm';
  export let dot = false;
  export let title: string | undefined = undefined;
  export let className: string = '';
  let customClass: string = '';
  export { customClass as class };

  $: variantClass = {
    neutral: 'bg-muted text-foreground-muted border border-border',
    brand:   'bg-brand/15 text-brand border border-brand/30',
    success: 'bg-success/15 text-success border border-success/30',
    warning: 'bg-warning/15 text-warning border border-warning/30',
    danger:  'bg-danger/15 text-danger border border-danger/30',
    info:    'bg-brand/10 text-foreground-muted border border-border'
  }[variant];

  $: sizeClass = {
    sm: 'h-5 px-2 text-[10px]',
    md: 'h-6 px-2.5 text-xs'
  }[size];

  $: dotColor = {
    neutral: 'bg-foreground-muted',
    brand:   'bg-brand',
    success: 'bg-success',
    warning: 'bg-warning',
    danger:  'bg-danger',
    info:    'bg-foreground-muted'
  }[variant];
</script>

<span
  {title}
  class={[
    'inline-flex items-center gap-1.5 rounded-full font-medium font-body whitespace-nowrap',
    variantClass,
    sizeClass,
    customClass,
    className
  ].filter(Boolean).join(' ')}
>
  {#if dot}
    <span class={['w-1.5 h-1.5 rounded-full', dotColor].join(' ')}></span>
  {/if}
  <slot />
</span>

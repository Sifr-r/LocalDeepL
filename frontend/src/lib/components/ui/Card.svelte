<script lang="ts">
  /**
   * Card — design system primitive.
   *
   * The universal panel. Owns background + border + radius;
   * padding is applied via the p-* utility on the element.
   *
   * Variants:
   *   default  surface-1 bg, subtle border
   *   raised   surface-2 bg (used for nested groups inside another card)
   *   inset    surface-2 bg, no border (used inside cards for soft groups)
   *
   * Header / footer slots are optional and render inside a flex
   * column. The default slot is the body.
   */
  export let variant: 'default' | 'raised' | 'inset' = 'default';
  export let padding: 'none' | 'sm' | 'md' | 'lg' = 'md';
  export let className: string = '';
  let customClass: string = '';
  export { customClass as class };

  $: variantClass = {
    default: 'bg-card border border-border',
    raised: 'bg-card-raised border border-border',
    inset: 'bg-card-raised border-0'
  }[variant];

  $: paddingClass = {
    none: '',
    sm: 'p-3',
    md: 'p-4',
    lg: 'p-6'
  }[padding];
</script>

<div class={['rounded-[var(--radius-card)]', variantClass, paddingClass, customClass, className].filter(Boolean).join(' ')}>
  {#if $$slots.header}
    <div class="mb-3 pb-3 border-b border-border last:mb-0 last:pb-0">
      <slot name="header" />
    </div>
  {/if}
  <slot />
  {#if $$slots.footer}
    <div class="mt-3 pt-3 border-t border-border">
      <slot name="footer" />
    </div>
  {/if}
</div>

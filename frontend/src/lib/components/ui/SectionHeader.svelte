<script lang="ts">
  /**
   * SectionHeader — uppercase label with optional action slot.
   *
   * Used inside cards and panels to label logical sections:
   *   <SectionHeader title="Pipeline Mode" />
   *   <SectionHeader title="Document Processors">
   *     <button slot="action">+ Add</button>
   *   </SectionHeader>
   *
   * The "Config" / "Inspector" / etc. pill that used to float on
   * the right of section titles is gone; the action slot replaces it.
   */
  export let title: string;
  export let description: string = '';
  export let divider: boolean = true;
</script>

<div class={divider ? 'pb-2 border-b border-border mb-3' : 'mb-2'}>
  <div class="flex items-center justify-between gap-3">
    <div class="min-w-0">
      <h4 class="font-display text-xs font-semibold tracking-wider uppercase text-foreground-muted">
        {title}
      </h4>
      {#if description}
        <p class="mt-0.5 text-xs text-foreground-subtle">{description}</p>
      {/if}
    </div>
    {#if $$slots.action}
      <div class="shrink-0">
        <slot name="action" />
      </div>
    {/if}
  </div>
</div>

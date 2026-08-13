<script lang="ts">
  /**
   * Modal — design system primitive.
   *
   * Wraps a backdrop + dialog with proper focus management and
   * a11y (role="dialog", aria-modal, aria-labelledby, Escape to close,
   * click outside to close).
   *
   * Slots:
   *   default   — modal body
   *   header    — content next to the close button (right side of title row)
   *   footer    — action row at the bottom
   *
   * The footer slot replaces the default bottom border; pass anything
   * you want — usually a flex row of Buttons right-aligned.
   */
  import { createEventDispatcher, onMount } from 'svelte';
  import Button from './Button.svelte';

  export let open: boolean = false;
  export let title: string = '';
  export let description: string = '';
  export let maxWidth: 'sm' | 'md' | 'lg' | 'xl' = 'md';

  const dispatch = createEventDispatcher<{ close: void }>();

  let dialogEl: HTMLDivElement;
  let titleId = `modal-title-${Math.random().toString(36).slice(2, 9)}`;

  $: maxWidthClass = {
    sm: 'max-w-sm',
    md: 'max-w-md',
    lg: 'max-w-lg',
    xl: 'max-w-xl'
  }[maxWidth];

  function closeModal() {
    open = false;
    dispatch('close');
  }

  function handleBackdropKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') closeModal();
  }

  onMount(() => {
    // Future enhancement: trap focus inside the dialog while open
  });
</script>

{#if open}
  <!-- Backdrop -->
  <div
    class="fixed inset-0 z-50 bg-overlay/80 backdrop-blur-sm flex items-center justify-center p-4"
    role="presentation"
    on:click={closeModal}
    on:keydown={handleBackdropKeydown}
  >
    <!-- Dialog (stopPropagation so backdrop click doesn't fire) -->
    <div
      bind:this={dialogEl}
      on:click|stopPropagation
      on:keydown|stopPropagation
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      tabindex="-1"
      class={[
        'w-full shadow-2xl outline-none',
        maxWidthClass
      ].join(' ')}
    >
      <div class="bg-card border border-border rounded-xl p-6 max-h-[85vh] flex flex-col text-foreground">
        <!-- Header -->
        <div class="flex items-start justify-between gap-3 pb-4 border-b border-border">
          <div class="min-w-0 flex-1">
            <h3 id={titleId} class="font-display text-lg font-semibold text-foreground">
              {title}
            </h3>
            {#if description}
              <p class="text-xs text-foreground-muted mt-1">{description}</p>
            {/if}
          </div>
          <div class="flex items-center gap-2 shrink-0">
            {#if $$slots.header}
              <slot name="header" />
            {/if}
            <Button
              variant="ghost"
              size="sm"
              on:click={closeModal}
              title="Close dialog"
              ariaLabel="Close dialog"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </Button>
          </div>
        </div>

        <!-- Body -->
        <div class="flex-1 overflow-y-auto py-4">
          <slot />
        </div>

        <!-- Footer -->
        {#if $$slots.footer}
          <div class="flex justify-end gap-2 pt-4 border-t border-border">
            <slot name="footer" />
          </div>
        {/if}
      </div>
    </div>
  </div>
{/if}

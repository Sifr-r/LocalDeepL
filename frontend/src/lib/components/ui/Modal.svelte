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
  import { createEventDispatcher, tick } from 'svelte';
  import Button from './Button.svelte';

  export let open: boolean = false;
  export let title: string = '';
  export let description: string = '';
  export let maxWidth: 'sm' | 'md' | 'lg' | 'xl' = 'md';

  const dispatch = createEventDispatcher<{ close: void }>();

  let dialogEl: HTMLDivElement;
  let titleId = `modal-title-${Math.random().toString(36).slice(2, 9)}`;
  // Initialise to the opposite of `open` so a `Modal` mounted with
  // `open={true}` still fires the open-path on its first reactive tick
  // (otherwise the initial value already matches and the transition
  // guard would skip focus management).
  let prevOpen = !open;
  // Element that had focus before the modal opened — restored on close.
  let prevActiveElement: HTMLElement | null = null;

  $: maxWidthClass = {
    sm: 'max-w-sm',
    md: 'max-w-md',
    lg: 'max-w-lg',
    xl: 'max-w-xl'
  }[maxWidth];

  /**
   * Returns the focusable descendants of `root` in DOM order, skipping
   * disabled controls, hidden inputs, and elements with a negative
   * tabindex (which includes the dialog root itself).
   *
   * No further visibility filter: the CSS selector above already
   * excludes disabled/hidden controls, and a strict `offsetParent`
   * check would break in jsdom (which does not compute layout) and
   * in any environment where the dialog is rendered without the
   * surrounding CSS module.
   */
  function getFocusable(root: HTMLElement): HTMLElement[] {
    const selector =
      'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]),' +
      ' select:not([disabled]), textarea:not([disabled]),' +
      ' [tabindex]:not([tabindex="-1"])';
    return Array.from(root.querySelectorAll<HTMLElement>(selector));
  }

  function focusFirst() {
    if (!dialogEl) return;
    const focusables = getFocusable(dialogEl);
    if (focusables.length > 0) {
      focusables[0].focus();
    } else {
      dialogEl.focus();
    }
  }

  function closeModal() {
    // Idempotent so the window capture-phase Escape handler and the
    // backdrop's bubble-phase handler can't both dispatch `close` for
    // a single keypress.
    if (!open) return;
    open = false;
    dispatch('close');
  }

  function handleWindowKeydown(e: KeyboardEvent) {
    if (!open) return;
    if (e.key === 'Escape') {
      closeModal();
      return;
    }
    if (e.key !== 'Tab' || !dialogEl) return;
    const focusables = getFocusable(dialogEl);
    if (focusables.length === 0) {
      // No focusable descendants — keep focus pinned to the dialog root.
      e.preventDefault();
      dialogEl.focus();
      return;
    }
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    const active = document.activeElement as HTMLElement | null;
    const focusInside = active !== null && dialogEl.contains(active);
    if (e.shiftKey) {
      if (!focusInside || active === first) {
        e.preventDefault();
        last.focus();
      }
    } else {
      if (!focusInside || active === last) {
        e.preventDefault();
        first.focus();
      }
    }
  }

  function handleBackdropKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') closeModal();
  }

  // Open/close transition: capture the trigger on open, restore focus on close.
  // Uses the prevOpen guard so this only fires on actual transitions, not on
  // every reactive tick.
  $: {
    if (open !== prevOpen) {
      if (open) {
        if (typeof document !== 'undefined') {
          const active = document.activeElement as HTMLElement | null;
          prevActiveElement =
            active && active !== document.body && typeof active.focus === 'function'
              ? active
              : null;
        }
        tick().then(focusFirst);
      } else if (typeof document !== 'undefined' && prevActiveElement) {
        const el = prevActiveElement;
        prevActiveElement = null;
        // Defer to the next frame so the dialog has unmounted before we
        // hand focus back to the trigger.
        tick().then(() => {
          if (typeof el.focus === 'function') el.focus();
        });
      }
      prevOpen = open;
    }
  }
</script>

<!--
  Capture phase so the dialog's `on:keydown|stopPropagation` (which is
  declared in the bubble phase) cannot prevent this listener from seeing
  Tab/Shift+Tab pressed inside the dialog. Capture runs before any
  element's bubble-phase handler, so we always get a chance to trap the
  focus before the default browser focus shift happens.
-->
<svelte:window on:keydown|capture={handleWindowKeydown} />

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

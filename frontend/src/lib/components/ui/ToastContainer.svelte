<script lang="ts">
  import { toastStore } from '../../stores/appStore';

  type Level = 'info' | 'success' | 'warning' | 'error';

  /**
   * Toast level → design tokens. Map each level to:
   *   - a left-accent border color
   *   - an icon color
   *   - a soft background tint
   */
  function getLevelStyles(level: Level) {
    switch (level) {
      case 'success':
        return {
          container: 'bg-success/10 border-success/30 text-foreground',
          accent: 'border-l-success',
          icon: 'text-success'
        };
      case 'warning':
        return {
          container: 'bg-warning/10 border-warning/30 text-foreground',
          accent: 'border-l-warning',
          icon: 'text-warning'
        };
      case 'error':
        return {
          container: 'bg-danger/10 border-danger/30 text-foreground',
          accent: 'border-l-danger',
          icon: 'text-danger'
        };
      case 'info':
      default:
        return {
          container: 'bg-brand/10 border-brand/30 text-foreground',
          accent: 'border-l-brand',
          icon: 'text-brand'
        };
    }
  }
</script>

<div
  class="fixed bottom-5 right-5 z-50 flex flex-col gap-2 max-w-md pointer-events-none"
  role="region"
  aria-label="Notifications"
  aria-live="polite"
  aria-relevant="additions"
>
  {#each $toastStore as toast (toast.id)}
    {@const styles = getLevelStyles(toast.level)}
    <div
      class={[
        'pointer-events-auto flex items-start justify-between gap-3 px-4 py-3',
        'rounded-md border border-l-4 shadow-lg backdrop-blur-md',
        'animate-slide-in font-body text-sm',
        styles.container,
        styles.accent
      ].join(' ')}
      role={toast.level === 'error' ? 'alert' : 'status'}
    >
      <div class="flex items-start gap-2.5 min-w-0">
        <span class={['shrink-0 mt-0.5', styles.icon].join(' ')} aria-hidden="true">
          {#if toast.level === 'success'}
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
            </svg>
          {:else if toast.level === 'warning'}
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          {:else if toast.level === 'error'}
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          {:else}
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          {/if}
        </span>
        <span class="leading-snug">{toast.message}</span>
      </div>

      <button
        type="button"
        class="shrink-0 -mr-1 -mt-1 p-1 rounded text-foreground-muted hover:text-foreground hover:bg-muted transition-colors"
        aria-label="Dismiss notification"
        title="Dismiss"
        on:click={() => toastStore.removeToast(toast.id)}
      >
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  {/each}
</div>

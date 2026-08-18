<script lang="ts">
  /**
   * AuthRequiredBanner — F3.3 audit fix.
   *
   * Persistent banner shown when the API client has seen a 401
   * response (the configured bearer token is missing or wrong).
   * The banner deep-links to the Settings view's auth tab and
   * can be manually dismissed.
   */
  import { authRequired, activeTab } from '../../stores/appStore';

  function openSettings() {
    authRequired.set(false);
    activeTab.set('settings');
  }

  function dismiss() {
    authRequired.set(false);
  }
</script>

{#if $authRequired}
  <div
    role="status"
    aria-live="polite"
    class="flex items-center justify-between gap-3 px-4 py-2.5 mx-4 mt-3
           rounded-md border border-l-4 border-l-danger
           bg-danger/10 border-danger/30 text-foreground text-sm font-body
           shadow-sm"
  >
    <div class="flex items-start gap-2.5 min-w-0">
      <span class="shrink-0 mt-0.5 text-danger" aria-hidden="true">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      </span>
      <div class="min-w-0">
        <strong class="font-medium">Authentication required</strong>
        <span class="text-foreground-muted ml-1">
          — the API rejected the request with a 401. Set a bearer token in
          Settings to continue.
        </span>
      </div>
    </div>

    <div class="shrink-0 flex items-center gap-2">
      <button
        type="button"
        on:click={openSettings}
        class="px-3 py-1 rounded text-xs font-medium bg-brand text-brand-foreground
               hover:opacity-90 transition-opacity"
      >
        Open Settings
      </button>
      <button
        type="button"
        on:click={dismiss}
        aria-label="Dismiss authentication banner"
        title="Dismiss"
        class="p-1 rounded text-foreground-muted hover:text-foreground hover:bg-muted transition-colors"
      >
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  </div>
{/if}

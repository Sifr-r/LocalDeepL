<script lang="ts">
  import { onDestroy, onMount, tick } from 'svelte';
  import { activeTab, themeStore, websocketStore, type TabType } from '../../stores/appStore';
  import { fetchApi } from '../../api/client';
  import type { FetchOptions } from '../../api/fetchOptions';

  const tabs: { id: string; label: string; tabKey: TabType }[] = [
    { id: 'app-tab-btn-workstation', label: 'OCR Workstation', tabKey: 'workstation' },
    { id: 'app-tab-btn-translation', label: 'Translation', tabKey: 'translation' },
    { id: 'app-tab-btn-glossary', label: 'Glossary', tabKey: 'glossary' },
    { id: 'app-tab-btn-settings', label: 'Settings', tabKey: 'settings' },
    { id: 'app-tab-btn-jobs', label: 'Jobs', tabKey: 'jobs' },
    { id: 'app-tab-btn-transcription', label: 'Transcription', tabKey: 'transcription' },
    { id: 'app-tab-btn-extraction', label: 'Extraction', tabKey: 'extraction' }
  ];

  // Honest connection status: liveness ping against /health plus the
  // live WebSocket state while a job is streaming.
  const HEALTH_POLL_MS = 15000;
  let backendOnline: boolean | null = null; // null = probing
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  // AbortController for the in-flight /health probe. A new controller is
  // created per ping (and the previous one aborted) so the 15-s poll
  // tick does not race an older request that is still in flight, and
  // ``onDestroy`` aborts the latest one so an unmount mid-ping does not
  // keep the network round-trip running after the component is gone.
  let pingAbort: AbortController | null = null;

  async function pingHealth() {
    pingAbort?.abort(); // cancel any in-flight ping before starting a new one
    pingAbort = new AbortController();
    const { signal } = pingAbort;
    const healthOpts: FetchOptions = {
      signal,
      cache: 'no-store',
      // Health probes must NOT surface as user-facing toasts on 5xx;
      // a flapping backend would otherwise spam the user every 15 s.
      silent: true
    };
    try {
      const res = await fetchApi<{ status: string }>('/health', healthOpts);
      // ``res`` may be ``null`` if the response body was empty /
      // unparseable; treat that as "not online" rather than throwing.
      // Phase C / Task 21: verify the ``status`` field too so an empty
      // body or unexpected shape (e.g. ``{}``) cannot flip the badge
      // to "online" without an actual ok signal from the server.
      backendOnline = res !== null && res.status === 'ok';
    } catch (err: unknown) {
      // An AbortError means the component unmounted (or a newer ping
      // superseded this one). Treat both as a no-op for the visible
      // badge — a superseded ping is not a "backend is down" signal,
      // and an unmount mid-ping should not flip the badge right as
      // the component is being torn down.
      if (err instanceof DOMException && err.name === 'AbortError') {
        return;
      }
      backendOnline = false;
    }
  }

  onMount(() => {
    void pingHealth();
    pollTimer = setInterval(pingHealth, HEALTH_POLL_MS);
  });

  onDestroy(() => {
    if (pollTimer) clearInterval(pollTimer);
    pingAbort?.abort();
    pingAbort = null;
  });

  type ConnState = 'checking' | 'offline' | 'online' | 'live';
  $: connState = ($websocketStore.isConnected
    ? 'live'
    : backendOnline === null
    ? 'checking'
    : backendOnline
    ? 'online'
    : 'offline') as ConnState;

  const connLabel: Record<ConnState, string> = {
    checking: 'Checking…',
    offline: 'Offline',
    online: 'Online',
    live: 'Live'
  };

  function toggleTheme() {
    themeStore.update((t) => (t === 'dark' ? 'light' : 'dark'));
  }

  // WAI-ARIA tablist keyboard pattern. The roving `tabindex` already
  // puts only the active tab in the tab order; arrow keys move focus
  // AND activate the new tab (the "automatic activation" pattern,
  // which fits a primary navigation tablist where every tab is a
  // one-keystroke destination). Home/End jump to the first/last tab.
  async function onTabKeydown(e: KeyboardEvent, fromIndex: number) {
    let target: number | null = null;
    if (e.key === 'ArrowRight') {
      target = (fromIndex + 1) % tabs.length;
    } else if (e.key === 'ArrowLeft') {
      target = (fromIndex - 1 + tabs.length) % tabs.length;
    } else if (e.key === 'Home') {
      target = 0;
    } else if (e.key === 'End') {
      target = tabs.length - 1;
    }
    if (target === null || target === fromIndex) return;
    e.preventDefault();
    activeTab.set(tabs[target].tabKey);
    // Defer focus until Svelte has updated the active tab's tabindex
    // and aria-selected, so the next focus() lands on the right node.
    await tick();
    document.getElementById(tabs[target].id)?.focus();
  }
</script>

<header class="w-full bg-card/80 backdrop-blur-md border-b border-border px-5 h-14 flex items-center justify-between sticky top-0 z-30">
  <!-- Brand + Nav cluster -->
  <div class="flex items-center gap-8 min-w-0">
    <!-- Brand mark -->
    <a href="/" class="flex items-center gap-2.5 shrink-0" aria-label="OmniScribe home">
      <div class="w-7 h-7 rounded-md bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center text-white font-display font-bold text-[11px] tracking-wider shadow-sm">
        OS
      </div>
      <span class="font-display font-semibold text-[15px] tracking-tight text-foreground">
        OmniScribe
      </span>
      <span class="hidden sm:inline-flex items-center h-5 px-1.5 rounded text-[10px] font-mono text-foreground-muted bg-muted border border-border">
        v2.5
      </span>
    </a>

    <!-- Navigation Tabs -->
    <!-- WAI-ARIA tab pattern: the container is a `tablist`, each
         button is a `tab`. Roving `tabindex` (active=0, others=-1)
         gives keyboard users a single tab stop that follows the
         selected tab. The `aria-label` is a stable human-readable
         name for assistive tech; the design language is screen
         reader-agnostic.

         The svelte-check `a11y_no_noninteractive_element_to_interactive_role`
         warning fires because `<nav>` is implicitly a navigation
         landmark while `tablist` is an interactive composite role.
         The two roles serve different assistive-tech audiences: the
         landmark shortcut (`nav` → "skip to navigation") and the
         tablist keyboard model. We keep both: the surrounding
         `<header>` already advertises the section, and `aria-label`
         on the tablist gives the tab list its own name. Suppressing
         the warning here is intentional and minimal. -->
    <!-- svelte-ignore a11y_no_noninteractive_element_to_interactive_role -->
    <nav
      class="flex items-center gap-1 overflow-x-auto -mx-1 px-1"
      role="tablist"
      aria-label="Primary"
    >
      {#each tabs as tab, i (tab.id)}
        <button
          id={tab.id}
          type="button"
          role="tab"
          aria-selected={$activeTab === tab.tabKey ? 'true' : 'false'}
          tabindex={$activeTab === tab.tabKey ? 0 : -1}
          class={[
            'h-8 px-3 rounded-md text-xs font-medium font-body whitespace-nowrap',
            'transition-colors duration-150',
            'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-card',
            $activeTab === tab.tabKey
              ? 'bg-brand text-brand-foreground shadow-sm'
              : 'text-foreground-muted hover:text-foreground hover:bg-muted'
          ].join(' ')}
          on:click={() => activeTab.set(tab.tabKey)}
          on:keydown={(e) => onTabKeydown(e, i)}
        >
          {tab.label}
        </button>
      {/each}
    </nav>
  </div>

  <!-- Right cluster: status + theme toggle -->
  <div class="flex items-center gap-2 shrink-0">
    <!-- Connection status (honest: /health probe + live WS state) -->
    <div
      class="hidden sm:inline-flex items-center gap-1.5 h-7 px-2.5 rounded-full bg-muted border border-border text-[11px] font-mono text-foreground-muted"
      title={connState === 'live'
        ? 'Progress stream connected'
        : connState === 'online'
        ? 'Backend reachable'
        : connState === 'offline'
        ? 'Backend unreachable'
        : 'Probing backend…'}
      role="status"
      aria-live="polite"
    >
      <span class="relative flex h-2 w-2">
        {#if connState === 'live'}
          <span class="absolute inline-flex h-full w-full rounded-full bg-success opacity-60 animate-ping"></span>
          <span class="relative inline-flex rounded-full h-2 w-2 bg-success"></span>
        {:else if connState === 'online'}
          <span class="relative inline-flex rounded-full h-2 w-2 bg-success"></span>
        {:else if connState === 'offline'}
          <span class="relative inline-flex rounded-full h-2 w-2 bg-danger"></span>
        {:else}
          <span class="relative inline-flex rounded-full h-2 w-2 bg-warning animate-pulse"></span>
        {/if}
      </span>
      <span>{connLabel[connState]}</span>
    </div>

    <!-- Theme toggle -->
    <button
      type="button"
      title="Toggle theme"
      aria-label="Toggle theme"
      on:click={toggleTheme}
      class="h-8 w-8 inline-flex items-center justify-center rounded-md text-foreground-muted hover:text-foreground hover:bg-muted border border-border transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-card"
    >
      {#if $themeStore === 'dark'}
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
        </svg>
      {:else}
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
        </svg>
      {/if}
    </button>
  </div>
</header>

<!--
  App.svelte - Root Application Orchestrator Component
  
  Responsibility:
  Top-level root component for the OmniScribe Frontend application. Combines:
  1. TabRibbon: Navigation bar & theme switcher
  2. WorkstationView: 3-column OCR Workstation (id="view-workstation")
  3. TranslationView: Context-aware AI translation tab (id="view-translation")
  4. GlossaryView: Terminology lexicon library (id="view-glossary")
  5. SettingsView: System configuration & credentials (id="view-settings")
  6. JobHistoryView: OCR job history (id="view-jobs")
  7. TranscriptionView: Audio transcription (id="view-transcription")
  8. ExtractionView: Structured extraction (id="view-extraction")
  9. ToastContainer: Floating alert notifications container
  10. ProviderModal / ExportModal: overlay dialogs
  
  CRITICAL PRESERVATION:
  Ensures all legacy HTML element IDs and structure remain present so end-to-end Playwright tests
  (`e2e/test_ui.py`) and legacy JS scripts continue to pass without modifications.
  
  Accessibility:
  - Theme class is applied reactively to <html> so the toggle works without a reload
  - Screen reader landmark regions (`header`, `main`)
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { activeTab, loadAppConfig, themeStore } from '$lib/stores/appStore';
  import TabRibbon from '$lib/components/ui/TabRibbon.svelte';
  import AuthRequiredBanner from '$lib/components/ui/AuthRequiredBanner.svelte';
  import ToastContainer from '$lib/components/ui/ToastContainer.svelte';
  import WorkstationView from '$lib/components/workstation/WorkstationView.svelte';
  import TranslationView from '$lib/components/views/TranslationView.svelte';
  import GlossaryView from '$lib/components/views/GlossaryView.svelte';
  import SettingsView from '$lib/components/views/SettingsView.svelte';
  import JobHistoryView from '$lib/components/views/JobHistoryView.svelte';
  import TranscriptionView from '$lib/components/views/TranscriptionView.svelte';
  import ExtractionView from '$lib/components/views/ExtractionView.svelte';
  import ProviderModal from '$lib/components/modals/ProviderModal.svelte';
  import ExportModal from '$lib/components/modals/ExportModal.svelte';

  // Apply the theme class reactively so the TabRibbon toggle takes effect
  // immediately (not only on the next full reload).
  $: if (typeof document !== 'undefined') {
    document.documentElement.classList.toggle('light', $themeStore === 'light');
  }

  /** Initialize Application Configuration on Mount */
  onMount(async () => {
    // Fetch config & available models from backend API
    await loadAppConfig();
  });
</script>

<!-- Skip-to-content link. Hidden by default with `sr-only`; the
     `focus:not-sr-only` brings it on-screen when a keyboard user
     tabs into it. Saves Tab users from walking through all 7 tabs
     in the TabRibbon on every page load. -->
<a
  href="#view-workstation"
  class="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:px-3 focus:py-1.5 focus:rounded focus:bg-brand focus:text-brand-foreground focus:text-xs focus:font-medium focus:shadow-lg"
>
  Skip to content
</a>

<!-- Root App Shell Container -->
<div class="flex flex-col h-screen w-screen bg-app text-foreground overflow-hidden relative font-sans">
  <!-- Ambient Glow Backdrop Effects -->
  <div class="pointer-events-none fixed -top-40 -left-40 w-96 h-96 rounded-full ambient-glow-1 z-0 opacity-40"></div>
  <div class="pointer-events-none fixed -bottom-40 -right-40 w-96 h-96 rounded-full ambient-glow-2 z-0 opacity-30"></div>

  <!-- Top App Navigation Ribbon (Preserves app-tab-btn-* IDs) -->
  <TabRibbon />

  <!-- F3.3 audit fix: persistent banner shown when the API has
       rejected a request with a 401. Deep-links to the Settings
       view's auth tab. -->
  <AuthRequiredBanner />

  <!-- Main View Area (Preserves view-* IDs; only the active view is mounted) -->
  <main class="flex-1 flex flex-col min-h-0 relative z-10 overflow-y-auto">
    {#if $activeTab === 'workstation'}
      <WorkstationView />
    {:else if $activeTab === 'translation'}
      <TranslationView />
    {:else if $activeTab === 'glossary'}
      <GlossaryView />
    {:else if $activeTab === 'settings'}
      <SettingsView />
    {:else if $activeTab === 'jobs'}
      <JobHistoryView />
    {:else if $activeTab === 'transcription'}
      <TranscriptionView />
    {:else if $activeTab === 'extraction'}
      <ExtractionView />
    {/if}
  </main>

  <!-- Modals & Overlay Containers -->
  <ProviderModal />
  <ExportModal />
  <ToastContainer />
</div>

<style>
  :global(body) {
    margin: 0;
    padding: 0;
    overflow: hidden;
  }
</style>

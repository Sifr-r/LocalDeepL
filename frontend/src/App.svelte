<!--
  App.svelte - Root Application Orchestrator Component
  
  Responsibility:
  Top-level root component for LocalDeepL Frontend application. Combines:
  1. TabRibbon: Navigation bar & theme switcher
  2. WorkstationView: 3-column OCR Workstation (id="view-workstation")
  3. TranslationView: Context-aware AI translation tab (id="view-translation")
  4. GlossaryView: Terminology lexicon library (id="view-glossary")
  5. SettingsView: System configuration & credentials (id="view-settings")
  6. ToastContainer: Floating alert notifications container (id="toast-container")
  7. ProviderModal: Add/edit custom LLM provider catalog (id="provider-modal")
  8. ExportModal: Download OCR text outputs
  
  CRITICAL PRESERVATION:
  Ensures all legacy HTML element IDs and structure remain present so end-to-end Playwright tests
  (`test_ui.py`) and legacy JS scripts continue to pass without modifications.
  
  Accessibility:
  - Outer app container sets dark mode theme class on document element
  - Screen reader landmark regions (`header`, `main`)
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { loadAppConfig, themeStore } from '$lib/stores/appStore';
  import TabRibbon from '$lib/components/ui/TabRibbon.svelte';
  import ToastContainer from '$lib/components/ui/ToastContainer.svelte';
  import WorkstationView from '$lib/components/workstation/WorkstationView.svelte';
  import TranslationView from '$lib/components/views/TranslationView.svelte';
  import GlossaryView from '$lib/components/views/GlossaryView.svelte';
  import SettingsView from '$lib/components/views/SettingsView.svelte';
  import ProviderModal from '$lib/components/modals/ProviderModal.svelte';
  import ExportModal from '$lib/components/modals/ExportModal.svelte';

  /** Initialize Application Configuration on Mount */
  onMount(async () => {
    // Set root document theme attribute
    if (typeof window !== 'undefined') {
      if ($themeStore === 'light') {
        document.documentElement.classList.add('light');
      } else {
        document.documentElement.classList.remove('light');
      }
    }

    // Fetch config & available models from backend API
    await loadAppConfig();
  });
</script>

<!-- Root App Shell Container -->
<div class="flex flex-col h-screen w-screen bg-slate-950 text-slate-100 overflow-hidden relative font-sans">
  <!-- Ambient Glow Backdrop Effects -->
  <div class="pointer-events-none fixed -top-40 -left-40 w-96 h-96 rounded-full ambient-glow-1 z-0 opacity-40"></div>
  <div class="pointer-events-none fixed -bottom-40 -right-40 w-96 h-96 rounded-full ambient-glow-2 z-0 opacity-30"></div>

  <!-- Top App Navigation Ribbon (Preserves app-tab-btn-* IDs) -->
  <TabRibbon />

  <!-- Main View Area (Preserves view-workstation, view-translation, view-glossary, view-settings IDs) -->
  <main class="flex-1 flex flex-col min-h-0 relative z-10">
    <WorkstationView />
    <TranslationView />
    <GlossaryView />
    <SettingsView />
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
    background-color: #030712;
  }
</style>

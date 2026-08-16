/**
 * App.svelte view-mounting test (audit L8).
 *
 * Asserts that App.svelte uses Svelte ``{#if}`` blocks to mount only the
 * currently active view at a time, instead of rendering all seven
 * simultaneously and gating them with the CSS ``hidden`` attribute.
 *
 * Approach:
 *   1. Stub every view component (WorkstationView, TranslationView, …)
 *      and every chrome component (TabRibbon, ToastContainer,
 *      ProviderModal, ExportModal) with a tiny fixture that emits a
 *      tagged ``<section data-view="…">`` / ``<div data-chrome="…">``.
 *      This keeps the test focused on App.svelte's view-switching logic
 *      and avoids exercising the real components' store / network
 *      dependencies.
 *   2. Drive the active tab by writing to the mocked ``activeTab``
 *      store, then assert that exactly one ``[data-view]`` element is
 *      in the DOM and that it matches the active tab.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { mount, tick, unmount } from 'svelte';
import type { ActiveTab } from '$lib/stores/appStore';

// Hoist the activeTab store so the appStore mock can re-export the same
// instance the test drives.
const { activeTab } = vi.hoisted(() => {
  // ``require`` returns ``any`` so the generic on ``writable`` is not
  // type-checkable here. Cast the require result to the public type to
  // preserve the ``ActiveTab`` parameter on the store.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { writable } = require('svelte/store') as typeof import('svelte/store');
  return { activeTab: writable<ActiveTab>('workstation') };
});

vi.mock('$lib/stores/appStore', () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { writable } = require('svelte/store');
  const defaultJobState = {
    activeJobId: null,
    percent: 0,
    stage: 'idle',
    statusMessage: '',
    warnings: [],
    chunks: [],
    failedPages: [],
    completedPages: [],
    qualitySummary: null,
    isProcessing: false
  };
  const defaultDocumentModel = {
    pages: [],
    textArtifacts: [],
    textArtifactId: null,
    textArtifactToken: null,
    bboxes: [],
    confidenceSummary: { average: 1, min: 1, max: 1 },
    pageCount: 0,
    trustSummary: null
  };
  return {
    activeTab,
    themeStore: writable('dark'),
    authStore: writable({}),
    defaultJobState,
    defaultDocumentModel,
    documentStore: writable({ ...defaultDocumentModel, filename: null }),
    jobStore: writable({ ...defaultJobState }),
    configStore: writable({
      api_base: 'http://127.0.0.1:11434',
      model: 'llama3:latest',
      pipeline_mode: 'hybrid',
      dense_mode: 'auto',
      spellcheck: 'none',
      document_processors: [],
      security: { max_upload_bytes: 52428800, max_upload_mb: 50 }
    }),
    toastStore: { pushToast: vi.fn(), set: () => {}, update: () => {}, subscribe: () => () => {} },
    modelStore: writable({ general: [], ocr: [], translation: [], transcription: [], lastFetched: {} }),
    exportModalOpen: writable(false),
    providerModalOpen: writable(false),
    websocketStore: {
      connect: vi.fn(),
      disconnect: vi.fn(),
      requestCancel: vi.fn().mockResolvedValue(undefined),
      subscribe: () => () => {}
    },
    loadAppConfig: vi.fn().mockResolvedValue(undefined),
    refreshModels: vi.fn().mockResolvedValue(undefined),
    pushToast: vi.fn()
  };
});

// Stub out the seven view components with the MockView* fixtures. Each
// fixture renders a <section data-view="…"> so the test can count views
// in the DOM. We use ``vi.mock`` factories that defer the actual
// component resolution until after Vite has transformed the ``.svelte``
// files — passing the raw path through to vi.mock directly would bypass
// the Svelte Vite plugin and fail with a syntax error.
vi.mock('$lib/components/workstation/WorkstationView.svelte', async () => {
  const mod = await import('./fixtures/MockViewWorkstation.svelte');
  return { default: mod.default };
});
vi.mock('$lib/components/views/TranslationView.svelte', async () => {
  const mod = await import('./fixtures/MockViewTranslation.svelte');
  return { default: mod.default };
});
vi.mock('$lib/components/views/GlossaryView.svelte', async () => {
  const mod = await import('./fixtures/MockViewGlossary.svelte');
  return { default: mod.default };
});
vi.mock('$lib/components/views/SettingsView.svelte', async () => {
  const mod = await import('./fixtures/MockViewSettings.svelte');
  return { default: mod.default };
});
vi.mock('$lib/components/views/JobHistoryView.svelte', async () => {
  const mod = await import('./fixtures/MockViewJobs.svelte');
  return { default: mod.default };
});
vi.mock('$lib/components/views/TranscriptionView.svelte', async () => {
  const mod = await import('./fixtures/MockViewTranscription.svelte');
  return { default: mod.default };
});
vi.mock('$lib/components/views/ExtractionView.svelte', async () => {
  const mod = await import('./fixtures/MockViewExtraction.svelte');
  return { default: mod.default };
});

// Stub the chrome components with the MockChrome* fixtures.
vi.mock('$lib/components/ui/TabRibbon.svelte', async () => {
  const mod = await import('./fixtures/MockChromeTabRibbon.svelte');
  return { default: mod.default };
});
vi.mock('$lib/components/ui/ToastContainer.svelte', async () => {
  const mod = await import('./fixtures/MockChromeToast.svelte');
  return { default: mod.default };
});
vi.mock('$lib/components/modals/ProviderModal.svelte', async () => {
  const mod = await import('./fixtures/MockChromeProviderModal.svelte');
  return { default: mod.default };
});
vi.mock('$lib/components/modals/ExportModal.svelte', async () => {
  const mod = await import('./fixtures/MockChromeExportModal.svelte');
  return { default: mod.default };
});

import App from '../App.svelte';

const ALL_TABS: ActiveTab[] = [
  'workstation',
  'translation',
  'glossary',
  'settings',
  'jobs',
  'transcription',
  'extraction'
];

describe('App.svelte view mounting (L8)', () => {
  let target: HTMLDivElement;
  let app: ReturnType<typeof mount> | undefined;

  beforeEach(() => {
    activeTab.set('workstation');
    target = document.createElement('div');
    document.body.appendChild(target);
  });

  afterEach(() => {
    if (app) {
      unmount(app);
      app = undefined;
    }
    while (document.body.firstChild) {
      document.body.removeChild(document.body.firstChild);
    }
  });

  it('mounts only the active view on initial render', async () => {
    app = mount(App, { target });
    await tick();

    const views = target.querySelectorAll('[data-view]');
    expect(views.length).toBe(1);
    expect(views[0].getAttribute('data-view')).toBe('workstation');
  });

  it('mounts only the active view after switching tabs', async () => {
    app = mount(App, { target });
    await tick();

    for (const tab of ALL_TABS) {
      activeTab.set(tab);
      await tick();
      const views = target.querySelectorAll('[data-view]');
      expect(views.length, `expected exactly one view for tab "${tab}"`).toBe(1);
      expect(views[0].getAttribute('data-view')).toBe(tab);
    }
  });

  it('does not keep inactive view components in the DOM', async () => {
    app = mount(App, { target });
    await tick();

    // Start on workstation.
    expect(target.querySelector('[data-view="translation"]')).toBeNull();
    expect(target.querySelector('[data-view="settings"]')).toBeNull();

    // Switch to translation — workstation must be gone.
    activeTab.set('translation');
    await tick();
    expect(target.querySelector('[data-view="translation"]')).not.toBeNull();
    expect(target.querySelector('[data-view="workstation"]')).toBeNull();
    expect(target.querySelector('[data-view="settings"]')).toBeNull();

    // Switch to settings — translation must be gone too.
    activeTab.set('settings');
    await tick();
    expect(target.querySelector('[data-view="settings"]')).not.toBeNull();
    expect(target.querySelector('[data-view="translation"]')).toBeNull();
    expect(target.querySelector('[data-view="workstation"]')).toBeNull();
  });

  it('keeps chrome components mounted across tab switches', async () => {
    app = mount(App, { target });
    await tick();

    // All four chrome pieces must be present from the start.
    expect(target.querySelector('[data-chrome="tab-ribbon"]')).not.toBeNull();
    expect(target.querySelector('[data-chrome="toast"]')).not.toBeNull();
    expect(target.querySelector('[data-chrome="provider-modal"]')).not.toBeNull();
    expect(target.querySelector('[data-chrome="export-modal"]')).not.toBeNull();

    // And must still be present after a tab switch.
    activeTab.set('jobs');
    await tick();
    expect(target.querySelectorAll('[data-chrome]').length).toBe(4);
  });
});

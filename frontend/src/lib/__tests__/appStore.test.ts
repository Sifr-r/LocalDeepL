import { describe, it, expect, beforeEach, afterEach, vi, type MockInstance } from 'vitest';
import { get } from 'svelte/store';
import * as clientModule from '../api/client';
import {
  activeTab,
  themeStore,
  authStore,
  toastStore,
  pushToast,
  loadAppConfig,
  defaultConfig
} from '../stores/appStore';
import type { NamespacedModelsResponse } from '../types/api';
import {
  cleanupApp,
  mountApp
} from './appHarness';

const AUTH_STORAGE_KEY = 'omniscribe.auth.v1';

// ``appStore`` persists ``activeTab`` and ``themeStore`` to
// ``localStorage``; the harness tests below drive the real ``<App>``
// component, which subscribes to ``activeTab`` and writes back via the
// store's own subscriber. We wipe these keys in ``beforeEach`` (and
// again in ``afterEach``) so cross-test contamination cannot leak the
// default into a different test's first render.
const PERSISTED_KEYS = [
  'omniscribe_active_tab',
  'omniscribe_theme',
  AUTH_STORAGE_KEY
] as const;

describe('appStore', () => {
  beforeEach(() => {
    for (const key of PERSISTED_KEYS) {
      localStorage.removeItem(key);
      sessionStorage.removeItem(key);
    }
    toastStore.set([]);
    activeTab.set('workstation');
    themeStore.set('dark');
    authStore.set({});
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    for (const key of PERSISTED_KEYS) {
      localStorage.removeItem(key);
      sessionStorage.removeItem(key);
    }
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('initializes default active tab and theme', () => {
    expect(get(activeTab)).toBe('workstation');
    expect(get(themeStore)).toBe('dark');
  });

  it('allows pushing and clearing toasts', () => {
    toastStore.set([]);
    expect(get(toastStore).length).toBe(0);

    pushToast('info', 'Test notification', 5000);
    expect(get(toastStore).length).toBe(1);
    expect(get(toastStore)[0].message).toBe('Test notification');
  });

  it('hydrates configuration on loadAppConfig', async () => {
    const mockConfig = {
      default_engine: 'hybrid',
      pipeline_mode: 'hybrid',
      dense_mode: 'auto',
      dense_threshold: 10,
      spellcheck_mode: 'none',
      document_processors: [],
      security: { max_upload_bytes: 52428800, max_upload_mb: 50 }
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockConfig
    } as Response);

    await loadAppConfig();
    expect(global.fetch).toHaveBeenCalled();
  });

  // Audit L6: bearer tokens must NOT land in `localStorage` (XSS-reachable
  // across sessions). They now live in `sessionStorage` (cleared on tab
  // close). These tests pin that contract — if anyone re-introduces a
  // `localStorage` write for the auth key, the test below will fail.
  it('persists auth tokens to sessionStorage, not localStorage (audit L6)', () => {
    authStore.set({ global: 'secret-bearer-token', ocr: 'ocr-tok' });

    // Allow the `subscribe` callback to flush.
    return Promise.resolve().then(() => {
      expect(localStorage.getItem(AUTH_STORAGE_KEY)).toBeNull();
      const stored = sessionStorage.getItem(AUTH_STORAGE_KEY);
      expect(stored).not.toBeNull();
      expect(JSON.parse(stored as string)).toEqual({
        global: 'secret-bearer-token',
        ocr: 'ocr-tok',
      });
    });
  });

  it('clears auth tokens from sessionStorage when the store is reset', () => {
    authStore.set({ global: 'tok' });
    return Promise.resolve().then(() => {
      expect(sessionStorage.getItem(AUTH_STORAGE_KEY)).not.toBeNull();
      authStore.set({});
      return Promise.resolve().then(() => {
        // After reset, the store writes {} back; the key is still
        // present but holds an empty object (so a re-read returns {}
        // rather than re-hydrating a stale token).
        const stored = sessionStorage.getItem(AUTH_STORAGE_KEY);
        expect(stored).not.toBeNull();
        expect(JSON.parse(stored as string)).toEqual({});
      });
    });
  });

  it('one-time migration removes pre-fix tokens from localStorage on module load', async () => {
    // Simulate a stale token from a pre-L6 build sitting in `localStorage`.
    // After the L6 fix ships, the next time the module loads it should
    // clear that entry. The module has already loaded in this test file
    // (top-of-file import), so the migration ran during the first import
    // before we could plant the seed — so we simulate it explicitly: set
    // the stale entry, then trigger a fresh module evaluation.
    localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify({ global: 'stale' }));
    expect(localStorage.getItem(AUTH_STORAGE_KEY)).not.toBeNull();

    vi.resetModules();
    // Re-evaluating appStore runs `loadAuth()` again, which clears the
    // stale `localStorage` entry as part of the one-time migration.
    await import('../stores/appStore');

    expect(localStorage.getItem(AUTH_STORAGE_KEY)).toBeNull();
    vi.resetModules();
    // Restore the module graph for the rest of the suite.
    await import('../stores/appStore');
  });

  // -----------------------------------------------------------------
  // appHarness smoke tests (Phase C Task 14 / FE-01)
  //
  // These drive the real ``<App>`` component tree through
  // :file:`./appHarness.ts`. The harness owns the mount lifecycle
  // (Svelte 5 ``mount``/``unmount``); each test installs the same
  // controlled ``fetchApi`` mock so App's async onMount chain
  // settles deterministically and cleanup is idempotent.
  // -----------------------------------------------------------------
  describe('appHarness', () => {
    // Shared controlled ``fetchApi`` mock used by every harness test.
    // Resolves the routes App's onMount chain triggers:
    //   /health         (TabRibbon pingHealth)
    //   /config         (loadAppConfig)
    //   /models + /models/ocr + /models/translation +
    //   /models/transcription          (refreshModels)
    // The handler is ``async`` so the promise resolves on a single
    // microtask — bounded, not never-resolving — and App's chain
    // settles before the test asserts. ``mockRestore`` in each
    // test's ``finally`` returns the client to its real impl, and
    // ``vi.unstubAllGlobals`` (in the isolation test's finally
    // plus ``afterEach``) undoes the ``global.fetch`` swap.
    function setupControlledFetchApi(): MockInstance {
      const health = { status: 'ok' };
      const models: NamespacedModelsResponse = { models: [], ocr: [], translation: [] };
      return vi
        .spyOn(clientModule, 'fetchApi')
        .mockImplementation(async (path: string) => {
          if (path === '/health') return health;
          if (path === '/config') return { ...defaultConfig };
          if (path === '/models' || path.startsWith('/models/')) return models;
          return null;
        });
    }

    it('mounts <App> into a fresh <div>, renders its root header, and exposes the activeTab writable', async () => {
      const fetchApiSpy = setupControlledFetchApi();
      const harness = mountApp();
      try {
        // Contract 1: the harness exposes a live HTMLDivElement
        // appended to ``document.body`` — keeps the prior shape and
        // proves the test owns a real DOM target.
        expect(harness.target).toBeInstanceOf(HTMLDivElement);
        expect(harness.target.parentNode).toBe(document.body);

        // Contract 2: the real ``<App>`` template rendered into the
        // target, not a stub. ``App.svelte`` mounts ``<TabRibbon>``
        // whose outer element is a ``<header>``; waiting for that
        // node proves the async onMount settled and a real App DOM
        // was produced.
        await vi.waitFor(() => {
          expect(harness.target.querySelector('header')).not.toBeNull();
        });

        // Contract 3: the canonical ``activeTab`` writable surface.
        // The harness returns the same store the component
        // subscribes to — no mirror subscription, no leak.
        expect(typeof harness.activeTab.set).toBe('function');
        expect(typeof harness.activeTab.update).toBe('function');
        expect(typeof harness.activeTab.subscribe).toBe('function');
        expect(get(harness.activeTab)).toBe('workstation');
      } finally {
        await cleanupApp(harness);
        fetchApiSpy.mockRestore();
      }
    });

    it('cleanupApp() detaches the target and is idempotent across repeated calls', async () => {
      const fetchApiSpy = setupControlledFetchApi();
      const harness = mountApp();
      try {
        // ``mountApp()`` appended the target to ``document.body``.
        expect(harness.target.parentNode).toBe(document.body);

        await cleanupApp(harness);
        // First cleanup: Svelte's destroy lifecycle removed the
        // rendered App children from the target, and the target
        // itself was detached from its parent.
        expect(harness.target.parentNode).toBeNull();
        expect(harness.target.childNodes.length).toBe(0);

        // Second cleanup: idempotent no-op. The harness must not
        // throw on a re-entrant call.
        await cleanupApp(harness);
        expect(harness.target.parentNode).toBeNull();
        expect(harness.target.childNodes.length).toBe(0);
      } finally {
        // ``mockRestore`` is required here even though cleanup ran
        // — the spy is module-scoped, not harness-scoped.
        fetchApiSpy.mockRestore();
      }
    });

    // FE-01 isolation guarantee: mounting ``<App>`` must trigger
    // the expected ``fetchApi`` chain and must not produce any
    // uncontrolled real backend request. ``App.svelte``'s
    // ``onMount`` calls ``loadAppConfig()`` → ``fetchApi('/config')``
    // plus ``refreshModels()`` → ``fetchApi('/models')``,
    // ``fetchApi('/models/ocr')``,
    // ``fetchApi('/models/translation')`` and
    // ``fetchApi('/models/transcription')``. ``TabRibbon``'s
    // ``pingHealth`` adds ``fetchApi('/health')``. We wait for all
    // six calls via ``vi.waitFor`` (deterministic, no fixed
    // microtask count) and assert ``global.fetch`` was never
    // invoked.
    it('mounts without making any uncontrolled real network request (FE-01 isolation)', async () => {
      const fetchSpy = vi.fn();
      vi.stubGlobal('fetch', fetchSpy);

      const fetchApiSpy = setupControlledFetchApi();
      const harness = mountApp();
      try {
        await vi.waitFor(() => {
          const urls = fetchApiSpy.mock.calls.map((c) => c[0] as string);
          expect(urls).toContain('/health');
          expect(urls).toContain('/config');
          expect(urls).toContain('/models');
          expect(urls).toContain('/models/ocr');
          expect(urls).toContain('/models/translation');
          expect(urls).toContain('/models/transcription');
        });

        // No real ``fetch`` ever fired — the controlled ``fetchApi``
        // mock short-circuited the client boundary.
        expect(fetchSpy).not.toHaveBeenCalled();
      } finally {
        await cleanupApp(harness);
        fetchApiSpy.mockRestore();
        vi.unstubAllGlobals();
      }
    });
  });
});

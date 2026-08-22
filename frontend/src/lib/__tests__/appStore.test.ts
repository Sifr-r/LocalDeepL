import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { get } from 'svelte/store';
import * as clientModule from '../api/client';
import {
  activeTab,
  themeStore,
  authStore,
  toastStore,
  pushToast,
  loadAppConfig
} from '../stores/appStore';
import {
  cleanupApp,
  flushAppMount,
  mountApp,
  type AppHarness
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
  // These exercise the real ``<App>`` component tree via the
  // harness in :file:`./appHarness.ts`. The harness owns the mount
  // lifecycle (Svelte 5 ``mount``/``unmount``); each test owns its
  // own ``fetchApi`` stub and restores it in ``finally`` so the
  // store-level tests above (which call ``loadAppConfig`` directly
  // and rely on the un-stubbed real client) keep passing.
  // -----------------------------------------------------------------
  describe('appHarness', () => {
    // Always stub ``fetchApi`` before mounting ``<App>`` so the
    // component's async ``onMount`` chain (``loadAppConfig`` →
    // ``fetchApi('/config')`` + ``refreshModels`` → four
    // ``fetchApi('/models*')`` calls) does not leave a dangling
    // network round-trip if a test fails before its ``finally``
    // block runs.
    async function withMountedApp(
      fn: (harness: AppHarness) => Promise<void> | void
    ): Promise<void> {
      const fetchApiSpy = vi
        .spyOn(clientModule, 'fetchApi')
        // The component subscribes to a Svelte store that wires
        // fetchApi's resolution through ``configStore.set`` /
        // ``modelStore.update``; a never-resolving promise keeps
        // the in-flight request observable (asserted via
        // ``fetchApiSpy`` calls) without resolving into a real
        // store mutation.
        .mockImplementation(() => new Promise(() => {}));
      const harness = mountApp();
      try {
        await fn(harness);
      } finally {
        await cleanupApp(harness);
        fetchApiSpy.mockRestore();
      }
    }

    it('mountApp() returns an HTMLDivElement target and an activeTab writable defaulting to "workstation"', async () => {
      await withMountedApp((harness) => {
        expect(harness.target).toBeInstanceOf(HTMLDivElement);
        // The harness returns the canonical ``activeTab`` writable
        // from ``appStore`` — no mirror subscription is added, so
        // there is nothing to leak. The store contract is: callable
        // as a writable (set / update / subscribe).
        expect(typeof harness.activeTab.set).toBe('function');
        expect(typeof harness.activeTab.update).toBe('function');
        expect(typeof harness.activeTab.subscribe).toBe('function');
        // ``beforeEach`` pins ``activeTab`` to ``workstation``; the
        // harness returns the same store the component subscribes
        // to, so the value matches the canonical default.
        expect(get(harness.activeTab)).toBe('workstation');
      });
    });

    it('cleanupApp() detaches the target from its parent and tears down the component', async () => {
      const harness = mountApp();
      // Sanity: the harness appended the target to ``document.body``
      // before mounting, so the parent exists before cleanup.
      expect(harness.target.parentNode).toBe(document.body);
      // The component renders its own root <div> as the first child
      // of the target. After cleanup, that child must be gone (the
      // Svelte destroy lifecycle removed it) and the target must be
      // detached from its parent.
      await cleanupApp(harness);
      expect(harness.target.parentNode).toBeNull();
      expect(harness.target.childNodes.length).toBe(0);
    });

    // Phase C Task 14 / FE-01 isolation guarantee: mounting
    // ``<App>`` must not produce an uncontrolled real backend
    // request. ``<App>.svelte``'s ``onMount`` calls
    // ``loadAppConfig()`` → ``fetchApi('/config')`` plus
    // ``refreshModels()`` → four ``fetchApi('/models*')`` calls.
    // The plan's "wait one microtask" assertion is invalid here
    // because the async chain spans at least three microtasks
    // before it settles; we use ``flushAppMount`` to deterministically
    // drain the queue.
    //
    // We assert two complementary things:
    //  1. ``fetchApiSpy`` was invoked — the test owns the request
    //     boundary and the mount triggered the expected config /
    //     model fetches.
    //  2. ``global.fetch`` was never called — no real network
    //     request slipped past the ``fetchApi`` mock.
    it('mounts without making any uncontrolled real network request (FE-01 isolation)', async () => {
      const fetchApiSpy = vi
        .spyOn(clientModule, 'fetchApi')
        .mockImplementation(() => new Promise(() => {}));
      // ``vi.stubGlobal('fetch', spy)`` replaces the global
      // ``fetch`` reference; any code path that bypasses the
      // ``fetchApi`` mock would surface here.
      const fetchSpy = vi.fn();
      vi.stubGlobal('fetch', fetchSpy);

      const harness = mountApp();
      try {
        // Drain the Svelte scheduler + microtask queue. Three
        // ``Promise.resolve()`` iterations are enough to cover the
        // ``onMount`` → ``loadAppConfig`` → ``refreshModels`` chain.
        await flushAppMount();

        // Contract 1: the harness intercepted at least one
        // ``fetchApi`` call. We don't pin the exact URL set here
        // because that would couple this smoke test to the
        // ``loadAppConfig`` URL contract; we only assert the
        // boundary was reached.
        expect(fetchApiSpy).toHaveBeenCalled();
        const calledUrls = fetchApiSpy.mock.calls.map(
          (call) => call[0] as string
        );
        // ``loadAppConfig`` must hit ``/config``; ``refreshModels``
        // must hit the model-list endpoints. If either chain were
        // skipped, the harness would still be considered "mounted"
        // — pinning at least one of the two URL families proves
        // the async onMount actually ran.
        const hasConfigOrModelCall = calledUrls.some(
          (url) => url.includes('/config') || url.includes('/models')
        );
        expect(hasConfigOrModelCall).toBe(true);

        // Contract 2: no uncontrolled real ``fetch`` ever fired.
        // The ``fetchApi`` mock short-circuits at the client
        // boundary, so ``global.fetch`` must remain untouched.
        expect(fetchSpy).not.toHaveBeenCalled();
      } finally {
        await cleanupApp(harness);
        fetchApiSpy.mockRestore();
        vi.unstubAllGlobals();
      }
    });
  });
});

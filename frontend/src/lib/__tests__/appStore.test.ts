import { describe, it, expect, beforeEach, vi } from 'vitest';
import { get } from 'svelte/store';
import { activeTab, themeStore, authStore, toastStore, pushToast, loadAppConfig } from '../stores/appStore';

const AUTH_STORAGE_KEY = 'omniscribe.auth.v1';

describe('appStore', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    toastStore.set([]);
    activeTab.set('workstation');
    themeStore.set('dark');
    authStore.set({});
    vi.restoreAllMocks();
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
});

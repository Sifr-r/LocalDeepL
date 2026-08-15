import { describe, it, expect, beforeEach, vi } from 'vitest';
import { get } from 'svelte/store';
import { activeTab, themeStore, authStore, toastStore, pushToast, loadAppConfig } from '../stores/appStore';

describe('appStore', () => {
  beforeEach(() => {
    localStorage.clear();
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
});

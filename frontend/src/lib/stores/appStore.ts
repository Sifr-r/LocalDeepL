import { writable } from 'svelte/store';
import { loadJson, saveJson } from '../utils/persistence';
import type {
  AuthTokens,
  ConfigResponse,
  NamespacedModelsResponse,
  Toast,
  ToastLevel,
} from '../types/api';
import { fetchApi } from '../api/client';
// documentStore / jobStore / websocketStore used to be defined inline here.
// Extracting them into their own leaf modules (documentStore.ts, jobStore.ts,
// websocketStore.ts) breaks the appStore ↔ leaf-store import cycle (audit
// M5). The public API is preserved via ``export ... from`` re-exports below
// — this avoids creating local bindings that the linter would flag as unused.
export { websocketStore } from './websocketStore';
export { documentStore, defaultDocumentModel } from './documentStore';
export { jobStore, defaultJobState } from './jobStore';

export type ActiveTab =
  | 'workstation'
  | 'translation'
  | 'glossary'
  | 'settings'
  | 'jobs'
  | 'transcription'
  | 'extraction';
export type TabType = ActiveTab;

export type ThemeMode = 'dark' | 'light';

const STORAGE_KEYS = {
  ACTIVE_TAB: 'omniscribe_active_tab',
  THEME: 'omniscribe_theme',
  AUTH: 'omniscribe.auth.v1',
};

/**
 * F3.3 audit fix: tracks whether the API client has recently seen a
 * 401 response (the user is likely missing a bearer token, or the
 * one they configured is wrong). A persistent banner uses this flag
 * to deep-link to the Settings auth tab. Set to ``true`` on the
 * first 401; cleared by user dismiss or by the user editing the
 * auth tokens in the Settings view.
 */
export const authRequired = writable<boolean>(false);

// 1. activeTab Store
const initialTab = loadJson<ActiveTab>(STORAGE_KEYS.ACTIVE_TAB, 'workstation');
export const activeTab = writable<ActiveTab>(initialTab);
activeTab.subscribe((val) => saveJson(STORAGE_KEYS.ACTIVE_TAB, val));

// 2. themeStore
const initialTheme = loadJson<ThemeMode>(STORAGE_KEYS.THEME, 'dark');
export const themeStore = writable<ThemeMode>(initialTheme);
themeStore.subscribe((val) => saveJson(STORAGE_KEYS.THEME, val));

// 3. authStore
// Audit L6 fix: bearer tokens were persisted in `localStorage`, which is
// XSS-reachable across sessions. The token is now hydrated from and
// persisted to `sessionStorage` instead — same tab survives a reload, but
// the token is gone when the tab is closed. A long-lived XSS payload
// that activates on the next session has nothing to grab. Same-tab XSS
// can still read it during the session (same as `localStorage` once
// executed); eliminating that residual risk requires httpOnly cookies
// (Option C in the audit), which needs a server change and is tracked
// separately. `persistence.ts` is intentionally untouched — its helpers
// remain the right choice for non-sensitive UI prefs (`activeTab`,
// `themeStore`).
function loadAuth(): AuthTokens {
  if (typeof window === 'undefined') return {};
  // One-time migration: drop any pre-fix token that may still be sitting
  // in `localStorage` from an earlier build so it doesn't linger on disk.
  try {
    window.localStorage.removeItem(STORAGE_KEYS.AUTH);
  } catch {
    // best-effort; if removal fails (e.g. private-mode quota), the new
    // code path simply doesn't read from `localStorage` anyway.
  }
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEYS.AUTH);
    if (!raw) return {};
    return JSON.parse(raw) as AuthTokens;
  } catch {
    return {};
  }
}

function saveAuth(value: AuthTokens): void {
  if (typeof window === 'undefined') return;
  try {
    window.sessionStorage.setItem(STORAGE_KEYS.AUTH, JSON.stringify(value));
  } catch (err) {
    console.warn(`Failed to save ${STORAGE_KEYS.AUTH} to sessionStorage:`, err);
  }
}

const initialAuth = loadAuth();
export const authStore = writable<AuthTokens>(initialAuth);
authStore.subscribe((val) => saveAuth(val));

// 4. configStore
export const defaultConfig: ConfigResponse = {
  api_base: 'http://127.0.0.1:11434',
  api_key: '',
  model: 'llama3:latest',
  concurrency: 4,
  dpi: 200,
  dense_mode: 'auto',
  dense_threshold: 10,
  max_image_dim: 2048,
  refine: false,
  verify_model: false,
  pipeline_mode: 'hybrid',
  self_correction: false,
  binarize: false,
  dual_engine: false,
  spellcheck: 'none',
  cross_page: false,
  preprocess_pages: false,
  orientation_detection: false,
  deskew: false,
  denoise: false,
  normalize_contrast: false,
  crop_cleanup: false,
  quality_routing: false,
  document_processors: [],
  use_async: false,
  security: { max_upload_bytes: 52428800, max_upload_mb: 50 },
};
export const configStore = writable<ConfigResponse>(defaultConfig);

// 5. jobStore and 6. documentStore were moved to their own modules
// (./jobStore.ts and ./documentStore.ts) to break the appStore ↔
// websocketStore import cycle. They are re-exported above so the
// existing `from '../stores/appStore'` public API is unchanged.

// 7. toastStore
function createToastStore() {
  const { subscribe, set, update } = writable<Toast[]>([]);

  // F3.5 audit fix: track the per-toast TTL timer so removeToast and
  // clearToasts can cancel a pending expiry. The previous code stored
  // no reference to the setTimeout handle, so a manual removeToast
  // or a clearToasts left the timer running — when it fired, the
  // update() was a no-op (the toast was already gone), but the
  // timer still kept a closure alive and prevented the GC from
  // collecting the message string until the TTL elapsed. The leak
  // is small per toast (a few KB) but compounds on a page with
  // long-lived navigation (TabRibbon health polls every 30s, each
  // generating an error toast on 401, the timer table grows
  // without bound).
  const timers: Map<string, ReturnType<typeof setTimeout>> = new Map();

  const pushToast = (level: ToastLevel, message: string, ttlMs: number = 5000): string => {
    const id = Math.random().toString(36).substring(2, 9);
    const newToast: Toast = {
      id,
      level,
      message,
      ttlMs,
      createdAt: Date.now(),
    };

    update((toasts) => [...toasts, newToast]);

    if (ttlMs > 0) {
      const timer = setTimeout(() => {
        timers.delete(id);
        update((toasts) => toasts.filter((t) => t.id !== id));
      }, ttlMs);
      timers.set(id, timer);
    }

    return id;
  };

  const removeToast = (id: string) => {
    // Cancel the pending expiry timer so the update() below is the
    // only mutation that removes this toast.
    const timer = timers.get(id);
    if (timer !== undefined) {
      clearTimeout(timer);
      timers.delete(id);
    }
    update((toasts) => toasts.filter((t) => t.id !== id));
  };

  const clearToasts = () => {
    // Cancel every pending expiry so a 50-toast spam + clearToasts
    // doesn't leave 50 timers running until their TTL elapses.
    for (const timer of timers.values()) {
      clearTimeout(timer);
    }
    timers.clear();
    set([]);
  };

  return {
    subscribe,
    set,
    update,
    pushToast,
    removeToast,
    clearToasts,
  };
}

export const toastStore = createToastStore();

/**
 * Top-level helper function for pushing toasts (used by components)
 */
export function pushToast(level: ToastLevel, message: string, ttlMs: number = 5000): string {
  return toastStore.pushToast(level, message, ttlMs);
}

// 8. modelStore
export interface ModelStoreState {
  general: string[];
  ocr: string[];
  translation: string[];
  transcription: string[];
  lastFetched: Record<string, number>;
}

export const defaultModelStore: ModelStoreState = {
  general: [],
  ocr: [],
  translation: [],
  transcription: [],
  lastFetched: {},
};

export const modelStore = writable<ModelStoreState>(defaultModelStore);

/**
 * Refresh model list for a given namespace or all namespaces
 */
export async function refreshModels(
  namespace?: 'general' | 'ocr' | 'translation' | 'transcription' | 'all'
): Promise<void> {
  if (!namespace || namespace === 'all') {
    await Promise.allSettled([
      refreshModels('general'),
      refreshModels('ocr'),
      refreshModels('translation'),
      refreshModels('transcription'),
    ]);
    return;
  }

  try {
    const ns = namespace === 'general' ? undefined : namespace;
    const url = ns ? `/models/${ns}` : '/models';
    const res = await fetchApi<NamespacedModelsResponse>(url);

    modelStore.update((curr) => {
      const next = { ...curr };
      if (namespace === 'ocr' && res && 'models' in res) {
        next.ocr = res.models;
      } else if (namespace === 'translation' && res && 'models' in res) {
        next.translation = res.models;
      } else if (namespace === 'transcription' && res && 'models' in res) {
        next.transcription = res.models;
      } else if (res && 'models' in res) {
        next.general = res.models;
        if ('ocr' in res && res.ocr) next.ocr = res.ocr;
        if ('translation' in res && res.translation) next.translation = res.translation;
      }
      next.lastFetched[namespace] = Date.now();
      return next;
    });
  } catch (err) {
    console.warn(`Failed to refresh models for namespace ${namespace}:`, err);
  }
}

/**
 * Hydrates runtime configuration and namespaced model lists from backend
 */
export async function loadAppConfig(): Promise<void> {
  try {
    const cfg = await fetchApi<ConfigResponse>('/config');
    configStore.set(cfg);
  } catch (err) {
    console.warn('Failed to load application runtime config:', err);
  }

  await refreshModels();
}

/**
 * Re-fetch the runtime config and replace the contents of `configStore`.
 * Plan §3 — `configStore.refreshConfig()`.
 */
export async function refreshConfig(): Promise<void> {
  const fresh = await fetchApi<ConfigResponse>('/config');
  configStore.set(fresh);
  await refreshModels();
}

/**
 * PATCH the OCR namespace section of the runtime config.
 * Plan §3 — `configStore.updateOcrNamespace()`.
 */
export async function updateOcrNamespace(
  patch: Partial<ConfigResponse>
): Promise<void> {
  const next = await fetchApi<ConfigResponse>('/config/ocr', {
    method: 'POST',
    body: JSON.stringify(patch)
  });
  configStore.update((curr) => ({ ...curr, ...patch }));
  await refreshModels('ocr');
}

/**
 * PATCH the Translation namespace section of the runtime config.
 * Plan §3 — `configStore.updateTranslationNamespace()`.
 */
export async function updateTranslationNamespace(
  patch: Partial<ConfigResponse>
): Promise<void> {
  const next = await fetchApi<ConfigResponse>('/config/translation', {
    method: 'POST',
    body: JSON.stringify(patch)
  });
  configStore.update((curr) => ({ ...curr, ...patch }));
  await refreshModels('translation');
}

/**
 * PATCH the Transcription namespace section of the runtime config.
 * Plan §3 — `configStore.updateTranscriptionNamespace()`.
 */
export async function updateTranscriptionNamespace(
  patch: Partial<ConfigResponse>
): Promise<void> {
  const next = await fetchApi<ConfigResponse>('/config/transcription', {
    method: 'POST',
    body: JSON.stringify(patch)
  });
  configStore.update((curr) => ({ ...curr, ...patch }));
  await refreshModels('transcription');
}

/**
 * Update a per-service auth token. Persists through the existing
 * `authStore` subscription, which writes to `sessionStorage` (audit
 * L6 fix — `localStorage` is XSS-reachable across sessions).
 * Plan §3 — `configStore.setPerServiceAuthToken()`.
 */
export function setPerServiceAuthToken(
  target: 'global' | 'ocr' | 'translation' | 'transcription',
  value: string | undefined
): void {
  authStore.update((curr) => ({ ...curr, [target]: value }));
}

// 9. Modal State Stores
export const exportModalOpen = writable<boolean>(false);
export {
  isProviderModalOpen,
  providerTargetNamespace,
  openProviderModal,
  closeProviderModal,
  isProviderModalOpen as providerModalOpen
} from './providerModalStore';


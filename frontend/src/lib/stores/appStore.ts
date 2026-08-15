import { writable } from 'svelte/store';
import { loadJson, saveJson } from '../utils/persistence';
import type {
  AuthTokens,
  ConfigResponse,
  DocumentViewModel,
  JobState,
  NamespacedModelsResponse,
  Toast,
  ToastLevel,
} from '../types/api';
import { fetchApi } from '../api/client';
import { websocketStore } from './websocketStore';

export { websocketStore };

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

// 1. activeTab Store
const initialTab = loadJson<ActiveTab>(STORAGE_KEYS.ACTIVE_TAB, 'workstation');
export const activeTab = writable<ActiveTab>(initialTab);
activeTab.subscribe((val) => saveJson(STORAGE_KEYS.ACTIVE_TAB, val));

// 2. themeStore
const initialTheme = loadJson<ThemeMode>(STORAGE_KEYS.THEME, 'dark');
export const themeStore = writable<ThemeMode>(initialTheme);
themeStore.subscribe((val) => saveJson(STORAGE_KEYS.THEME, val));

// 3. authStore
const initialAuth = loadJson<AuthTokens>(STORAGE_KEYS.AUTH, {});
export const authStore = writable<AuthTokens>(initialAuth);
authStore.subscribe((val) => saveJson(STORAGE_KEYS.AUTH, val));

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
  security: { max_upload_bytes: 52428800, max_upload_mb: 50 },
};
export const configStore = writable<ConfigResponse>(defaultConfig);

// 5. jobStore
export const defaultJobState: JobState = {
  activeJobId: null,
  percent: 0,
  stage: 'idle',
  statusMessage: '',
  warnings: [],
  chunks: [],
  failedPages: [],
  completedPages: [],
  qualitySummary: null,
  isProcessing: false,
};
export const jobStore = writable<JobState>(defaultJobState);

// 6. documentStore
export const defaultDocumentModel: DocumentViewModel = {
  pages: [],
  textArtifacts: [],
  textArtifactId: null,
  textArtifactToken: null,
  bboxes: [],
  confidenceSummary: { average: 1.0, min: 1.0, max: 1.0 },
  pageCount: 0,
  trustSummary: null,
};
export const documentStore = writable<DocumentViewModel>(defaultDocumentModel);

// 7. toastStore
function createToastStore() {
  const { subscribe, set, update } = writable<Toast[]>([]);

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
      setTimeout(() => {
        update((toasts) => toasts.filter((t) => t.id !== id));
      }, ttlMs);
    }

    return id;
  };

  const removeToast = (id: string) => {
    update((toasts) => toasts.filter((t) => t.id !== id));
  };

  const clearToasts = () => {
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
  namespace?: 'general' | 'ocr' | 'translation' | 'transcription'
): Promise<void> {
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
      next.lastFetched[namespace || 'all'] = Date.now();
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
}

/**
 * PATCH the OCR namespace section of the runtime config.
 * Plan §3 — `configStore.updateOcrNamespace()`.
 */
export async function updateOcrNamespace(
  patch: Partial<ConfigResponse>
): Promise<void> {
  const next = await fetchApi<ConfigResponse>('/config', {
    method: 'POST',
    body: JSON.stringify({ ocr: patch })
  });
  configStore.set(next);
}

/**
 * PATCH the Translation namespace section of the runtime config.
 * Plan §3 — `configStore.updateTranslationNamespace()`.
 */
export async function updateTranslationNamespace(
  patch: Partial<ConfigResponse>
): Promise<void> {
  const next = await fetchApi<ConfigResponse>('/config', {
    method: 'POST',
    body: JSON.stringify({ translation: patch })
  });
  configStore.set(next);
}

/**
 * PATCH the Transcription namespace section of the runtime config.
 * Plan §3 — `configStore.updateTranscriptionNamespace()`.
 */
export async function updateTranscriptionNamespace(
  patch: Partial<ConfigResponse>
): Promise<void> {
  const next = await fetchApi<ConfigResponse>('/config', {
    method: 'POST',
    body: JSON.stringify({ transcription: patch })
  });
  configStore.set(next);
}

/**
 * Update a per-service auth token. Persists through the existing
 * `authStore` subscription, which writes to `localStorage`.
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
export const providerModalOpen = writable<boolean>(false);


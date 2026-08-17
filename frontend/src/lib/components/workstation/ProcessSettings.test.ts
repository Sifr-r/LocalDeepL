import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { mount, unmount } from 'svelte';
import type { ConfigResponse } from '../../types/api';

// Hoist a writable configStore mock so the vi.mock factory can re-export
// the same instance the test drives. `vi.hoisted` runs before module
// evaluation, so we cannot use ESM `import` here; the `require` form is
// locally permitted by the lint rule because there is no synchronous
// ESM alternative.
const { configStoreMock } = vi.hoisted(() => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const storeMod: typeof import('svelte/store') = require('svelte/store');
  const configStoreMock = storeMod.writable<ConfigResponse>({
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
    security: { max_upload_bytes: 52428800, max_upload_mb: 50 }
  });
  return { configStoreMock };
});

vi.mock('../../stores/appStore', () => ({
  configStore: configStoreMock
}));

// Imported after vi.mock so the mock is in place.
import ProcessSettings from './ProcessSettings.svelte';

const ALL_PROCESSOR_KEYS = [
  'reading_order',
  'quality_analysis',
  'structure_analysis',
  'section_analysis',
  'layout_enrichment',
  'table_extraction'
] as const;

describe('ProcessSettings.svelte aria-pressed on document-processor pills (P2 #14)', () => {
  let target: HTMLDivElement;
  // The Svelte 5 `mount` return type is intentionally loose; we only
  // need it to hand back to `unmount()` in afterEach.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let app: any = null;

  beforeEach(() => {
    document.body.innerHTML = '';
    target = document.createElement('div');
    document.body.appendChild(target);
  });

  afterEach(() => {
    if (app) {
      try {
        unmount(app);
      } catch {
        /* already torn down */
      }
      app = null;
    }
    document.body.innerHTML = '';
  });

  it('each pill has aria-pressed="true" when every processor is in the active list', () => {
    configStoreMock.update((c) => ({ ...c, document_processors: [...ALL_PROCESSOR_KEYS] }));

    app = mount(ProcessSettings, { target });

    const pills = target.querySelectorAll<HTMLButtonElement>('#doc-processors-list button');
    expect(pills.length).toBe(ALL_PROCESSOR_KEYS.length);
    pills.forEach((pill) => {
      expect(pill.getAttribute('aria-pressed')).toBe('true');
    });
  });

  it('each pill has aria-pressed="false" when the active list is empty', () => {
    configStoreMock.update((c) => ({ ...c, document_processors: [] }));

    app = mount(ProcessSettings, { target });

    const pills = target.querySelectorAll<HTMLButtonElement>('#doc-processors-list button');
    expect(pills.length).toBe(ALL_PROCESSOR_KEYS.length);
    pills.forEach((pill) => {
      expect(pill.getAttribute('aria-pressed')).toBe('false');
    });
  });
});

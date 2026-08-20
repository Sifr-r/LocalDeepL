import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { mount, tick, unmount, type SvelteComponent } from 'svelte';

// Mock the API helpers so the test controls the catalog + per-provider
// model responses. The component imports from `../../api/endpoints`, so
// the mock path must match the relative resolution.
//
// vi.mock is hoisted, so we capture shared mutable state on
// `globalThis` to keep the mock factory side-effect-free.
const state = {
  providers: [] as Array<Record<string, unknown>>,
  modelsResponses: new Map<string, { models: string[]; error?: string | null }>(),
  modelsCalls: [] as string[],
  modelsDelays: new Map<string, number>()
};

vi.mock('../../api/endpoints', () => {
  return {
    getProviders: vi.fn(async () => state.providers),
    getProviderModels: vi.fn(async (id: string) => {
      state.modelsCalls.push(id);
      const delay = state.modelsDelays.get(id) ?? 0;
      if (delay > 0) {
        await new Promise((r) => setTimeout(r, delay));
      }
      return state.modelsResponses.get(id) ?? { models: [], error: 'no response stubbed' };
    })
  };
});

// Stub the modal store so we can drive the `isProviderModalOpen` flag
// from the test. Keep the same module shape so the component's
// `openProviderModal` / `closeProviderModal` calls still work.
vi.mock('../../stores/providerModalStore', () => {
  const { writable } = require('svelte/store') as typeof import('svelte/store');
  return {
    isProviderModalOpen: writable(false),
    providerTargetNamespace: writable<'ocr' | 'translation' | 'transcription' | 'general'>('ocr'),
    openProviderModal: vi.fn(),
    closeProviderModal: vi.fn()
  };
});

// Stub the app store: only `configStore` and `toastStore` are touched
// by the modal. We don't need the rest of the heavy app store (which
// pulls in pdfjs-dist, etc.) for this test.
vi.mock('../../stores/appStore', () => {
  const { writable } = require('svelte/store') as typeof import('svelte/store');
  // The real `configStore` is typed as a full `ConfigResponse` schema,
  // but the modal only writes to a small subset of fields. Loosen the
  // type to a permissive `Record<string, unknown>` so the test can
  // reset it to a partial baseline without re-declaring 24 fields.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const configStore: any = writable({ ocr_api_base: '', ocr_model: '' });
  return {
    configStore,
    toastStore: {
      pushToast: vi.fn()
    }
  };
});

import ProviderModal from './ProviderModal.svelte';
import {
  isProviderModalOpen,
  providerTargetNamespace
} from '../../stores/providerModalStore';
import { configStore, toastStore } from '../../stores/appStore';
import { getProviderModels } from '../../api/endpoints';

function makeProvider(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: 'mock-ollama',
    name: 'Mock Ollama',
    category: 'local',
    description: 'Local Ollama OpenAI-compatible server.',
    recommended_base_url: 'http://localhost:11434/v1',
    api_base: 'http://localhost:11434/v1',
    default_model: 'llama3.2-vision',
    requires_key: false,
    notes: '',
    ...overrides
  };
}

describe('ProviderModal — auto-loaded model lists', () => {
  // Svelte 5's `mount` return type is intentionally loose; we only need
  // to hand it back to `unmount` in afterEach.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let app: any = null;
  let target: HTMLDivElement;

  beforeEach(() => {
    state.providers = [];
    state.modelsResponses = new Map();
    state.modelsCalls = [];
    state.modelsDelays = new Map();
    vi.mocked(getProviderModels).mockClear();
    isProviderModalOpen.set(false);
    providerTargetNamespace.set('ocr');
    // Reset config store to a known empty baseline. The real store is
    // typed as `ConfigResponse` (24 fields) but the mock only carries
    // the two the modal touches; cast to keep this fixture small.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (configStore as any).set({ ocr_api_base: '', ocr_model: '' });
    // Reset toast spy.
    vi.mocked(toastStore.pushToast).mockClear();

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

  /** Mount the modal and wait for Svelte's tick queue to drain. */
  function mountModal(): SvelteComponent {
    app = mount(ProviderModal, { target });
    return app as SvelteComponent;
  }

  /** Open the modal and wait for the catalog fetch + initial render. */
  async function openModal() {
    isProviderModalOpen.set(true);
    await tick();
    // The reactive trigger on `$isProviderModalOpen` schedules a
    // catalog load; one more tick lets the async loader kick off.
    await tick();
    await tick();
  }

  it('fans out /models calls for every provider when the modal opens', async () => {
    state.providers = [
      makeProvider({ id: 'a' }),
      makeProvider({ id: 'b' }),
      makeProvider({ id: 'c' })
    ];
    state.modelsResponses.set('a', { models: ['m1', 'm2'] });
    state.modelsResponses.set('b', { models: ['x'] });
    state.modelsResponses.set('c', { models: [] });

    mountModal();
    await openModal();
    // Let the fan-out complete.
    await tick();
    await tick();

    expect(vi.mocked(getProviderModels).mock.calls.map((c) => c[0]).sort()).toEqual([
      'a',
      'b',
      'c'
    ]);
  });

  it('renders the live model count after a successful fetch', async () => {
    state.providers = [makeProvider({ id: 'a', name: 'Provider A' })];
    state.modelsResponses.set('a', { models: ['m1', 'm2', 'm3'] });

    mountModal();
    await openModal();
    await tick();
    await tick();
    await tick();

    const card = target.querySelector('[data-testid="provider-card"][data-provider-id="a"]');
    expect(card).not.toBeNull();
    const toggle = card!.querySelector('[data-testid="provider-models-toggle"]');
    expect(toggle?.textContent).toContain('3');
    expect(toggle?.textContent).toContain('model');
  });

  it('surfaces server-side errors without blocking the modal', async () => {
    state.providers = [makeProvider({ id: 'a' })];
    state.modelsResponses.set('a', { models: [], error: 'Provider unreachable (502)' });

    mountModal();
    await openModal();
    await tick();
    await tick();
    await tick();

    const card = target.querySelector('[data-testid="provider-card"][data-provider-id="a"]');
    const err = card!.querySelector('[data-testid="provider-models-error"]');
    expect(err?.textContent).toContain('Provider unreachable');
  });

  it('skips the network round-trip for placeholder-URL providers', async () => {
    state.providers = [
      makeProvider({
        id: 'vertex',
        api_base: 'https://<resource>.services.ai.azure.com/openai/v1'
      })
    ];

    mountModal();
    await openModal();
    await tick();
    await tick();

    // The component should not have called the /models endpoint for
    // a placeholder URL — that would just burn the 5s timeout.
    expect(state.modelsCalls).not.toContain('vertex');
    const card = target.querySelector('[data-testid="provider-card"][data-provider-id="vertex"]');
    const err = card!.querySelector('[data-testid="provider-models-error"]');
    expect(err?.textContent).toContain('Configure the URL');
  });

  it('refresh button re-fetches a single provider (force=true)', async () => {
    state.providers = [makeProvider({ id: 'a' })];
    state.modelsResponses.set('a', { models: ['m1'] });

    mountModal();
    await openModal();
    await tick();
    await tick();
    await tick();

    expect(state.modelsCalls.filter((id) => id === 'a').length).toBe(1);

    // Re-arm the stub so the second call returns fresh data.
    state.modelsResponses.set('a', { models: ['m1', 'm2', 'm3'] });

    const refresh = target.querySelector<HTMLButtonElement>(
      '[data-testid="provider-card"][data-provider-id="a"] [data-testid="provider-refresh"]'
    );
    expect(refresh).not.toBeNull();
    refresh!.click();
    await tick();
    await tick();
    await tick();

    expect(state.modelsCalls.filter((id) => id === 'a').length).toBe(2);
    const toggle = target.querySelector(
      '[data-testid="provider-card"][data-provider-id="a"] [data-testid="provider-models-toggle"]'
    );
    expect(toggle?.textContent).toContain('3');
  });

  it('expanding a provider card reveals the full model list with per-row "Use" buttons', async () => {
    state.providers = [makeProvider({ id: 'a' })];
    state.modelsResponses.set('a', { models: ['m1', 'm2'] });

    mountModal();
    await openModal();
    await tick();
    await tick();
    await tick();

    // List should be hidden by default.
    expect(
      target.querySelector('[data-testid="provider-models-list"]')
    ).toBeNull();

    const toggle = target.querySelector<HTMLButtonElement>(
      '[data-testid="provider-card"][data-provider-id="a"] [data-testid="provider-models-toggle"]'
    );
    toggle!.click();
    await tick();

    const items = target.querySelectorAll(
      '[data-testid="provider-card"][data-provider-id="a"] [data-testid="provider-models-list"] li'
    );
    expect(items.length).toBe(2);
    expect(items[0].textContent).toContain('m1');
    expect(items[1].textContent).toContain('m2');
  });

  it('clicking a per-model "Use" button applies that model to the current namespace', async () => {
    state.providers = [makeProvider({ id: 'a' })];
    state.modelsResponses.set('a', { models: ['m-special', 'm-other'] });

    mountModal();
    await openModal();
    await tick();
    await tick();
    await tick();

    const toggle = target.querySelector<HTMLButtonElement>(
      '[data-testid="provider-card"][data-provider-id="a"] [data-testid="provider-models-toggle"]'
    );
    toggle!.click();
    await tick();

    const useButtons = target.querySelectorAll<HTMLButtonElement>(
      '[data-testid="provider-card"][data-provider-id="a"] [data-testid="provider-models-list"] li button'
    );
    expect(useButtons.length).toBe(2);
    useButtons[0].click();
    await tick();

    // Config should now reflect the picked model. Read the store via
    // get() — svelte's writable stores fire the subscribe callback
    // synchronously on subscribe, so a `const unsub = subscribe(...)`
    // pattern hits a TDZ when the callback runs.
    const cfg = await import('svelte/store').then((m) => m.get(configStore));
    expect(cfg.ocr_model).toBe('m-special');
    expect(vi.mocked(toastStore.pushToast).mock.calls[0]?.[0]).toBe('success');
  });

  it('clears the per-provider state on close so a fresh open re-fetches', async () => {
    state.providers = [makeProvider({ id: 'a' })];
    state.modelsResponses.set('a', { models: ['m1'] });

    mountModal();
    await openModal();
    await tick();
    await tick();
    await tick();
    expect(state.modelsCalls).toEqual(['a']);

    isProviderModalOpen.set(false);
    await tick();
    await tick();
    await tick();

    // Re-open should kick off the catalog + fan-out again.
    isProviderModalOpen.set(true);
    await tick();
    await tick();
    await tick();
    await tick();

    expect(state.modelsCalls.filter((id) => id === 'a').length).toBe(2);
  });
});

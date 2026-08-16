import { describe, it, expect } from 'vitest';
import { get } from 'svelte/store';

/**
 * Audit M5 — guard the appStore ↔ websocketStore import cycle.
 *
 * The original graph:
 *   appStore.ts → websocketStore.ts → appStore.ts  (cycle)
 * caused `undefined` references depending on bundler module-eval order.
 * The fix split `documentStore` and `jobStore` into their own leaf
 * modules, so:
 *   appStore.ts        → websocketStore.ts, documentStore.ts, jobStore.ts
 *   websocketStore.ts  → documentStore.ts, jobStore.ts
 *   documentStore.ts   → (leaf)
 *   jobStore.ts        → (leaf)
 *
 * This test dynamically imports all four modules in several randomized
 * orderings and asserts every named export resolves to a defined value.
 * If anyone reintroduces a cycle the dynamic imports will surface a
 * TDZ / `undefined` binding on the first round.
 */

type StoreSpec = {
  readonly path: string;
  readonly names: readonly string[];
};

const STORES: readonly StoreSpec[] = [
  {
    path: '../stores/appStore',
    names: [
      'activeTab',
      'themeStore',
      'authStore',
      'configStore',
      'jobStore',
      'documentStore',
      'toastStore',
      'modelStore',
      'websocketStore',
      'defaultJobState',
      'defaultDocumentModel',
      'pushToast',
      'loadAppConfig',
      'refreshModels',
    ],
  },
  { path: '../stores/websocketStore', names: ['websocketStore'] },
  { path: '../stores/documentStore', names: ['documentStore', 'defaultDocumentModel'] },
  { path: '../stores/jobStore', names: ['jobStore', 'defaultJobState'] },
];

function shuffle<T>(arr: readonly T[]): T[] {
  const out = arr.slice();
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

describe('store import graph (audit M5 — no cycles)', () => {
  it.each([0, 1, 2, 3, 4, 5, 6, 7])('imports all 4 stores in randomized order (seed %i)', async () => {
    // Shuffle the load order so the test doesn't depend on which module
    // happens to be evaluated first.
    const ordered = shuffle(STORES);

    const loaded = new Map<string, Record<string, unknown>>();
    for (const store of ordered) {
      // Dynamic import — exercises the real ESM module graph, including
      // re-export bindings.
      const mod = (await import(store.path)) as Record<string, unknown>;
      loaded.set(store.path, mod);
    }

    for (const store of STORES) {
      const mod = loaded.get(store.path);
      expect(mod, `module ${store.path} should have loaded`).toBeDefined();
      // The `expect.toBeDefined()` above is a runtime guard; narrow for TS.
      const safeMod: Record<string, unknown> = mod as Record<string, unknown>;

      for (const name of store.names) {
        const value = safeMod[name];
        // The original cycle surfaced as `undefined` here when the
        // importing module was evaluated before the importer finished.
        // After the fix, every binding is a live, defined value.
        expect(value, `${store.path} → ${name} must not be undefined`).toBeDefined();
      }
    }
  });

  it('documentStore and jobStore expose writable stores with the expected defaults', async () => {
    const docMod = (await import('../stores/documentStore')) as Record<string, unknown>;
    const jobMod = (await import('../stores/jobStore')) as Record<string, unknown>;

    expect(get(docMod.documentStore as never)).toMatchObject({ pages: [], bboxes: [], pageCount: 0 });
    expect(get(jobMod.jobStore as never)).toMatchObject({ percent: 0, stage: 'idle', isProcessing: false });
  });

  it('appStore still re-exports documentStore and jobStore so existing consumers keep working', async () => {
    const app = (await import('../stores/appStore')) as Record<string, unknown>;
    // These names must still resolve from `appStore` so the 20+ existing
    // `import { documentStore } from '../stores/appStore'` call sites
    // keep compiling without edits.
    expect(app.documentStore).toBeDefined();
    expect(app.jobStore).toBeDefined();
    expect(app.defaultDocumentModel).toBeDefined();
    expect(app.defaultJobState).toBeDefined();
  });
});

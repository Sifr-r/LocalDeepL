/**
 * Mount the real ``<App>`` component into an isolated test container.
 *
 * Callers (the test suite) own the ``fetchApi`` / ``fetch`` stub so
 * the same harness can drive happy-path and failure-injection tests.
 *
 * ``cleanupApp`` is idempotent: a second call is a no-op. Genuine
 * unmount / onDestroy errors propagate.
 */
import { mount, unmount } from 'svelte';
import App from '../../App.svelte';
import { activeTab } from '../stores/appStore';
import type { ActiveTab } from '../stores/appStore';

interface HarnessState {
  readonly target: HTMLDivElement;
  readonly component: Record<string, unknown>;
  cleaned: boolean;
}

export interface AppHarness {
  /** The detached <div> the component is mounted into. */
  readonly target: HTMLDivElement;
  /** Canonical ``activeTab`` writable from ``appStore``. */
  readonly activeTab: typeof activeTab;
}

const states = new WeakMap<AppHarness, HarnessState>();

export function mountApp(): AppHarness {
  const target = document.createElement('div');
  document.body.appendChild(target);
  const component = mount(App, { target }) as Record<string, unknown>;
  const harness: AppHarness = { target, activeTab };
  states.set(harness, { target, component, cleaned: false });
  return harness;
}

/**
 * Tear down the harness: unmount the component (awaiting Svelte's
 * ``onDestroy`` lifecycle, including ``AbortController.abort`` and
 * interval clearing), then detach the target from its parent.
 * Idempotent — a second call is a no-op. ``cleaned`` is set before
 * the unmount await so a second concurrent cleanup converges on
 * the no-op path.
 */
export async function cleanupApp(harness: AppHarness): Promise<void> {
  const state = states.get(harness);
  if (!state || state.cleaned) return;
  state.cleaned = true;
  try {
    await unmount(state.component);
  } finally {
    if (state.target.parentNode) {
      state.target.parentNode.removeChild(state.target);
    }
  }
}

export type { ActiveTab };

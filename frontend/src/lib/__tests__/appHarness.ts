/**
 * Test harness for mounting <App> in isolation.
 *
 * Phase C Task 14 / FE-01: lets component-level smoke tests exercise the
 * real root ``<App>`` Svelte component without booting the full Vite app
 * shell (``main.ts``). The harness is intentionally minimal — it owns
 * the mount lifecycle but does not mock any network boundary. Callers
 * (the test suite) own the ``fetchApi`` / ``fetch`` stub so the same
 * harness can be reused for both happy-path and failure-injection tests.
 *
 * Svelte 5 API:
 *   - ``mount`` from ``svelte`` returns the component's exported
 *     bindings. ``unmount`` runs the destroy lifecycle and returns a
 *     Promise<void>. The plan's Svelte 4 ``new App({ target })`` example
 *     does not compile against ``svelte@^5`` — this file uses the
 *     current API instead.
 *
 * Subscription discipline:
 *   - The harness returns the canonical ``activeTab`` writable store
 *     directly rather than a mirror. Mirroring would require a
 *     ``subscribe`` call without an explicit unsubscribe, which leaks a
 *     listener across tests. Returning the canonical store means the
 *     test drives the same store the component subscribes to, with no
 *     extra subscriptions to clean up.
 *   - ``cleanupApp`` calls ``unmount`` (which fires the Svelte
 *     ``onDestroy`` lifecycle and aborts in-flight AbortControllers)
 *     and then detaches the target from ``document.body``. Both are
 *     safe to call once per mount; calling ``cleanupApp`` twice is a
 *     no-op on the second call (the target has no parent).
 */
import { mount, tick, unmount } from 'svelte';
import App from '../../App.svelte';
import { activeTab } from '../stores/appStore';
import type { ActiveTab } from '../stores/appStore';

export interface AppHarness {
  /** The detached <div> the component mounted into. */
  readonly target: HTMLDivElement;
  /**
   * Canonical ``activeTab`` writable from ``appStore``. Tests can
   * ``set``/``update`` it to drive tab switches; the component
   * subscribes to the same store, so the reactive tree re-renders.
   * No additional subscription is added by the harness — there is
   * nothing to leak.
   */
  readonly activeTab: typeof activeTab;
  /**
   * Opaque exports object returned by Svelte's ``mount``. Held only
   * so ``cleanupApp`` can pass it back to ``unmount``. Typed as
   * ``Record<string, unknown>`` to match the ``unmount`` signature
   * in Svelte 5; ``App.svelte`` declares no exports, so this is
   * effectively an empty record.
   */
  readonly component: Record<string, unknown>;
}

/**
 * Mount ``<App>`` into a fresh detached ``<div>`` appended to
 * ``document.body``. Returns the harness handle.
 *
 * The target is appended (rather than left floating) so Svelte's DOM
 * measurements (``clientWidth``, etc.) inside any descendant component
 * resolve to a real layout box. ``cleanupApp`` will detach it again
 * before the next test runs, so cross-test contamination is bounded.
 */
export function mountApp(): AppHarness {
  const target = document.createElement('div');
  document.body.appendChild(target);

  // Svelte 5 ``mount`` returns the component's exported bindings.
  // ``App.svelte`` declares no ``export``/``$bindable`` props, so the
  // resulting object is essentially empty — we hold it only to pass
  // back to ``unmount`` later.
  const component = mount(App, { target });

  return { target, activeTab, component };
}

/**
 * Tear down the harness. Awaits the Svelte ``unmount`` promise so the
 * destruction lifecycle (``onDestroy``, ``AbortController.abort``,
 * ``setInterval`` clear) completes before the test asserts.
 *
 * Safe to call once per ``mountApp``; calling it twice is a no-op on
 * the second call because ``target.parentNode`` is already null.
 */
export async function cleanupApp(harness: AppHarness): Promise<void> {
  try {
    await unmount(harness.component);
  } catch {
    // Swallow: if the component was already unmounted (e.g. an
    // earlier ``cleanupApp`` call in the same test), the lookup in
    // Svelte's internal mount-table returns no-op. We still want to
    // detach the target so a follow-up mountApp starts clean.
  }
  if (harness.target.parentNode) {
    harness.target.parentNode.removeChild(harness.target);
  }
}

/**
 * Flush the Svelte 5 microtask queue plus a few extra
 * ``Promise.resolve()`` ticks. App.svelte's ``onMount`` is
 * ``async`` and chains ``loadAppConfig()`` → ``fetchApi('/config')``
 * plus ``refreshModels()`` → four ``fetchApi('/models*')`` calls. The
 * awaited work spans at least three microtasks before it settles
 * (one for the ``onMount`` async wrapper, one for the inner
 * ``fetchApi`` await, one for ``refreshModels``'s
 * ``Promise.allSettled``). Tests that need to observe post-mount
 * state (or assert that ``fetchApi`` was called) should ``await``
 * this before checking.
 *
 * The plan's "wait one microtask" assertion is invalid against the
 * current App.svelte because the first awaited fetch doesn't resolve
 * inside a single tick. This helper gives tests a deterministic
 * multi-tick flush without leaking timer handles.
 */
export async function flushAppMount(): Promise<void> {
  // First flush the Svelte scheduler (``tick``) so any synchronous
  // ``$effect`` / reactive updates scheduled by the initial render
  // run before we drain the JS microtask queue.
  await tick();
  // Drain microtasks. Three iterations cover: ``onMount`` wrapper →
  // ``loadAppConfig`` await → ``refreshModels`` parallel awaits.
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}

// Re-export ``ActiveTab`` so consumers can type their tab-key
// literals without re-importing from the deep ``appStore`` path.
export type { ActiveTab };

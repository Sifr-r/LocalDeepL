import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { mount, tick, unmount } from 'svelte';
import { get } from 'svelte/store';
import TabRibbon from './TabRibbon.svelte';
import { activeTab, type ActiveTab } from '../../stores/appStore';
import { fetchApi as fetchApiSpy } from '../../api/client';

// ``vi.mock`` is hoisted above the imports by Vitest. The default
// ``fetchApi`` mock returns a never-resolving promise so the a11y
// tests do NOT issue a real ``/health`` network request when
// TabRibbon mounts and ``pingHealth`` fires in ``onMount``. The
// abort test overrides this default per-test via
// ``vi.mocked(fetchApiSpy).mockImplementation`` to reject with
// ``DOMException('aborted', 'AbortError')`` when the captured
// signal aborts, which drives ``pingHealth``'s ``AbortError`` catch.
vi.mock('../../api/client', async (importOriginal) => {
  const actual = (await importOriginal()) as typeof import('../../api/client');
  return {
    ...actual,
    fetchApi: vi.fn(() => new Promise(() => {})),
    fetchApiWithHeaders: vi.fn(actual.fetchApiWithHeaders),
    fetchFile: vi.fn(actual.fetchFile)
  };
});

/**
 * P1 #6: WAI-ARIA tab roles on TabRibbon.
 *
 * The tab ribbon was a plain `<nav>` with `<button>` children. Screen
 * readers could not announce it as a tabbed navigation; keyboard users
 * had no roving `tabindex` to indicate the active tab.
 *
 * The fix adds:
 *  - `role="tablist"` + `aria-label` on the container `<nav>`
 *  - `role="tab"` on each tab button
 *  - `aria-selected="true" | "false"` on each tab button
 *  - Roving `tabindex` (active=0, others=-1)
 */
describe('TabRibbon.svelte WAI-ARIA tab roles (P1 #6)', () => {
  let target: HTMLDivElement;
  let app: ReturnType<typeof mount> | null = null;
  // `appStore` persists `activeTab` to `localStorage`; capture the
  // pre-test value so we can restore it in afterEach and avoid leaking
  // store state between test files.
  let originalActiveTab: ActiveTab;

  beforeEach(() => {
    document.body.innerHTML = '';
    target = document.createElement('div');
    document.body.appendChild(target);
    originalActiveTab = get(activeTab);
    // Reset the shared ``fetchApi`` spy between tests: clear call
    // history and re-apply the never-resolving default so the abort
    // test's mock does not leak into subsequent a11y tests.
    vi.clearAllMocks();
    vi.mocked(fetchApiSpy).mockImplementation(
      () => new Promise(() => {})
    );
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
    activeTab.set(originalActiveTab);
    document.body.innerHTML = '';
  });

  it('container <nav> has role="tablist" and a non-empty aria-label', async () => {
    app = mount(TabRibbon, { target });
    await tick();

    const tablist = target.querySelector('[role="tablist"]');
    expect(tablist).not.toBeNull();
    const ariaLabel = tablist?.getAttribute('aria-label');
    expect(ariaLabel).toBeTruthy();
    expect(ariaLabel?.length ?? 0).toBeGreaterThan(0);
  });

  it('each tab button has role="tab" (7 tabs: workstation, translation, glossary, settings, jobs, transcription, extraction)', async () => {
    app = mount(TabRibbon, { target });
    await tick();

    const tabs = target.querySelectorAll('[role="tab"]');
    expect(tabs.length).toBe(7);
  });

  it('the active tab has aria-selected="true" and all other tabs have aria-selected="false"', async () => {
    activeTab.set('extraction');
    app = mount(TabRibbon, { target });
    await tick();

    const tabs = Array.from(target.querySelectorAll<HTMLElement>('[role="tab"]'));
    const selectedTrue = tabs.filter(
      (t) => t.getAttribute('aria-selected') === 'true'
    );
    const selectedFalse = tabs.filter(
      (t) => t.getAttribute('aria-selected') === 'false'
    );
    expect(selectedTrue.length).toBe(1);
    expect(selectedFalse.length).toBe(tabs.length - 1);

    const active = selectedTrue[0];
    expect(active?.id).toBe('app-tab-btn-extraction');
  });

  it('the active tab has tabindex="0" and all other tabs have tabindex="-1" (roving tabindex)', async () => {
    activeTab.set('extraction');
    app = mount(TabRibbon, { target });
    await tick();

    const tabs = Array.from(target.querySelectorAll<HTMLElement>('[role="tab"]'));
    const roving0 = tabs.filter((t) => t.getAttribute('tabindex') === '0');
    const rovingN1 = tabs.filter((t) => t.getAttribute('tabindex') === '-1');
    expect(roving0.length).toBe(1);
    expect(rovingN1.length).toBe(tabs.length - 1);

    const active = roving0[0];
    expect(active?.id).toBe('app-tab-btn-extraction');
  });

  it('clicking a different tab updates aria-selected and roving tabindex accordingly', async () => {
    activeTab.set('workstation');
    app = mount(TabRibbon, { target });
    await tick();

    const translationTab = target.querySelector<HTMLButtonElement>(
      '#app-tab-btn-translation'
    );
    expect(translationTab).not.toBeNull();
    expect(translationTab?.getAttribute('aria-selected')).toBe('false');
    expect(translationTab?.getAttribute('tabindex')).toBe('-1');

    translationTab?.click();
    await tick();

    expect(translationTab?.getAttribute('aria-selected')).toBe('true');
    expect(translationTab?.getAttribute('tabindex')).toBe('0');

    const workstationTab = target.querySelector<HTMLButtonElement>(
      '#app-tab-btn-workstation'
    );
    expect(workstationTab?.getAttribute('aria-selected')).toBe('false');
    expect(workstationTab?.getAttribute('tabindex')).toBe('-1');
  });

  // FE-07 / Phase C Task 13: ``pingHealth`` must (1) thread
  // ``fetchApi`` with ``silent: true`` so a 5xx probe never surfaces
  // as a toast, (2) wire a real ``AbortSignal`` through ``RequestInit``
  // so the request is cancellable, and (3) swallow ``AbortError`` so
  // an unmount mid-ping does not flip the connection badge to
  // ``Offline``. This test pins all three contracts deterministically:
  // a controlled ``fetchApi`` mock that rejects with
  // ``DOMException('aborted', 'AbortError')`` when the abort listener
  // fires (vitest's jsdom environment mixes jsdom's ``Event`` with
  // Node's ``AbortController``, so ``signal.dispatchEvent(new Event(
  // 'abort'))`` would throw — invoking the captured listener directly
  // exercises the same code path without the cross-realm mismatch).
  it('cancels in-flight health ping on component destroy and swallows AbortError', async () => {
    const fetchApiMock = vi.mocked(fetchApiSpy);
    // Replace the default never-resolving mock with one that
    // rejects with a DOMException named 'AbortError' when its abort
    // listener fires. ``fetchApi`` re-throws
    // DOMException-with-name-AbortError untouched, so
    // ``pingHealth``'s catch runs and swallows it without mutating
    // ``backendOnline``. The captured listener is the same one the
    // production ``fetch`` would fire on abort.
    const abortCapture: { current: (() => void) | null } = { current: null };
    fetchApiMock.mockImplementation(
      (_url: string, init?: RequestInit) => {
        return new Promise<Response>((_resolve, reject) => {
          abortCapture.current = () => {
            reject(new DOMException('aborted', 'AbortError'));
          };
          init?.signal?.addEventListener('abort', abortCapture.current);
        });
      }
    );

    // ``localApp`` is declared outside the try block so the finally
    // clause can still unmount it if a pre-unmount assertion fails
    // — the outer describe block's ``app`` is owned by the a11y
    // tests and must not be polluted by this test on failure.
    let localApp: ReturnType<typeof mount> | null = null;
    try {
      localApp = mount(TabRibbon, { target });
      await tick();

      // Contract 1: ``silent: true`` is forwarded to ``fetchApi``.
      // ``silent`` is consumed inside ``fetchApi`` (and stripped
      // before the underlying fetch), so the assertion lives at the
      // ``fetchApi`` boundary.
      expect(fetchApiMock).toHaveBeenCalledWith(
        '/health',
        expect.objectContaining({ silent: true })
      );
      // Contract 2: the captured signal is a real ``AbortSignal`` —
      // the ``pingAbort`` controller is wired through the options
      // bag.
      const lastCall = fetchApiMock.mock.calls.at(-1);
      const opts = (lastCall?.[1] ?? {}) as { signal?: AbortSignal };
      const signal = opts.signal ?? null;
      expect(signal).toBeInstanceOf(AbortSignal);
      expect(signal?.aborted).toBe(false);

      // While the ping is still in flight, the connection badge
      // shows 'Checking…' (``backendOnline === null``).
      expect(target.textContent).toContain('Checking');

      // Contract 3: fire the captured abort listener (the same code
      // path the production ``fetch`` would drive on abort) while
      // the component is still mounted. The mocked ``fetchApi``
      // rejects with ``DOMException('aborted', 'AbortError')``;
      // ``pingHealth``'s catch swallows it and returns without
      // mutating ``backendOnline``. The badge stays 'Checking…'
      // (a non-AbortError rejection would flip it to 'Offline') —
      // this is the deterministic observable that the
      // ``AbortError`` catch branch ran.
      abortCapture.current?.();
      await tick();
      expect(target.textContent).toContain('Checking');
      expect(target.textContent).not.toContain('Offline');

      // Contract 4: unmount fires ``onDestroy``, which calls
      // ``pingAbort.abort()`` — the production cancellation path.
      // The signal is genuinely aborted (``signal.aborted === true``).
      unmount(localApp);
      localApp = null;
      expect(signal?.aborted).toBe(true);
    } finally {
      if (localApp) {
        try {
          unmount(localApp);
        } catch {
          /* already torn down */
        }
        localApp = null;
      }
    }
  });
});

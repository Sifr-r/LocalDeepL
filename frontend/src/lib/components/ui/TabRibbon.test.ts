import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { mount, tick, unmount } from 'svelte';
import { get } from 'svelte/store';
import TabRibbon from './TabRibbon.svelte';
import { activeTab, type ActiveTab } from '../../stores/appStore';
import { fetchApi as fetchApiSpy } from '../../api/client';

// ``vi.mock`` is hoisted above the imports by Vitest. The abort test
// below asserts the ``silent: true`` contract at the ``fetchApi`` layer,
// because ``silent`` is consumed by ``fetchApi`` for toast suppression
// and is stripped before the underlying global ``fetch`` is called — so
// spying on the global fetch alone (the existing pattern) would miss
// the flag. The wrapper still delegates to the actual implementation,
// so the a11y tests further down — which never assert on fetch behavior
// — are unaffected.
vi.mock('../../api/client', async (importOriginal) => {
  const actual = (await importOriginal()) as typeof import('../../api/client');
  return {
    ...actual,
    fetchApi: vi.fn(actual.fetchApi),
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
  // The Svelte 5 `mount` return type is intentionally loose; we only
  // need it to hand back to `unmount()` in afterEach.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let app: any = null;
  // `appStore` persists `activeTab` to `localStorage`; capture the
  // pre-test value so we can restore it in afterEach and avoid leaking
  // store state between test files.
  let originalActiveTab: ActiveTab;

  beforeEach(() => {
    document.body.innerHTML = '';
    target = document.createElement('div');
    document.body.appendChild(target);
    originalActiveTab = get(activeTab);
    // The vi.mock-wrapped fetchApi above is a shared spy; clear its
    // call history between tests so the abort test's
    // ``fetchApiSpy.mock.calls`` assertions only see calls from this
    // test rather than accumulating from earlier a11y tests.
    vi.clearAllMocks();
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

  // FE-07 / Phase C Task 13: pingHealth must wire fetchApi with an
  // AbortController whose signal aborts on unmount. Without this, an
  // unmount mid-ping leaves the request running until the server replies,
  // and the 15-second setInterval can race a previous ping that is still
  // in flight. This test pins that contract.
  it('cancels in-flight health ping on component destroy', async () => {
    // Type the captured signal as ``AbortSignal | null`` so we can
    // thread it back through fetchApi's ``RequestInit['signal']``
    // widening. The ``!`` definite-assignment assertion satisfies
    // ``noUnusedLocals`` without seeding a literal ``null`` value —
    // TypeScript 5.9 narrows ``let x: T | null = null`` to the literal
    // ``null`` type and then treats ``x?.aborted`` as a property access
    // on ``never`` (an optional chain on a known-null value). The
    // variable is always reassigned by the mock implementation before
    // any read, so the uninitialized declaration is safe and matches
    // the pre-existing test's intent.
    let abortSignal!: AbortSignal | null;
    // Capture the signal's abort listener (black-box): fetchApi threads
    // the signal from pingHealth into the underlying global fetch, so
    // attaching ``addEventListener('abort', ...)`` here proves the
    // AbortController is actually wired all the way through to the
    // request. Asserting the listener fires after unmount is the
    // deterministic proxy for pingHealth's ``AbortError`` catch branch
    // (which relies on the abort event to swallow a late response as
    // a no-op). A never-resolving Promise keeps the ping in flight for
    // the duration of the test so we can assert on the abort end-state
    // without race-prone timers.
    let abortListenerFired = false;
    const fetchSpy = vi
      .fn()
      .mockImplementation((_url: string, init?: RequestInit) => {
        const signal = (init?.signal ?? null) as AbortSignal | null;
        abortSignal = signal;
        if (signal) {
          signal.addEventListener('abort', () => {
            abortListenerFired = true;
          });
        }
        return new Promise<Response>(() => {
          /* never resolves; we abort from the test */
        });
      });
    vi.stubGlobal('fetch', fetchSpy);

    // Declare ``localApp`` outside the try block so the finally clause
    // can still unmount it if an assertion before unmount fails — the
    // outer describe block's ``app`` variable is owned by the a11y
    // tests and must not be polluted by this abort test on failure.
    let localApp: ReturnType<typeof mount> | null = null;
    try {
      localApp = mount(TabRibbon, { target });
      await tick();
      // pingHealth ran in onMount and captured the signal in fetchSpy.
      expect(fetchSpy).toHaveBeenCalledTimes(1);
      // The captured request signal must be a real AbortSignal instance
      // — not merely defined — so the AbortController is wired through.
      // We use ``abortSignal instanceof AbortSignal`` (with the LHS
      // cast to ``unknown`` because the DOM lib widens ``AbortSignal |
      // null`` and TypeScript requires a non-nullable LHS for
      // ``instanceof``) rather than
      // ``expect(abortSignal).toBeInstanceOf(AbortSignal)`` to avoid
      // the Vitest matcher narrowing ``abortSignal`` to ``never`` for
      // the optional-chain accesses further down.
      expect((abortSignal as unknown) instanceof AbortSignal).toBe(true);
      expect(abortSignal?.aborted).toBe(false);
      // Health probes must not surface as user-facing toasts on 5xx;
      // ``silent`` is consumed by ``fetchApi`` (and stripped before the
      // underlying ``fetch``), so the assertion lives at the fetchApi
      // boundary — the spy was installed via the ``vi.mock`` wrapper at
      // the top of this file.
      expect(fetchApiSpy).toHaveBeenCalledWith(
        '/health',
        expect.objectContaining({ silent: true })
      );

      // Unmount — the AbortController in pingHealth must fire so the
      // in-flight request is cancelled and a later ping cannot race it.
      unmount(localApp);
      localApp = null;
      expect(abortSignal?.aborted).toBe(true);
      // The signal's abort listener captured on the fetch side must
      // have fired, which is the deterministic proxy for the signal
      // being wired end-to-end through fetchApi (the precondition
      // pingHealth's catch branch relies on to swallow the resulting
      // AbortError as a no-op).
      expect(abortListenerFired).toBe(true);
    } finally {
      if (localApp) {
        try {
          unmount(localApp);
        } catch {
          /* already torn down */
        }
        localApp = null;
      }
      vi.unstubAllGlobals();
    }
  });
});

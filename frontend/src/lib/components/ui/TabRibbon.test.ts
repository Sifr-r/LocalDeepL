import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { mount, tick, unmount } from 'svelte';
import { get } from 'svelte/store';
import TabRibbon from './TabRibbon.svelte';
import { activeTab, type ActiveTab } from '../../stores/appStore';

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
});

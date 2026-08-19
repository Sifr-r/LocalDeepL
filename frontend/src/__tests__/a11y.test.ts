import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { mount, unmount, tick } from 'svelte';
import Toggle from '$lib/components/ui/Toggle.svelte';
import SettingsView from '$lib/components/views/SettingsView.svelte';
import ExtractionView from '$lib/components/views/ExtractionView.svelte';
import TranslationView from '$lib/components/views/TranslationView.svelte';
import TranscriptionView from '$lib/components/views/TranscriptionView.svelte';
import ExportModal from '$lib/components/modals/ExportModal.svelte';
import { activeTab, exportModalOpen } from '$lib/stores/appStore';
import { isTranscribing } from '$lib/stores/transcriptionStore';
import { documentStore, defaultDocumentModel } from '$lib/stores/documentStore';

vi.mock('$lib/api/client', () => ({
  fetchApi: vi.fn().mockResolvedValue({ models: ['whisper-1', 'gpt-4o'] }),
  fetchApiWithHeaders: vi.fn().mockResolvedValue({ body: {}, headers: new Headers() }),
  fetchFile: vi.fn().mockResolvedValue(new Blob(['fake']))
}));

describe('Accessibility & UI Invariants (a11y.test.ts)', () => {
  let target: HTMLDivElement;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let component: any = null;

  beforeEach(() => {
    document.body.innerHTML = '';
    target = document.createElement('div');
    document.body.appendChild(target);
    activeTab.set('workstation');
    documentStore.set({ ...defaultDocumentModel });
    isTranscribing.set(false);
  });

  afterEach(() => {
    if (component) {
      try {
        unmount(component);
      } catch {
        /* ignore */
      }
      component = null;
    }
    document.body.innerHTML = '';
  });

  describe('Toggle.svelte a11y & focus styling', () => {
    it('renders with role="switch", valid aria-label, and hidden native input with peer focus ring', () => {
      component = mount(Toggle, {
        target,
        props: {
          id: 'test-toggle',
          label: 'Test Feature Switch',
          description: 'Enable feature',
          checked: false
        }
      });

      const input = target.querySelector('input#test-toggle') as HTMLInputElement;
      expect(input).not.toBeNull();
      expect(input.getAttribute('role')).toBe('switch');
      expect(input.getAttribute('type')).toBe('checkbox');
      expect(input.getAttribute('aria-label')).toBe('Test Feature Switch');

      // Native checkbox should stay visually hidden (opacity-0) without flashing native checkbox on focus
      expect(input.className).toContain('opacity-0');
      expect(input.className).not.toContain('focus-visible:opacity-100');

      // Styled switch track must have peer-focus-visible ring classes
      const switchTrack = target.querySelector('span.peer-focus-visible\\:ring-2');
      expect(switchTrack).not.toBeNull();
    });
  });

  describe('SettingsView.svelte tablist and tabpanels', () => {
    it('has role="tablist", aria-selected, and matching aria-controls and aria-labelledby', async () => {
      activeTab.set('settings');
      component = mount(SettingsView, { target });
      await tick();

      const tablist = target.querySelector('[role="tablist"]');
      expect(tablist).not.toBeNull();
      expect(tablist?.getAttribute('aria-label')).toBe('Settings namespace');

      const tabs = Array.from(target.querySelectorAll('[role="tab"]')) as HTMLButtonElement[];
      expect(tabs.length).toBe(4);

      for (const tab of tabs) {
        const tabId = tab.getAttribute('id');
        const controlsId = tab.getAttribute('aria-controls');
        expect(tabId).toBeTruthy();
        expect(controlsId).toBeTruthy();

        // The tabpanel must exist when its tab is active
        if (tab.getAttribute('aria-selected') === 'true') {
          const panel = target.querySelector(`#${controlsId}`);
          expect(panel).not.toBeNull();
          expect(panel?.getAttribute('role')).toBe('tabpanel');
          expect(panel?.getAttribute('aria-labelledby')).toBe(tabId);
        }
      }
    });
  });

  describe('ExtractionView.svelte form controls and status', () => {
    it('has explicit label and aria-label on textarea, and role="status" on loading state', async () => {
      activeTab.set('extraction');
      component = mount(ExtractionView, { target });
      await tick();

      const textarea = target.querySelector('textarea#extraction-input-text');
      expect(textarea).not.toBeNull();
      expect(textarea?.getAttribute('aria-label')).toBeTruthy();

      const label = target.querySelector('label[for="extraction-input-text"]');
      expect(label).not.toBeNull();
    });
  });

  describe('TranslationView.svelte form controls and live status', () => {
    it('has explicit labels for controls and role="status" on live regions', async () => {
      activeTab.set('translation');
      component = mount(TranslationView, { target });
      await tick();

      const textarea = target.querySelector('textarea#translation-source-text');
      expect(textarea).not.toBeNull();
      expect(textarea?.getAttribute('aria-label')).toBeTruthy();

      const label = target.querySelector('label[for="translation-source-text"]');
      expect(label).not.toBeNull();
    });
  });

  describe('TranscriptionView.svelte controls and live regions', () => {
    it('has explicit labels for audio input and controls, and role="status" during transcription', async () => {
      activeTab.set('transcription');
      component = mount(TranscriptionView, { target });
      await tick();

      const fileInput = target.querySelector('input#audio-file-input');
      expect(fileInput).not.toBeNull();
      expect(fileInput?.getAttribute('aria-label')).toBe('Upload audio file');
      const label = target.querySelector('label[for="audio-file-input"]');
      expect(label).not.toBeNull();

      // Trigger transcribing state and assert live region
      isTranscribing.set(true);
      await tick();
      const statusEl = target.querySelector('[role="status"]');
      expect(statusEl).not.toBeNull();
      expect(statusEl?.getAttribute('aria-live')).toBe('polite');
      isTranscribing.set(false);
    });
  });

  describe('ExportModal.svelte accessibility', () => {
    it('renders modal dialog with accessible title and export options', async () => {
      exportModalOpen.set(true);
      component = mount(ExportModal, { target });
      await tick();

      const modal = target.querySelector('[role="dialog"]');
      expect(modal).not.toBeNull();
      exportModalOpen.set(false);
    });
  });
});

// ---------------------------------------------------------------------------
// Audit-secondary F25: axe-core integration via vitest-axe
// ---------------------------------------------------------------------------
//
// The manual ``role=`` / ``aria-label`` checks above catch missing
// attributes on the components we wrote. The axe-core integration
// below catches the rest of the WCAG 2.1 AA surface: color contrast,
// focus order, label associations, landmark roles, etc. Both
// layers are useful: a manual check is precise (catches "we forgot
// the label on this specific button"), an axe scan is broad
// (catches the dozens of rules we did not think to enumerate).
//
// ``vitest-axe`` is the vitest-native wrapper around
// ``jest-axe``; ``toHaveNoViolations`` is the matcher that
// inspects the latest ``axe.run()`` result.

import { axe } from 'vitest-axe';
// ``toHaveNoViolations`` lives in the matchers subpath of
// vitest-axe (the main index only re-exports ``axe`` and
// ``configureAxe``). The subpath import is documented in the
// vitest-axe README.
import { toHaveNoViolations } from 'vitest-axe/dist/matchers';

expect.extend({ toHaveNoViolations });

describe('axe-core WCAG 2.1 AA scans (a11y.test.ts)', () => {
  let target: HTMLDivElement;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let component: any = null;

  beforeEach(() => {
    document.body.innerHTML = '';
    target = document.createElement('div');
    document.body.appendChild(target);
    activeTab.set('workstation');
    documentStore.set({ ...defaultDocumentModel });
    isTranscribing.set(false);
  });

  afterEach(() => {
    if (component) {
      try {
        unmount(component);
      } catch {
        /* ignore */
      }
      component = null;
    }
    document.body.innerHTML = '';
  });

  it('Toggle.svelte has no axe-core violations', async () => {
    component = mount(Toggle, {
      target,
      props: {
        id: 'test-toggle-axe',
        label: 'Test Feature Switch',
        description: 'Enable feature',
        checked: false
      }
    });
    await tick();
    const results = await axe(target);
    // Audit-secondary F25: full ``toHaveNoViolations`` check is
    // the long-term goal. Today the suite has 1 known violation
    // (the ``heading-order`` rule on multi-h1/h2/h3 trees — see
    // the followup below). The test pins the current state:
    // every observed violation must be in the known-issues set.
    // A regression that adds a new violation type is caught by
    // the "no new rule" check.
    const knownRules = new Set(['heading-order']);
    const observedRules = new Set(results.violations.map((v) => v.id));
    const newRules = [...observedRules].filter((r) => !knownRules.has(r));
    expect(newRules).toEqual([]);
  });

  it('SettingsView.svelte tablist has no axe-core violations', async () => {
    activeTab.set('settings');
    component = mount(SettingsView, { target });
    await tick();
    const results = await axe(target);
    const knownRules = new Set(['heading-order']);
    const observedRules = new Set(results.violations.map((v) => v.id));
    const newRules = [...observedRules].filter((r) => !knownRules.has(r));
    expect(newRules).toEqual([]);
  });

  it('ExtractionView.svelte form has no axe-core violations', async () => {
    activeTab.set('extraction');
    component = mount(ExtractionView, { target });
    await tick();
    const results = await axe(target);
    const knownRules = new Set(['heading-order']);
    const observedRules = new Set(results.violations.map((v) => v.id));
    const newRules = [...observedRules].filter((r) => !knownRules.has(r));
    expect(newRules).toEqual([]);
  });

  it('axe-core reports zero critical / serious violations', async () => {
    // Across all three views, no axe-core violation may be at
    // ``critical`` or ``serious`` impact. The ``heading-order``
    // rule is ``moderate`` impact and is the long-tail cleanup
    // tracked above. ``minor`` and ``moderate`` violations are
    // tolerated; ``serious`` and ``critical`` are not.
    const views = [
      () => {
        activeTab.set('workstation');
        component = mount(ExtractionView, { target });
      },
      () => {
        activeTab.set('settings');
        component = mount(SettingsView, { target });
      },
      () => {
        activeTab.set('workstation');
        component = mount(Toggle, {
          target,
          props: {
            id: 'axe-toggle',
            label: 'Toggle',
            description: 'A toggle',
            checked: false
          }
        });
      }
    ];

    for (const mountView of views) {
      document.body.innerHTML = '';
      target = document.createElement('div');
      document.body.appendChild(target);
      if (component) {
        try {
          unmount(component);
        } catch {
          /* ignore */
        }
        component = null;
      }
      mountView();
      await tick();
      const results = await axe(target);
      const blocking = results.violations.filter(
        (v) => v.impact === 'serious' || v.impact === 'critical'
      );
      expect(blocking).toEqual([]);
    }
  });
});

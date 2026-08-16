import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { mount, tick, unmount } from 'svelte';
import Modal from './Modal.svelte';

/**
 * Keyboard focus-trap behaviour for `Modal`.
 *
 * The trap is enforced by a capture-phase `<svelte:window>` keydown
 * listener so the dialog's own `on:keydown|stopPropagation` cannot hide
 * Tab/Shift+Tab from us. Events are therefore dispatched on the
 * currently focused element with `bubbles: true` to walk the capture
 * path from `window` down to the target.
 */
describe('Modal focus trap', () => {
  let target: HTMLDivElement;
  let trigger: HTMLButtonElement;
  // The Svelte 5 `mount` return type is intentionally loose; we only
  // need it to hand back to `unmount()` in afterEach.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let app: any = null;

  function pressKey(key: string, init: Partial<KeyboardEventInit> = {}) {
    const el = document.activeElement ?? document.body;
    const event = new KeyboardEvent('keydown', {
      key,
      bubbles: true,
      cancelable: true,
      ...init
    });
    el.dispatchEvent(event);
    return event;
  }

  function getDialog(): HTMLDivElement {
    const d = target.querySelector('[role="dialog"]') as HTMLDivElement | null;
    if (!d) throw new Error('Dialog not found in modal target');
    return d;
  }

  function getBody(): HTMLDivElement {
    const dialog = getDialog();
    const body = dialog.querySelector('.flex-1.overflow-y-auto') as HTMLDivElement | null;
    if (!body) throw new Error('Modal body not found');
    return body;
  }

  function appendInputs(count: number): HTMLInputElement[] {
    const body = getBody();
    const inputs: HTMLInputElement[] = [];
    for (let i = 0; i < count; i++) {
      const input = document.createElement('input');
      input.type = 'text';
      input.dataset.testid = `input-${i}`;
      body.appendChild(input);
      inputs.push(input);
    }
    return inputs;
  }

  function focusablesInDialog(): HTMLElement[] {
    return Array.from(
      getDialog().querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]),' +
          ' select:not([disabled]), textarea:not([disabled]),' +
          ' [tabindex]:not([tabindex="-1"])'
      )
    );
  }

  /** Two ticks: the first flushes the Svelte update queue; the second
   *  lets the `tick().then(focusFirst)` chain inside the modal's open
   *  transition run. */
  async function flushFocusManagement() {
    await tick();
    await tick();
  }

  beforeEach(() => {
    document.body.innerHTML = '';
    trigger = document.createElement('button');
    trigger.id = 'modal-trigger';
    trigger.textContent = 'Open';
    document.body.appendChild(trigger);
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

  it('moves focus to the first focusable element when the modal opens', async () => {
    trigger.focus();
    expect(document.activeElement).toBe(trigger);

    app = mount(Modal, { target, props: { open: true, title: 'Test' } });
    appendInputs(3);
    await flushFocusManagement();

    const focusables = focusablesInDialog();
    expect(focusables.length).toBeGreaterThan(0);
    expect(document.activeElement).toBe(focusables[0]);
  });

  it('cycles Tab from the last focusable back to the first', async () => {
    trigger.focus();
    app = mount(Modal, { target, props: { open: true, title: 'Test' } });
    appendInputs(2);
    await flushFocusManagement();

    const focusables = focusablesInDialog();
    const last = focusables[focusables.length - 1];
    last.focus();
    expect(document.activeElement).toBe(last);

    pressKey('Tab');
    expect(document.activeElement).toBe(focusables[0]);
  });

  it('cycles Shift+Tab from the first focusable back to the last', async () => {
    trigger.focus();
    app = mount(Modal, { target, props: { open: true, title: 'Test' } });
    appendInputs(2);
    await flushFocusManagement();

    const focusables = focusablesInDialog();
    const first = focusables[0];
    first.focus();
    expect(document.activeElement).toBe(first);

    pressKey('Tab', { shiftKey: true });
    expect(document.activeElement).toBe(focusables[focusables.length - 1]);
  });

  it('does not interfere with default Tab navigation when focus is in the middle', async () => {
    trigger.focus();
    app = mount(Modal, { target, props: { open: true, title: 'Test' } });
    appendInputs(3);
    await flushFocusManagement();

    const focusables = focusablesInDialog();
    focusables[1].focus();
    expect(document.activeElement).toBe(focusables[1]);

    // The handler should let the browser's native Tab navigation take
    // over when focus is somewhere in the middle of the list.
    const ev = pressKey('Tab');
    expect(ev.defaultPrevented).toBe(false);
  });

  it('does not interfere with default Shift+Tab navigation when focus is in the middle', async () => {
    trigger.focus();
    app = mount(Modal, { target, props: { open: true, title: 'Test' } });
    appendInputs(3);
    await flushFocusManagement();

    const focusables = focusablesInDialog();
    focusables[2].focus();
    expect(document.activeElement).toBe(focusables[2]);

    const ev = pressKey('Tab', { shiftKey: true });
    expect(ev.defaultPrevented).toBe(false);
  });

  it('pulls focus back into the modal when focus has somehow escaped', async () => {
    trigger.focus();
    app = mount(Modal, { target, props: { open: true, title: 'Test' } });
    appendInputs(2);
    await flushFocusManagement();

    // Simulate a stray focus outside the dialog (e.g. devtools, or a
    // browser quirk). The next Tab should snap back to the first
    // focusable in the modal, not escape further.
    trigger.focus();
    expect(document.activeElement).toBe(trigger);

    const focusables = focusablesInDialog();
    pressKey('Tab');
    expect(document.activeElement).toBe(focusables[0]);
  });

  it('closes the modal on Escape and dispatches the close event', async () => {
    let closeDispatched = false;
    const closeHandler = (_e: Event) => {
      closeDispatched = true;
    };
    app = mount(Modal, {
      target,
      props: { open: true, title: 'Test' },
      events: { close: closeHandler }
    });
    await tick();

    expect(target.querySelector('[role="dialog"]')).not.toBeNull();
    pressKey('Escape');
    await tick();
    expect(target.querySelector('[role="dialog"]')).toBeNull();
    expect(closeDispatched).toBe(true);
  });

  it('restores focus to the trigger element when the modal closes', async () => {
    trigger.focus();
    expect(document.activeElement).toBe(trigger);

    app = mount(Modal, { target, props: { open: true, title: 'Test' } });
    await flushFocusManagement();
    // Focus should have moved into the modal.
    expect(document.activeElement).not.toBe(trigger);

    pressKey('Escape');
    await flushFocusManagement();
    expect(document.activeElement).toBe(trigger);
  });

  it('keeps focus pinned to the dialog root when there are no focusable descendants', async () => {
    trigger.focus();
    app = mount(Modal, { target, props: { open: true, title: 'Test' } });
    await flushFocusManagement();

    const dialog = getDialog();
    // Strip every focusable so the trap sees an empty focusable list.
    dialog
      .querySelectorAll<HTMLElement>(
        'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])'
      )
      .forEach((el) => el.remove());
    dialog.focus();
    expect(document.activeElement).toBe(dialog);

    const ev = pressKey('Tab');
    // The trap must have suppressed the default focus shift.
    expect(ev.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(dialog);
  });
});

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { mount, unmount } from 'svelte';
import Select from './Select.svelte';

/**
 * P1 #5: ARIA error/hint association on the Select primitive.
 *
 * The component renders an error or hint `<p>` below the select but
 * did not link it to the select via `aria-describedby`, nor did it set
 * `aria-invalid` on the select. Screen readers could not announce the
 * error or hint on focus. The `ariaLabel` prop (added in 2bec3bf)
 * covered the labeling side; this commit closes the association side.
 *
 * Three states are tested:
 *   1. error only     → aria-describedby = `${id}-error`, aria-invalid="true"
 *   2. hint only      → aria-describedby = `${id}-hint`,  aria-invalid absent
 *   3. neither        → both attributes absent
 */
describe('Select.svelte ARIA associations (P1 #5)', () => {
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

  it('sets aria-describedby to the error <p> id and aria-invalid="true" when error is present', () => {
    app = mount(Select, {
      target,
      props: {
        id: 'lang',
        error: 'required',
        options: [{ value: 'en', label: 'English' }]
      }
    });

    const select = target.querySelector('select#lang') as HTMLSelectElement;
    expect(select).not.toBeNull();
    const errorP = target.querySelector('#lang-error') as HTMLParagraphElement;
    expect(errorP).not.toBeNull();
    expect(errorP.textContent?.trim()).toBe('required');

    expect(select.getAttribute('aria-describedby')).toBe('lang-error');
    expect(select.getAttribute('aria-invalid')).toBe('true');
  });

  it('sets aria-describedby to the hint <p> id and omits aria-invalid when only hint is present', () => {
    app = mount(Select, {
      target,
      props: {
        id: 'lang',
        hint: 'pick the target language',
        options: [{ value: 'en', label: 'English' }]
      }
    });

    const select = target.querySelector('select#lang') as HTMLSelectElement;
    expect(select).not.toBeNull();
    const hintP = target.querySelector('#lang-hint') as HTMLParagraphElement;
    expect(hintP).not.toBeNull();
    expect(hintP.textContent?.trim()).toBe('pick the target language');

    expect(select.getAttribute('aria-describedby')).toBe('lang-hint');
    expect(select.getAttribute('aria-invalid')).toBeNull();
  });

  it('omits both aria-describedby and aria-invalid when neither error nor hint is set', () => {
    app = mount(Select, {
      target,
      props: { id: 'lang', options: [{ value: 'en', label: 'English' }] }
    });

    const select = target.querySelector('select#lang') as HTMLSelectElement;
    expect(select).not.toBeNull();

    expect(select.getAttribute('aria-describedby')).toBeNull();
    expect(select.getAttribute('aria-invalid')).toBeNull();
  });
});

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { mount, unmount } from 'svelte';
import Input from './Input.svelte';

/**
 * P1 #5: ARIA error/hint association on the Input primitive.
 *
 * The component renders an error or hint `<p>` below the input but
 * did not link it to the input via `aria-describedby`, nor did it set
 * `aria-invalid` on the input. Screen readers could not announce the
 * error or hint on focus. The `ariaLabel` prop (added in 2bec3bf)
 * covered the labeling side; this commit closes the association side.
 *
 * Three states are tested:
 *   1. error only     → aria-describedby = `${id}-error`, aria-invalid="true"
 *   2. hint only      → aria-describedby = `${id}-hint`,  aria-invalid absent
 *   3. neither        → both attributes absent
 */
describe('Input.svelte ARIA associations (P1 #5)', () => {
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
    app = mount(Input, {
      target,
      props: { id: 'username', error: 'required', hint: undefined }
    });

    const input = target.querySelector('input#username') as HTMLInputElement;
    expect(input).not.toBeNull();
    const errorP = target.querySelector('#username-error') as HTMLParagraphElement;
    expect(errorP).not.toBeNull();
    expect(errorP.textContent?.trim()).toBe('required');

    expect(input.getAttribute('aria-describedby')).toBe('username-error');
    expect(input.getAttribute('aria-invalid')).toBe('true');
  });

  it('sets aria-describedby to the hint <p> id and omits aria-invalid when only hint is present', () => {
    app = mount(Input, {
      target,
      props: { id: 'username', error: undefined, hint: 'between 3 and 20 chars' }
    });

    const input = target.querySelector('input#username') as HTMLInputElement;
    expect(input).not.toBeNull();
    const hintP = target.querySelector('#username-hint') as HTMLParagraphElement;
    expect(hintP).not.toBeNull();
    expect(hintP.textContent?.trim()).toBe('between 3 and 20 chars');

    expect(input.getAttribute('aria-describedby')).toBe('username-hint');
    expect(input.getAttribute('aria-invalid')).toBeNull();
  });

  it('omits both aria-describedby and aria-invalid when neither error nor hint is set', () => {
    app = mount(Input, { target, props: { id: 'username' } });

    const input = target.querySelector('input#username') as HTMLInputElement;
    expect(input).not.toBeNull();

    expect(input.getAttribute('aria-describedby')).toBeNull();
    expect(input.getAttribute('aria-invalid')).toBeNull();
  });
});

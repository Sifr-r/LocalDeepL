<script lang="ts">
  /**
   * Input — design system primitive.
   *
   * One component for text, password, email, number, search, url.
   * Wraps a native <input> so we keep browser autofill, a11y, and
   * form behavior for free.
   *
   * Pass a `label` to render the form-label above the input.
   * Pass `hint` for helper text (shown below, muted).
   * Pass `error` to switch the input to the error state and show
   * the error message instead of the hint.
   */
  // The DOM ``AutoFill`` enum isn't surfaced by every tsconfig / eslint
  // globals combo, so we type the autocomplete values locally as a
  // permissive string. The native input element accepts any
  // WHATWG-autocomplete token; the browser falls back to ``on`` for
  // unknown values, so the loose type matches the runtime contract
  // without enumerating the spec's full template-literal union.
  type AutoFillValue = string;
  export let id: string = `input-${Math.random().toString(36).slice(2, 9)}`;
  export let type: 'text' | 'password' | 'email' | 'number' | 'search' | 'url' | 'tel' = 'text';
  export let value: string | number = '';
  export let placeholder = '';
  export let label = '';
  export let hint = '';
  export let error: string = '';
  export let disabled = false;
  export let readonly = false;
  export let fullWidth = true;
  export let autocomplete: string = '';
  export let name = '';
  export let maxlength: number | null = null;
  export let min: number | string | null = null;
  export let max: number | string | null = null;
  export let step: number | string | null = null;
</script>

<div class={fullWidth ? 'w-full' : ''}>
  {#if label}
    <label for={id} class="form-label">{label}</label>
  {/if}
  <input
    {id}
    {type}
    {name}
    {placeholder}
    {disabled}
    {readonly}
    {maxlength}
    {min}
    {max}
    step={step}
    autocomplete={(autocomplete ? (autocomplete as AutoFillValue) : undefined) as never}
    aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined}
    aria-invalid={error ? 'true' : undefined}
    bind:value
    on:input
    on:change
    on:blur
    on:focus
    on:keydown
    on:keyup
    class={[
      'w-full h-9 px-3 rounded-md text-sm font-body',
      'bg-card text-foreground placeholder:text-foreground-subtle',
      'border transition-colors',
      'focus:outline-none focus:ring-2 focus:ring-brand/20',
      error
        ? 'border-danger focus:border-danger focus:ring-danger/20'
        : 'border-input focus:border-brand',
      disabled && 'opacity-50 cursor-not-allowed'
    ].filter(Boolean).join(' ')}
  />
  {#if error}
    <p id={`${id}-error`} class="mt-1 text-xs text-danger">{error}</p>
  {:else if hint}
    <p id={`${id}-hint`} class="mt-1 text-xs text-foreground-muted">{hint}</p>
  {/if}
</div>

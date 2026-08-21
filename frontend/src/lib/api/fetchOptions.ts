/**
 * FetchOptions — common shape for every endpoints.ts wrapper.
 *
 * `signal` lets callers cancel an in-flight request when the component
 * unmounts (use {@link createAbortController} for the typical lifecycle).
 *
 * `silent` suppresses the toast side-effect that ``fetchApi`` triggers on
 * non-2xx responses (see ``./client``). Phase C / FE-07 (Task 12)
 * exposes it through this higher-level interface so view code can opt
 * out for noisy loops (e.g. the 2-second async-job polling in
 * ``TranslationView.pollAsyncStatus``); the endpoint wrapper forwards
 * the flag to the underlying ``fetchApi`` call.
 *
 * Distinct from the lower-level ``FetchOptions`` exported by ``./client``
 * (which extends ``RequestInit`` and re-declares the same ``silent``
 * flag for toast suppression). This higher-level interface is the one
 * callers pass through view code; we merge ``signal`` and ``silent``
 * into the request-init object forwarded to ``fetchApi`` /
 * ``fetchApiWithHeaders`` / ``fetchFile``.
 */
export interface FetchOptions {
  signal?: AbortSignal;
  silent?: boolean;
}

/**
 * createAbortController — convenience for Svelte `onMount` / `onDestroy`
 * lifecycles.
 *
 * Usage:
 * ```ts
 * onMount(async () => {
 *   const ctrl = createAbortController();
 *   const data = await configApi.get({}, { signal: ctrl.signal });
 *   return () => ctrl.abort();
 * });
 * ```
 */
export function createAbortController(): AbortController {
  return new AbortController();
}

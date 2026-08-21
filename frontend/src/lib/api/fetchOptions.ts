/**
 * FetchOptions — common shape for every endpoints.ts wrapper.
 *
 * `signal` lets callers cancel an in-flight request when the component
 * unmounts (use {@link createAbortController} for the typical lifecycle).
 *
 * Distinct from the lower-level ``FetchOptions`` exported by ``./client``
 * (which extends ``RequestInit`` and adds a ``silent`` flag for toast
 * suppression). This higher-level interface is the one callers pass
 * through view code; we merge ``signal`` into the request-init object
 * forwarded to ``fetchApi`` / ``fetchApiWithHeaders`` / ``fetchFile``.
 */
export interface FetchOptions {
  signal?: AbortSignal;
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

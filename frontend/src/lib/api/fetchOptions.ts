/**
 * FetchOptions — common shape for every endpoints.ts wrapper and the few
 * view-level ``fetchApi`` call sites that opt into the abort / toast-silent
 * plumbing (e.g. ``TabRibbon.svelte``'s 15-second ``/health`` probe, see
 * FE-07 / Phase C Task 13).
 *
 * - ``signal`` lets callers cancel an in-flight request when the component
 *   unmounts (use {@link createAbortController} for the typical lifecycle).
 * - ``silent`` suppresses the toast side-effect that ``fetchApi`` triggers on
 *   non-2xx responses (see ``./client``). Phase C / FE-07 (Task 12) exposes
 *   it through this higher-level interface so view code can opt out for noisy
 *   loops (e.g. the 2-second async-job polling in
 *   ``TranslationView.pollAsyncStatus`` and the 15-second health probe in
 *   ``TabRibbon.pingHealth``); the endpoint wrapper forwards the flag to the
 *   underlying ``fetchApi`` call. For direct ``fetchApi`` call sites in view
 *   code, ``silent: true`` is passed straight through to the client-level
 *   options bag.
 * - ``cache`` is forwarded to ``RequestInit`` so polling endpoints can opt
 *   out of the browser HTTP cache (``'no-store'`` for the health probe is
 *   the canonical example — without it, a flapping backend could stay cached
 *   as "online" for the duration of the cache TTL even though the probe
 *   failed a moment earlier). Mirrors the ``RequestInit['cache']`` union
 *   from the DOM lib so call sites stay typed end-to-end.
 *
 * Distinct from the lower-level ``FetchOptions`` exported by ``./client``
 * (which extends ``RequestInit`` and re-declares the same ``silent`` flag for
 * toast suppression). This higher-level interface is the one callers pass
 * through view code; we merge ``signal``, ``silent`` and ``cache`` into the
 * request-init object forwarded to ``fetchApi`` / ``fetchApiWithHeaders`` /
 * ``fetchFile``.
 */
export interface FetchOptions {
  signal?: AbortSignal;
  silent?: boolean;
  cache?: RequestCache;
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

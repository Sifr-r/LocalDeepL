/**
 * translationService.ts — typed wrappers over `endpoints.translationApi`.
 *
 * Phase C / FE-07: every view that talks to ``/api/translate*`` routes
 * through this module so the call sites stay decoupled from the
 * underlying ``fetchApi`` plumbing. ``FetchOptions`` is forwarded so
 * callers can wire an ``AbortSignal`` from their ``onMount`` /
 * ``onDestroy`` lifecycles.
 *
 * Conventions:
 *   - Free async functions; the module is not a class or singleton.
 *   - The exported ``TranslatePayload`` / ``TranslateAsyncJob``
 *     aliases are the canonical ``TranslationRequest`` plus the
 *     narrow async-submission tuple, so callers don't need to import
 *     the underlying wire types.
 */
import { translationApi } from '../api/endpoints';
import type { FetchOptions } from '../api/fetchOptions';
import type { NLLBTranslationResponse, TranslationRequest } from '../types/api';

/**
 * Canonical translation payload — kept as an alias of
 * {@link TranslationRequest} so service consumers don't have to
 * import the wire type directly.
 */
export type TranslatePayload = TranslationRequest;

/** Successful sync-translate response — ``{ translated_text }``. */
export interface TranslateResponse {
  translated_text: string;
}

/** Async-submission tuple: ``{ job_id, status }``. */
export interface TranslateAsyncJob {
  job_id: string;
  status: string;
}

/**
 * NLLB fast-engine translation response — alias of the
 * {@link NLLBTranslationResponse} wire type so service consumers
 * don't have to import it directly.
 *
 * Mirrors the {@link TranslateResponse} shape but also carries the
 * server-side ``source_lang`` / ``target_lang`` echoes.
 */
export type TranslateNllbResponse = NLLBTranslationResponse;

/**
 * Synchronous `POST /api/translate` — returns the translated text.
 *
 * @param payload Translation request (text/artifact + target language).
 * @param options Optional `FetchOptions` (caller-owned abort signal).
 */
export async function translate(
  payload: TranslatePayload,
  options?: FetchOptions
): Promise<TranslateResponse> {
  return translationApi.translate(payload, options);
}

/**
 * NLLB fast-engine translation payload — raw text plus target language.
 *
 * Kept as an inline alias so callers don't need to know the wire
 * shape; the server endpoint (``POST /api/translate/nllb``) accepts
 * exactly these two fields.
 */
export interface TranslateNllbPayload {
  text: string;
  target_language: string;
}

/**
 * NLLB fast-engine ``POST /api/translate/nllb`` — returns the
 * translated text without going through the LangGraph routing layer.
 *
 * Phase C / FE-07 (Task 12): exposed via the typed
 * ``translationService`` so the NLLB branch in ``TranslationView``
 * doesn't need a raw ``fetchApi`` call site.
 */
export async function translateNllb(
  payload: TranslateNllbPayload,
  options?: FetchOptions
): Promise<TranslateNllbResponse> {
  return translationApi.translateNllb(payload, options);
}

/**
 * Async `POST /api/translate/async` — returns a job id immediately;
 * callers poll with {@link getTranslationStatus}.
 */
export async function translateAsync(
  payload: TranslatePayload,
  options?: FetchOptions
): Promise<TranslateAsyncJob> {
  return translationApi.translateAsync(payload, options);
}

/**
 * `GET /api/translate/status/{jobId}` — returns the current async
 * translation job state (``status``, ``translated_text``,
 * ``error``...).
 *
 * The endpoint returns ``unknown`` at the wrapper level because the
 * payload shape varies across job states (queued / running / complete
 * / error). Callers branch on ``status``.
 */
export async function getTranslationStatus(
  jobId: string,
  options?: FetchOptions
): Promise<unknown> {
  return translationApi.getStatus(jobId, options);
}

/**
 * glossaryService.ts — typed wrappers over `endpoints.glossaryApi`.
 *
 * Phase C / FE-07: ``GlossaryView.svelte`` had two raw
 * ``fetchApi('/glossary/library/...')`` call sites; this module keeps
 * them in one place and exposes the import helpers (`importFile` /
 * `importUrl`) so the file-upload and URL-import flows share a typed
 * surface with the rest of the API.
 *
 * The remaining `glossaryApi` methods (``getEntries``, ``toggle``,
 * ``delete``, ``reorder``) are intentionally not re-exported here —
 * they are local mutations better inlined into the view until they
 * grow enough side effects to warrant their own service.
 */
import { glossaryApi } from '../api/endpoints';
import type { FetchOptions } from '../api/fetchOptions';
import type {
  GlossaryEntry,
  GlossaryFormat,
  GlossaryImportJobResponse,
  GlossaryListItem,
  GlossaryPreviewResponse
} from '../types/api';

/** GET `/api/glossary/library` response — list of available libraries. */
export interface LibrariesResponse {
  libraries: GlossaryListItem[];
}

/** GET `/api/glossary/library/merged` response — merged active entries. */
export interface MergedResponse {
  entries: GlossaryEntry[];
}

/** GET `/api/glossary/library/preview` response. */
export type PreviewResponse = GlossaryPreviewResponse;

/**
 * GET `/api/glossary/library` — list available libraries (enabled or
 * all, depending on the server filter — see the backend route).
 */
export async function getLibraries(options?: FetchOptions): Promise<LibrariesResponse> {
  return glossaryApi.getLibraries(options);
}

/**
 * GET `/api/glossary/library/merged` — the union of every enabled
 * library's entries, sorted by insertion order.
 */
export async function getMerged(options?: FetchOptions): Promise<MergedResponse> {
  return glossaryApi.getMerged(options);
}

/**
 * GET `/api/glossary/library/preview` — preview the active merged
 * library in the UI-ready rendering. The shape is owned by the server
 * (see ``GlossaryPreviewResponse``).
 *
 * The plan's task scope lists `getPreview(libraryId, ...)`; the
 * underlying endpoint is library-scoped via the active selection, so
 * the service signature follows the wrapper.
 */
export async function getPreview(options?: FetchOptions): Promise<PreviewResponse> {
  return glossaryApi.getPreview(options);
}

/**
 * POST `/api/glossary/import` (multipart file upload) — kicks off a
 * glossary import job for a TBX / CSV / JSON / XLIFF / TMX file. The
 * server may run synchronously for ≤ SYNC_THRESHOLD entries or hand
 * off to a background task for larger inputs.
 */
export async function importFile(
  formData: FormData,
  options?: FetchOptions
): Promise<GlossaryImportJobResponse> {
  return glossaryApi.importFile(formData, options);
}

/**
 * POST `/api/glossary/import/url` — kick off a URL-based import (the
 * server fetches the upstream glossary, validates it for SSRF, and
 * runs it through the same parser pipeline).
 *
 * @param url Upstream glossary URL (must pass the backend SSRF guard).
 * @param format Parser dispatch (`tbx` / `csv` / `json_pairs` / ...).
 * @param name Optional human-readable library name; the server falls
 *   back to a generated name from the URL when omitted.
 */
export async function importUrl(
  url: string,
  format: GlossaryFormat,
  name?: string,
  options?: FetchOptions
): Promise<GlossaryImportJobResponse> {
  return glossaryApi.importUrl(url, format, name, options);
}

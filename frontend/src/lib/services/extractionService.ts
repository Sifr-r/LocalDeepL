/**
 * extractionService.ts — typed wrappers over `endpoints.extractionApi`.
 *
 * Phase C / FE-07: raw `fetchApi('/extract' | '/export/document' |
 * '/export/docx')` call sites in `ExtractionView.svelte` migrated to
 * this module so the view is decoupled from the `endpoints.ts`
 * wrapper shape.
 *
 * Phase C / Task 9 follow-on: `exportDocument` and `exportDocx` are
 * exposed through `extractionApi` as well as top-level exports, so
 * callers that prefer namespacing get the same surface.
 *
 * Phase C / Task 12: `exportHtml`, `exportDocxTree`, and
 * `exportBlocktree` are added for the same reason — `ExtractionView`
 * had three raw `fetchFile`/`fetchApi` export call sites that needed
 * hoisting onto `extractionApi` first.
 */
import { extractionApi } from '../api/endpoints';
import type { DocumentExportResult } from '../api/endpoints';
import type { FetchOptions } from '../api/fetchOptions';
import type {
  DocumentExportRequest,
  ExportBlockTreeRequest,
  ExportDocxRequest,
  ExportHtmlRequest,
  ExtractionRequest
} from '../types/api';

/** Canonical extraction payload — alias of {@link ExtractionRequest}. */
export type ExtractPayload = ExtractionRequest;

/** Successful extract response — ``{ extracted_data }``. */
export interface ExtractResponse {
  extracted_data: unknown;
}

/** Document export input — alias of {@link DocumentExportRequest}. */
export type ExportDocumentPayload = DocumentExportRequest;

/** HTML export input — alias of {@link ExportHtmlRequest}. */
export type ExportHtmlPayload = ExportHtmlRequest;

/** Block-tree export input — alias of {@link ExportBlockTreeRequest}. */
export type ExportBlocktreePayload = ExportBlockTreeRequest;

/** DOCX-tree export input — alias of {@link ExportBlockTreeRequest}. */
export type ExportDocxTreePayload = ExportBlockTreeRequest;

/** POST `/api/extract` — schema-bounded structured extraction. */
export async function extract(
  payload: ExtractPayload,
  options?: FetchOptions
): Promise<ExtractResponse> {
  return extractionApi.extract(payload, options);
}

/**
 * POST `/api/export/document` — convert an artifact pair into the
 * requested format (markdown / html / docx / block-tree JSON).
 *
 * Returns the artifact id + token so the caller can stream the result
 * from `GET /api/export/{id}`.
 */
export async function exportDocument(
  payload: ExportDocumentPayload,
  options?: FetchOptions
): Promise<DocumentExportResult> {
  return extractionApi.exportDocument(payload, options);
}

/**
 * POST `/api/export/docx` — convert a raw text blob into a ``.docx``
 * binary. Returns the document body as a ``Blob``.
 */
export async function exportDocx(
  payload: ExportDocxRequest,
  options?: FetchOptions
): Promise<Blob> {
  return extractionApi.exportDocx(payload, options);
}

/**
 * POST `/api/export/html` — convert an artifact pair into an ``.html``
 * blob. Returns the document body as a ``Blob``.
 *
 * Phase C / FE-07 (Task 12): hoisted onto ``extractionService`` so the
 * HTML export button in ``ExtractionView`` no longer needs a raw
 * ``fetchFile`` call site.
 */
export async function exportHtml(
  payload: ExportHtmlPayload,
  options?: FetchOptions
): Promise<Blob> {
  return extractionApi.exportHtml(payload, options);
}

/**
 * POST `/api/export/docx-tree` — convert an artifact pair into a
 * block-tree-aware ``.docx`` blob. Returns the document body as a
 * ``Blob``.
 *
 * Phase C / FE-07 (Task 12): hoisted onto ``extractionService`` so the
 * DOCX-tree export button in ``ExtractionView`` no longer needs a raw
 * ``fetchFile`` call site.
 */
export async function exportDocxTree(
  payload: ExportDocxTreePayload,
  options?: FetchOptions
): Promise<Blob> {
  return extractionApi.exportDocxTree(payload, options);
}

/**
 * POST `/api/export/blocktree` — return the document's block tree as
 * structured JSON. The response shape is server-defined; callers
 * branch on the actual payload (``unknown``).
 *
 * Phase C / FE-07 (Task 12): hoisted onto ``extractionService`` so the
 * BlockTree export button in ``ExtractionView`` no longer needs a raw
 * ``fetchApi`` call site.
 */
export async function exportBlocktree(
  payload: ExportBlocktreePayload,
  options?: FetchOptions
): Promise<unknown> {
  return extractionApi.exportBlocktree(payload, options);
}

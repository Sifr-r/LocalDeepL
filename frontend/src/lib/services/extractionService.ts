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
 */
import { extractionApi } from '../api/endpoints';
import type { DocumentExportResult } from '../api/endpoints';
import type { FetchOptions } from '../api/fetchOptions';
import type {
  DocumentExportRequest,
  ExportDocxRequest,
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

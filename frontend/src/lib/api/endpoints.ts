import { fetchApi, fetchApiWithHeaders, fetchFile } from './client';
import type { FetchOptions } from './fetchOptions';
import type {
  RuntimeConfig,
  ProviderPreset,
  JobRecordResponse,
  OcrJobStatusResponse,
  TranslationRequest,
  ExtractionRequest,
  GlossaryEntry,
  GlossaryImportJobResponse,
  GlossaryListItem,
  GlossaryFormat,
  GlossaryPreviewResponse,
  NLLBTranslationResponse,
  TranscriptionSegment,
  TrustSummary,
  DocumentExportFormat,
  DocumentExportRequest,
  ExportDocxRequest,
  ExportHtmlRequest,
  ExportBlockTreeRequest
} from '../types/api';

export async function getConfig(options?: FetchOptions): Promise<RuntimeConfig> {
  return fetchApi<RuntimeConfig>('/config', { signal: options?.signal });
}

export async function updateConfig(
  updates: Partial<RuntimeConfig>,
  options?: FetchOptions
): Promise<RuntimeConfig> {
  return fetchApi<RuntimeConfig>('/config', {
    method: 'POST',
    body: JSON.stringify(updates),
    signal: options?.signal
  });
}

export async function getProviders(options?: FetchOptions): Promise<ProviderPreset[]> {
  const data = await fetchApi<{ providers: ProviderPreset[] }>('/providers', {
    signal: options?.signal
  });
  return data.providers || [];
}

export async function getProviderDetails(
  id: string,
  options?: FetchOptions
): Promise<ProviderPreset> {
  return fetchApi<ProviderPreset>(`/providers/${id}`, { signal: options?.signal });
}

/**
 * Live model list for a single provider. Calls the server's
 * ``GET /api/providers/{id}/models`` endpoint, which fans out to the
 * provider's own ``GET {base}/v1/models`` (or
 * ``GET {base}/api/tags`` for Ollama) and falls back to the static
 * preset list on error. The server uses a 5-second per-request
 * timeout, so the worst-case latency here is bounded even when a
 * provider is unreachable.
 *
 * The endpoint may return an ``error`` field when the live fetch
 * failed; the static ``models`` list is still populated in that
 * case. Callers should treat ``models`` as the source of truth and
 * surface ``error`` as a non-blocking warning.
 */
export interface ProviderModelsResponse {
  models: string[];
  error?: string | null;
}

export async function getProviderModels(
  id: string,
  options?: FetchOptions
): Promise<ProviderModelsResponse> {
  return fetchApi<ProviderModelsResponse>(`/providers/${id}/models`, { signal: options?.signal });
}

export interface ProcessOcrResult {
  /** Parsed response body (JSON when the endpoint returns JSON, otherwise the raw blob). */
  body: unknown;
  /** Lower-cased response headers — used to read side-channel metadata like ``X-Document-Trust``. */
  headers: Record<string, string>;
  /** Parsed ``X-Document-Trust`` summary, or ``null`` when the trust layer was off. */
  trustSummary: TrustSummary | null;
  /** Convenience: text artifact id from ``X-Text-Artifact-Id``. */
  textArtifactId: string | null;
  /** Convenience: text artifact token from ``X-Text-Artifact-Token``. */
  textArtifactToken: string | null;
}

/**
 * Process an upload through ``/api/process`` and surface response headers.
 *
 * The endpoint returns a binary PDF body; callers historically treated
 * it as JSON (legacy sync API contract). Phase 2.18 keeps the existing
 * JSON-shaped callers working by also returning ``body`` for JSON
 * responses, and exposes the headers so the WorkstationView can read
 * ``X-Document-Trust`` and the artifact id/token.
 */
export async function processOcr(
  formData: FormData,
  options?: FetchOptions
): Promise<ProcessOcrResult> {
  const { body, headers } = await fetchApiWithHeaders<unknown>('/process', {
    method: 'POST',
    body: formData,
    signal: options?.signal
  });

  const trustRaw = headers['x-document-trust'];
  let trustSummary: TrustSummary | null = null;
  if (trustRaw) {
    try {
      trustSummary = JSON.parse(trustRaw) as TrustSummary;
    } catch {
      trustSummary = null;
    }
  }

  return {
    body,
    headers,
    trustSummary,
    textArtifactId: headers['x-text-artifact-id'] ?? null,
    textArtifactToken: headers['x-text-artifact-token'] ?? null
  };
}

export async function getOcrStatus(
  jobId: string,
  options?: FetchOptions
): Promise<OcrJobStatusResponse> {
  return fetchApi<OcrJobStatusResponse>(`/process/status/${jobId}`, { signal: options?.signal });
}

/**
 * Submit an upload to the async OCR endpoint and return the job_id.
 *
 * The server returns ``202 Accepted`` with ``{ job_id, status: "pending" }`
 * immediately; the actual OCR runs on a single-worker asyncio queue
 * (or a Celery worker when the ``async-translation`` extras + a Redis
 * broker are configured). Progress streams through the bound WebSocket
 * channel; poll :func:`getOcrStatus` until ``status === "complete"`` and
 * then download the result PDF via :func:`getOcrResult`.
 */
export async function processOcrAsync(
  formData: FormData,
  options?: FetchOptions
): Promise<{ job_id: string; status: string }> {
  return fetchApi<{ job_id: string; status: string }>('/process/async', {
    method: 'POST',
    body: formData,
    silent: true,
    signal: options?.signal
  });
}

/**
 * Download the searchable PDF produced by a completed async OCR job.
 *
 * ``token`` is the per-job ``text_artifact_token`` from the status
 * response (not the user's auth bearer). It is passed as the
 * ``token`` query parameter so the URL works in a plain browser
 * download link without needing a header. The route also accepts
 * the token via the ``Authorization: Bearer <token>`` header.
 */
export async function getOcrResult(
  jobId: string,
  token: string,
  options?: FetchOptions
): Promise<Blob> {
  return fetchFile(`/jobs/${jobId}/result?token=${encodeURIComponent(token)}`, {
    signal: options?.signal
  });
}

export interface DocumentExportResult {
  artifact_id: string;
  token: string;
  format: string;
}

export async function exportDocument(
  payload: DocumentExportRequest,
  options?: FetchOptions
): Promise<DocumentExportResult> {
  return fetchApi<DocumentExportResult>('/export/document', {
    method: 'POST',
    body: JSON.stringify(payload),
    signal: options?.signal
  });
}

export async function exportDocx(
  payload: ExportDocxRequest,
  options?: FetchOptions
): Promise<Blob> {
  return fetchFile('/export/docx', {
    method: 'POST',
    body: JSON.stringify(payload),
    headers: {
      'Content-Type': 'application/json'
    },
    signal: options?.signal
  });
}

/**
 * Translate a raw text blob through the NLLB fast engine.
 *
 * Phase C / FE-07 (Task 12): hoisted onto ``translationApi`` so the
 * typed ``translationService`` can dispatch through a single namespace.
 */
export async function translateNllb(
  payload: { text: string; target_language: string },
  options?: FetchOptions
): Promise<NLLBTranslationResponse> {
  return fetchApi<NLLBTranslationResponse>('/translate/nllb', {
    method: 'POST',
    body: JSON.stringify(payload),
    signal: options?.signal
  });
}

/**
 * Export a text artifact as an HTML file. Returns the document body as a
 * ``Blob`` so callers can pipe it straight into a download trigger.
 *
 * Phase C / FE-07 (Task 12): hoisted onto ``extractionApi`` so the typed
 * ``extractionService`` can dispatch through a single namespace.
 */
export async function exportHtml(
  payload: ExportHtmlRequest,
  options?: FetchOptions
): Promise<Blob> {
  return fetchFile('/export/html', {
    method: 'POST',
    body: JSON.stringify(payload),
    headers: {
      'Content-Type': 'application/json'
    },
    signal: options?.signal
  });
}

/**
 * Export a text artifact as a ``.docx`` built from the document's
 * block tree. Returns the document body as a ``Blob``.
 *
 * Phase C / FE-07 (Task 12): hoisted onto ``extractionApi`` so the typed
 * ``extractionService`` can dispatch through a single namespace.
 */
export async function exportDocxTree(
  payload: ExportBlockTreeRequest,
  options?: FetchOptions
): Promise<Blob> {
  return fetchFile('/export/docx-tree', {
    method: 'POST',
    body: JSON.stringify(payload),
    headers: {
      'Content-Type': 'application/json'
    },
    signal: options?.signal
  });
}

/**
 * Export the document's block tree as structured JSON.
 *
 * The response shape is server-defined and varies per pipeline; we keep
 * the wrapper return type as ``unknown`` so callers branch on the actual
 * payload (typically ``{ blocks: ... }`` or a flat node array).
 *
 * Phase C / FE-07 (Task 12): hoisted onto ``extractionApi`` so the typed
 * ``extractionService`` can dispatch through a single namespace.
 */
export async function exportBlocktree(
  payload: ExportBlockTreeRequest,
  options?: FetchOptions
): Promise<unknown> {
  return fetchApi<unknown>('/export/blocktree', {
    method: 'POST',
    body: JSON.stringify(payload),
    signal: options?.signal
  });
}

export const configApi = {
  get: getConfig,
  update: updateConfig,
  getModels: (namespace: string = 'general', options?: FetchOptions) =>
    // The server only registers /api/models plus the ocr/translation/
    // transcription namespaces — 'general' maps to the bare route.
    fetchApi<{ models: string[] }>(
      namespace && namespace !== 'general' ? `/models/${namespace}` : '/models',
      { signal: options?.signal }
    )
};

export const ocrApi = {
  process: processOcr,
  processAsync: processOcrAsync,
  getStatus: getOcrStatus,
  getResult: getOcrResult,
  cancel: (jobId: string, options?: FetchOptions) =>
    fetchApi(`/jobs/${jobId}/cancel`, { method: 'POST', signal: options?.signal })
};

export const translationApi = {
  translate: (payload: TranslationRequest, options?: FetchOptions) =>
    fetchApi<{ translated_text: string }>('/translate', {
      method: 'POST',
      body: JSON.stringify(payload),
      signal: options?.signal
    }),
  translateAsync: (payload: TranslationRequest, options?: FetchOptions) =>
    fetchApi<{ job_id: string; status: string }>('/translate/async', {
      method: 'POST',
      body: JSON.stringify(payload),
      signal: options?.signal
    }),
  getStatus: (jobId: string, options?: FetchOptions) =>
    fetchApi(`/translate/status/${jobId}`, {
      signal: options?.signal,
      silent: options?.silent
    }),
  /**
   * NLLB fast-engine translation. See {@link translateNllb} for the
   * parameter shape.
   *
   * Phase C / FE-07 (Task 12): hoisted onto ``translationApi`` for
   * namespace parity with ``translate`` / ``translateAsync``.
   */
  translateNllb
};

export const transcriptionApi = {
  transcribe: (formData: FormData, options?: FetchOptions) =>
    fetchApi<{ text: string; segments: TranscriptionSegment[] }>('/transcribe', {
      method: 'POST',
      body: formData,
      signal: options?.signal
    })
};

export const glossaryApi = {
  getLibraries: (options?: FetchOptions) =>
    fetchApi<GlossaryListItem[]>('/glossary/library', { signal: options?.signal }),
  getEntries: (id: string, options?: FetchOptions) =>
    fetchApi<{ entries: GlossaryEntry[] } | GlossaryEntry[]>(`/glossary/library/${id}/entries`, {
      signal: options?.signal
    }),
  getMerged: (options?: FetchOptions) =>
    fetchApi<{ entries: GlossaryEntry[] }>('/glossary/library/merged', { signal: options?.signal }),
  getPreview: (options?: FetchOptions) =>
    fetchApi<GlossaryPreviewResponse>('/glossary/library/preview', { signal: options?.signal }),
  toggle: (id: string, enabled: boolean, options?: FetchOptions) =>
    fetchApi(`/glossary/library/${id}/enable`, {
      method: 'POST',
      body: JSON.stringify({ enabled }),
      signal: options?.signal
    }),
  delete: (id: string, options?: FetchOptions) =>
    fetchApi(`/glossary/library/${id}`, { method: 'DELETE', signal: options?.signal }),
  reorder: (orderedIds: string[], options?: FetchOptions) =>
    fetchApi('/glossary/library/reorder', {
      method: 'POST',
      body: JSON.stringify({ ordered_ids: orderedIds }),
      signal: options?.signal
    }),
  importFile: (formData: FormData, options?: FetchOptions) =>
    fetchApi<GlossaryImportJobResponse>('/glossary/import', {
      method: 'POST',
      body: formData,
      signal: options?.signal
    }),
  importUrl: (url: string, format: GlossaryFormat, name?: string, options?: FetchOptions) =>
    fetchApi<GlossaryImportJobResponse>('/glossary/import/url', {
      method: 'POST',
      body: JSON.stringify({ url, format, name }),
      signal: options?.signal
    })
};

export const jobsApi = {
  list: (options?: FetchOptions) =>
    fetchApi<JobRecordResponse[]>('/jobs', { signal: options?.signal }),
  clear: (options?: FetchOptions) =>
    fetchApi('/jobs', { method: 'DELETE', signal: options?.signal }),
  cancel: (jobId: string, options?: FetchOptions) =>
    fetchApi(`/jobs/${jobId}/cancel`, { method: 'POST', signal: options?.signal })
};

export const providersApi = {
  list: getProviders,
  get: getProviderDetails,
  models: getProviderModels
};

// Artifact GETs carry the token-bound access token in the Authorization
// header (SECURITY.md: artifact tokens must not be placed in query strings).
// The server enforces this via `get_access_token` (header-only).
export const artifactsApi = {
  getText: (id: string, token: string, options?: FetchOptions) =>
    fetchFile(`/text/${id}`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: options?.signal
    }),
  /**
   * Fetch an artifact's text payload and normalize it to a plain
   * ``string`` in one call. The endpoint returns a JSON body whose
   * shape varies per document (array of pages, object keyed by page
   * index, or a raw string); this helper flattens all three into a
   * newline-separated string so callers can drop the result into a
   * ``<textarea>`` without re-implementing the array/object/string
   * normalization in three different views.
   *
   * The token travels in the ``Authorization`` header, not the URL.
   */
  getTextAsString: async (
    id: string,
    token: string,
    options?: FetchOptions
  ): Promise<string> => {
    const blob = await fetchFile(`/text/${id}`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: options?.signal
    });
    const raw = await blob.text();
    try {
      const parsed = JSON.parse(raw) as unknown;
      if (Array.isArray(parsed)) {
        return parsed.filter((p): p is string => typeof p === 'string').join('\n\n');
      }
      if (parsed && typeof parsed === 'object') {
        return Object.values(parsed as Record<string, unknown>)
          .flat()
          .filter((p): p is string => typeof p === 'string')
          .join('\n\n');
      }
      return String(parsed);
    } catch {
      return raw;
    }
  },
  getExport: (id: string, token: string, options?: FetchOptions) =>
    fetchFile(`/export/${id}`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: options?.signal
    })
};

export const extractionApi = {
  extract: (payload: ExtractionRequest, options?: FetchOptions) =>
    fetchApi<{ extracted_data: unknown }>('/extract', {
      method: 'POST',
      body: JSON.stringify(payload),
      signal: options?.signal
    }),
  /**
   * Export an artifact as a structured document (markdown / html / docx /
   * block-tree). See {@link exportDocument} for the parameter shape.
   *
   * Phase C / FE-07: hoisted onto ``extractionApi`` so the typed
   * ``extractionService`` can dispatch through a single namespace.
   */
  exportDocument,
  /**
   * Export a raw text blob as a ``.docx``. See {@link exportDocx} for
   * the parameter shape.
   *
   * Phase C / FE-07: hoisted onto ``extractionApi`` for parity with
   * ``exportDocument``.
   */
  exportDocx,
  /**
   * Export a text artifact as an ``.html`` blob. See {@link exportHtml}
   * for the parameter shape.
   *
   * Phase C / FE-07 (Task 12): hoisted onto ``extractionApi`` for
   * namespace parity with ``exportDocument`` / ``exportDocx``.
   */
  exportHtml,
  /**
   * Export a text artifact as a block-tree-aware ``.docx`` blob. See
   * {@link exportDocxTree} for the parameter shape.
   *
   * Phase C / FE-07 (Task 12): hoisted onto ``extractionApi`` for
   * namespace parity with ``exportDocument`` / ``exportDocx``.
   */
  exportDocxTree,
  /**
   * Export the document's block tree as structured JSON. See
   * {@link exportBlocktree} for the parameter shape.
   *
   * Phase C / FE-07 (Task 12): hoisted onto ``extractionApi`` for
   * namespace parity with ``exportDocument`` / ``exportDocx``.
   */
  exportBlocktree
};

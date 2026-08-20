import { fetchApi, fetchApiWithHeaders, fetchFile } from './client';
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
  TranscriptionSegment,
  TrustSummary,
  DocumentExportFormat
} from '../types/api';

export async function getConfig(): Promise<RuntimeConfig> {
  return fetchApi<RuntimeConfig>('/config');
}

export async function updateConfig(updates: Partial<RuntimeConfig>): Promise<RuntimeConfig> {
  return fetchApi<RuntimeConfig>('/config', {
    method: 'POST',
    body: JSON.stringify(updates)
  });
}

export async function getProviders(): Promise<ProviderPreset[]> {
  const data = await fetchApi<{ providers: ProviderPreset[] }>('/providers');
  return data.providers || [];
}

export async function getProviderDetails(id: string): Promise<ProviderPreset> {
  return fetchApi<ProviderPreset>(`/providers/${id}`);
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
  id: string
): Promise<ProviderModelsResponse> {
  return fetchApi<ProviderModelsResponse>(`/providers/${id}/models`);
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
export async function processOcr(formData: FormData): Promise<ProcessOcrResult> {
  const { body, headers } = await fetchApiWithHeaders<unknown>('/process', {
    method: 'POST',
    body: formData
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
    textArtifactToken: headers['x-text-artifact-token'] ?? null,
  };
}

export async function getOcrStatus(jobId: string): Promise<OcrJobStatusResponse> {
  return fetchApi<OcrJobStatusResponse>(`/process/status/${jobId}`);
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
export async function processOcrAsync(formData: FormData): Promise<{ job_id: string; status: string }> {
  return fetchApi<{ job_id: string; status: string }>('/process/async', {
    method: 'POST',
    body: formData,
    silent: true
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
export async function getOcrResult(jobId: string, token: string): Promise<Blob> {
  return fetchFile(`/jobs/${jobId}/result?token=${encodeURIComponent(token)}`);
}

export interface DocumentExportResult {
  artifact_id: string;
  token: string;
  format: string;
}

export async function exportDocument(payload: {
  text_artifact_id?: string;
  text_artifact_token?: string;
  metadata_artifact_id?: string;
  metadata_artifact_token?: string;
  export_format?: DocumentExportFormat | string;
  format?: string;
  filename?: string;
  [key: string]: unknown;
}): Promise<DocumentExportResult> {
  return fetchApi<DocumentExportResult>('/export/document', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export async function exportDocx(payload: {
  text?: string;
  [key: string]: unknown;
}): Promise<Blob> {
  return fetchFile('/export/docx', {
    method: 'POST',
    body: JSON.stringify(payload),
    headers: {
      'Content-Type': 'application/json'
    }
  });
}

export const configApi = {
  get: getConfig,
  update: updateConfig,
  getModels: (namespace: string = 'general') =>
    // The server only registers /api/models plus the ocr/translation/
    // transcription namespaces — 'general' maps to the bare route.
    fetchApi<{ models: string[] }>(
      namespace && namespace !== 'general' ? `/models/${namespace}` : '/models'
    )
};

export const ocrApi = {
  process: processOcr,
  processAsync: processOcrAsync,
  getStatus: getOcrStatus,
  getResult: getOcrResult,
  cancel: (jobId: string) => fetchApi(`/jobs/${jobId}/cancel`, { method: 'POST' })
};

export const translationApi = {
  translate: (payload: TranslationRequest) =>
    fetchApi<{ translated_text: string }>('/translate', { method: 'POST', body: JSON.stringify(payload) }),
  translateAsync: (payload: TranslationRequest) =>
    fetchApi<{ job_id: string; status: string }>('/translate/async', { method: 'POST', body: JSON.stringify(payload) }),
  getStatus: (jobId: string) => fetchApi(`/translate/status/${jobId}`)
};

export const transcriptionApi = {
  transcribe: (formData: FormData) =>
    fetchApi<{ text: string; segments: TranscriptionSegment[] }>('/transcribe', { method: 'POST', body: formData })
};

export const glossaryApi = {
  getLibraries: () => fetchApi<{ libraries: GlossaryListItem[] }>('/glossary/library'),
  getEntries: (id: string) => fetchApi<{ entries: GlossaryEntry[] } | GlossaryEntry[]>(`/glossary/library/${id}/entries`),
  getMerged: () => fetchApi<{ entries: GlossaryEntry[] }>('/glossary/library/merged'),
  getPreview: () => fetchApi<GlossaryPreviewResponse>('/glossary/library/preview'),
  toggle: (id: string, enabled: boolean) =>
    fetchApi(`/glossary/library/${id}/enable`, { method: 'POST', body: JSON.stringify({ enabled }) }),
  delete: (id: string) => fetchApi(`/glossary/library/${id}`, { method: 'DELETE' }),
  reorder: (orderedIds: string[]) =>
    fetchApi('/glossary/library/reorder', { method: 'POST', body: JSON.stringify({ ordered_ids: orderedIds }) }),
  importFile: (formData: FormData) => fetchApi<GlossaryImportJobResponse>('/glossary/import', { method: 'POST', body: formData }),
  importUrl: (url: string, format: GlossaryFormat, name?: string) =>
    fetchApi<GlossaryImportJobResponse>('/glossary/import/url', { method: 'POST', body: JSON.stringify({ url, format, name }) })
};

export const jobsApi = {
  list: () => fetchApi<JobRecordResponse[]>('/jobs'),
  clear: () => fetchApi('/jobs', { method: 'DELETE' }),
  cancel: (jobId: string) => fetchApi(`/jobs/${jobId}/cancel`, { method: 'POST' })
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
  getText: (id: string, token: string) =>
    fetchFile(`/text/${id}`, { headers: { Authorization: `Bearer ${token}` } }),
  getExport: (id: string, token: string) =>
    fetchFile(`/export/${id}`, { headers: { Authorization: `Bearer ${token}` } })
};

export const extractionApi = {
  extract: (payload: ExtractionRequest) =>
    fetchApi<{ extracted_data: unknown }>('/extract', { method: 'POST', body: JSON.stringify(payload) })
};


import { fetchApi, fetchApiWithHeaders, fetchFile } from './client';
import type {
  RuntimeConfig,
  ProviderPreset,
  JobRecordResponse,
  ProcessSettings,
  TranslationRequest,
  TranscriptionRequest,
  ExtractionRequest,
  GlossaryListItem,
  GlossaryFormat,
  TrustSummary
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

export interface ProcessOcrResult {
  /** Parsed response body (JSON when the endpoint returns JSON, otherwise the raw blob). */
  body: any;
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
  const { body, headers } = await fetchApiWithHeaders<any>('/process', {
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

export async function getOcrStatus(jobId: string): Promise<any> {
  return fetchApi(`/process/status/${jobId}`);
}

export async function exportDocument(payload: {
  text_artifact_id?: string;
  format?: string;
  filename?: string;
  [key: string]: any;
}): Promise<any> {
  return fetchApi('/export/document', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export async function exportDocx(payload: {
  text_artifact_id?: string;
  filename?: string;
  [key: string]: any;
}): Promise<any> {
  return fetchApi('/export/docx', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export const configApi = {
  get: getConfig,
  update: updateConfig,
  getModels: (namespace: string = 'general') => fetchApi<{ models: string[] }>(`/models/${namespace}`)
};

export const ocrApi = {
  process: processOcr,
  getStatus: getOcrStatus,
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
    fetchApi<{ text: string; segments: any[] }>('/transcribe', { method: 'POST', body: formData })
};

export const glossaryApi = {
  getLibraries: () => fetchApi<{ libraries: GlossaryListItem[] }>('/glossary/library'),
  getEntries: (id: string) => fetchApi<{ entries: any[] }>(`/glossary/library/${id}/entries`),
  getMerged: () => fetchApi<Record<string, string>>('/glossary/merged'),
  getPreview: () => fetchApi<any>('/glossary/library/preview'),
  toggle: (id: string, enabled: boolean) =>
    fetchApi(`/glossary/library/${id}/enable`, { method: 'POST', body: JSON.stringify({ enabled }) }),
  delete: (id: string) => fetchApi(`/glossary/library/${id}`, { method: 'DELETE' }),
  reorder: (orderedIds: string[]) =>
    fetchApi('/glossary/library/reorder', { method: 'POST', body: JSON.stringify({ ordered_ids: orderedIds }) }),
  importFile: (formData: FormData) => fetchApi('/glossary/import', { method: 'POST', body: formData }),
  importUrl: (url: string, format: GlossaryFormat, name?: string) =>
    fetchApi('/glossary/import/url', { method: 'POST', body: JSON.stringify({ url, format, name }) })
};

export const jobsApi = {
  list: () => fetchApi<{ jobs: JobRecordResponse[] }>('/jobs'),
  clear: () => fetchApi('/jobs', { method: 'DELETE' }),
  cancel: (jobId: string) => fetchApi(`/jobs/${jobId}/cancel`, { method: 'POST' })
};

export const providersApi = {
  list: getProviders,
  get: getProviderDetails
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
    fetchApi<{ extracted_data: any }>('/extract', { method: 'POST', body: JSON.stringify(payload) })
};


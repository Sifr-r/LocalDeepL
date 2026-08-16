/**
 * workstationService.ts — pure service layer for the workstation OCR pipeline.
 *
 * Audit M6: `WorkstationView.svelte` was a fat component that coupled
 * FormData construction, API polling, WebSocket negotiation, error
 * classification, and store-update logic directly into the UI. This
 * module owns every side effect that touches the outside world so the
 * component can stay focused on rendering and store wiring.
 *
 * Conventions:
 *   - Functions are pure (no Svelte-store writes) — the component
 *     applies the returned patches to its reactive stores.
 *   - Functions that call APIs accept an optional `deps` bag so unit
 *     tests can inject mocks without `vi.mock`-ing the whole module.
 *     Default implementations reach into the real `api/endpoints.ts`
 *     and `stores/websocketStore.ts` modules, which the existing
 *     `WorkstationView.test.ts` already mocks at the module boundary.
 *   - No DOM, no Svelte component imports, no `bind:` directives —
 *     the service is the same shape on Node and in the browser.
 */
import {
  getOcrResult,
  getOcrStatus,
  processOcr,
  processOcrAsync,
  type ProcessOcrResult
} from '../api/endpoints';
import { isFetchError } from '../api/client';
import { websocketStore } from '../stores/websocketStore';
import type {
  DocumentViewModel,
  JobState,
  OcrJobStatusResponse,
  PageResult,
  TrustSummary
} from '../types/api';

// ---------------------------------------------------------------------------
// 1. FormData construction
// ---------------------------------------------------------------------------

/**
 * Names of the per-preprocess toggles the master ``preprocess_pages``
 * flag aggregates over. The master flag is derived from these so the
 * UI toggles stay honest: a user who flips any one toggle on also
 * opts the document into the preprocess pipeline.
 */
const PREPROCESS_TOGGLES = [
  'orientation_detection',
  'deskew',
  'denoise',
  'normalize_contrast',
  'crop_cleanup'
] as const;
type PreprocessToggle = (typeof PREPROCESS_TOGGLES)[number];

/**
 * Minimal config-store shape the OCR FormData consumes. Wider config
 * types (e.g. ``ConfigResponse``) are accepted because every field is
 * optional — the function only reads what it needs.
 */
export interface OcrFormConfig {
  pipeline_mode?: string | null;
  dense_mode?: string | null;
  spellcheck?: string | null;
  document_processors?: string[] | null;
  preprocess_pages?: boolean | null;
  orientation_detection?: boolean | null;
  deskew?: boolean | null;
  denoise?: boolean | null;
  normalize_contrast?: boolean | null;
  crop_cleanup?: boolean | null;
}

export interface BuildFormDataInput {
  file: File;
  config: OcrFormConfig;
  channelId: string;
  sessionToken: string;
}

/**
 * Build the FormData that both ``POST /api/process`` (sync) and
 * ``POST /api/process/async`` consume. The backend only authorizes
 * progress streaming when BOTH the channel id and its session token
 * are presented (``progress_channel`` + ``progress_token``) and the
 * WS handshake has completed.
 */
export function buildOcrFormData(input: BuildFormDataInput): FormData {
  const { file, config, channelId, sessionToken } = input;
  const formData = new FormData();
  formData.append('file', file);
  formData.append('progress_channel', channelId);
  formData.append('progress_token', sessionToken);
  if (config.pipeline_mode) formData.append('pipeline_mode', config.pipeline_mode);
  if (config.dense_mode) formData.append('dense_mode', config.dense_mode);
  if (config.spellcheck) formData.append('spellcheck', config.spellcheck);
  if (config.document_processors?.length) {
    formData.append('document_processors', config.document_processors.join(','));
  }
  const anyPreprocess = PREPROCESS_TOGGLES.some((f) => Boolean(config[f]));
  formData.append('preprocess_pages', String(config.preprocess_pages || anyPreprocess));
  for (const field of PREPROCESS_TOGGLES) {
    formData.append(field, String(Boolean(config[field])));
  }
  return formData;
}

// ---------------------------------------------------------------------------
// 2. Legacy response body extractors
// ---------------------------------------------------------------------------

/**
 * Extract the legacy ``pages`` array from a sync OCR response body.
 * Returns ``undefined`` when the field is missing or the body is not
 * an object — the caller preserves its prior value in that case.
 *
 * The modern OCR endpoint returns a PDF blob instead of JSON, so this
 * helper is intentionally a no-op for the binary path.
 */
export function extractPages(body: unknown): PageResult[] | undefined {
  if (!body || typeof body !== 'object') return undefined;
  const candidate = (body as { pages?: unknown }).pages;
  if (!Array.isArray(candidate)) return undefined;
  return candidate as PageResult[];
}

/**
 * Extract the legacy ``confidence`` number from a sync OCR response
 * body. Returns ``undefined`` when the field is missing or not numeric.
 */
export function extractConfidence(body: unknown): number | undefined {
  if (!body || typeof body !== 'object') return undefined;
  const value = (body as { confidence?: unknown }).confidence;
  return typeof value === 'number' ? value : undefined;
}

// ---------------------------------------------------------------------------
// 3. Progress channel (WebSocket lifecycle)
// ---------------------------------------------------------------------------

/**
 * Structural minimum of the ``websocketStore`` API the service
 * touches. Lets unit tests inject a hand-rolled fake without depending
 * on the full concrete store shape.
 */
export interface WebSocketStoreLike {
  connect(): Promise<{ channelId: string; sessionToken: string }>;
  disconnect(): void;
  requestCancel(): Promise<void>;
}

export interface ProgressSession {
  channelId: string;
  sessionToken: string;
}

export interface OpenProgressChannelOptions {
  websocketStore?: WebSocketStoreLike;
}

/**
 * Open a progress WebSocket channel for the current run. Resolves only
 * after the WS handshake completes (the backend requires the handshake
 * to register the session token before it will authorize streaming).
 */
export async function openProgressChannel(
  options: OpenProgressChannelOptions = {}
): Promise<ProgressSession> {
  const ws = options.websocketStore ?? websocketStore;
  const session = await ws.connect();
  return { channelId: session.channelId, sessionToken: session.sessionToken };
}

export interface CloseProgressChannelOptions {
  websocketStore?: WebSocketStoreLike;
}

/** Release the progress channel — call after every run (success or error). */
export function closeProgressChannel(
  options: CloseProgressChannelOptions = {}
): void {
  const ws = options.websocketStore ?? websocketStore;
  ws.disconnect();
}

export interface RequestProgressCancelOptions {
  websocketStore?: WebSocketStoreLike;
}

/**
 * Ask the worker to cancel the current run. Sends the cancel frame on
 * the WS channel and the ``/api/progress/cancel/{channel}`` HTTP call.
 * Optimistic — the worker honors the cancel at its next block
 * boundary, and the server confirms with a ``cancelled`` frame or a
 * 503 response (audit P2-10).
 */
export async function requestProgressCancel(
  options: RequestProgressCancelOptions = {}
): Promise<void> {
  const ws = options.websocketStore ?? websocketStore;
  await ws.requestCancel();
}

// ---------------------------------------------------------------------------
// 4. Polling
// ---------------------------------------------------------------------------

export interface PollOcrStatusOptions {
  /** Milliseconds between polls. */
  intervalMs?: number;
  /** Maximum polls before giving up. */
  maxAttempts?: number;
  /** Injectable for tests; defaults to the real ``getOcrStatus``. */
  fetchStatus?: (jobId: string) => Promise<OcrJobStatusResponse>;
}

const DEFAULT_POLL_INTERVAL_MS = 2000;
const DEFAULT_POLL_MAX_ATTEMPTS = 1000;

/**
 * Poll ``GET /api/process/status/{jobId}`` until the job reports a
 * terminal state (``complete`` or ``error``). The 2-second cadence is
 * long enough to avoid hot-spinning the queue worker and short enough
 * that the progress bar feels live. 1000 polls = ~33 minutes — well
 * under the 24h record retention ceiling.
 */
export async function pollOcrJobStatus(
  jobId: string,
  options: PollOcrStatusOptions = {}
): Promise<OcrJobStatusResponse> {
  const intervalMs = options.intervalMs ?? DEFAULT_POLL_INTERVAL_MS;
  const maxAttempts = options.maxAttempts ?? DEFAULT_POLL_MAX_ATTEMPTS;
  const fetchStatus = options.fetchStatus ?? getOcrStatus;
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    const status = await fetchStatus(jobId);
    if (status.status === 'complete' || status.status === 'error') {
      return status;
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error(
    `OCR job ${jobId} did not complete within ${(maxAttempts * intervalMs) / 1000}s`
  );
}

// ---------------------------------------------------------------------------
// 5. Submission (sync + async)
// ---------------------------------------------------------------------------

export interface SubmitSyncOcrOptions {
  processOcr?: (formData: FormData) => Promise<ProcessOcrResult>;
}

/**
 * Submit the OCR form via the synchronous ``POST /api/process``
 * endpoint. Returns the response body, headers, trust summary, and
 * artifact ids so the caller can route the result to the appropriate
 * stores.
 */
export function submitSyncOcr(
  formData: FormData,
  options: SubmitSyncOcrOptions = {}
): Promise<ProcessOcrResult> {
  const submit = options.processOcr ?? processOcr;
  return submit(formData);
}

export interface SubmitAsyncOcrOptions {
  processOcrAsync?: typeof processOcrAsync;
  getOcrStatus?: (jobId: string) => Promise<OcrJobStatusResponse>;
  getOcrResult?: (jobId: string, token: string) => Promise<Blob>;
  /** Forwarded to :func:`pollOcrJobStatus`. */
  pollIntervalMs?: number;
  /** Forwarded to :func:`pollOcrJobStatus`. */
  pollMaxAttempts?: number;
}

export interface AsyncOcrSubmission {
  jobId: string;
  status: OcrJobStatusResponse;
  resultBlob: Blob;
}

/**
 * Async-mode submission: POST to ``/api/process/async``, poll for the
 * terminal state, then download the result PDF blob. Throws when the
 * job did not complete cleanly (non-``complete`` status, missing
 * artifact info, or upstream error).
 */
export async function submitAsyncOcr(
  formData: FormData,
  options: SubmitAsyncOcrOptions = {}
): Promise<AsyncOcrSubmission> {
  const submit = options.processOcrAsync ?? processOcrAsync;
  const fetchStatus = options.getOcrStatus ?? getOcrStatus;
  const fetchResult = options.getOcrResult ?? getOcrResult;

  const queued = await submit(formData);
  const status = await pollOcrJobStatus(queued.job_id, {
    fetchStatus,
    intervalMs: options.pollIntervalMs,
    maxAttempts: options.pollMaxAttempts
  });
  if (
    status.status !== 'complete' ||
    !status.text_artifact_id ||
    !status.text_artifact_token
  ) {
    throw new Error(status.error || 'Async OCR job did not complete');
  }
  const resultBlob = await fetchResult(status.job_id, status.text_artifact_token);
  return { jobId: queued.job_id, status, resultBlob };
}

// ---------------------------------------------------------------------------
// 6. Document-store patches
// ---------------------------------------------------------------------------

export interface ApplySyncResultInput {
  result: ProcessOcrResult;
  file: File | null;
  /** Prior document-store value — used for the ``pages`` fallback only. */
  prev: DocumentViewModel;
}

export interface ApplySyncResult {
  /** Patch the component should apply to ``documentStore``. */
  documentPatch: Partial<DocumentViewModel>;
  /**
   * ``true`` when the response body is a non-empty Blob — the caller
   * should then bind it to the PDF preview.
   */
  shouldBindPreview: boolean;
  /** Suggested filename for the PDF preview (``<base>.ocr.pdf``). */
  previewFileName: string | null;
  /** Patch the component should apply to ``jobStore``. */
  jobPatch: Partial<JobState>;
}

/**
 * Reduce a successful sync OCR result to a document-store patch plus a
 * job-store patch and a hint to bind the response blob to the preview.
 * Pure: the caller applies the patches to the relevant stores.
 *
 * The sync path always overrides the artifact id/token on the document
 * store, even to ``null`` when the response lacked the headers — this
 * matches the original behavior so a failed-sync run cannot leave a
 * stale artifact handle on the store.
 */
export function applySyncResult(input: ApplySyncResultInput): ApplySyncResult {
  const { result, file, prev } = input;
  const baseName = file?.name?.replace(/\.[^.]+$/, '') || 'document';
  const shouldBindPreview = result.body instanceof Blob && result.body.size > 0;
  const trustSummary: TrustSummary | null = result.trustSummary;
  return {
    documentPatch: {
      filename: file ? file.name : prev.filename,
      // Legacy JSON paths may still include a ``pages`` array; the
      // modern OCR endpoint returns a PDF blob instead and we let
      // the streamed WebSocket frames populate pageCount.
      pages: extractPages(result.body) ?? prev.pages,
      textArtifact: result.textArtifactId
        ? { id: result.textArtifactId, token: result.textArtifactToken ?? '' }
        : null,
      textArtifactId: result.textArtifactId ?? null,
      textArtifactToken: result.textArtifactToken ?? null,
      confidence: extractConfidence(result.body) ?? prev.confidence,
      // Phase 2.18 — surface trust summary in the document store so
      // the TrustPanel can render it. ``null`` when the trust layer
      // was off (X-Document-Trust header absent).
      trustSummary
    },
    shouldBindPreview,
    previewFileName: shouldBindPreview ? `${baseName}.ocr.pdf` : null,
    jobPatch: {
      activeJobId: result.textArtifactId ?? null,
      percent: 100,
      stage: 'complete',
      statusMessage: 'Done',
      isProcessing: false
    }
  };
}

export interface ApplyAsyncResultInput {
  status: OcrJobStatusResponse;
  file: File | null;
  prevDocument: DocumentViewModel;
  prevJob: JobState;
}

export interface ApplyAsyncResult {
  documentPatch: Partial<DocumentViewModel>;
  jobPatch: Partial<JobState>;
}

/**
 * Reduce a successful async OCR status to a document-store patch and a
 * job-store patch. Unlike the sync path, the async patch falls back to
 * the prior store value when ``text_artifact_id`` or
 * ``text_artifact_token`` is missing — the caller may have set a
 * different artifact during a previous run, and we don't want to
 * clobber it.
 */
export function applyAsyncResult(input: ApplyAsyncResultInput): ApplyAsyncResult {
  const { status, file, prevDocument, prevJob } = input;
  return {
    documentPatch: {
      filename: file ? file.name : prevDocument.filename,
      textArtifact: status.text_artifact_id
        ? { id: status.text_artifact_id, token: status.text_artifact_token ?? '' }
        : null,
      textArtifactId: status.text_artifact_id ?? prevDocument.textArtifactId ?? null,
      textArtifactToken: status.text_artifact_token ?? prevDocument.textArtifactToken ?? null
    },
    jobPatch: {
      activeJobId: status.text_artifact_id ?? prevJob.activeJobId ?? null,
      percent: 100,
      stage: 'complete',
      statusMessage: 'Done',
      isProcessing: false
    }
  };
}

// ---------------------------------------------------------------------------
// 7. Initial job state + failure classification
// ---------------------------------------------------------------------------

export interface BuildInitialJobStateInput {
  useAsync: boolean;
}

/**
 * Per-run ``jobStore`` reset. The async path starts at the ``queued``
 * stage so the progress overlay reads "Uploading document…" before
 * the worker picks the job up; the sync path starts at ``init``.
 */
export function buildInitialJobState(
  input: BuildInitialJobStateInput
): Partial<JobState> {
  return {
    isProcessing: true,
    percent: 2,
    stage: input.useAsync ? 'queued' : 'init',
    statusMessage: 'Uploading document…'
  };
}

export interface OcrFailureClassification {
  /** ``true`` when the upstream returned 503 with a ``cancelled: true`` body. */
  cancelled: boolean;
  /** Human-readable message for the toast and ``statusMessage``. */
  message: string;
}

/**
 * Classify an OCR run failure: distinguish user-initiated cancellation
 * (HTTP 503 with ``cancelled: true``) from a real error. Returns the
 * message to surface on the toast and the job store.
 */
export function classifyOcrFailure(err: unknown): OcrFailureClassification {
  if (isFetchError(err) && err.status === 503) {
    const body = (err.data ?? {}) as { cancelled?: boolean };
    if (body.cancelled) {
      return { cancelled: true, message: 'Cancelled' };
    }
  }
  const message = err instanceof Error ? err.message : 'Processing failed';
  return { cancelled: false, message };
}

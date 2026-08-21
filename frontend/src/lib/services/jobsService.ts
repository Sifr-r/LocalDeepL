/**
 * jobsService.ts — typed wrappers over `endpoints.jobsApi`.
 *
 * Phase C / FE-07: ``JobHistoryView.svelte`` had two raw
 * ``fetchApi('/jobs' | '/jobs/{id}/cancel', ...)`` call sites; this
 * module centralizes them so the view can iterate over a typed
 * `JobRecordResponse[]` without re-deriving the URL shape on every
 * page render.
 */
import { jobsApi } from '../api/endpoints';
import type { FetchOptions } from '../api/fetchOptions';
import type { JobRecordResponse } from '../types/api';

/**
 * GET `/api/jobs` — return the full job history the single-worker
 * queue keeps in memory (or whatever backend `state.job_history` is
 * wired to).
 */
export async function list(options?: FetchOptions): Promise<JobRecordResponse[]> {
  return jobsApi.list(options);
}

/**
 * DELETE `/api/jobs` — clear the entire job history. Used by the
 * "Clear all" button in `JobHistoryView`.
 */
export async function clear(options?: FetchOptions): Promise<unknown> {
  return jobsApi.clear(options);
}

/**
 * POST `/api/jobs/{jobId}/cancel` — best-effort cancellation. The
 * worker honors the cancel at its next block boundary.
 */
export async function cancel(
  jobId: string,
  options?: FetchOptions
): Promise<unknown> {
  return jobsApi.cancel(jobId, options);
}

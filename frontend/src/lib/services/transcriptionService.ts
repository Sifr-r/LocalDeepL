/**
 * transcriptionService.ts — typed wrappers over `endpoints.transcriptionApi`.
 *
 * Phase C / FE-07: ``TranscriptionView.svelte`` was the only view with
 * a raw ``fetchApi('/transcribe', ...)`` site; this service module
 * keeps that call site in one place so the view can stay focused on
 * the recording lifecycle.
 */
import { transcriptionApi } from '../api/endpoints';
import type { FetchOptions } from '../api/fetchOptions';
import type { TranscriptionSegment } from '../types/api';

/** Successful transcribe response — ``{ text, segments }``. */
export interface TranscribeResponse {
  text: string;
  segments: TranscriptionSegment[];
}

/**
 * POST `/api/transcribe` — multipart upload, returns the transcribed
 * text plus the per-segment timing list.
 *
 * @param formData Multipart payload: ``audio`` file plus optional
 *   fields (provider, model, language, etc. — see the backend router
 *   for the full shape).
 */
export async function transcribe(
  formData: FormData,
  options?: FetchOptions
): Promise<TranscribeResponse> {
  return transcriptionApi.transcribe(formData, options);
}

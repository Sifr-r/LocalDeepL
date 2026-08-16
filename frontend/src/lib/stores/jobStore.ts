import { writable } from 'svelte/store';
import type { JobState } from '../types/api';

/**
 * Leaf module — no internal store dependencies.
 *
 * Lives in its own file so that `websocketStore` can import it without
 * creating a cycle through `appStore` (which re-exports it for the
 * existing public API). See frontend/src/lib/stores/appStore.ts and
 * the M5 audit entry in the workspace audit report.
 */
export const defaultJobState: JobState = {
  activeJobId: null,
  percent: 0,
  stage: 'idle',
  statusMessage: '',
  warnings: [],
  chunks: [],
  failedPages: [],
  completedPages: [],
  qualitySummary: null,
  isProcessing: false,
};

export const jobStore = writable<JobState>(defaultJobState);

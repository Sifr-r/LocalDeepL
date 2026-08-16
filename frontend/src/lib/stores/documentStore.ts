import { writable } from 'svelte/store';
import type { DocumentViewModel } from '../types/api';

/**
 * Leaf module — no internal store dependencies.
 *
 * Lives in its own file so that `websocketStore` can import it without
 * creating a cycle through `appStore` (which re-exports it for the
 * existing public API). See frontend/src/lib/stores/appStore.ts and
 * the M5 audit entry in the workspace audit report.
 */
export const defaultDocumentModel: DocumentViewModel = {
  pages: [],
  textArtifacts: [],
  textArtifactId: null,
  textArtifactToken: null,
  bboxes: [],
  // Audit P2-10: null (not { average: 1.0 }) so the metadata panel shows
  // "—" before any result exists instead of a fake "Overall confidence 100%".
  confidenceSummary: null,
  pageCount: 0,
  trustSummary: null,
};

export const documentStore = writable<DocumentViewModel>(defaultDocumentModel);

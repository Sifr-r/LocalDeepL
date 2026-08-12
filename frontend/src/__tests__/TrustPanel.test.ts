import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { mount, tick } from 'svelte';
import type { DocumentViewModel } from '../lib/types/api';

// Hoist a writable documentStore so the panel picks up our test state.
// `require` (not `import`) is intentional: vi.hoisted runs before module
// evaluation, so we must defer the import to keep vitest happy.
const { documentStoreMock } = vi.hoisted(() => {
  // Cast to any — `require` returns `any` and vitest's type checker
  // disallows generic calls on untyped functions.
  const storeMod: any = require('svelte/store');
  return {
    documentStoreMock: storeMod.writable({
      pages: [],
      textArtifacts: [],
      bboxes: [],
      confidenceSummary: { average: 1, min: 1, max: 1 },
      pageCount: 0,
      trustSummary: null
    })
  };
});

vi.mock('../lib/stores/appStore', () => ({
  documentStore: documentStoreMock
}));

// Imported after vi.mock so the mock is in place.
import TrustPanel from '../lib/components/workstation/TrustPanel.svelte';

describe('TrustPanel', () => {
  beforeEach(() => {
    documentStoreMock.set({
      pages: [],
      textArtifacts: [],
      bboxes: [],
      confidenceSummary: { average: 1, min: 1, max: 1 },
      pageCount: 0,
      trustSummary: null
    });
  });

  afterEach(() => {
    while (document.body.firstChild) {
      document.body.removeChild(document.body.firstChild);
    }
  });

  it('hides the panel when documentStore.trustSummary is null', async () => {
    const target = document.createElement('div');
    document.body.appendChild(target);
    mount(TrustPanel, { target });
    await tick();

    // No "OCR trust" heading rendered at all.
    expect(target.textContent ?? '').not.toMatch(/OCR trust/);
  });

  it('hides the panel when no blocks were scored (scored_count=0)', async () => {
    documentStoreMock.update((d: DocumentViewModel) => ({
      ...d,
      trustSummary: {
        block_count: 0,
        scored_count: 0,
        flagged_count: 0,
        average: 0,
        histogram: {},
        flag_counts: {}
      }
    }));

    const target = document.createElement('div');
    document.body.appendChild(target);
    mount(TrustPanel, { target });
    await tick();

    expect(target.textContent ?? '').not.toMatch(/OCR trust/);
  });

  it('renders distribution histogram and flagged-block count when present', async () => {
    documentStoreMock.update((d: DocumentViewModel) => ({
      ...d,
      trustSummary: {
        block_count: 20,
        scored_count: 20,
        flagged_count: 5,
        average: 0.78,
        histogram: {
          '0.0-0.2': 2,
          '0.2-0.4': 1,
          '0.4-0.6': 2,
          '0.6-0.8': 5,
          '0.8-1': 10
        },
        flag_counts: {
          HALLUCINATION_RISK: 3,
          WATERMARK_HIT: 2
        }
      }
    }));

    const target = document.createElement('div');
    document.body.appendChild(target);
    mount(TrustPanel, { target });
    await tick();

    const text = target.textContent ?? '';
    // Section header
    expect(text).toMatch(/OCR trust/);
    // Average score shown as percentage (0.78 → 78%)
    expect(text).toMatch(/78%/);
    // Flagged count
    expect(text).toMatch(/5/);
    // Flag names from flag_counts
    expect(text).toMatch(/HALLUCINATION_RISK/);
    expect(text).toMatch(/WATERMARK_HIT/);
  });

  it('shows the no-flagged-blocks message when flag_counts is empty', async () => {
    documentStoreMock.update((d: DocumentViewModel) => ({
      ...d,
      trustSummary: {
        block_count: 10,
        scored_count: 10,
        flagged_count: 0,
        average: 0.95,
        histogram: { '0.8-1': 10 },
        flag_counts: {}
      }
    }));

    const target = document.createElement('div');
    document.body.appendChild(target);
    mount(TrustPanel, { target });
    await tick();

    expect(target.textContent ?? '').toMatch(/No flagged blocks in this run/);
  });
});

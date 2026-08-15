import { describe, it, expect, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import { websocketStore } from '../stores/websocketStore';
import {
  defaultDocumentModel,
  defaultJobState,
  documentStore,
  jobStore
} from '../stores/appStore';
import type {
  BlockCompleteFrame,
  BlockRevisedFrame,
  CancelledFrame,
  PageCompleteFrame,
  ProgressFrame,
  WebSocketEnvelope
} from '../types/api';

/**
 * Frame contract tests — shapes mirror the backend frame builders in
 * omniscribe/api/services/progress.py (ProgressService.build_*_frame).
 */
describe('websocketStore', () => {
  beforeEach(() => {
    jobStore.set({ ...defaultJobState });
    documentStore.set({ ...defaultDocumentModel, bboxes: [] });
  });

  it('exports websocketStore instance', () => {
    expect(websocketStore).toBeDefined();
    expect(typeof websocketStore.subscribe).toBe('function');
  });

  it('applies legacy progress frames (no type discriminator)', () => {
    const frame: ProgressFrame = {
      status: 'Running OCR on page 3…',
      percent: 45,
      stage: 'ocr'
    };
    websocketStore.handleFrame(frame);

    const job = get(jobStore);
    expect(job.percent).toBe(45);
    expect(job.stage).toBe('ocr');
    expect(job.statusMessage).toBe('Running OCR on page 3…');
  });

  it('collects warning frames without clobbering percent', () => {
    const progress: ProgressFrame = { status: 'Converting…', percent: 40, stage: 'ocr' };
    const warning: ProgressFrame = {
      status: 'OCR failed for page 2: TimeoutError',
      percent: 0,
      stage: 'ocr',
      warning: true
    };
    websocketStore.handleFrame(progress);
    websocketStore.handleFrame(warning);

    const job = get(jobStore);
    expect(job.percent).toBe(40); // warning placeholder percent ignored
    expect(job.warnings).toContain('OCR failed for page 2: TimeoutError');
  });

  it('appends block_complete frames as normalized bboxes', () => {
    const frame: BlockCompleteFrame = {
      type: 'block_complete',
      page_idx: 0,
      block_idx: 2,
      bbox: [0.1, 0.2, 0.5, 0.25],
      text: 'Hello world',
      kind: 'text',
      confidence: 0.93
    };
    websocketStore.handleFrame(frame);

    const doc = get(documentStore);
    expect(doc.bboxes).toHaveLength(1);
    expect(doc.bboxes[0]).toMatchObject({
      block_id: 'p0_b2',
      page: 0,
      block: 2,
      text: 'Hello world',
      confidence: 0.93
    });
    expect(doc.pageCount).toBe(1);
  });

  it('block_revised replaces the matching streamed block', () => {
    const initial: BlockCompleteFrame = {
      type: 'block_complete',
      page_idx: 1,
      block_idx: 0,
      bbox: [0, 0, 1, 0.1],
      text: 'first pass',
      kind: 'text',
      confidence: 0.4
    };
    const revised: BlockRevisedFrame = {
      type: 'block_revised',
      page_idx: 1,
      block_idx: 0,
      attempt: 1,
      bbox: [0, 0, 1, 0.1],
      text: 'second pass',
      kind: 'text',
      confidence: 0.97
    };
    websocketStore.handleFrame(initial);
    websocketStore.handleFrame(revised);

    const doc = get(documentStore);
    expect(doc.bboxes).toHaveLength(1);
    expect(doc.bboxes[0].text).toBe('second pass');
    expect(doc.bboxes[0].revised).toBe(true);
  });

  it('page_complete marks the page done', () => {
    const frame: PageCompleteFrame = { type: 'page_complete', page_idx: 0 };
    websocketStore.handleFrame(frame);
    expect(get(jobStore).completedPages).toEqual([0]);
    expect(get(documentStore).pageCount).toBe(1);
  });

  it('cancelled frames stop the run', () => {
    jobStore.update((s) => ({ ...s, isProcessing: true, percent: 60 }));
    const frame: CancelledFrame = {
      type: 'cancelled',
      status: 'Cancelled by user.',
      percent: 0,
      stage: 'cancelled'
    };
    websocketStore.handleFrame(frame);

    const job = get(jobStore);
    expect(job.stage).toBe('cancelled');
    expect(job.isProcessing).toBe(false);
  });

  it('tolerates unknown frame types without throwing', () => {
    // Cast through the envelope so the future-frame fixture still
    // exercises the unknown-frame branch without the lint rule.
    const future: WebSocketEnvelope = { type: 'future_frame', anything: true } as WebSocketEnvelope;
    expect(() => websocketStore.handleFrame(future)).not.toThrow();
  });
});

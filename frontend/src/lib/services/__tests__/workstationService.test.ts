import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { FetchError } from '../../api/client';
import type { ProcessOcrResult } from '../../api/endpoints';
import type {
  DocumentViewModel,
  JobState,
  OcrJobStatusResponse,
  TrustSummary
} from '../../types/api';
import {
  applyAsyncResult,
  applySyncResult,
  buildInitialJobState,
  buildOcrFormData,
  classifyOcrFailure,
  closeProgressChannel,
  extractConfidence,
  extractPages,
  openProgressChannel,
  pollOcrJobStatus,
  requestProgressCancel,
  submitAsyncOcr,
  submitSyncOcr
} from '../workstationService';

/**
 * Service-level tests for `workstationService.ts`. The component test
 * (`__tests__/WorkstationView.test.ts`) covers wiring and store
 * integration; these tests cover the pure business logic in
 * isolation, including FormData construction, polling cadence,
 * async-submission orchestration, and failure classification.
 */

function makeFile(name = 'sample.pdf'): File {
  return new File(['binary'], name, { type: 'application/pdf' });
}

function makeConfig(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    pipeline_mode: 'hybrid',
    dense_mode: 'auto',
    spellcheck: 'none',
    document_processors: [],
    preprocess_pages: false,
    orientation_detection: false,
    deskew: false,
    denoise: false,
    normalize_contrast: false,
    crop_cleanup: false,
    ...overrides
  };
}

function makePrevDocument(overrides: Partial<DocumentViewModel> = {}): DocumentViewModel {
  return {
    pages: [],
    textArtifacts: [],
    textArtifactId: null,
    textArtifactToken: null,
    bboxes: [],
    confidenceSummary: null,
    pageCount: 0,
    trustSummary: null,
    ...overrides
  };
}

function makePrevJob(overrides: Partial<JobState> = {}): JobState {
  return {
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
    ...overrides
  };
}

describe('workstationService — FormData construction', () => {
  it('appends the file, progress channel, and progress token', () => {
    const form = buildOcrFormData({
      file: makeFile('doc.pdf'),
      config: makeConfig(),
      channelId: 'chan_1',
      sessionToken: 'tok_1'
    });
    expect(form).toBeInstanceOf(FormData);
    expect(form.get('file')).toBeInstanceOf(File);
    expect((form.get('file') as File).name).toBe('doc.pdf');
    expect(form.get('progress_channel')).toBe('chan_1');
    expect(form.get('progress_token')).toBe('tok_1');
  });

  it('appends pipeline_mode / dense_mode / spellcheck only when set', () => {
    const cleared = buildOcrFormData({
      file: makeFile(),
      config: makeConfig({
        pipeline_mode: '',
        dense_mode: undefined,
        spellcheck: null,
        document_processors: []
      }),
      channelId: 'c',
      sessionToken: 't'
    });
    expect(cleared.has('pipeline_mode')).toBe(false);
    expect(cleared.has('dense_mode')).toBe(false);
    expect(cleared.has('spellcheck')).toBe(false);
    expect(cleared.has('document_processors')).toBe(false);

    const set = buildOcrFormData({
      file: makeFile(),
      config: makeConfig({
        pipeline_mode: 'grounded',
        dense_mode: 'on',
        spellcheck: 'en-US'
      }),
      channelId: 'c',
      sessionToken: 't'
    });
    expect(set.get('pipeline_mode')).toBe('grounded');
    expect(set.get('dense_mode')).toBe('on');
    expect(set.get('spellcheck')).toBe('en-US');
  });

  it('joins document_processors as a comma-separated string', () => {
    const form = buildOcrFormData({
      file: makeFile(),
      config: makeConfig({
        document_processors: ['reading_order', 'quality_analysis', 'layout_enrichment']
      }),
      channelId: 'c',
      sessionToken: 't'
    });
    expect(form.get('document_processors')).toBe(
      'reading_order,quality_analysis,layout_enrichment'
    );
  });

  it('derives preprocess_pages=true when any per-toggle is enabled', () => {
    const form = buildOcrFormData({
      file: makeFile(),
      config: makeConfig({ deskew: true }),
      channelId: 'c',
      sessionToken: 't'
    });
    expect(form.get('preprocess_pages')).toBe('true');
    expect(form.get('deskew')).toBe('true');
    // Untoggled fields serialize to 'false' so the backend always
    // sees a value for every key in the contract.
    expect(form.get('orientation_detection')).toBe('false');
    expect(form.get('denoise')).toBe('false');
    expect(form.get('normalize_contrast')).toBe('false');
    expect(form.get('crop_cleanup')).toBe('false');
  });

  it('honors an explicit preprocess_pages override over the derived value', () => {
    // No per-toggle set, but the master flag is true → master wins.
    const form = buildOcrFormData({
      file: makeFile(),
      config: makeConfig({ preprocess_pages: true }),
      channelId: 'c',
      sessionToken: 't'
    });
    expect(form.get('preprocess_pages')).toBe('true');
  });
});

describe('workstationService — body extractors', () => {
  it('returns undefined from extractPages for null / non-object bodies', () => {
    expect(extractPages(null)).toBeUndefined();
    expect(extractPages(undefined)).toBeUndefined();
    expect(extractPages('string')).toBeUndefined();
    expect(extractPages(42)).toBeUndefined();
  });

  it('returns undefined from extractPages when pages is missing or wrong type', () => {
    expect(extractPages({})).toBeUndefined();
    expect(extractPages({ pages: 'oops' })).toBeUndefined();
    expect(extractPages({ pages: null })).toBeUndefined();
  });

  it('returns the array from extractPages when present', () => {
    const pages = [{ page: 0, text: 'hi' }];
    expect(extractPages({ pages })).toBe(pages);
  });

  it('returns undefined from extractConfidence for non-numeric values', () => {
    expect(extractConfidence(null)).toBeUndefined();
    expect(extractConfidence({})).toBeUndefined();
    expect(extractConfidence({ confidence: 'high' })).toBeUndefined();
    expect(extractConfidence({ confidence: null })).toBeUndefined();
  });

  it('returns the number from extractConfidence when present', () => {
    expect(extractConfidence({ confidence: 0.87 })).toBe(0.87);
  });
});

describe('workstationService — progress channel', () => {
  it('openProgressChannel returns channelId / sessionToken from the store', async () => {
    const fakeWs = {
      connect: vi.fn().mockResolvedValue({ channelId: 'chan_x', sessionToken: 'tok_x' }),
      disconnect: vi.fn(),
      requestCancel: vi.fn().mockResolvedValue(undefined)
    };
    const session = await openProgressChannel({ websocketStore: fakeWs });
    expect(session).toEqual({ channelId: 'chan_x', sessionToken: 'tok_x' });
    expect(fakeWs.connect).toHaveBeenCalledTimes(1);
  });

  it('closeProgressChannel delegates to the store', () => {
    const fakeWs = {
      connect: vi.fn(),
      disconnect: vi.fn(),
      requestCancel: vi.fn()
    };
    closeProgressChannel({ websocketStore: fakeWs });
    expect(fakeWs.disconnect).toHaveBeenCalledTimes(1);
  });

  it('requestProgressCancel delegates to the store and awaits the promise', async () => {
    const fakeWs = {
      connect: vi.fn(),
      disconnect: vi.fn(),
      requestCancel: vi.fn().mockResolvedValue(undefined)
    };
    await requestProgressCancel({ websocketStore: fakeWs });
    expect(fakeWs.requestCancel).toHaveBeenCalledTimes(1);
  });
});

describe('workstationService — pollOcrJobStatus', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns immediately when the first poll reports a terminal status', async () => {
    const terminal: OcrJobStatusResponse = {
      job_id: 'job_1',
      filename: 'f.pdf',
      status: 'complete',
      created_at: 0
    };
    const fetchStatus = vi.fn().mockResolvedValue(terminal);
    const result = await pollOcrJobStatus('job_1', { fetchStatus });
    expect(result).toBe(terminal);
    expect(fetchStatus).toHaveBeenCalledTimes(1);
  });

  it('also short-circuits on the "error" status', async () => {
    const errored: OcrJobStatusResponse = {
      job_id: 'job_2',
      filename: 'f.pdf',
      status: 'error',
      created_at: 0,
      error: 'boom'
    };
    const fetchStatus = vi.fn().mockResolvedValue(errored);
    const result = await pollOcrJobStatus('job_2', { fetchStatus });
    expect(result.status).toBe('error');
    expect(fetchStatus).toHaveBeenCalledTimes(1);
  });

  it('keeps polling at the requested cadence until the status is terminal', async () => {
    const pending: OcrJobStatusResponse = {
      job_id: 'job_3',
      filename: 'f.pdf',
      status: 'processing',
      created_at: 0
    };
    const complete: OcrJobStatusResponse = { ...pending, status: 'complete' };
    const fetchStatus = vi
      .fn()
      .mockResolvedValueOnce(pending)
      .mockResolvedValueOnce(pending)
      .mockResolvedValueOnce(complete);

    const promise = pollOcrJobStatus('job_3', {
      fetchStatus,
      intervalMs: 100,
      maxAttempts: 10
    });

    // Drain the two pending polls + their waits, then the terminal poll.
    await vi.advanceTimersByTimeAsync(100);
    await vi.advanceTimersByTimeAsync(100);
    const result = await promise;
    expect(result.status).toBe('complete');
    expect(fetchStatus).toHaveBeenCalledTimes(3);
  });

  it('throws when the job never reports a terminal status within maxAttempts', async () => {
    const pending: OcrJobStatusResponse = {
      job_id: 'job_4',
      filename: 'f.pdf',
      status: 'processing',
      created_at: 0
    };
    const fetchStatus = vi.fn().mockResolvedValue(pending);
    const promise = pollOcrJobStatus('job_4', {
      fetchStatus,
      intervalMs: 10,
      maxAttempts: 3
    });
    // Attach the catch handler BEFORE advancing timers — otherwise
    // the unhandled rejection trips the test runner.
    const caught = promise.catch((e) => e as Error);
    // Three attempts → three 10ms sleeps scheduled by the loop body.
    // Advance one timer at a time so the microtask queue drains
    // between fetches; advancing all 30ms in one shot skips the
    // intermediate ``fetchStatus`` microtasks.
    await vi.advanceTimersByTimeAsync(10);
    await vi.advanceTimersByTimeAsync(10);
    await vi.advanceTimersByTimeAsync(10);
    const err = await caught;
    expect(err).toBeInstanceOf(Error);
    expect((err as Error).message).toMatch(/did not complete within 0.03s/);
    expect(fetchStatus).toHaveBeenCalledTimes(3);
  });
});

describe('workstationService — submitSyncOcr', () => {
  it('delegates to the injected processOcr and returns its result', async () => {
    const expected: ProcessOcrResult = {
      body: { status: 'ok' },
      headers: { 'x-text-artifact-id': 'aid', 'x-text-artifact-token': 'tok' },
      trustSummary: null,
      textArtifactId: 'aid',
      textArtifactToken: 'tok'
    };
    const processOcr = vi.fn().mockResolvedValue(expected);
    const result = await submitSyncOcr(new FormData(), { processOcr });
    expect(result).toBe(expected);
    expect(processOcr).toHaveBeenCalledTimes(1);
  });
});

describe('workstationService — submitAsyncOcr', () => {
  it('submits, polls, downloads, and returns the result blob', async () => {
    const processOcrAsync = vi.fn().mockResolvedValue({ job_id: 'job_async', status: 'pending' });
    const finalStatus: OcrJobStatusResponse = {
      job_id: 'job_async',
      filename: 'f.pdf',
      status: 'complete',
      created_at: 0,
      text_artifact_id: 'aid',
      text_artifact_token: 'tok'
    };
    const getOcrStatus = vi.fn().mockResolvedValue(finalStatus);
    const blob = new Blob(['pdf-bytes'], { type: 'application/pdf' });
    const getOcrResult = vi.fn().mockResolvedValue(blob);

    const result = await submitAsyncOcr(new FormData(), {
      processOcrAsync,
      getOcrStatus,
      getOcrResult
    });

    expect(processOcrAsync).toHaveBeenCalledTimes(1);
    expect(getOcrStatus).toHaveBeenCalledWith('job_async');
    expect(getOcrResult).toHaveBeenCalledWith('job_async', 'tok');
    expect(result.jobId).toBe('job_async');
    expect(result.status).toBe(finalStatus);
    expect(result.resultBlob).toBe(blob);
  });

  it('throws when the polled status is "error"', async () => {
    const processOcrAsync = vi.fn().mockResolvedValue({ job_id: 'job_e', status: 'pending' });
    const getOcrStatus = vi.fn().mockResolvedValue({
      job_id: 'job_e',
      filename: 'f.pdf',
      status: 'error',
      created_at: 0,
      error: 'VLM timeout'
    });
    await expect(
      submitAsyncOcr(new FormData(), { processOcrAsync, getOcrStatus, getOcrResult: vi.fn() })
    ).rejects.toThrow('VLM timeout');
  });

  it('throws when the polled status is complete but lacks artifact info', async () => {
    const processOcrAsync = vi.fn().mockResolvedValue({ job_id: 'job_x', status: 'pending' });
    const getOcrStatus = vi.fn().mockResolvedValue({
      job_id: 'job_x',
      filename: 'f.pdf',
      status: 'complete',
      created_at: 0
    });
    await expect(
      submitAsyncOcr(new FormData(), { processOcrAsync, getOcrStatus, getOcrResult: vi.fn() })
    ).rejects.toThrow('Async OCR job did not complete');
  });
});

describe('workstationService — applySyncResult', () => {
  const trustSummary: TrustSummary = {
    block_count: 4,
    scored_count: 4,
    flagged_count: 0,
    average: 0.92,
    histogram: {},
    flag_counts: {}
  };

  it('reduces a successful sync result into a document + job patch', () => {
    const blob = new Blob(['pdf'], { type: 'application/pdf' });
    const result: ProcessOcrResult = {
      body: blob,
      headers: {},
      trustSummary,
      textArtifactId: 'aid_1',
      textArtifactToken: 'tok_1'
    };
    const applied = applySyncResult({
      result,
      file: makeFile('scan.pdf'),
      prev: makePrevDocument()
    });

    expect(applied.shouldBindPreview).toBe(true);
    expect(applied.previewFileName).toBe('scan.ocr.pdf');
    expect(applied.documentPatch).toMatchObject({
      filename: 'scan.pdf',
      textArtifactId: 'aid_1',
      textArtifactToken: 'tok_1',
      textArtifact: { id: 'aid_1', token: 'tok_1' },
      trustSummary
    });
    expect(applied.jobPatch).toEqual({
      activeJobId: 'aid_1',
      percent: 100,
      stage: 'complete',
      statusMessage: 'Done',
      isProcessing: false
    });
  });

  it('falls back to prev.pages when the body has no legacy ``pages`` array', () => {
    const prev = makePrevDocument({ pages: [{ page: 0, text: 'old' }] });
    const blob = new Blob(['pdf'], { type: 'application/pdf' });
    const applied = applySyncResult({
      result: {
        body: blob,
        headers: {},
        trustSummary: null,
        textArtifactId: 'aid',
        textArtifactToken: 'tok'
      },
      file: makeFile(),
      prev
    });
    expect(applied.documentPatch.pages).toEqual([{ page: 0, text: 'old' }]);
  });

  it('extracts legacy ``pages`` and ``confidence`` from a JSON body', () => {
    const applied = applySyncResult({
      result: {
        body: { pages: [{ page: 0, text: 'hi' }], confidence: 0.81 },
        headers: {},
        trustSummary: null,
        textArtifactId: 'aid',
        textArtifactToken: 'tok'
      },
      file: makeFile(),
      prev: makePrevDocument()
    });
    expect(applied.shouldBindPreview).toBe(false);
    expect(applied.previewFileName).toBeNull();
    expect(applied.documentPatch.pages).toEqual([{ page: 0, text: 'hi' }]);
    expect(applied.documentPatch.confidence).toBe(0.81);
  });

  it('clears the artifact handles when the response lacks artifact headers', () => {
    const applied = applySyncResult({
      result: {
        body: { status: 'ok' },
        headers: {},
        trustSummary: null,
        textArtifactId: null,
        textArtifactToken: null
      },
      file: makeFile(),
      prev: makePrevDocument({ textArtifactId: 'stale' })
    });
    expect(applied.documentPatch.textArtifactId).toBeNull();
    expect(applied.documentPatch.textArtifactToken).toBeNull();
    expect(applied.documentPatch.textArtifact).toBeNull();
  });
});

describe('workstationService — applyAsyncResult', () => {
  it('reduces a complete async status into a document + job patch', () => {
    const status: OcrJobStatusResponse = {
      job_id: 'job_a',
      filename: 'a.pdf',
      status: 'complete',
      created_at: 0,
      text_artifact_id: 'aid_a',
      text_artifact_token: 'tok_a'
    };
    const applied = applyAsyncResult({
      status,
      file: makeFile('a.pdf'),
      prevDocument: makePrevDocument(),
      prevJob: makePrevJob()
    });
    expect(applied.documentPatch).toMatchObject({
      filename: 'a.pdf',
      textArtifactId: 'aid_a',
      textArtifactToken: 'tok_a',
      textArtifact: { id: 'aid_a', token: 'tok_a' }
    });
    expect(applied.jobPatch).toEqual({
      activeJobId: 'aid_a',
      percent: 100,
      stage: 'complete',
      statusMessage: 'Done',
      isProcessing: false
    });
  });

  it('falls back to prevDocument artifact fields when the status lacks them', () => {
    const status: OcrJobStatusResponse = {
      job_id: 'job_b',
      filename: 'b.pdf',
      status: 'complete',
      created_at: 0
    };
    const prev = makePrevDocument({
      textArtifactId: 'prev_aid',
      textArtifactToken: 'prev_tok'
    });
    const applied = applyAsyncResult({
      status,
      file: makeFile('b.pdf'),
      prevDocument: prev,
      prevJob: makePrevJob({ activeJobId: 'prev_job' })
    });
    expect(applied.documentPatch.textArtifactId).toBe('prev_aid');
    expect(applied.documentPatch.textArtifactToken).toBe('prev_tok');
    expect(applied.documentPatch.textArtifact).toBeNull();
    expect(applied.jobPatch.activeJobId).toBe('prev_job');
  });
});

describe('workstationService — buildInitialJobState', () => {
  it('uses the queued stage for async submissions', () => {
    expect(buildInitialJobState({ useAsync: true })).toEqual({
      isProcessing: true,
      percent: 2,
      stage: 'queued',
      statusMessage: 'Uploading document…'
    });
  });

  it('uses the init stage for sync submissions', () => {
    expect(buildInitialJobState({ useAsync: false })).toEqual({
      isProcessing: true,
      percent: 2,
      stage: 'init',
      statusMessage: 'Uploading document…'
    });
  });
});

describe('workstationService — classifyOcrFailure', () => {
  it('flags a 503 with cancelled: true as a cancellation', () => {
    const err = new FetchError('cancelled', 503, { cancelled: true });
    expect(classifyOcrFailure(err)).toEqual({ cancelled: true, message: 'Cancelled' });
  });

  it('treats a 503 without cancelled: true as a real error', () => {
    const err = new FetchError('boom', 503, { detail: 'gpu offline' });
    expect(classifyOcrFailure(err)).toEqual({ cancelled: false, message: 'boom' });
  });

  it('falls back to a generic message for non-Error throws', () => {
    // The service preserves the original component contract: only
    // ``Error`` instances contribute their message; anything else
    // resolves to the generic 'Processing failed' fallback.
    expect(classifyOcrFailure('oops')).toEqual({
      cancelled: false,
      message: 'Processing failed'
    });
    expect(classifyOcrFailure(null)).toEqual({
      cancelled: false,
      message: 'Processing failed'
    });
  });

  it('uses err.message for a plain Error', () => {
    expect(classifyOcrFailure(new Error('Network down'))).toEqual({
      cancelled: false,
      message: 'Network down'
    });
  });
});

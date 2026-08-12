import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { mount, tick } from 'svelte';
import WorkstationView from '../lib/components/workstation/WorkstationView.svelte';

// Hoist the mock handles so the vi.mock factories (which run before module
// evaluation) can reach them.
const {
  connectMock,
  disconnectMock,
  requestCancelMock,
  processOcrMock,
  pushToastMock
} = vi.hoisted(() => ({
  connectMock: vi.fn(),
  disconnectMock: vi.fn(),
  requestCancelMock: vi.fn().mockResolvedValue(undefined),
  processOcrMock: vi.fn(),
  pushToastMock: vi.fn()
}));

vi.mock('../lib/stores/appStore', () => {
  const { writable } = require('svelte/store');
  return {
    activeTab: writable('workstation'),
    themeStore: writable('dark'),
    authStore: writable({}),
    documentStore: writable({
      pages: [],
      textArtifacts: [],
      textArtifactId: null,
      textArtifactToken: null,
      bboxes: [],
      confidenceSummary: { average: 1, min: 1, max: 1 },
      pageCount: 0,
      filename: null,
      jobId: null
    }),
    jobStore: writable({
      activeJobId: null,
      percent: 0,
      stage: 'idle',
      warnings: [],
      chunks: [],
      failedPages: [],
      isProcessing: false
    }),
    configStore: writable({
      api_base: 'http://127.0.0.1:11434',
      model: 'llama3:latest',
      pipeline_mode: 'hybrid',
      dense_mode: 'auto',
      spellcheck: 'none',
      document_processors: [],
      security: { max_upload_bytes: 52428800, max_upload_mb: 50 }
    }),
    toastStore: { pushToast: pushToastMock, set: () => {}, update: () => {}, subscribe: () => () => {} },
    modelStore: writable({ general: [], ocr: [], translation: [], transcription: [], lastFetched: {} }),
    exportModalOpen: writable(false),
    providerModalOpen: writable(false),
    websocketStore: {
      connect: connectMock,
      disconnect: disconnectMock,
      requestCancel: requestCancelMock,
      subscribe: () => () => {}
    },
    loadAppConfig: vi.fn().mockResolvedValue(undefined),
    refreshModels: vi.fn().mockResolvedValue(undefined),
    pushToast: pushToastMock
  };
});

vi.mock('../lib/api/endpoints', () => ({
  processOcr: processOcrMock
}));

function makeFile(): File {
  return new File(['dummy'], 'test.pdf', { type: 'application/pdf' });
}

function setInputFiles(input: HTMLInputElement, files: File[]): void {
  // jsdom 26 doesn't expose DataTransfer, so fake the readonly `files` property
  // on the input element directly. The change handler reads `input.files[0]`
  // and dispatches `fileSelect` up to WorkstationView.
  Object.defineProperty(input, 'files', {
    value: files,
    configurable: true
  });
}

async function waitForButtonEnabled(button: HTMLButtonElement, timeoutMs = 1000): Promise<void> {
  const start = Date.now();
  while (button.disabled && Date.now() - start < timeoutMs) {
    await tick();
    await new Promise((r) => setTimeout(r, 5));
  }
}

describe('WorkstationView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    connectMock.mockResolvedValue({ channelId: 'chan_test_1', sessionToken: 'tok_test_1' });
    processOcrMock.mockResolvedValue({
      body: { status: 'ok' },
      headers: { 'x-text-artifact-id': 'job_1', 'x-text-artifact-token': 'tok_1' },
      trustSummary: null,
      textArtifactId: 'job_1',
      textArtifactToken: 'tok_1'
    });
  });

  afterEach(() => {
    while (document.body.firstChild) {
      document.body.removeChild(document.body.firstChild);
    }
  });

  it('opens a WS channel, posts to /api/process with channel_id, and hides #process-view on success', async () => {
    const target = document.createElement('div');
    document.body.appendChild(target);
    mount(WorkstationView, { target });
    await tick();

    const startBtn = document.getElementById('start-btn') as HTMLButtonElement;
    expect(startBtn).toBeTruthy();
    expect(startBtn.disabled).toBe(true); // disabled until a file is selected

    // Verify the legacy file input still exists (Playwright contract).
    const fileInput = document.getElementById('file-input') as HTMLInputElement;
    expect(fileInput).toBeTruthy();
    expect(fileInput.type).toBe('file');

    // Drive the legacy <input id="file-input"> inside <UploadPanel> so its
    // `on:change` handler fires and dispatches the fileSelect event up to
    // WorkstationView's handler.
    const file = makeFile();
    setInputFiles(fileInput, [file]);
    fileInput.dispatchEvent(new Event('change', { bubbles: true }));

    // Wait for Svelte to flush the fileSelect -> selectedFile -> button update.
    await waitForButtonEnabled(startBtn);
    expect(startBtn.disabled).toBe(false);

    // Click start.
    startBtn.click();
    // Let microtasks settle (connect mock + processOcr mock are async).
    await new Promise((r) => setTimeout(r, 30));
    await new Promise((r) => setTimeout(r, 30));
    await tick();

    // 1) websocketStore.connect was called once.
    expect(connectMock).toHaveBeenCalledTimes(1);

    // 2) processOcr was called once with a FormData containing channel_id and the file.
    expect(processOcrMock).toHaveBeenCalledTimes(1);
    const submittedFormData = processOcrMock.mock.calls[0][0] as FormData;
    expect(submittedFormData).toBeInstanceOf(FormData);
    expect(submittedFormData.get('channel_id')).toBe('chan_test_1');
    const fileBlob = submittedFormData.get('file') as Blob;
    expect(fileBlob).toBeInstanceOf(Blob);
    expect((fileBlob as File).name).toBe('test.pdf');

    // 3) #process-view toggles back to .hidden after success.
    const processView = document.getElementById('process-view');
    expect(processView).toBeTruthy();
    expect(processView!.classList.contains('hidden')).toBe(true);
  });

  it('surfaces a toast and skips the OCR call when the WS channel fails to open', async () => {
    connectMock.mockRejectedValueOnce(new Error('session expired'));

    const target = document.createElement('div');
    document.body.appendChild(target);
    mount(WorkstationView, { target });
    await tick();

    const fileInput = document.getElementById('file-input') as HTMLInputElement;
    const file = makeFile();
    setInputFiles(fileInput, [file]);
    fileInput.dispatchEvent(new Event('change', { bubbles: true }));

    const startBtn = document.getElementById('start-btn') as HTMLButtonElement;
    await waitForButtonEnabled(startBtn);
    startBtn.click();
    await new Promise((r) => setTimeout(r, 30));
    await tick();

    expect(connectMock).toHaveBeenCalledTimes(1);
    expect(processOcrMock).not.toHaveBeenCalled();
    expect(pushToastMock).toHaveBeenCalledWith('error', expect.stringContaining('session expired'));
  });

  it('passes the X-Document-Trust summary into documentStore.trustSummary when present', async () => {
    const trustSummary = {
      block_count: 12,
      scored_count: 10,
      flagged_count: 2,
      average: 0.86,
      histogram: { '0.0-0.2': 1, '0.2-0.4': 0, '0.4-0.6': 1, '0.6-0.8': 2, '0.8-1': 6 },
      flag_counts: { HALLUCINATION_RISK: 1, WATERMARK_HIT: 1 }
    };
    processOcrMock.mockResolvedValueOnce({
      body: { status: 'ok' },
      headers: {
        'x-text-artifact-id': 'job_trust',
        'x-text-artifact-token': 'tok_trust',
        'x-document-trust': JSON.stringify(trustSummary)
      },
      trustSummary,
      textArtifactId: 'job_trust',
      textArtifactToken: 'tok_trust'
    });

    const target = document.createElement('div');
    document.body.appendChild(target);
    mount(WorkstationView, { target });
    await tick();

    const fileInput = document.getElementById('file-input') as HTMLInputElement;
    const file = makeFile();
    setInputFiles(fileInput, [file]);
    fileInput.dispatchEvent(new Event('change', { bubbles: true }));

    const startBtn = document.getElementById('start-btn') as HTMLButtonElement;
    await waitForButtonEnabled(startBtn);
    startBtn.click();
    await new Promise((r) => setTimeout(r, 30));
    await new Promise((r) => setTimeout(r, 30));
    await tick();

    // The mock appStore is a writable; we can read its current value via the
    // store reference from the module mock. The store was declared in the
    // vi.mock factory above; re-importing it here would re-run the factory,
    // so we instead rely on the fact that the store is shared across the
    // mocked module (vitest hoists vi.mock and caches module instances).
    const mocked = await import('../lib/stores/appStore');
    const docs = await new Promise<any>((resolve) => {
      const unsub = mocked.documentStore.subscribe((v) => {
        resolve(v);
        unsub();
      });
    });
    expect(docs.trustSummary).toEqual(trustSummary);
  });
});

import { describe, it, expect, beforeEach, vi, type Mock } from 'vitest';

/**
 * Tests for the NDJSON wire format on the progress WebSocket.
 *
 * The server sends every frame as one JSON object followed by a
 * single '\n' (line-delimited JSON). The browser must:
 *   1. Parse each line independently.
 *   2. Recover if a transport delivers two frames in one text
 *      payload (the failure mode that produced the user-visible
 *      "Failed to parse WebSocket envelope" errors during heavy
 *      OCR bursts).
 *   3. Skip empty lines from a trailing newline.
 */

type Handler = (event: { data: string }) => void;

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  onmessage: Handler | null = null;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: ((err: unknown) => void) | null = null;
  readyState = 0; // CONNECTING
  url: string;
  sentFrames: string[] = [];

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sentFrames.push(data);
  }

  close() {
    this.readyState = 3;
    if (this.onclose) this.onclose();
  }

  // Test helper — deliver a single text frame to the message handler.
  deliverText(data: string) {
    if (this.onmessage) this.onmessage({ data });
  }

  // Test helper — simulate a transport that concatenates two NDJSON
  // frames into one text payload (the bug we're defending against).
  deliverConcatenated(...lines: string[]) {
    if (this.onmessage) this.onmessage({ data: lines.join('\n') });
  }
}

// Loose, partial WebSocket contract — we only implement the surface
// ``connectProgressSocket`` actually touches. ``svelte-check`` rejects
// the full WebSocket type because our mock doesn't include every
// static field, so we cast to a structural minimum.
type MinimalWebSocket = new (url: string) => {
  onmessage: Handler | null;
  onopen: (() => void) | null;
  onclose: (() => void) | null;
  onerror: ((err: unknown) => void) | null;
  send: (data: string) => void;
  close: () => void;
};

const globalAny = globalThis as unknown as {
  WebSocket: MinimalWebSocket;
};

beforeEach(() => {
  MockWebSocket.instances = [];
  globalAny.WebSocket = MockWebSocket as unknown as MinimalWebSocket;
});

describe('connectProgressSocket — NDJSON wire format', () => {
  it('parses a single NDJSON frame (one object + trailing newline)', async () => {
    const { connectProgressSocket } = await import('../websocket');
    const received: unknown[] = [];
    const controller = connectProgressSocket(
      'chan-1',
      'tok-1',
      (msg) => received.push(msg)
    );
    const ws = MockWebSocket.instances[0]!;
    if (ws.onopen) ws.onopen();
    ws.deliverText('{"status":"started","percent":10,"stage":"convert"}\n');
    expect(received).toEqual([
      { status: 'started', percent: 10, stage: 'convert' },
    ]);
    controller.close();
  });

  it('parses a single NDJSON frame without the trailing newline (legacy compat)', async () => {
    const { connectProgressSocket } = await import('../websocket');
    const received: unknown[] = [];
    const controller = connectProgressSocket(
      'chan-2',
      'tok-2',
      (msg) => received.push(msg)
    );
    const ws = MockWebSocket.instances[0]!;
    if (ws.onopen) ws.onopen();
    ws.deliverText('{"status":"running","percent":50,"stage":"ocr"}');
    expect(received).toEqual([
      { status: 'running', percent: 50, stage: 'ocr' },
    ]);
    controller.close();
  });

  it('recovers when a single text frame contains multiple NDJSON objects', async () => {
    // This is the production failure mode: the transport delivers
    // two JSON objects in one text payload. The newline delimiter
    // lets the client split and parse each independently.
    const { connectProgressSocket } = await import('../websocket');
    const received: unknown[] = [];
    const controller = connectProgressSocket(
      'chan-3',
      'tok-3',
      (msg) => received.push(msg)
    );
    const ws = MockWebSocket.instances[0]!;
    if (ws.onopen) ws.onopen();
    ws.deliverConcatenated(
      '{"status":"refining","percent":80,"stage":"refine"}',
      '{"type":"block_retry","page_idx":0,"block_idx":3,"attempt":1,"confidence":0.85,"target":0.98}',
      ''
    );
    expect(received).toEqual([
      { status: 'refining', percent: 80, stage: 'refine' },
      {
        type: 'block_retry',
        page_idx: 0,
        block_idx: 3,
        attempt: 1,
        confidence: 0.85,
        target: 0.98,
      },
    ]);
    controller.close();
  });

  it('skips empty lines and the trailing empty segment after a final newline', async () => {
    const { connectProgressSocket } = await import('../websocket');
    const received: unknown[] = [];
    const controller = connectProgressSocket(
      'chan-4',
      'tok-4',
      (msg) => received.push(msg)
    );
    const ws = MockWebSocket.instances[0]!;
    if (ws.onopen) ws.onopen();
    // Three frames concatenated, with the resulting payload ending
    // in a single trailing newline. The split produces 4 elements
    // — three JSON lines plus one empty string — and we must not
    // call onMessage for the empty one.
    ws.deliverText(
      '{"status":"a","percent":10,"stage":"convert"}\n' +
        '{"status":"b","percent":20,"stage":"ocr"}\n' +
        '{"status":"c","percent":30,"stage":"refine"}\n'
    );
    expect(received).toHaveLength(3);
    expect(received[0]).toEqual({ status: 'a', percent: 10, stage: 'convert' });
    expect(received[1]).toEqual({ status: 'b', percent: 20, stage: 'ocr' });
    expect(received[2]).toEqual({ status: 'c', percent: 30, stage: 'refine' });
    controller.close();
  });

  it('logs and skips a single malformed line without dropping subsequent frames', async () => {
    // A bad line in the middle of a burst must not corrupt the
    // rest of the stream. One frame lost, every other frame
    // delivered.
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const { connectProgressSocket } = await import('../websocket');
    const received: unknown[] = [];
    const controller = connectProgressSocket(
      'chan-5',
      'tok-5',
      (msg) => received.push(msg)
    );
    const ws = MockWebSocket.instances[0]!;
    if (ws.onopen) ws.onopen();
    ws.deliverConcatenated(
      '{"status":"a","percent":10,"stage":"convert"}',
      'this-is-not-json',
      '{"status":"b","percent":20,"stage":"ocr"}'
    );
    expect(received).toHaveLength(2);
    expect(received[0]).toEqual({ status: 'a', percent: 10, stage: 'convert' });
    expect(received[1]).toEqual({ status: 'b', percent: 20, stage: 'ocr' });
    expect(errorSpy).toHaveBeenCalled();
    errorSpy.mockRestore();
    controller.close();
  });
});

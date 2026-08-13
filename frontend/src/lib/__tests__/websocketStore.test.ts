import { describe, it, expect, vi, beforeEach } from 'vitest';
import { websocketStore } from '../stores/websocketStore';

describe('websocketStore', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('exports websocketStore instance', () => {
    expect(websocketStore).toBeDefined();
    expect(typeof websocketStore.subscribe).toBe('function');
  });

  it('handles progress frame dispatching gracefully', () => {
    const frame = {
      type: 'ocr_progress',
      channel_id: 'test-ch-123',
      percent: 45,
      stage: 'processing_ocr',
      warnings: []
    };

    expect(() => websocketStore.handleFrame(frame as any)).not.toThrow();
  });
});

import { get, writable } from 'svelte/store';
import type {
  BBoxItem,
  BlockCompleteFrame,
  BlockRetryFrame,
  BlockRevisedFrame,
  CancelledFrame,
  ChunkCompleteFrame,
  PageCompleteFrame,
  ProgressFrame,
  QualitySummaryFrame,
  WebSocketEnvelope,
} from '../types/api';
import { connectProgressSocket, openProgressSession, type ProgressSocketController } from '../api/websocket';
import { fetchApi } from '../api/client';
// Import directly from the leaf modules instead of from `./appStore`.
// Previously the import went through `appStore`, which itself re-exported
// `websocketStore` — that created a cycle (appStore → websocketStore →
// appStore) and let bundler module-eval order leak `undefined` references
// into the first frame. See audit M5.
import { documentStore } from './documentStore';
import { jobStore } from './jobStore';

export interface WebSocketStoreState {
  channelId: string | null;
  sessionToken: string | null;
  isConnected: boolean;
  isConnecting: boolean;
}

/** How long to wait for the WS handshake before giving up (ms). */
const OPEN_TIMEOUT_MS = 6000;

function blockKey(page: number, block: number): string {
  return `p${page}_b${block}`;
}

function upsertBBox(frame: BlockCompleteFrame | BlockRevisedFrame, revised: boolean): void {
  documentStore.update((curr) => {
    const item: BBoxItem = {
      block_id: blockKey(frame.page_idx, frame.block_idx),
      page: frame.page_idx,
      block: frame.block_idx,
      bbox: frame.bbox,
      confidence: frame.confidence,
      text: frame.text,
      kind: frame.kind,
      revised,
    };
    const idx = curr.bboxes.findIndex((b) => b.block_id === item.block_id);
    const bboxes = idx >= 0
      ? [...curr.bboxes.slice(0, idx), item, ...curr.bboxes.slice(idx + 1)]
      : [...curr.bboxes, item];
    return {
      ...curr,
      bboxes,
      pageCount: Math.max(curr.pageCount, frame.page_idx + 1),
    };
  });
}

function createWebSocketStore() {
  const { subscribe, set, update } = writable<WebSocketStoreState>({
    channelId: null,
    sessionToken: null,
    isConnected: false,
    isConnecting: false,
  });

  let controller: ProgressSocketController | null = null;

  const handleFrame = (frame: WebSocketEnvelope) => {
    if (!frame || typeof frame !== 'object') return;

    // Legacy progress frames carry no `type` discriminator — the server
    // routes them on shape ({status, percent, stage, warning?}).
    if (!('type' in frame) || frame.type === undefined) {
      if (!('percent' in frame) && !('status' in frame)) return;
      const progress = frame as ProgressFrame;
      jobStore.update((curr) => {
        if (progress.warning) {
          // Warning frames carry percent=0 as a placeholder — keep the
          // bar where it is and surface the message instead.
          const message = progress.status || 'Warning during processing';
          const warnings = curr.warnings.includes(message)
            ? curr.warnings
            : [...curr.warnings, message];
          return { ...curr, warnings, statusMessage: message };
        }
        return {
          ...curr,
          percent: typeof progress.percent === 'number' ? progress.percent : curr.percent,
          stage: progress.stage || curr.stage,
          statusMessage: progress.status ?? curr.statusMessage,
        };
      });
      return;
    }

    switch (frame.type) {
      case 'block_complete':
        upsertBBox(frame as BlockCompleteFrame, false);
        break;
      case 'block_revised':
        upsertBBox(frame as BlockRevisedFrame, true);
        break;
      case 'block_retry': {
        const retry = frame as BlockRetryFrame;
        jobStore.update((curr) => ({
          ...curr,
          statusMessage: `Re-OCR block ${retry.block_idx + 1} on page ${retry.page_idx + 1} (attempt ${retry.attempt})`,
        }));
        break;
      }
      case 'page_complete': {
        const page = frame as PageCompleteFrame;
        jobStore.update((curr) => ({
          ...curr,
          completedPages: curr.completedPages.includes(page.page_idx)
            ? curr.completedPages
            : [...curr.completedPages, page.page_idx],
        }));
        documentStore.update((curr) => ({
          ...curr,
          pageCount: Math.max(curr.pageCount, page.page_idx + 1),
        }));
        break;
      }
      case 'quality_summary': {
        const summary = frame as QualitySummaryFrame;
        if (summary.scope === 'job' || summary.page_idx === undefined) {
          jobStore.update((curr) => ({
            ...curr,
            qualitySummary: {
              scope: summary.scope,
              target: summary.target,
              avg_confidence: summary.avg_confidence,
              repaired_count: summary.repaired_count,
              below_target_count: summary.below_target_count,
              page_idx: summary.page_idx,
            },
          }));
        }
        break;
      }
      case 'chunk_complete': {
        const chunk = frame as ChunkCompleteFrame;
        jobStore.update((curr) => {
          const chunks = curr.chunks.filter((c) => c.chunk_idx !== chunk.chunk_idx);
          chunks.push({
            chunk_idx: chunk.chunk_idx,
            total_chunks: chunk.total_chunks,
            page_range: chunk.page_range,
            source_pages: chunk.source_pages,
            text_chars_so_far: chunk.text_chars_so_far,
            overall_percent: chunk.overall_percent,
          });
          chunks.sort((a, b) => a.chunk_idx - b.chunk_idx);
          return {
            ...curr,
            chunks,
            percent: chunk.overall_percent ?? curr.percent,
            statusMessage: `Chunk ${chunk.chunk_idx + 1}/${chunk.total_chunks} complete (pages ${chunk.page_range})`,
          };
        });
        break;
      }
      case 'cancelled': {
        const cancelled = frame as CancelledFrame;
        jobStore.update((curr) => ({
          ...curr,
          stage: 'cancelled',
          percent: 0,
          statusMessage: cancelled.status || 'Cancelled by user.',
          isProcessing: false,
        }));
        break;
      }
      default:
        // chunk_init / translate_chunk_complete / glossary_import and any
        // future frames are tolerated without state changes here.
        break;
    }
  };

  const connect = async (clientId?: string): Promise<{ channelId: string; sessionToken: string }> => {
    const id = clientId || `client_${Math.random().toString(36).substring(2, 10)}`;
    update((s) => ({ ...s, isConnecting: true }));

    try {
      const session = await openProgressSession(id);
      const { channel_id, session_token } = session;

      if (controller) {
        controller.close();
      }

      // The backend only authorizes progress streaming after the WS
      // handshake registers the session token server-side, so resolve
      // only once the socket is actually OPEN.
      const opened = new Promise<void>((resolve, reject) => {
        const timer = setTimeout(() => {
          reject(new Error('Progress socket did not open in time.'));
        }, OPEN_TIMEOUT_MS);

        controller = connectProgressSocket(
          channel_id,
          session_token,
          (msg) => handleFrame(msg),
          {
            onOpen: () => {
              clearTimeout(timer);
              update((s) => ({ ...s, isConnected: true, isConnecting: false }));
              resolve();
            },
            onError: () => {
              update((s) => ({ ...s, isConnected: false }));
            },
            onClose: () => {
              update((s) => ({ ...s, isConnected: false, isConnecting: false }));
            },
          }
        );
      });

      await opened;

      update((s) => ({
        ...s,
        channelId: channel_id,
        sessionToken: session_token,
        isConnected: true,
        isConnecting: false,
      }));

      return { channelId: channel_id, sessionToken: session_token };
    } catch (err) {
      if (controller) {
        controller.close();
        controller = null;
      }
      update((s) => ({ ...s, isConnected: false, isConnecting: false }));
      throw err;
    }
  };

  const requestCancel = async (channelId?: string): Promise<void> => {
    // Capture the latest snapshot synchronously — avoids leaking a Svelte subscription.
    const snap = get({ subscribe });
    const targetChannelId = channelId ?? snap.channelId ?? undefined;
    const targetToken = snap.sessionToken ?? undefined;

    if (controller && targetChannelId) {
      controller.send({ type: 'cancel', channel_id: targetChannelId });
    }

    if (targetChannelId) {
      try {
        await fetchApi(`/progress/cancel/${encodeURIComponent(targetChannelId)}`, {
          method: 'POST',
          silent: true,
          headers: targetToken ? { 'X-Progress-Token': targetToken } : undefined
        });
      } catch (err) {
        console.warn('Failed to call progress cancel endpoint:', err);
      }
    }

    // Optimistic UI: the worker honors the cancel on its next block
    // boundary — an in-flight VLM call finishes first — and the server
    // confirms with a `cancelled` frame / 503 response (audit P2-10).
    jobStore.update((curr) => ({
      ...curr,
      stage: 'cancelling',
      statusMessage: 'Cancelling — waiting for the current model call…'
    }));
  };

  const disconnect = (): void => {
    if (controller) {
      controller.close();
      controller = null;
    }
    set({
      channelId: null,
      sessionToken: null,
      isConnected: false,
      isConnecting: false,
    });
  };

  return {
    subscribe,
    set,
    update,
    connect,
    handleFrame,
    requestCancel,
    disconnect,
  };
}

export const websocketStore = createWebSocketStore();

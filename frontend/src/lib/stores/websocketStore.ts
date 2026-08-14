import { get, writable } from 'svelte/store';
import type { BlockCompleteFrame, OcrProgressFrame, WebSocketEnvelope } from '../types/api';
import { connectProgressSocket, openProgressSession, type ProgressSocketController } from '../api/websocket';
import { fetchApi } from '../api/client';
import { documentStore, jobStore } from './appStore';

export interface WebSocketStoreState {
  channelId: string | null;
  sessionToken: string | null;
  isConnected: boolean;
  isConnecting: boolean;
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

    switch (frame.type) {
      case 'ocr_progress': {
        const ocrFrame = frame as OcrProgressFrame;
        jobStore.update((curr) => ({
          ...curr,
          activeJobId: ocrFrame.job_id || curr.activeJobId,
          percent: ocrFrame.percent,
          stage: ocrFrame.stage,
          warnings: ocrFrame.warnings || curr.warnings,
          chunks: ocrFrame.chunk_summary || curr.chunks,
          failedPages: ocrFrame.failed_pages || curr.failedPages,
        }));
        break;
      }
      case 'block_complete': {
        const blockFrame = frame as BlockCompleteFrame;
        documentStore.update((curr) => {
          const newBBox = {
            block_id: blockFrame.block_id,
            page: blockFrame.page,
            bbox: blockFrame.bbox,
            confidence: blockFrame.confidence,
            text: blockFrame.text,
          };
          return {
            ...curr,
            bboxes: [...curr.bboxes, newBBox],
          };
        });
        break;
      }
      case 'cancel': {
        jobStore.update((curr) => ({
          ...curr,
          stage: 'cancelled',
          percent: 0,
        }));
        break;
      }
      default:
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

      controller = connectProgressSocket(
        channel_id,
        session_token,
        (msg) => handleFrame(msg),
        {
          onError: () => {
            update((s) => ({ ...s, isConnected: false, isConnecting: false }));
          },
          onClose: () => {
            update((s) => ({ ...s, isConnected: false, isConnecting: false }));
          },
        }
      );

      update((s) => ({
        ...s,
        channelId: channel_id,
        sessionToken: session_token,
        isConnected: true,
        isConnecting: false,
      }));

      return { channelId: channel_id, sessionToken: session_token };
    } catch (err) {
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
  
    jobStore.update((curr) => ({
      ...curr,
      stage: 'cancelled',
      percent: 0
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

import { fetchApi } from './client';
import type { WebSocketEnvelope } from '../types/api';

export interface ProgressSessionResponse {
  channel_id: string;
  session_token: string;
}

export interface ProgressSocketController {
  close: () => void;
  send: (data: unknown) => void;
  getSocket: () => WebSocket | null;
}

export interface ConnectProgressSocketOptions {
  onMessage: (msg: WebSocketEnvelope) => void;
  onOpen?: () => void;
  onError?: (err: Event) => void;
  onClose?: () => void;
  maxRetries?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
}

/**
 * Open a new progress channel session on the backend
 */
export async function openProgressSession(clientId: string): Promise<ProgressSessionResponse> {
  return fetchApi<ProgressSessionResponse>('/progress/session', {
    method: 'POST',
    body: JSON.stringify({ client_id: clientId }),
  });
}

/**
 * Connect to progress WebSocket endpoint with exponential backoff & reconnect
 */
export function connectProgressSocket(
  channelId: string,
  token: string,
  onMessage: (msg: WebSocketEnvelope) => void,
  options?: Partial<ConnectProgressSocketOptions>
): ProgressSocketController {
  const maxRetries = options?.maxRetries ?? 5;
  const baseDelayMs = options?.baseDelayMs ?? 1000;
  const maxDelayMs = options?.maxDelayMs ?? 30000;

  let socket: WebSocket | null = null;
  let retryCount = 0;
  let isManualClose = false;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  function getWsUrl(): string {
    if (typeof window === 'undefined') {
      return `ws://localhost:8000/ws/${channelId}?token=${encodeURIComponent(token)}`;
    }
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    return `${protocol}//${host}/ws/${channelId}?token=${encodeURIComponent(token)}`;
  }

  function connect(): void {
    if (isManualClose) return;

    if (typeof WebSocket === 'undefined') {
      console.warn('WebSocket environment constructor is undefined');
      return;
    }

    try {
      const url = getWsUrl();
      socket = new WebSocket(url);

      socket.onopen = () => {
        retryCount = 0;
        if (options?.onOpen) {
          options.onOpen();
        }
      };

      socket.onmessage = (event: MessageEvent) => {
        // The server sends line-delimited JSON: every text frame is
        // one or more JSON objects, each terminated by a single '\n'.
        // The delimiter lets us recover from a transport that
        // accidentally concatenates multiple frames into one text
        // payload (a real failure mode we've seen when the OCR
        // pipeline fires many progress / block_retry events in a
        // burst). Parse each line independently so a single bad
        // frame doesn't take down the whole stream.
        const raw = typeof event.data === 'string' ? event.data : '';
        if (!raw) return;
        const lines = raw.split('\n');
        for (const line of lines) {
          if (!line) continue;
          try {
            const frame = JSON.parse(line) as WebSocketEnvelope;
            onMessage(frame);
          } catch (err) {
            console.error('Failed to parse WebSocket envelope:', err, line);
          }
        }
      };

      socket.onerror = (event: Event) => {
        if (options?.onError) {
          options.onError(event);
        }
      };

      socket.onclose = () => {
        if (options?.onClose) {
          options.onClose();
        }

        if (!isManualClose && retryCount < maxRetries) {
          retryCount++;
          const exponentialDelay = Math.min(
            baseDelayMs * Math.pow(2, retryCount - 1),
            maxDelayMs
          );
          const jitter = Math.random() * 200;
          const delay = exponentialDelay + jitter;

          reconnectTimer = setTimeout(() => {
            connect();
          }, delay);
        }
      };
    } catch (err) {
      console.error('Error instantiating WebSocket:', err);
    }
  }

  connect();

  return {
    close: () => {
      isManualClose = true;
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      if (socket) {
        socket.close();
        socket = null;
      }
    },
    send: (data: unknown) => {
      if (socket && socket.readyState === WebSocket.OPEN) {
        const payload = typeof data === 'string' ? data : JSON.stringify(data);
        socket.send(payload);
      } else {
        console.warn('Cannot send over closed WebSocket');
      }
    },
    getSocket: () => socket,
  };
}

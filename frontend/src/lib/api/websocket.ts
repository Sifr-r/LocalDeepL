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
  /**
   * F3.10 audit fix: callback fired once the reconnect budget is
   * exhausted. Without it, the controller silently gives up after
   * ``maxRetries`` attempts and the UI keeps displaying the "live"
   * progress overlay indefinitely. The workstation uses this to
   * surface a "Connection lost — refresh to retry" banner and stop
   * the in-flight job.
   */
  onGiveUp?: (info: { reason: string; attempts: number }) => void;
  /**
   * F3.11 audit fix: predicate that inspects a CloseEvent and returns
   * ``true`` when the close was a deliberate client-side action (the
   * channel token was wrong, the server rejected the auth frame, the
   * server is shutting down, etc.) and reconnecting would just
   * thrash. The default predicate covers the close codes we know to
   * be terminal:
   *   - ``1008`` Policy Violation (the auth frame was wrong)
   *   - ``4001-4099`` application-defined codes (the server uses the
   *     4xxx range to signal auth/channel errors; the exact codes
   *     are documented in ``api/routers/websocket.py``)
   *   - ``1012`` Service Restart
   *   - ``1013`` Try Again Later
   * The predicate is intentionally pluggable so the workstation can
   * extend it (e.g. to also bail on a particular server-side
   * diagnostic frame) without forking the controller.
   */
  shouldReconnectOnClose?: (event: { code: number; reason: string }) => boolean;
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
  // F3.11: default close-code predicate. The set is conservative —
  // anything we don't recognise gets a reconnect attempt, which is
  // the right default for transient network blips.
  const defaultShouldReconnect = (event: { code: number; reason: string }) => {
    // 1000 Normal Closure, 1001 Going Away, 1006 Abnormal Closure
    // (no Close frame) all warrant a retry.
    if (event.code === 1000 || event.code === 1001 || event.code === 1006) {
      return true;
    }
    // 1008 Policy Violation — the auth frame was wrong. Retrying
    // with the same token would just hit 1008 again. Terminal.
    if (event.code === 1008) {
      return false;
    }
    // 4xxx — application-defined. The backend uses these for
    // auth/channel errors. Terminal.
    if (event.code >= 4000 && event.code < 5000) {
      return false;
    }
    // 1012 Service Restart / 1013 Try Again Later — the server is
    // mid-restart; a retry will succeed shortly. Transient.
    if (event.code === 1012 || event.code === 1013) {
      return true;
    }
    // Unknown codes: retry. Better to thrash for a few seconds than
    // to silently give up on the user's first connection blip.
    return true;
  };
  const shouldReconnect =
    options?.shouldReconnectOnClose ?? defaultShouldReconnect;

  let socket: WebSocket | null = null;
  let retryCount = 0;
  let isManualClose = false;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  function getWsUrl(): string {
    // The session token is NOT part of the URL: query-string secrets
    // leak into server access logs, proxy logs, and browser history.
    // It is sent as the first frame after open instead (see onopen).
    if (typeof window === 'undefined') {
      return `ws://localhost:8000/ws/${channelId}`;
    }
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    return `${protocol}//${host}/ws/${channelId}`;
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
        // Authenticate immediately: the server requires this auth frame
        // as the first message and closes with 1008 if it is missing,
        // malformed, or doesn't match the minted channel/token pair.
        socket?.send(JSON.stringify({ type: 'auth', session_token: token }));
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

      socket.onclose = (event: CloseEvent) => {
        if (options?.onClose) {
          options.onClose();
        }

        if (isManualClose) return;

        // F3.11 audit fix: inspect the close code. Auth-class closes
        // (1008 Policy Violation, server-defined 4xxx) are terminal
        // — the same auth token would just hit the same code
        // again. ``shouldReconnect`` is the pluggable predicate so
        // the workstation can extend the terminal set without
        // forking this controller.
        if (!shouldReconnect({ code: event.code, reason: event.reason })) {
          if (options?.onGiveUp) {
            options.onGiveUp({
              reason: `server closed channel (code=${event.code}, reason=${event.reason || '<empty>'})`,
              attempts: retryCount,
            });
          }
          return;
        }

        if (retryCount < maxRetries) {
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
        } else {
          // F3.10 audit fix: reconnect budget exhausted. Surface
          // this to the caller so the UI can stop the in-flight job
          // (the server is unreachable, the result will never
          // arrive) and switch to a "Connection lost" banner.
          if (options?.onGiveUp) {
            options.onGiveUp({
              reason: `reconnect budget exhausted (${maxRetries} attempts)`,
              attempts: retryCount,
            });
          }
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

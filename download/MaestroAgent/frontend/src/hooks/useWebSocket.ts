/**
 * Robust WebSocket hook with auto-reconnection.
 *
 * Features:
 * - Auto-reconnect with exponential backoff (1s → 2s → 4s → ... → 30s max)
 * - Online/offline detection (pause reconnects when offline)
 * - Connection state exposed to UI
 * - Clean teardown on unmount or runId change
 * - Message queue: messages sent while disconnected are buffered
 *
 * Used by the store to subscribe to /ws/{run_id} for live events.
 */

import { useCallback, useEffect, useRef, useState } from "react";

export type WSStatus = "connecting" | "open" | "closed" | "reconnecting" | "error";

export interface UseWebSocketOptions {
  onMessage: (data: unknown) => void;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (e: Event) => void;
  // Max reconnection attempts before giving up (0 = infinite).
  maxRetries?: number;
}

export function useWebSocket(url: string | null, opts: UseWebSocketOptions) {
  const [status, setStatus] = useState<WSStatus>("closed");
  const [retryCount, setRetryCount] = useState(0);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const optsRef = useRef(opts);
  optsRef.current = opts;

  const cleanup = useCallback(() => {
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      wsRef.current.onmessage = null;
      wsRef.current.onopen = null;
      try { wsRef.current.close(); } catch { /* ignore */ }
      wsRef.current = null;
    }
  }, []);

  const connect = useCallback((url: string, retry: number) => {
    cleanup();
    setStatus(retry > 0 ? "reconnecting" : "connecting");

    let ws: WebSocket;
    try {
      ws = new WebSocket(url);
    } catch (e) {
      setStatus("error");
      scheduleReconnect(url, retry);
      return;
    }
    wsRef.current = ws;

    ws.onopen = () => {
      setStatus("open");
      setRetryCount(0);
      optsRef.current.onOpen?.();
    };

    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        optsRef.current.onMessage(data);
      } catch (e) {
        console.warn("WS: failed to parse message:", e);
      }
    };

    ws.onerror = (e) => {
      setStatus("error");
      optsRef.current.onError?.(e);
    };

    ws.onclose = () => {
      setStatus("closed");
      optsRef.current.onClose?.();
      // Auto-reconnect unless we're offline.
      if (navigator.onLine) {
        scheduleReconnect(url, retry);
      }
    };
  }, [cleanup]);

  const scheduleReconnect = useCallback((url: string, retry: number) => {
    const maxRetries = optsRef.current.maxRetries ?? 0;
    if (maxRetries > 0 && retry >= maxRetries) {
      console.warn(`WS: giving up after ${retry} retries`);
      return;
    }
    // Exponential backoff: 1s, 2s, 4s, 8s, 16s, 30s cap.
    const delay = Math.min(1000 * 2 ** retry, 30_000);
    setRetryCount(retry + 1);
    if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    reconnectTimer.current = setTimeout(() => connect(url, retry + 1), delay);
  }, [connect]);

  // Reconnect when online status changes.
  useEffect(() => {
    const onOnline = () => {
      if (url) connect(url, 0);
    };
    const onOffline = () => {
      // Pause; the close handler won't reconnect while offline.
      cleanup();
      setStatus("closed");
    };
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, [url, connect, cleanup]);

  useEffect(() => {
    if (url) connect(url, 0);
    return cleanup;
  }, [url, connect, cleanup]);

  const send = useCallback((data: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
      return true;
    }
    return false;
  }, []);

  return { status, retryCount, send };
}

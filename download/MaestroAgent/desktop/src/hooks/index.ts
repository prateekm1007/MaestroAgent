/**
 * Custom hooks for MaestroAgent.
 *
 * - useTauriEvent: subscribe to a Tauri event from the Rust shell.
 * - useTauriCommand: invoke a Tauri command with loading/error state.
 * - useVoiceInput: Web Speech API for speech-to-agent input.
 * - useGraphClipboard: copy/paste nodes in the graph builder.
 * - useInterval: declarative setInterval.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

/**
 * Subscribe to a Tauri event. Returns the latest payload.
 */
export function useTauriEvent<T = unknown>(
  eventName: string,
  handler: (payload: T) => void
): void {
  useEffect(() => {
    let unlisten: UnlistenFn | undefined;
    let active = true;
    listen<T>(eventName, (e) => {
      if (active) handler(e.payload);
    }).then((un) => {
      if (active) unlisten = un;
      else un();
    });
    return () => {
      active = false;
      unlisten?.();
    };
  }, [eventName, handler]);
}

/**
 * Invoke a Tauri command with loading + error state.
 */
export function useTauriCommand<TArgs extends unknown[], TResult>(
  command: string
) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<TResult | null>(null);

  const call = useCallback(
    async (...args: TArgs): Promise<TResult | null> => {
      setLoading(true);
      setError(null);
      try {
        // Tauri's invoke takes a single args object; we map positional
        // args to named args by convention (arg0, arg1, ...).
        const invokeArgs: Record<string, unknown> = {};
        args.forEach((a, i) => {
          invokeArgs[`arg${i}`] = a;
        });
        const result = await invoke<TResult>(command, invokeArgs);
        setData(result);
        return result;
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        setError(msg);
        return null;
      } finally {
        setLoading(false);
      }
    },
    [command]
  );

  return { call, loading, error, data, setData };
}

/**
 * Voice input via the Web Speech API (SpeechRecognition).
 *
 * Returns:
 * - listening: whether the mic is active
 * - transcript: the accumulated text
 * - start / stop / reset functions
 * - supported: whether the browser supports speech recognition
 *
 * Note: in Tauri, this uses the OS webview's SpeechRecognition.
 * Chromium-based webviews support this; Safari/WebKit may not.
 */
export function useVoiceInput() {
  const [listening, setListening] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [supported, setSupported] = useState(false);
  const recognitionRef = useRef<any>(null);

  useEffect(() => {
    const SpeechRecognition =
      (window as any).SpeechRecognition ||
      (window as any).webkitSpeechRecognition;
    if (SpeechRecognition) {
      setSupported(true);
      const recognition = new SpeechRecognition();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = "en-US";

      recognition.onresult = (event: any) => {
        let final = "";
        let interim = "";
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const result = event.results[i];
          if (result.isFinal) {
            final += result[0].transcript;
          } else {
            interim += result[0].transcript;
          }
        }
        setTranscript((prev) => prev + final + interim);
      };

      recognition.onerror = (event: any) => {
        console.warn("speech recognition error:", event.error);
        setListening(false);
      };

      recognition.onend = () => {
        setListening(false);
      };

      recognitionRef.current = recognition;
    }

    return () => {
      try {
        recognitionRef.current?.stop();
      } catch {
        // ignore
      }
    };
  }, []);

  const start = useCallback(() => {
    if (!recognitionRef.current) return;
    try {
      recognitionRef.current.start();
      setListening(true);
    } catch (e) {
      console.warn("failed to start recognition:", e);
    }
  }, []);

  const stop = useCallback(() => {
    try {
      recognitionRef.current?.stop();
    } catch {
      // ignore
    }
    setListening(false);
  }, []);

  const reset = useCallback(() => {
    setTranscript("");
  }, []);

  return { listening, transcript, start, stop, reset, supported };
}

/**
 * useInterval — declarative setInterval hook.
 * Pass null as delay to pause.
 */
export function useInterval(callback: () => void, delay: number | null): void {
  const savedCallback = useRef(callback);

  useEffect(() => {
    savedCallback.current = callback;
  }, [callback]);

  useEffect(() => {
    if (delay === null) return;
    const id = setInterval(() => savedCallback.current(), delay);
    return () => clearInterval(id);
  }, [delay]);
}

/**
 * useDebounce — debounce a value.
 */
export function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

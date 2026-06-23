/**
 * Custom hooks for MaestroAgent (browser-native).
 *
 * - useVoiceInput: Web Speech API for speech-to-agent goal entry.
 * - useInterval: declarative setInterval.
 * - useDebounce: debounce a value.
 * - useLocalStorage: persistent state in localStorage (PWA-friendly).
 * - useOnlineStatus: detect connectivity (PWA offline mode).
 */

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Voice input via the Web Speech API (SpeechRecognition).
 * Works in Chrome, Edge, Brave (Chromium-based). Safari support varies.
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
          if (result.isFinal) final += result[0].transcript;
          else interim += result[0].transcript;
        }
        setTranscript((prev) => prev + final + interim);
      };
      recognition.onerror = (event: any) => {
        console.warn("speech recognition error:", event.error);
        setListening(false);
      };
      recognition.onend = () => setListening(false);
      recognitionRef.current = recognition;
    }
    return () => {
      try {
        recognitionRef.current?.stop();
      } catch { /* ignore */ }
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
    try { recognitionRef.current?.stop(); } catch { /* ignore */ }
    setListening(false);
  }, []);

  const reset = useCallback(() => setTranscript(""), []);

  return { listening, transcript, start, stop, reset, supported };
}

/** Declarative setInterval. Pass null to pause. */
export function useInterval(callback: () => void, delay: number | null): void {
  const savedCallback = useRef(callback);
  useEffect(() => { savedCallback.current = callback; }, [callback]);
  useEffect(() => {
    if (delay === null) return;
    const id = setInterval(() => savedCallback.current(), delay);
    return () => clearInterval(id);
  }, [delay]);
}

/** Debounce a value. */
export function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

/** Persistent state in localStorage. PWA-friendly across sessions. */
export function useLocalStorage<T>(key: string, initial: T): [T, (v: T | ((prev: T) => T)) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const stored = localStorage.getItem(key);
      return stored ? JSON.parse(stored) as T : initial;
    } catch {
      return initial;
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch { /* ignore quota errors */ }
  }, [key, value]);
  return [value, setValue];
}

/** Online/offline status — useful for PWA offline indicator. */
export function useOnlineStatus(): boolean {
  const [online, setOnline] = useState(navigator.onLine);
  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, []);
  return online;
}

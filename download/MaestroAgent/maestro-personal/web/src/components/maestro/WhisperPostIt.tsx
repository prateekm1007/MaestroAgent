"use client";

import { useEffect, useState, useRef } from "react";
import { Zap, X, Mail, ChevronLeft, ChevronRight } from "lucide-react";
import { maestroApi } from "@/lib/maestro-api";

/**
 * WhisperPostIt -- a minimal overlay that appears on the Today page.
 *
 * Tufte design: hairline border, amber accent, no gradients, no
 * skeuomorphism, no framer-motion. Dismissible, auto-rotates through
 * multiple whispers.
 *
 * Features:
 *  - Clean card with border-l-2 amber accent (matches the design system)
 *  - The whisper title + body
 *  - A "Draft follow-up" button if the whisper has an entity
 *  - A dismiss (X) button
 *  - Left / right chevron buttons to manually page through whispers.
 *    Manual paging pauses auto-rotation for 30s.
 *  - Dot indicators at the bottom are clickable to jump directly.
 *  - Auto-dismiss after 45 seconds of inactivity (resets on manual nav).
 *  - role="status" + aria-live="polite" for screen reader announcement.
 *  - Mobile-aware positioning (bottom-20 to avoid covering the nav).
 */

const MANUAL_NAV_PAUSE_MS = 30_000;
const AUTO_ROTATE_MS = 15_000;
const AUTO_DISMISS_MS = 45_000;

export function WhisperPostIt({ onDraft }: { onDraft?: (entity: string) => void }) {
  const [whispers, setWhispers] = useState<any[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [dismissed, setDismissed] = useState(false);
  const [loading, setLoading] = useState(true);
  const manualNavUntilRef = useRef<number>(0);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const { data, live } = await maestroApi.getWhispers();
        if (!alive) return;
        if (live) {
          const list = Array.isArray(data) ? data : (data?.whispers || []);
          setWhispers(list);
        }
      } catch {
        // Non-fatal -- whispers are a nice-to-have
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    if (whispers.length <= 1 || dismissed) return;
    const interval = setInterval(() => {
      if (Date.now() < manualNavUntilRef.current) return;
      setCurrentIndex(prev => (prev + 1) % whispers.length);
    }, AUTO_ROTATE_MS);
    return () => clearInterval(interval);
  }, [whispers.length, dismissed]);

  useEffect(() => {
    if (whispers.length === 0 || dismissed) return;
    const timeout = setTimeout(() => setDismissed(true), AUTO_DISMISS_MS);
    return () => clearTimeout(timeout);
  }, [whispers.length, dismissed, currentIndex]);

  const goPrev = () => {
    if (whispers.length <= 1) return;
    manualNavUntilRef.current = Date.now() + MANUAL_NAV_PAUSE_MS;
    setCurrentIndex(prev => (prev - 1 + whispers.length) % whispers.length);
  };
  const goNext = () => {
    if (whispers.length <= 1) return;
    manualNavUntilRef.current = Date.now() + MANUAL_NAV_PAUSE_MS;
    setCurrentIndex(prev => (prev + 1) % whispers.length);
  };

  if (loading || dismissed || whispers.length === 0) return null;

  const whisper = whispers[currentIndex];
  if (!whisper) return null;

  const title = whisper.title || whisper.headline || "Whisper";
  const body = whisper.body || whisper.message || whisper.text || "";
  const entity = whisper.entity || whisper.recipient || "";

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-20 right-4 md:bottom-6 md:right-6 z-50 max-w-sm"
    >
      {/* Clean card -- Tufte: border-l-2 accent, no gradient, no skeuomorphism */}
      <div className="border-l-2 border-amber-500 bg-white p-4 shadow-sm">
        {/* Header */}
        <div className="flex items-start justify-between gap-2 mb-2">
          <div className="flex items-center gap-1.5">
            <Zap className="h-4 w-4 text-amber-600" fill="currentColor" />
            <span className="text-[10px] font-bold uppercase tracking-wider text-gray-700">
              Whisper
            </span>
            {whispers.length > 1 && (
              <span className="text-[10px] text-gray-400 ml-1">
                {currentIndex + 1} / {whispers.length}
              </span>
            )}
          </div>
          <button
            onClick={() => setDismissed(true)}
            className="text-gray-400 hover:text-black transition-colors"
            aria-label="Dismiss"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* Title */}
        <h4 className="text-sm font-semibold text-black mb-1 leading-snug">
          {title}
        </h4>

        {/* Body */}
        {body && (
          <p className="text-xs text-gray-600 leading-relaxed mb-3">
            {body.length > 150 ? body.substring(0, 150) + "…" : body}
          </p>
        )}

        {/* Action buttons + left/right paging controls */}
        <div className="flex items-center justify-between gap-2">
          {entity && onDraft ? (
            <button
              onClick={() => {
                onDraft(entity);
                setDismissed(true);
              }}
              className="inline-flex items-center gap-1.5 text-xs font-medium text-white bg-amber-700 hover:bg-amber-800 px-3 py-1.5 transition-colors"
            >
              <Mail className="h-3 w-3" />
              Draft follow-up
            </button>
          ) : (
            <span />
          )}

          {whispers.length > 1 && (
            <div className="flex items-center gap-1">
              <button
                onClick={goPrev}
                className="inline-flex items-center justify-center h-6 w-6 text-gray-600 hover:bg-gray-100 transition-colors"
                aria-label="Previous whisper"
                title="Previous whisper"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <button
                onClick={goNext}
                className="inline-flex items-center justify-center h-6 w-6 text-gray-600 hover:bg-gray-100 transition-colors"
                aria-label="Next whisper"
                title="Next whisper"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          )}
        </div>

        {/* Dot indicators -- uniform width, active = filled */}
        {whispers.length > 1 && (
          <div className="flex gap-1.5 mt-3 justify-center">
            {whispers.map((_, i) => (
              <button
                key={i}
                onClick={() => {
                  manualNavUntilRef.current = Date.now() + MANUAL_NAV_PAUSE_MS;
                  setCurrentIndex(i);
                }}
                aria-label={`Go to whisper ${i + 1}`}
                className={`h-1.5 w-1.5 rounded-full transition-colors ${
                  i === currentIndex ? "bg-amber-700" : "bg-gray-300 hover:bg-gray-400"
                }`}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

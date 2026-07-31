"use client";

import { useEffect, useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Zap, X, Mail, ChevronLeft, ChevronRight } from "lucide-react";
import { maestroApi } from "@/lib/maestro-api";

/**
 * WhisperPostIt -- a post-it note overlay that appears on the Today page.
 *
 * Instead of whispers being a separate tab with 0 results, this component
 * fetches whispers in the background and displays them as a sticky note
 * overlay in the corner of the Today page. Nice graphics, dismissible,
 * auto-rotates through multiple whispers.
 *
 * The post-it has:
 *  - Yellow paper texture with a slight rotation (like a real sticky note)
 *  - A pushpin icon at the top
 *  - The whisper title + body
 *  - A "Draft follow-up" button if the whisper has an entity
 *  - A dismiss (X) button
 *  - Left / right chevron buttons to manually page through whispers.
 *    Manual paging pauses the auto-rotation for 30s so the user has time
 *    to read the whisper they navigated to.
 *  - Dot indicators at the bottom reflect the current position and are
 *    clickable to jump directly to a whisper.
 *  - Auto-dismiss after 45 seconds of inactivity (resets on manual nav).
 */

// When the user manually pages, pause auto-rotation for this long so
// they have time to read the whisper they navigated to.
const MANUAL_NAV_PAUSE_MS = 30_000;
// Auto-rotate interval when the user has not touched the controls.
const AUTO_ROTATE_MS = 15_000;
// Auto-dismiss the entire post-it after this long (resets on manual nav).
const AUTO_DISMISS_MS = 45_000;

export function WhisperPostIt({ onDraft }: { onDraft?: (entity: string) => void }) {
  const [whispers, setWhispers] = useState<any[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [dismissed, setDismissed] = useState(false);
  const [loading, setLoading] = useState(true);
  // Wall-clock time at which the user last manually paged. While
  // Date.now() < manualNavUntilRef.current, auto-rotation is paused.
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

  // Auto-rotate through whispers every AUTO_ROTATE_MS, but only when the
  // user has not manually paged within the last MANUAL_NAV_PAUSE_MS.
  useEffect(() => {
    if (whispers.length <= 1 || dismissed) return;
    const interval = setInterval(() => {
      if (Date.now() < manualNavUntilRef.current) return; // paused
      setCurrentIndex(prev => (prev + 1) % whispers.length);
    }, AUTO_ROTATE_MS);
    return () => clearInterval(interval);
  }, [whispers.length, dismissed]);

  // Auto-dismiss after AUTO_DISMISS_MS of inactivity. Resets whenever
  // the user manually pages (currentIndex changes via goPrev/goNext),
  // so an actively-used post-it never dismisses out from under them.
  useEffect(() => {
    if (whispers.length === 0 || dismissed) return;
    const timeout = setTimeout(() => setDismissed(true), AUTO_DISMISS_MS);
    return () => clearTimeout(timeout);
  }, [whispers.length, dismissed, currentIndex]);

  // Manual paging -- left / right. Pauses auto-rotation for
  // MANUAL_NAV_PAUSE_MS so the user has time to read the whisper they
  // navigated to. Wraps around at the ends.
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
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: 20, rotate: -2 }}
        animate={{ opacity: 1, y: 0, rotate: -2 }}
        exit={{ opacity: 0, y: 20, rotate: -2 }}
        transition={{ type: "spring", stiffness: 300, damping: 25 }}
        className="fixed bottom-6 right-6 z-50 max-w-sm"
      >
        {/* Post-it note */}
        <div
          className="relative "
          style={{
            background: "linear-gradient(135deg, #fff9c4 0%, #fff59d 50%, #fff176 100%)",
            borderRadius: "2px",
            padding: "20px 20px 16px 20px",
            borderTop: "none",
            borderLeft: "1px solid #fdd835",
            borderRight: "1px solid #f9a825",
            borderBottom: "1px solid #f57f17",
            minHeight: "120px",
          }}
        >
          {/* Pushpin */}
          <div
            className="absolute -top-2 left-1/2 -translate-x-1/2 w-4 h-4  "
            style={{
              background: "radial-gradient(circle at 30% 30%, #ef5350, #c62828)",
              border: "1px solid #b71c1c",
            }}
          />

          {/* Header */}
          <div className="flex items-start justify-between gap-2 mb-2">
            <div className="flex items-center gap-1.5">
              <Zap className="h-4 w-4 " fill="currentColor" />
              <span className="text-[10px] font-bold uppercase tracking-wider text-amber-800">
                Whisper
              </span>
              {whispers.length > 1 && (
                <span className="text-[10px] text-amber-800/70 ml-1">
                  {currentIndex + 1} / {whispers.length}
                </span>
              )}
            </div>
            <button
              onClick={() => setDismissed(true)}
              className="/60 hover: transition-colors"
              aria-label="Dismiss"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>

          {/* Title */}
          <h4 className="text-sm font-semibold  mb-1 leading-snug">
            {title}
          </h4>

          {/* Body */}
          {body && (
            <p className="text-xs text-amber-800/90 leading-relaxed mb-3">
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
                className="inline-flex items-center gap-1.5 text-xs font-medium text-white bg-amber-700 hover:bg-amber-800 px-3 py-1.5  transition-colors "
              >
                <Mail className="h-3 w-3" />
                Draft follow-up
              </button>
            ) : (
              <span /> // keep layout stable when there's no draft action
            )}

            {whispers.length > 1 && (
              <div className="flex items-center gap-1">
                <button
                  onClick={goPrev}
                  className="inline-flex items-center justify-center h-6 w-6 text-amber-800 hover:bg-amber-800/10 transition-colors"
                  aria-label="Previous whisper"
                  title="Previous whisper"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <button
                  onClick={goNext}
                  className="inline-flex items-center justify-center h-6 w-6 text-amber-800 hover:bg-amber-800/10 transition-colors"
                  aria-label="Next whisper"
                  title="Next whisper"
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            )}
          </div>

          {/* Rotation indicator -- clickable dots */}
          {whispers.length > 1 && (
            <div className="flex gap-1 mt-3 justify-center">
              {whispers.map((_, i) => (
                <button
                  key={i}
                  onClick={() => {
                    manualNavUntilRef.current = Date.now() + MANUAL_NAV_PAUSE_MS;
                    setCurrentIndex(i);
                  }}
                  aria-label={`Go to whisper ${i + 1}`}
                  className={`h-1.5  transition-all ${
                    i === currentIndex ? "w-6 bg-amber-700" : "w-1.5 bg-amber-700/30 hover:bg-amber-700/50"
                  }`}
                />
              ))}
            </div>
          )}

          {/* Folded corner effect */}
          <div
            className="absolute bottom-0 right-0"
            style={{
              width: "0",
              height: "0",
              borderStyle: "solid",
              borderWidth: "0 0 16px 16px",
              borderColor: "transparent transparent #f57f17 transparent",
            }}
          />
        </div>
      </motion.div>
    </AnimatePresence>
  );
}

"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Zap, X, Mail, Sparkles } from "lucide-react";
import { maestroApi } from "@/lib/maestro-api";

/**
 * WhisperPostIt — a post-it note overlay that appears on the Today page.
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
 *  - Auto-dismiss after 30 seconds
 */

export function WhisperPostIt({ onDraft }: { onDraft?: (entity: string) => void }) {
  const [whispers, setWhispers] = useState<any[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [dismissed, setDismissed] = useState(false);
  const [loading, setLoading] = useState(true);

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
        // Non-fatal — whispers are a nice-to-have
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, []);

  // Auto-rotate through whispers every 15 seconds
  useEffect(() => {
    if (whispers.length <= 1 || dismissed) return;
    const interval = setInterval(() => {
      setCurrentIndex(prev => (prev + 1) % whispers.length);
    }, 15000);
    return () => clearInterval(interval);
  }, [whispers.length, dismissed]);

  // Auto-dismiss after 45 seconds
  useEffect(() => {
    if (whispers.length === 0 || dismissed) return;
    const timeout = setTimeout(() => setDismissed(true), 45000);
    return () => clearTimeout(timeout);
  }, [whispers.length, dismissed]);

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

          {/* Action buttons */}
          {entity && onDraft && (
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
          )}

          {/* Rotation indicator */}
          {whispers.length > 1 && (
            <div className="flex gap-1 mt-3">
              {whispers.map((_, i) => (
                <div
                  key={i}
                  className={`h-1  transition-all ${
                    i === currentIndex ? "w-6 bg-amber-700" : "w-2 bg-amber-700/30"
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

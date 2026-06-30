/**
 * Keyboard shortcuts + command palette for MaestroAgent.
 *
 * Shortcuts:
 *   ⌘K / Ctrl+K   Open command palette
 *   ⌘N / Ctrl+N   New run (open StartRunModal)
 *   ⌘1-8          Switch views (dashboard, graph, agents, loops, terminal, files, metrics, templates)
 *   ⌘/            Toggle sidebar (future)
 *   ⌘,            Settings (future)
 *   Esc           Close any open modal
 *
 * The command palette is a Cmd+K palette (Linear/Notion-style) that
 * lets power users navigate and act without the mouse.
 */

import { useEffect, useState, useCallback } from "react";
import { useAppStore, ViewId } from "../store/appStore";

const VIEW_KEYS: Record<string, ViewId> = {
  "1": "dashboard",
  "2": "graph",
  "3": "agents",
  "4": "loops",
  "5": "terminal",
  "6": "files",
  "7": "metrics",
  "8": "templates",
};

export interface Command {
  id: string;
  label: string;
  hint?: string;
  action: () => void;
  group?: string;
}

export function useKeyboardShortcuts() {
  const setActiveView = useAppStore((s) => s.setActiveView);
  const openStartRunModal = useAppStore((s) => s.openStartRunModal);
  const closeStartRunModal = useAppStore((s) => s.closeStartRunModal);
  const closeSpawnModal = useAppStore((s) => s.closeSpawnModal);
  const closeDebateModal = useAppStore((s) => s.closeDebateModal);
  const closeCreateLoopModal = useAppStore((s) => s.closeCreateLoopModal);
  const [paletteOpen, setPaletteOpen] = useState(false);

  const openPalette = useCallback(() => setPaletteOpen(true), []);
  const closePalette = useCallback(() => setPaletteOpen(false), []);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;

      // ⌘K / Ctrl+K — command palette
      if (mod && e.key === "k") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
        return;
      }

      // ⌘N / Ctrl+N — new run
      if (mod && e.key === "n") {
        e.preventDefault();
        openStartRunModal();
        return;
      }

      // ⌘1-8 — switch views
      if (mod && VIEW_KEYS[e.key]) {
        e.preventDefault();
        setActiveView(VIEW_KEYS[e.key]);
        return;
      }

      // Esc — close modals + palette
      if (e.key === "Escape") {
        setPaletteOpen(false);
        closeStartRunModal();
        closeSpawnModal();
        closeDebateModal();
        closeCreateLoopModal();
        return;
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [
    setActiveView, openStartRunModal,
    closeStartRunModal, closeSpawnModal, closeDebateModal, closeCreateLoopModal,
  ]);

  const commands: Command[] = [
    { id: "new-run", label: "New Run", hint: "⌘N", group: "Actions", action: () => { openStartRunModal(); closePalette(); } },
    { id: "view-dashboard", label: "Go to Dashboard", hint: "⌘1", group: "Navigate", action: () => { setActiveView("dashboard"); closePalette(); } },
    { id: "view-graph", label: "Go to Graph Builder", hint: "⌘2", group: "Navigate", action: () => { setActiveView("graph"); closePalette(); } },
    { id: "view-agents", label: "Go to Agents", hint: "⌘3", group: "Navigate", action: () => { setActiveView("agents"); closePalette(); } },
    { id: "view-loops", label: "Go to Loops", hint: "⌘4", group: "Navigate", action: () => { setActiveView("loops"); closePalette(); } },
    { id: "view-terminal", label: "Go to Terminal", hint: "⌘5", group: "Navigate", action: () => { setActiveView("terminal"); closePalette(); } },
    { id: "view-files", label: "Go to Files", hint: "⌘6", group: "Navigate", action: () => { setActiveView("files"); closePalette(); } },
    { id: "view-metrics", label: "Go to Metrics", hint: "⌘7", group: "Navigate", action: () => { setActiveView("metrics"); closePalette(); } },
    { id: "view-templates", label: "Go to Templates", hint: "⌘8", group: "Navigate", action: () => { setActiveView("templates"); closePalette(); } },
  ];

  return { paletteOpen, openPalette, closePalette, commands };
}

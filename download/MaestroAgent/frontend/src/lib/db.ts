/**
 * IndexedDB offline cache — persistent client-side storage for the PWA.
 *
 * The service worker caches the app shell (HTML/JS/CSS) for offline
 * rendering. This module caches *data* so the UI can show past runs,
 * templates, and graph drafts even when the backend is unreachable.
 *
 * Tiers:
 * - `runs`       — recent run summaries (last 100)
 * - `events`     — event streams per run (last 1000 each, for replay)
 * - `graphs`     — user-saved graph drafts (exported from GraphBuilder)
 * - `templates`  — cached template list (refreshed when online)
 * - `kv`         — arbitrary key/value (settings, last view, etc.)
 *
 * All operations are async and resilient: if IndexedDB is unavailable
 * (private mode, quota exceeded), we silently no-op and the app still
 * works online-only.
 */

const DB_NAME = "maestroagent";
const DB_VERSION = 1;
const STORES = ["runs", "events", "graphs", "templates", "kv"] as const;
type StoreName = (typeof STORES)[number];

let dbPromise: Promise<IDBDatabase | null> | null = null;

function openDB(): Promise<IDBDatabase | null> {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve) => {
    if (typeof indexedDB === "undefined") {
      resolve(null);
      return;
    }
    try {
      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = () => {
        const db = req.result;
        for (const name of STORES) {
          if (!db.objectStoreNames.contains(name)) {
            const store = db.createObjectStore(name, { keyPath: "id" });
            if (name === "runs" || name === "events") {
              store.createIndex("run_id", "run_id", { unique: false });
              store.createIndex("ts", "ts", { unique: false });
            }
            if (name === "templates") {
              store.createIndex("name", "name", { unique: false });
            }
          }
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => resolve(null);
    } catch {
      resolve(null);
    }
  });
  return dbPromise;
}

async function tx<T>(
  store: StoreName,
  mode: IDBTransactionMode,
  fn: (s: IDBObjectStore) => IDBRequest<T>
): Promise<T | null> {
  const db = await openDB();
  if (!db) return null;
  return new Promise((resolve) => {
    try {
      const t = db.transaction(store, mode);
      const s = t.objectStore(store);
      const req = fn(s);
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => resolve(null);
    } catch {
      resolve(null);
    }
  });
}

// --- Runs ---

export interface CachedRun {
  id: string;
  run_id: string;
  status: string;
  goal: string;
  template: string;
  cost_usd: number;
  iteration: number;
  ts: string;
}

export async function cacheRun(run: CachedRun): Promise<void> {
  await tx("runs", "readwrite", (s) => s.put(run) as IDBRequest<IDBValidKey>);
  // Trim to last 100.
  const all = await listRuns();
  if (all && all.length > 100) {
    for (const old of all.slice(100)) {
      await tx("runs", "readwrite", (s) => s.delete(old.id) as IDBRequest<undefined>);
    }
  }
}

export async function listRuns(): Promise<CachedRun[] | null> {
  const db = await openDB();
  if (!db) return null;
  return new Promise((resolve) => {
    try {
      const t = db.transaction("runs", "readonly");
      const idx = t.objectStore("runs").index("ts");
      const req = idx.getAll();
      req.onsuccess = () => resolve((req.result as CachedRun[]).sort((a, b) => b.ts.localeCompare(a.ts)));
      req.onerror = () => resolve(null);
    } catch {
      resolve(null);
    }
  });
}

export async function getRun(runId: string): Promise<CachedRun | null> {
  const db = await openDB();
  if (!db) return null;
  return new Promise((resolve) => {
    try {
      const t = db.transaction("runs", "readonly");
      const idx = t.objectStore("runs").index("run_id");
      const req = idx.get(runId);
      req.onsuccess = () => resolve(req.result || null);
      req.onerror = () => resolve(null);
    } catch {
      resolve(null);
    }
  });
}

// --- Events ---

export async function cacheEvent(event: {
  id: string;
  run_id: string;
  type: string;
  ts: string;
  payload: Record<string, unknown>;
}): Promise<void> {
  await tx("events", "readwrite", (s) => s.put(event) as IDBRequest<IDBValidKey>);
}

export async function listEvents(runId: string, limit = 500): Promise<unknown[] | null> {
  const db = await openDB();
  if (!db) return null;
  return new Promise((resolve) => {
    try {
      const t = db.transaction("events", "readonly");
      const idx = t.objectStore("events").index("run_id");
      const req = idx.getAll(runId);
      req.onsuccess = () => {
        const results = (req.result as any[]).sort((a, b) => a.ts.localeCompare(b.ts));
        resolve(results.slice(-limit));
      };
      req.onerror = () => resolve(null);
    } catch {
      resolve(null);
    }
  });
}

export async function clearEvents(runId: string): Promise<void> {
  const db = await openDB();
  if (!db) return;
  return new Promise((resolve) => {
    try {
      const t = db.transaction("events", "readwrite");
      const idx = t.objectStore("events").index("run_id");
      const req = idx.openCursor(runId);
      req.onsuccess = () => {
        const cursor = req.result;
        if (cursor) {
          cursor.delete();
          cursor.continue();
        } else {
          resolve();
        }
      };
      req.onerror = () => resolve();
    } catch {
      resolve();
    }
  });
}

// --- Graph drafts (saved from GraphBuilder) ---

export interface SavedGraph {
  id: string;
  name: string;
  description: string;
  nodes: unknown[];
  edges: unknown[];
  created_at: string;
  updated_at: string;
}

export async function saveGraph(graph: SavedGraph): Promise<void> {
  await tx("graphs", "readwrite", (s) => s.put(graph) as IDBRequest<IDBValidKey>);
}

export async function listGraphs(): Promise<SavedGraph[] | null> {
  const all = await tx("graphs", "readonly", (s) => s.getAll() as IDBRequest<SavedGraph[]>);
  return all ? all.sort((a, b) => b.updated_at.localeCompare(a.updated_at)) : null;
}

export async function deleteGraph(id: string): Promise<void> {
  await tx("graphs", "readwrite", (s) => s.delete(id) as IDBRequest<undefined>);
}

// --- Templates cache ---

export async function cacheTemplates(templates: unknown[]): Promise<void> {
  // Clear and re-populate.
  const db = await openDB();
  if (!db) return;
  return new Promise((resolve) => {
    try {
      const t = db.transaction("templates", "readwrite");
      const s = t.objectStore("templates");
      s.clear();
      for (const tpl of templates) {
        s.put({ id: (tpl as any).name, ...(tpl as object) });
      }
      t.oncomplete = () => resolve();
      t.onerror = () => resolve();
    } catch {
      resolve();
    }
  });
}

export async function listCachedTemplates(): Promise<unknown[] | null> {
  const all = await tx("templates", "readonly", (s) => s.getAll() as IDBRequest<unknown[]>);
  return all;
}

// --- KV (settings, last view, etc.) ---

export async function kvGet<T>(key: string): Promise<T | null> {
  const result = await tx<{ value: T } | undefined>("kv", "readonly", (s) => s.get(key) as IDBRequest<{ value: T } | undefined>);
  return result?.value ?? null;
}

export async function kvSet<T>(key: string, value: T): Promise<void> {
  await tx("kv", "readwrite", (s) => s.put({ id: key, value }) as IDBRequest<IDBValidKey>);
}

export async function kvDelete(key: string): Promise<void> {
  await tx("kv", "readwrite", (s) => s.delete(key) as IDBRequest<undefined>);
}

// --- Maintenance ---

export async function clearAll(): Promise<void> {
  const db = await openDB();
  if (!db) return;
  return new Promise((resolve) => {
    try {
      const t = db.transaction(STORES as unknown as string[], "readwrite");
      for (const name of STORES) {
        t.objectStore(name).clear();
      }
      t.oncomplete = () => resolve();
      t.onerror = () => resolve();
    } catch {
      resolve();
    }
  });
}

export async function getStorageEstimate(): Promise<{ usage: number; quota: number } | null> {
  if (typeof navigator === "undefined" || !navigator.storage?.estimate) return null;
  const est = await navigator.storage.estimate();
  return { usage: est.usage || 0, quota: est.quota || 0 };
}

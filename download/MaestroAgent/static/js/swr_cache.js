// SWR CACHE — Stale-While-Revalidate with retry, offline, cancellation
// ═══════════════════════════════════════════════════════════════════════════

const SWR = {
  // Cache: key → { data, timestamp, promise, abort, error, url }
  _cache: new Map(),
  _subscribers: new Map(),
  _online: navigator.onLine,
  DEDUP_MS: 2000,
  STALE_MS: 30000,
  MAX_RETRIES: 3,
  RETRY_DELAYS: [1000, 2000, 4000],

  init() {
    window.addEventListener('online', () => {
      this._online = true;
      this.revalidateAll();
      hideOfflineBanner();
    });
    window.addEventListener('offline', () => {
      this._online = false;
      showOfflineBanner();
    });
  },

  on(key, callback) {
    if (!this._subscribers.has(key)) this._subscribers.set(key, new Set());
    this._subscribers.get(key).add(callback);
    const entry = this._cache.get(key);
    if (entry) {
      callback({ data: entry.data, error: entry.error, loading: false, fromCache: true });
    }
    return () => this._subscribers.get(key)?.delete(callback);
  },

  _notify(key, state) {
    const subs = this._subscribers.get(key);
    if (subs) subs.forEach(cb => { try { cb(state); } catch (e) { console.warn(e); } });
  },

  async fetch(key, url, options = {}) {
    const now = Date.now();
    const entry = this._cache.get(key);

    // Dedup: if a fetch is in-flight, return its promise
    if (entry?.promise && now - entry.timestamp < this.DEDUP_MS) {
      return entry.promise;
    }

    // Cancel any previous in-flight request for this key
    if (entry?.abort) {
      try { entry.abort.abort(); } catch (e) {}
    }

    const abort = new AbortController();
    const fetchPromise = this._doFetch(key, url, { ...options, signal: abort.signal });

    this._cache.set(key, {
      data: entry?.data,
      timestamp: now,
      promise: fetchPromise,
      abort,
      error: null,
      url,
    });

    // If we have stale data, notify immediately (stale-while-revalidate)
    if (entry?.data) {
      this._notify(key, { data: entry.data, error: null, loading: true, fromCache: true });
    } else {
      this._notify(key, { data: null, error: null, loading: true, fromCache: false });
    }

    return fetchPromise;
  },

  async _doFetch(key, url, options, retryCount = 0) {
    try {
      const resp = await fetch(MAESTRO_API + url, options);
      if (!resp.ok) {
        const err = new Error(`HTTP ${resp.status}: ${resp.statusText}`);
        err.status = resp.status;
        throw err;
      }
      const data = await resp.json();
      const entry = this._cache.get(key);
      this._cache.set(key, {
        ...entry,
        data,
        timestamp: Date.now(),
        promise: null,
        abort: null,
        error: null,
        url,
      });
      this._notify(key, { data, error: null, loading: false, fromCache: false });
      return data;
    } catch (err) {
      if (err.name === 'AbortError') {
        return null;
      }

      // Retry with exponential backoff — but NOT for definitive client errors.
      // 4xx (except 408 Request Timeout, 429 Too Many Requests) won't change
      // on retry. Retrying 404s caused 6 wasteful failed requests in the
      // console for /api/oem/time-axis (intentional 404 = insufficient data).
      const isDefinitiveClientError =
        err.status && err.status >= 400 && err.status < 500 &&
        err.status !== 408 && err.status !== 429;
      if (!isDefinitiveClientError && retryCount < this.MAX_RETRIES && this._online) {
        const delay = this.RETRY_DELAYS[retryCount] || 4000;
        await new Promise(r => setTimeout(r, delay));
        return this._doFetch(key, url, options, retryCount + 1);
      }

      // Final failure — serve cached data if available, else error
      const entry = this._cache.get(key);
      const cachedData = entry?.data;
      this._cache.set(key, {
        ...entry,
        promise: null,
        abort: null,
        error: err,
      });
      if (cachedData) {
        this._notify(key, { data: cachedData, error: err, loading: false, fromCache: true, offline: !this._online });
        return cachedData;
      } else {
        this._notify(key, { data: null, error: err, loading: false, fromCache: false });
        throw err;
      }
    }
  },

  mutate(key, updater) {
    const entry = this._cache.get(key);
    if (!entry) return;
    const newData = typeof updater === 'function' ? updater(entry.data) : updater;
    this._cache.set(key, { ...entry, data: newData });
    this._notify(key, { data: newData, error: null, loading: false, fromCache: true, optimistic: true });
  },

  invalidate(key) {
    const entry = this._cache.get(key);
    if (!entry?.url) return;
    this.fetch(key, entry.url);
  },

  invalidatePrefix(prefix) {
    for (const [key, entry] of this._cache.entries()) {
      if (key.startsWith(prefix) && entry?.url) {
        this.fetch(key, entry.url);
      }
    }
  },

  revalidateAll() {
    for (const [key, entry] of this._cache.entries()) {
      if (entry?.url && !entry.promise) {
        this.fetch(key, entry.url);
      }
    }
  },

  get(key) {
    return this._cache.get(key)?.data;
  },
};

SWR.init();

// ═══════════════════════════════════════════════════════════════════════════
// API HELPERS — typed wrappers around SWR.fetch
// ═══════════════════════════════════════════════════════════════════════════

const api = {
  getOEM: (path) => SWR.fetch('oem:' + path, '/api/oem' + path),
  postOEM: async (path, body) => {
    // Round 67 Phase 3.3: POST must NOT use SWR cache.
    // Mutations served as stale GET data is a real hazard.
    const resp = await fetch('/api/oem' + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await resp.json();
    if (resp.ok) {
      SWR.invalidatePrefix('oem:');  // bust cache after mutation
    }
    return data;
  },
  getPersonal: (path) => fetch('/api/personal' + path).then(r => r.json()),
  postPersonal: (path, body) =>
    fetch('/api/personal' + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then(r => r.json()),
  getImports: () => SWR.fetch('imports:list', '/api/imports'),
  getOAuthStatus: () => SWR.fetch('oauth:status', '/api/oauth/status'),
};

// ═══════════════════════════════════════════════════════════════════════════
// ERROR BOUNDARY — global error toast + offline banner
// ═══════════════════════════════════════════════════════════════════════════

function showError(message, duration = 5000) {
  let toast = document.getElementById('error-toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'error-toast';
    toast.className = 'fixed top-4 right-4 bg-brand-rose/20 border border-brand-rose/40 text-brand-rose px-4 py-3 rounded-lg shadow-2xl text-sm z-50 max-w-md';
    document.body.appendChild(toast);
  }
  toast.innerHTML = `<div class="flex items-start gap-2">
    <span class="text-brand-rose font-bold">!</span>
    <div class="flex-1">${escapeHtml(message)}</div>
    <button onclick="this.parentElement.parentElement.remove()" class="text-brand-rose/60 hover:text-brand-rose">x</button>
  </div>`;
  toast.style.display = 'block';
  clearTimeout(toast._timeout);
  toast._timeout = setTimeout(() => { toast.style.display = 'none'; }, duration);
}

function showOfflineBanner() {
  let banner = document.getElementById('offline-banner');
  if (!banner) {
    banner = document.createElement('div');
    banner.id = 'offline-banner';
    banner.className = 'fixed top-0 left-0 right-0 bg-brand-amber/20 border-b border-brand-amber/40 text-brand-amber text-center py-1.5 text-xs z-50';
    banner.innerHTML = 'Offline — showing cached data. Changes may not persist.';
    document.body.appendChild(banner);
  }
  banner.style.display = 'block';
}

function hideOfflineBanner() {
  const banner = document.getElementById('offline-banner');
  if (banner) banner.style.display = 'none';
}

// ═══════════════════════════════════════════════════════════════════════════
// RENDER HELPERS
// ═══════════════════════════════════════════════════════════════════════════

function escapeHtml(s) {
  if (s == null) return '';
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

// escapeJs — escape a string for safe interpolation into a JS string literal
// inside an inline onclick="..." handler.
//
// The auditor found that escapeHtml() is insufficient for this context:
// the browser decodes HTML entities (like &#39;) BEFORE passing the string
// to the JS engine, so a single quote in the data decodes back to ' and
// breaks out of the JS string literal. This is an XSS vector when the
// data comes from attacker-influenceable sources (signal titles, customer
// names, etc.).
//
// escapeJs() escapes for JS string context: replaces ' with \\', " with \\",
// \ with \\\\, and strips newlines. Used in onclick="fn('${escapeJs(x)}')"
// patterns. For HTML content (not inside JS strings), escapeHtml() is correct.
function escapeJs(s) {
  if (s == null) return '';
  return String(s)
    .replace(/\\/g, '\\\\')
    .replace(/'/g, "\\'")
    .replace(/"/g, '\\"')
    .replace(/\n/g, '\\n')
    .replace(/\r/g, '\\r');
}

// ═══════════════════════════════════════════════════════════════════════════
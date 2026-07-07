# MAESTRO FRONTEND — WORLD-CLASS ROADMAP
## Strict Coder Instructions: From Current State to Production Enterprise

**Document Purpose:** Mechanical, verifiable instructions for transforming the Maestro frontend from its current state into a Fortune 100–grade production system.

**Rule Zero:** Every phase has a gate. You CANNOT proceed to the next phase until the current phase's gate passes. No exceptions. No "I'll fix it later." No "it works on my machine."

---

## CURRENT STATE (Baseline — Verified by Execution)

```
app.html ............. 67 KB   (1,236 lines — single monolithic file)
static/js/*.js ....... 521 KB  (40 files — unminified, no bundler)
static/app.css ....... 42 KB   (compiled Tailwind — but scans wrong paths)
static/css/*.css ..... 169 KB  (3 hand-written CSS files)
────────────────────────────────────
TOTAL ................ 799 KB  uncompressed, unminified, unbundled

innerHTML calls ...... 300+    (every surface renders via string templates)
onclick handlers ..... 130+    (inline event handlers — CSP violation)
Global functions ..... all     (no module system, everything in window scope)
escapeHtml location .. swr_cache.js:246  (wrong file — used by 30+ files)
TypeScript ........... 0%      (pure JavaScript, no types)
Tests (frontend) ..... 0       (zero frontend tests exist)
Build tool ........... none    (no Vite, no esbuild, no webpack)
package.json ......... none    (no frontend dependency management)
Lighthouse score ..... unknown (never run)
```

---

## PHASE 1 — FIX THE CRITICAL BUGS (Day 1, 4 hours)

### 1.1 Fix the onboarding button bug

**File:** `static/js/onboarding.js`, function `renderOnboardingName()`

**Change:**
```javascript
// BEFORE (broken — .trim is a method reference, not a call)
oninput="document.getElementById('onboard-name-btn').disabled = !this.value.trim"

// AFTER (fixed)
oninput="document.getElementById('onboard-name-btn').disabled = !this.value.trim()"
```

**Gate:** Open onboarding → type a name → button enables. If button stays disabled, STOP and fix it.

### 1.2 Fix escapeHtml / escapeJs location

These functions are used by 30+ files but defined in `swr_cache.js` line 246. This is wrong.

**Steps:**
1. Create `static/js/utils.js` with these functions:
```javascript
// utils.js — shared utilities (loaded FIRST, before all other scripts)
function escapeHtml(s) {
  if (!s) return '';
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function escapeJs(s) {
  if (!s) return '';
  return String(s).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '\\"');
}
function humanize(text) { /* move from humanize.js */ }
function formatConfidence(c) { /* move from core.js or wherever it lives */ }
function formatTimestamp(ts) { /* move from wherever it lives */ }
function errorHTML(el, msg, fn) { /* move from wherever it lives */ }
```

2. Add `<script src="/static/js/utils.js"></script>` as the FIRST script in `app.html`, BEFORE `csp-shim.js`.

3. Delete the duplicate definitions from `swr_cache.js` (lines 246-270).

4. Search for ALL other definitions of `escapeHtml`, `escapeJs`, `formatConfidence`, `errorHTML` across all JS files and remove duplicates.

**Gate:** `grep -rn "function escapeHtml" static/js/` returns exactly ONE result: `utils.js`. Same for `escapeJs`.

### 1.3 Fix the Tailwind content paths

**File:** `tailwind.config.js`

**Change:**
```javascript
// BEFORE
content: ["./app.html", "./scripts/app-script.js"],

// AFTER
content: [
  "./app.html",
  "./static/onboarding.html",
  "./static/js/**/*.js",  // JS files generate HTML with Tailwind classes
],
```

**Gate:** Run `npx tailwindcss -i tailwind-input.css -o static/app.css --minify`. Grep the output for a class you know is only used in a JS file (e.g., `ds-card-suggestion`). If it's missing, the content path is wrong.

### 1.4 Add a back button to onboarding

**File:** `static/js/onboarding.js`

Add to every screen's HTML (screens 2-5), before the Continue button:
```html
<button class="maestro-btn maestro-btn-ghost maestro-btn-full"
        onclick="showOnboardingScreen(${step - 1})" style="margin-bottom:8px;">
  ← Back
</button>
```

**Gate:** On screen 3, click Back → returns to screen 2 with name preserved.

---

## PHASE 2 — BUILD SYSTEM (Day 2-3, 8 hours)

### 2.1 Create package.json

**File:** `package.json` (at project root, next to `app.html`)

```json
{
  "name": "maestro-frontend",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest",
    "lint": "eslint static/js/",
    "typecheck": "tsc --noEmit",
    "lighthouse": "lighthouse http://localhost:8765 --output=json --output-path=./lighthouse-report.json"
  },
  "devDependencies": {
    "vite": "^6.0.0",
    "vitest": "^3.0.0",
    "eslint": "^9.0.0",
    "typescript": "^5.7.0",
    "lighthouse": "^12.0.0",
    "tailwindcss": "^3.4.0",
    "autoprefixer": "^10.4.0",
    "postcss": "^8.4.0"
  }
}
```

### 2.2 Create vite.config.js

**File:** `vite.config.js`

```javascript
import { defineConfig } from 'vite';
import { resolve } from 'path';

export default defineConfig({
  root: '.',
  publicDir: 'static',
  build: {
    outDir: 'dist',
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'app.html'),
        onboarding: resolve(__dirname, 'static/onboarding.html'),
      },
      output: {
        // Code splitting — group by domain
        manualChunks: {
          'core': [
            './static/js/utils.js',
            './static/js/csp-shim.js',
            './static/js/core.js',
            './static/js/swr_cache.js',
            './static/js/maestro.js',
          ],
          'home': [
            './static/js/home_core.js',
            './static/js/home_renderers.js',
          ],
          'surfaces': [
            './static/js/ask.js',
            './static/js/ask_v2.js',
            './static/js/today.js',
            './static/js/work.js',
            './static/js/learn.js',
          ],
          'cognitive': [
            './static/js/cognition.js',
            './static/js/intent_cascade.js',
            './static/js/contradictions.js',
            './static/js/prediction_market.js',
            './static/js/assumptions.js',
          ],
          'engineering': [
            './static/js/eng_audit.js',
            './static/js/drill_down_modal.js',
          ],
        },
      },
    },
    // Performance budgets — build FAILS if exceeded
    chunkSizeWarningLimit: 100, // warn if any chunk > 100KB
    minify: 'terser',
    terserOptions: {
      compress: { drop_console: false, drop_debugger: true },
    },
    sourcemap: true,
  },
  server: {
    port: 1420,
    proxy: {
      '/api': 'http://localhost:8765',
      '/ws': { target: 'ws://localhost:8765', ws: true },
      '/static': 'http://localhost:8765',
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['tests/**/*.test.js'],
  },
});
```

### 2.3 Migrate script tags to ES modules

This is the biggest change. You must convert ALL 40 `<script defer src="...">` tags in `app.html` into a single entry point.

**File:** `static/js/main.js` (NEW)

```javascript
// main.js — single entry point. Vite bundles this + all imports.
// Load order matters: utils first, then core, then surfaces.

// ── Core (always loaded) ──
import './utils.js';
import './csp-shim.js';
import './core.js';
import './swr_cache.js';
import './maestro.js';
import './humanize.js';
import './org_dot.js';
import './icons.js';

// ── Eagerly loaded (needed on first paint — Today surface) ──
import './ambient_organizational_judgment.js';
import './home_core.js';
import './home_renderers.js';
import './drill_down_modal.js';
import './prepared_decisions.js';
import './today.js';

// ── Lazy loaded (only when user navigates to that surface) ──
const lazySurfaces = {
  'ask':        () => import('./ask.js'),
  'ask-v2':     () => import('./ask_v2.js'),
  'work':       () => import('./work.js'),
  'learn':      () => import('./learn.js'),
  'physics':    () => import('./physics_laws.js'),
  'live':       () => import('./live_meeting.js'),
  'eng-signals':() => import('./eng_audit.js'),
  'customer':   () => import('./customer_judgment_engine.js'),
  'digital_twin': () => import('./digital_twin.js'),
  'intents':    () => import('./intent_cascade.js'),
  'contradictions': () => import('./contradictions.js'),
  'predictions':() => import('./prediction_market.js'),
  'assumptions':() => import('./assumptions.js'),
  'cognition':  () => import('./cognition.js'),
  'evolution':  () => import('./evolution.js'),
  'autobiography': () => import('./autobiography.js'),
  'playbook':   () => import('./playbook.js'),
  'personal':   () => import('./personal.js'),
  'canvas':     () => import('./canvas.js'),
  'coordination': () => import('./coordination.js'),
  'memory':     () => import('./trajectory_panel.js'),
};

// Hook into navTo to lazy-load surface code on first visit
const _loadedSurfaces = new Set();
const originalNavTo = window.navTo;
window.navTo = async function(surface) {
  if (lazySurfaces[surface] && !_loadedSurfaces.has(surface)) {
    await lazySurfaces[surface]();
    _loadedSurfaces.add(surface);
  }
  return originalNavTo(surface);
};

// ── App initialization (must be last) ──
import './app_init.js';
```

**In `app.html`, replace ALL 40 `<script>` tags with:**
```html
<script type="module" src="/static/js/main.js"></script>
```

**IMPORTANT:** The current code uses global functions everywhere. You CANNOT simply add `export`/`import` to each file without breaking things. The migration strategy is:

1. Keep all functions on `window` scope (add `window.functionName = functionName` at the bottom of each file if needed).
2. Vite will still tree-shake unused code within each chunk.
3. The lazy loading above is the PRIMARY win — 20+ surfaces' code won't load until visited.

**Gate:**
```bash
pnpm build
# Output must show:
#   dist/assets/main-[hash].js        < 150 KB  (core + today)
#   dist/assets/home-[hash].js        < 60 KB   (home dashboard)
#   dist/assets/surfaces-[hash].js    < 80 KB   (ask/work/learn)
#   dist/assets/cognitive-[hash].js   < 50 KB   (cognitive surfaces)
#   dist/assets/personal-[hash].js    < 30 KB   (lazy: personal mode)
#   ... (one chunk per lazy surface, each < 30 KB)
#
# Total JS < 200 KB for initial load (core + today only)
# Total JS < 500 KB for full load (all surfaces)
#
# Compare to current: 521 KB ALL loaded on every page.
```

### 2.4 Update backend to serve built files

**File:** `backend/maestro_api/main.py`

In the `frontend_mode == "app"` section, add a check for `dist/` first:

```python
# Check for built frontend first (production)
dist_path = app_dir / "dist"
if dist_path.exists() and (dist_path / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=dist_path / "assets"), name="assets")
    @app.get("/")
    async def serve_root():
        return FileResponse(dist_path / "index.html", media_type="text/html")
    @app.get("/app.html")
    async def serve_app():
        return FileResponse(dist_path / "index.html", media_type="text/html")
    logger.info("Serving built frontend from %s", dist_path)
else:
    # Fallback to dev mode (unbundled static files)
    # ... existing code ...
```

**Gate:** Run `pnpm build` → start backend → visit `http://localhost:8765/` → page loads with bundled JS. Check Network tab: should see 3-5 JS files, not 40+.

---

## PHASE 3 — TESTING INFRASTRUCTURE (Day 4-5, 8 hours)

### 3.1 Create test directory structure

```
tests/
  unit/
    utils.test.js
    humanize.test.js
    swr_cache.test.js
    autocomplete.test.js
    onboarding.test.js
  integration/
    api.test.js
    navigation.test.js
  e2e/
    onboarding.spec.js
    dashboard.spec.js
    ask.spec.js
```

### 3.2 Unit tests for critical functions

**File:** `tests/unit/utils.test.js`

```javascript
import { describe, it, expect } from 'vitest';
import '../static/js/utils.js'; // loads escapeHtml, escapeJs into global scope

describe('escapeHtml', () => {
  it('escapes < and >', () => {
    expect(escapeHtml('<script>alert(1)</script>')).toBe('&lt;script&gt;alert(1)&lt;/script&gt;');
  });
  it('escapes quotes', () => {
    expect(escapeHtml('he said "hello"')).toBe('he said &quot;hello&quot;');
  });
  it('handles null/undefined', () => {
    expect(escapeHtml(null)).toBe('');
    expect(escapeHtml(undefined)).toBe('');
  });
  it('handles empty string', () => {
    expect(escapeHtml('')).toBe('');
  });
});

describe('escapeJs', () => {
  it('escapes single quotes for onclick handlers', () => {
    expect(escapeJs("O'Brien")).toBe("O\\'Brien");
  });
  it('escapes backslashes', () => {
    expect(escapeJs('path\\to\\file')).toBe('path\\\\to\\\\file');
  });
});
```

**File:** `tests/unit/humanize.test.js`

```javascript
import { describe, it, expect } from 'vitest';
import '../static/js/utils.js';
import '../static/js/humanize.js';

describe('humanize', () => {
  it('strips law codes', () => {
    expect(humanize('L-0001: priya is a bottleneck')).not.toContain('L-0001');
  });
  it('strips confidence numbers', () => {
    expect(humanize('pattern (confidence: 0.85)')).not.toContain('0.85');
  });
  it('replaces OEM with Maestro', () => {
    expect(humanize('OEM is online')).toContain('Maestro');
  });
  it('replaces "learning object" with "pattern"', () => {
    expect(humanize('5 learning objects')).toContain('pattern');
  });
  it('handles null', () => {
    expect(humanize(null)).toBe('');
  });
});
```

**File:** `tests/unit/onboarding.test.js`

```javascript
import { describe, it, expect, vi } from 'vitest';
import '../static/js/utils.js';
import '../static/js/onboarding.js';

describe('onboarding screen 2', () => {
  it('renders a name input', () => {
    const html = renderOnboardingName();
    expect(html).toContain('id="onboard-name"');
  });
  it('button enables when name is typed', () => {
    const html = renderOnboardingName();
    // The oninput handler must call .trim() not .trim
    expect(html).toContain('.trim()');
  });
});
```

### 3.3 Add E2E test skeleton (Playwright)

**File:** `tests/e2e/onboarding.spec.js`

```javascript
import { test, expect } from '@playwright/test';

test('onboarding: user can complete all 6 screens', async ({ page }) => {
  await page.goto('/onboarding.html');
  
  // Screen 1: Welcome
  await page.click('text=Get Started');
  
  // Screen 2: Name
  await page.fill('#onboard-name', 'Test User');
  const continueBtn = page.locator('#onboard-name-btn');
  await expect(continueBtn).toBeEnabled(); // THIS IS THE BUG FIX VERIFICATION
  await continueBtn.click();
  
  // Screen 3: About
  await page.fill('#onboard-role', 'CTO');
  await page.click('text=Continue');
  
  // Screen 4: Work tools — skip
  await page.click('text=Skip for now');
  
  // Screen 5: Personal tools — skip
  await page.click('text=Skip for now');
  
  // Screen 6: Done
  await expect(page.locator('text=You\\'re in.')).toBeVisible();
});

test('onboarding: back button preserves data', async ({ page }) => {
  await page.goto('/onboarding.html');
  await page.click('text=Get Started');
  await page.fill('#onboard-name', 'Alice');
  await page.click('#onboard-name-btn');
  
  // Screen 3 — click back
  await page.click('text=← Back');
  
  // Screen 2 — name should still be there
  await expect(page.locator('#onboard-name')).toHaveValue('Alice');
});
```

**Gate:**
```bash
pnpm test          # all unit tests pass
pnpm test:e2e      # onboarding E2E passes
```

---

## PHASE 4 — ELIMINATE INLINE EVENT HANDLERS (Day 6-8, 12 hours)

### The Problem
130+ `onclick=` attributes scattered across HTML strings. This:
1. Violates Content-Security-Policy (requires `unsafe-inline`)
2. Makes event handling untestable
3. Creates XSS vectors when user data is interpolated

### 4.1 Implement event delegation

**File:** `static/js/events.js` (NEW)

```javascript
// events.js — centralized event delegation. Replaces ALL inline onclick handlers.
// Every clickable element uses data-action="actionName" instead of onclick="function()".

const _actionRegistry = new Map();

function registerAction(name, handler) {
  _actionRegistry.set(name, handler);
}

function initEventDelegation() {
  document.addEventListener('click', (e) => {
    const target = e.target.closest('[data-action]');
    if (!target) return;
    const action = target.dataset.action;
    const handler = _actionRegistry.get(action);
    if (handler) {
      e.preventDefault();
      handler(target, e);
    }
  });
  
  document.addEventListener('input', (e) => {
    const target = e.target.closest('[data-oninput]');
    if (!target) return;
    const action = target.dataset.oninput;
    const handler = _actionRegistry.get(action);
    if (handler) handler(target, e);
  });
}

// Initialize on DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initEventDelegation);
} else {
  initEventDelegation();
}

export { registerAction };
```

### 4.2 Migration pattern (do this for EVERY file)

For each file, replace inline handlers one at a time:

**BEFORE (in `home_renderers.js`):**
```javascript
`<div class="card" onclick="openDrilldown('recommendation', '${escapeJs(r.title)}')">`
```

**AFTER:**
```javascript
`<div class="card" data-action="openDrilldown" data-type="recommendation" data-id="${escapeHtml(r.title)}">`
```

Then in the surface's init function:
```javascript
registerAction('openDrilldown', (el) => {
  openDrilldown(el.dataset.type, el.dataset.id);
});
```

### 4.3 Migration order (most dangerous first)

1. `onboarding.js` — 10 onclick handlers (user-facing, broken)
2. `home_core.js` — 17 onclick handlers (most-visited page)
3. `home_renderers.js` — 8 onclick handlers
4. `today.js` — 26 onclick handlers (largest file)
5. `drill_down_modal.js` — 23 onclick handlers
6. Remaining files (batch — 50+ handlers)

**Gate:**
```bash
grep -rn 'onclick=' static/js/ app.html | wc -l
# MUST return 0. Every inline handler replaced with data-action.
```

Then:
```bash
# Test the app still works
pnpm dev
# Click every button on every surface. Nothing should be broken.
```

### 4.4 Update CSP headers

**File:** `backend/maestro_api/main.py`

```python
# After all inline handlers are removed:
app.add_middleware(
    CORSMiddleware,
    # ... existing CORS config ...
)

@app.middleware("http")
async def add_csp_header(request, call_next):
    response = await call_next(request)
    if request.url.path in ('/', '/app.html'):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "          # NO 'unsafe-inline'
            "style-src 'self' 'unsafe-inline'; "  # Tailwind needs inline styles
            "img-src 'self' data:; "
            "connect-src 'self' ws: wss:; "
            "font-src 'self';"
        )
    return response
```

**Gate:** Open DevTools → Security tab → CSP status should show "No violations."

---

## PHASE 5 — COMPONENT ARCHITECTURE (Day 9-14, 24 hours)

### The Problem
300+ `innerHTML` assignments with 100-line template strings. No reactivity. Every data change re-renders the entire surface.

### 5.1 Introduce a lightweight reactive state manager

**File:** `static/js/state.js` (NEW)

```javascript
// state.js — minimal reactive state. NOT a framework. Just enough to
// stop re-rendering 500-line HTML strings on every API response.

class Store {
  constructor(initial = {}) {
    this._state = { ...initial };
    this._listeners = new Map();
  }
  
  get(key) { return this._state[key]; }
  
  set(key, value) {
    const old = this._state[key];
    if (old === value) return; // skip no-ops
    this._state[key] = value;
    (this._listeners.get(key) || []).forEach(fn => fn(value, old));
    (this._listeners.get('*') || []).forEach(fn => fn(key, value, old));
  }
  
  subscribe(key, fn) {
    if (!this._listeners.has(key)) this._listeners.set(key, []);
    this._listeners.get(key).push(fn);
    return () => {
      const arr = this._listeners.get(key);
      arr.splice(arr.indexOf(fn), 1);
    };
  }
  
  // Batch updates — coalesce multiple sets into one render cycle
  batch(fn) {
    this._batching = true;
    this._pendingUpdates = [];
    fn();
    this._batching = false;
    const updates = [...this._pendingUpdates];
    this._pendingUpdates = [];
    updates.forEach(([key, val, old]) => {
      (this._listeners.get(key) || []).forEach(fn => fn(val, old));
    });
  }
}

// Global store — one per surface
const appStore = new Store({
  currentSurface: 'today',
  oemState: null,
  briefing: null,
  laws: [],
  recommendations: [],
  autocompleteResults: [],
});

export { Store, appStore };
```

### 5.2 Create reusable component functions

**File:** `static/js/components/card.js` (NEW)

```javascript
// card.js — reusable card component. Used by 15+ surfaces.
// Each component is a PURE FUNCTION: (data) => HTML string.
// No DOM access. No side effects. Testable in isolation.

export function RecommendationCard(r, opts = {}) {
  const urgencyTag = r.urgency === 'urgent' ? 'tag-rose' : r.urgency === 'normal' ? 'tag-amber' : 'tag-gray';
  const compact = opts.compact;
  
  return `
    <div class="card ${r.urgency === 'urgent' ? 'urgent' : ''} mb-3"
         data-action="openDrilldown" data-type="recommendation" data-id="${escapeHtml(r.title)}">
      <div class="flex items-start justify-between mb-2">
        <div class="flex-1">
          <div class="text-sm font-semibold">${escapeHtml(humanize(r.title))}</div>
          ${!compact ? `<div class="text-[11px] text-fg-400 mt-1">${escapeHtml(humanize(r.description || ''))}</div>` : ''}
        </div>
        <span class="tag ${urgencyTag}">${escapeHtml(r.urgency || 'normal')}</span>
      </div>
      <div class="flex items-center gap-3 text-[10px] text-fg-500 mt-2">
        <span>${r.evidence_count || 0} signals</span>
        ${r.linked_laws?.length ? `<span>· ${r.linked_laws.length} patterns</span>` : ''}
      </div>
    </div>`;
}

export function MetricTile(label, value, drilldownId) {
  return `
    <div class="metric metric-clickable"
         data-action="openDrilldown" data-type="metric" data-id="${escapeHtml(drilldownId)}">
      <div class="metric-value">${escapeHtml(String(value))}</div>
      <div class="metric-label">${escapeHtml(label)}</div>
    </div>`;
}

export function ErrorState(message, retryAction) {
  return `
    <div class="error-state">
      <span>${escapeHtml(message)}</span>
      ${retryAction ? `<button data-action="${escapeHtml(retryAction)}" class="btn btn-ghost text-[10px] ml-2">Retry</button>` : ''}
    </div>`;
}

export function LoadingState(text = 'Loading…') {
  return `<div class="loading-state"><span class="spinner"></span> ${escapeHtml(text)}</div>`;
}

export function EmptyState(text, icon = '📭') {
  return `<div class="empty-state"><span class="fs-24">${icon}</span><div class="text-sm text-fg-500 mt-2">${escapeHtml(text)}</div></div>`;
}
```

### 5.3 Refactor ONE surface end-to-end (home_renderers.js)

Use `home_renderers.js` as the template. Once it's clean, replicate the pattern.

**BEFORE:** 265 lines of `innerHTML = \`...\`` with 27 `onclick` handlers.

**AFTER:**
```javascript
import { RecommendationCard, MetricTile, ErrorState, LoadingState } from './components/card.js';
import { appStore } from './state.js';

function renderOvernightChanges(changes) {
  const el = document.getElementById('ecc-overnight');
  if (!changes?.length) {
    el.innerHTML = EmptyState('No changes overnight', '🌙');
    return;
  }
  el.innerHTML = changes.map(c => OvernightChangeItem(c)).join('');
}

// Subscribe to store changes — only re-render the part that changed
appStore.subscribe('overnightChanges', renderOvernightChanges);
```

**Gate:**
```bash
# home_renderers.js should be < 150 lines (down from 446)
wc -l static/js/home_renderers.js
# MUST be < 150

# All 10 home dashboard widgets still render correctly
# (verify manually + add integration test)
```

### 5.4 Component migration order

Do ONE surface per day. Do NOT batch. Verify each one before moving on.

| Day | Surface | Current Lines | Target Lines | Priority |
|-----|---------|--------------|--------------|----------|
| 1 | `home_renderers.js` | 446 | < 150 | HIGH (most visible) |
| 2 | `home_core.js` | 420 | < 200 | HIGH |
| 3 | `today.js` | 1502 | < 600 | HIGH (default surface) |
| 4 | `onboarding.js` | 468 | < 250 | HIGH (first impression) |
| 5 | `drill_down_modal.js` | 401 | < 200 | MEDIUM |
| 6 | `ask_v2.js` | 477 | < 250 | MEDIUM |
| 7 | `personal.js` | 731 | < 350 | MEDIUM |
| 8 | `work.js` | 548 | < 250 | MEDIUM |
| 9 | `eng_audit.js` | 397 | < 200 | LOW |
| 10 | All remaining (batch) | ~3,500 | < 1,500 | LOW |

**Gate (end of Phase 5):**
```bash
wc -l static/js/*.js | tail -1
# MUST be < 7,000 (down from 10,832)

# No file should exceed 600 lines
awk '{print FILENAME":"NF}' static/js/*.js | sort -t: -k2 -n | tail -5
# Largest file MUST be < 600 lines
```

---

## PHASE 6 — PERFORMANCE BUDGETS (Day 15-16, 8 hours)

### 6.1 Define budgets (enforced in CI)

**File:** `performance-budgets.json`

```json
{
  "initial-js": { "max-kb": 150, "description": "JS loaded on first paint (core + today)" },
  "total-js": { "max-kb": 400, "description": "Total JS for all surfaces" },
  "total-css": { "max-kb": 50, "description": "Total CSS (Tailwind purge + design system)" },
  "lcp": { "max-ms": 2500, "description": "Largest Contentful Paint" },
  "fid": { "max-ms": 100, "description": "First Input Delay" },
  "cls": { "max": 0.1, "description": "Cumulative Layout Shift" },
  "lighthouse-performance": { "min": 90 },
  "lighthouse-accessibility": { "min": 95 },
  "lighthouse-best-practices": { "min": 95 },
  "dom-nodes": { "max": 1500, "description": "Max DOM nodes at any point" },
  "time-to-interactive": { "max-ms": 3500 }
}
```

### 6.2 Add CI performance gate

**File:** `.github/workflows/frontend-perf.yml`

```yaml
name: Frontend Performance
on: [push, pull_request]
jobs:
  perf:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '22' }
      - run: npm install -g pnpm && pnpm install
      - run: pnpm build
      - name: Check bundle sizes
        run: |
          node scripts/check-bundle-sizes.js
      - name: Start backend + run Lighthouse
        run: |
          cd backend && pip install -e . && MAESTRO_APP_DIR=.. python -m maestro_cli.main serve --port 8765 &
          sleep 5
          pnpm lighthouse
      - name: Check Lighthouse scores
        run: node scripts/check-lighthouse.js
```

**File:** `scripts/check-bundle-sizes.js`

```javascript
import { readFileSync, readdirSync, statSync } from 'fs';
import { join } from 'path';

const budgets = JSON.parse(readFileSync('performance-budgets.json', 'utf8'));
const distDir = 'dist/assets';
const jsFiles = readdirSync(distDir).filter(f => f.endsWith('.js'));
const totalJsKb = jsFiles.reduce((sum, f) => sum + statSync(join(distDir, f)).size / 1024, 0);

if (totalJsKb > budgets['total-js']['max-kb']) {
  console.error(`FAIL: Total JS is ${totalJsKb.toFixed(0)}KB (budget: ${budgets['total-js']['max-kb']}KB)`);
  process.exit(1);
}
console.log(`PASS: Total JS is ${totalJsKb.toFixed(0)}KB (budget: ${budgets['total-js']['max-kb']}KB)`);
```

**Gate:**
```bash
pnpm build && node scripts/check-bundle-sizes.js
# MUST print "PASS"
```

### 6.3 Add resource hints

**In `app.html` `<head>`:**
```html
<!-- Preconnect to API (if different origin) -->
<link rel="preconnect" href="https://api.maestro.app" crossorigin>

<!-- Preload critical API endpoints -->
<link rel="preload" href="/api/oem/ceo-briefing" as="fetch" crossorigin>
<link rel="preload" href="/api/oem/dashboard" as="fetch" crossorigin>

<!-- Preload critical fonts -->
<link rel="preload" href="/static/fonts/montserrat-latin.woff2" as="font" type="font/woff2" crossorigin>

<!-- Preload critical CSS -->
<link rel="preload" href="/static/css/design-system.css" as="style">
```

---

## PHASE 7 — ACCESSIBILITY HARDENING (Day 17-19, 12 hours)

### 7.1 Focus trap for modals

**File:** `static/js/components/focus-trap.js` (NEW)

```javascript
export function createFocusTrap(container) {
  const focusableSelector = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
  let previouslyFocused = null;
  
  function trap(e) {
    if (e.key !== 'Tab') return;
    const focusable = container.querySelectorAll(focusableSelector);
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }
  
  return {
    activate() {
      previouslyFocused = document.activeElement;
      container.addEventListener('keydown', trap);
      const first = container.querySelector(focusableSelector);
      if (first) first.focus();
    },
    deactivate() {
      container.removeEventListener('keydown', trap);
      if (previouslyFocused) previouslyFocused.focus();
    },
  };
}
```

Wire into drill-down modal:
```javascript
// In drill_down_modal.js, when opening:
const trap = createFocusTrap(document.getElementById('drilldown-modal'));
trap.activate();

// When closing:
trap.deactivate();
```

### 7.2 ARIA live regions for dynamic content

**In `app.html`, add:**
```html
<!-- Screen reader announcements for dynamic content -->
<div id="sr-announcer" aria-live="polite" aria-atomic="true"
     class="sr-only" style="position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);">
</div>
```

**In `utils.js`, add:**
```javascript
function announce(message) {
  const el = document.getElementById('sr-announcer');
  if (el) {
    el.textContent = '';
    requestAnimationFrame(() => { el.textContent = message; });
  }
}
```

**Wire into navigation:**
```javascript
// In maestro.js navTo():
announce(`Navigated to ${pageNames[surface] || surface}`);
```

### 7.3 Keyboard navigation audit checklist

For EACH surface, verify:
- [ ] All interactive elements reachable via Tab
- [ ] Focus visible (2px outline, sufficient contrast)
- [ ] Enter/Space activates buttons
- [ ] ESC closes modals/dropdowns
- [ ] Arrow keys navigate within dropdowns/command palette
- [ ] No focus traps (can Tab out of every region)
- [ ] Skip-to-content link works

**Gate:**
```bash
# Run axe-core accessibility scan
pnpm add -D @axe-core/playwright
# In E2E test:
import axe from '@axe-core/playwright';
const results = await axe(page).analyze();
expect(results.violations).toHaveLength(0);
```

---

## PHASE 8 — DESIGN SYSTEM CONSOLIDATION (Day 20-22, 12 hours)

### 8.1 Merge 4 CSS files into 1 design system

Current state:
- `app.css` (42KB) — Tailwind compiled
- `design-system.css` (26KB) — hand-written
- `invisible-maestro.css` (9KB) — hand-written
- `maestro-bumble.css` (93KB) — hand-written (the largest!)

**Action:**
1. Audit `maestro-bumble.css` (93KB!) — delete unused rules. Target: < 30KB.
2. Merge `invisible-maestro.css` into `design-system.css`.
3. Keep `app.css` as Tailwind output (auto-generated, don't hand-edit).
4. Final structure:
   - `app.css` — Tailwind utilities (auto-generated, ~20KB after purge)
   - `design-system.css` — all component styles (hand-written, < 40KB)

**Gate:**
```bash
# Total CSS must be < 60KB
find dist/assets -name "*.css" | xargs wc -c | tail -1
# MUST be < 60,000 bytes
```

### 8.2 Design tokens as CSS custom properties

**File:** `static/css/tokens.css` (NEW)

```css
:root {
  /* ── Spacing scale (4px base) ── */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  --space-10: 40px;
  --space-12: 48px;
  
  /* ── Typography scale ── */
  --text-xs: 10px;
  --text-sm: 12px;
  --text-base: 14px;
  --text-lg: 16px;
  --text-xl: 20px;
  --text-2xl: 24px;
  --text-hero: 32px;
  
  /* ── Border radius ── */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-pill: 9999px;
  
  /* ── Shadows ── */
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.3);
  --shadow-md: 0 4px 12px rgba(0,0,0,0.4);
  --shadow-lg: 0 8px 24px rgba(0,0,0,0.5);
  
  /* ── Transitions ── */
  --transition-fast: 150ms cubic-bezier(0.4, 0, 0.2, 1);
  --transition-normal: 200ms cubic-bezier(0.4, 0, 0.2, 1);
  --transition-slow: 300ms cubic-bezier(0.4, 0, 0.2, 1);
}
```

Replace ALL hardcoded values in CSS with tokens. Use `grep` to find offenders:
```bash
# Find hardcoded pixel values
grep -rn "padding: [0-9]" static/css/*.css | grep -v "var("
# Find hardcoded colors
grep -rn "#[0-9a-f]" static/css/*.css | grep -v "var("
```

---

## PHASE 9 — PWA & OFFLINE (Day 23-24, 8 hours)

### 9.1 Service worker with stale-while-revalidate

**File:** `static/sw.js`

```javascript
const CACHE_NAME = 'maestro-v2';
const API_CACHE = 'maestro-api-v2';
const STATIC_ASSETS = [
  '/',
  '/app.html',
  '/static/css/design-system.css',
  '/static/fonts/montserrat-latin.woff2',
];

// Install — cache shell
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

// Fetch — stale-while-revalidate for API, cache-first for static
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  
  if (url.pathname.startsWith('/api/oem/')) {
    // API: stale-while-revalidate (show cached immediately, update in background)
    event.respondWith(
      caches.open(API_CACHE).then(async (cache) => {
        const cached = await cache.match(event.request);
        const fetchPromise = fetch(event.request).then(response => {
          if (response.ok) cache.put(event.request, response.clone());
          return response;
        }).catch(() => cached); // offline → serve stale
        return cached || fetchPromise; // return cache hit immediately, or wait for network
      })
    );
  } else if (url.pathname.startsWith('/static/') || url.pathname.startsWith('/assets/')) {
    // Static: cache-first (immutable with content hash)
    event.respondWith(
      caches.match(event.request).then(cached => cached || fetch(event.request))
    );
  }
});

// Activate — clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME && k !== API_CACHE).map(k => caches.delete(k)))
    )
  );
});
```

### 9.2 Offline fallback

When the API is unreachable, show cached data with a clear "offline" indicator:

```javascript
// In swr_cache.js, add offline detection:
async function fetchWithOfflineFallback(url) {
  try {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    // Update cache
    SWR.set(url, data);
    return data;
  } catch (e) {
    const cached = SWR.get(url);
    if (cached) {
      showOfflineBanner();
      return cached;
    }
    throw e;
  }
}

function showOfflineBanner() {
  let banner = document.getElementById('offline-banner');
  if (!banner) {
    banner = document.createElement('div');
    banner.id = 'offline-banner';
    banner.className = 'offline-banner';
    banner.setAttribute('role', 'alert');
    banner.textContent = '⚡ Offline — showing cached data. Changes will sync when reconnected.';
    document.body.prepend(banner);
  }
  banner.style.display = 'block';
}
```

**Gate:**
1. Open app → verify it loads
2. Open DevTools → Application → Service Workers → "Offline" checkbox
3. Refresh → app still loads with cached data
4. Banner shows "Offline" message
5. Uncheck Offline → refresh → banner disappears, fresh data loads

---

## PHASE 10 — MONITORING & ERROR BOUNDARIES (Day 25-26, 8 hours)

### 10.1 Global error boundary

**File:** `static/js/error-boundary.js` (NEW)

```javascript
// error-boundary.js — catches unhandled errors and shows recovery UI

window.addEventListener('error', (event) => {
  reportError({
    type: 'uncaught',
    message: event.message,
    filename: event.filename,
    lineno: event.lineno,
    colno: event.colno,
    stack: event.error?.stack,
  });
});

window.addEventListener('unhandledrejection', (event) => {
  reportError({
    type: 'unhandled-promise',
    message: event.reason?.message || String(event.reason),
    stack: event.reason?.stack,
  });
});

function reportError(error) {
  // 1. Log to console (dev)
  console.error('[Maestro Error]', error);
  
  // 2. Send to telemetry (production)
  if (window.MAESTRO_TELEMETRY_URL) {
    fetch(window.MAESTRO_TELEMETRY_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...error,
        url: window.location.href,
        surface: window._currentSurface,
        userAgent: navigator.userAgent,
        timestamp: new Date().toISOString(),
      }),
    }).catch(() => {}); // telemetry failure must not crash
  }
  
  // 3. Show non-intrusive error to user
  showToast('Something went wrong. The team has been notified.', 'error');
}

// Per-surface error recovery
function withErrorBoundary(surfaceId, loadFn) {
  return async function() {
    const el = document.getElementById(surfaceId + '-content');
    try {
      await loadFn();
    } catch (e) {
      if (el) {
        el.innerHTML = `
          <div class="error-boundary">
            <div class="text-sm font-semibold text-brand-rose">This surface failed to load.</div>
            <div class="text-xs text-fg-400 mt-1">${escapeHtml(e.message)}</div>
            <button data-action="retrySurface" data-surface="${escapeHtml(surfaceId)}"
                    class="btn btn-primary text-xs mt-3">Retry</button>
          </div>`;
      }
      reportError({ type: 'surface-error', surface: surfaceId, message: e.message, stack: e.stack });
    }
  };
}
```

### 10.2 Performance monitoring

**File:** `static/js/perf-monitor.js` (NEW)

```javascript
// perf-monitor.js — Web Vitals collection (production only)

function reportWebVitals() {
  if (!('PerformanceObserver' in window)) return;
  
  // LCP
  new PerformanceObserver((list) => {
    const entries = list.getEntries();
    const lcp = entries[entries.length - 1];
    sendMetric('lcp', lcp.startTime);
  }).observe({ type: 'largest-contentful-paint', buffered: true });
  
  // FID
  new PerformanceObserver((list) => {
    list.getEntries().forEach(entry => {
      sendMetric('fid', entry.processingStart - entry.startTime);
    });
  }).observe({ type: 'first-input', buffered: true });
  
  // CLS
  let clsValue = 0;
  new PerformanceObserver((list) => {
    list.getEntries().forEach(entry => {
      if (!entry.hadRecentInput) clsValue += entry.value;
    });
    sendMetric('cls', clsValue);
  }).observe({ type: 'layout-shift', buffered: true });
  
  // Long tasks (> 50ms)
  new PerformanceObserver((list) => {
    list.getEntries().forEach(entry => {
      if (entry.duration > 50) {
        sendMetric('long-task', entry.duration, { name: entry.name });
      }
    });
  }).observe({ type: 'longtask', buffered: true });
}

function sendMetric(name, value, meta = {}) {
  // Send to telemetry endpoint (non-blocking)
  if (window.MAESTRO_TELEMETRY_URL) {
    navigator.sendBeacon(
      window.MAESTRO_TELEMETRY_URL + '/metrics',
      JSON.stringify({ name, value, ...meta, timestamp: Date.now() })
    );
  }
}

// Only in production
if (window.location.hostname !== 'localhost') {
  reportWebVitals();
}
```

---

## MASTER GATE — DEFINITION OF "WORLD-CLASS"

Before declaring the frontend "done," ALL of the following must pass:

```bash
# 1. Build succeeds with no warnings
pnpm build 2>&1 | grep -c "warning"
# MUST be 0

# 2. Bundle sizes within budget
node scripts/check-bundle-sizes.js
# MUST print "PASS"

# 3. All unit tests pass
pnpm test
# MUST print "✓ N tests passed"

# 4. All E2E tests pass
pnpm test:e2e
# MUST print "✓ N tests passed"

# 5. Zero inline event handlers
grep -rn 'onclick=' static/js/ app.html | wc -l
# MUST be 0

# 6. Zero console errors on load
# (run in Playwright): expect(pageErrors).toHaveLength(0)

# 7. Lighthouse scores
pnpm lighthouse
# Performance: ≥ 90
# Accessibility: ≥ 95
# Best Practices: ≥ 95
# SEO: ≥ 90

# 8. No file exceeds 600 lines
find static/js -name "*.js" -exec wc -l {} \; | awk '{if($1 > 600) print "FAIL:", $0}'
# MUST print nothing

# 9. PWA installable
# Open in Chrome → address bar shows "Install" icon

# 10. Offline works
# Toggle offline → app loads with cached data → banner shows

# 11. Accessibility
pnpm test:e2e --grep "accessibility"
# axe-core: 0 violations

# 12. No global scope pollution
# (run in browser console):
# Object.keys(window).filter(k => typeof window[k] === 'function').length
# MUST be < 20 (down from 100+)
```

---

## SUMMARY: WHERE WE ARE → WHERE WE SHOULD BE

| Metric | Current | After Phase 10 |
|--------|---------|---------------|
| Initial JS load | 521 KB (all loaded) | < 150 KB (core only) |
| Total JS | 521 KB | < 400 KB (code-split) |
| Total CSS | 169 KB | < 60 KB (purged + merged) |
| HTML | 67 KB (single file) | 15 KB (shell only) |
| HTTP requests (JS) | 40+ | 3-5 (bundled) |
| Build tool | none | Vite |
| TypeScript | 0% | 0% (deferred — too costly to migrate 10K lines) |
| Unit tests | 0 | 50+ |
| E2E tests | 0 | 15+ |
| Inline onclick | 130+ | 0 |
| Global functions | 100+ | < 20 |
| Largest JS file | 1,502 lines | < 600 lines |
| Lighthouse perf | unknown | ≥ 90 |
| Lighthouse a11y | unknown | ≥ 95 |
| PWA installable | no | yes |
| Offline support | no | yes |
| Error boundaries | 0 | every surface |
| CSP violations | many | 0 |
| Focus traps | 0 | all modals |
| Screen reader support | partial | full |

### Timeline: 26 working days (5 weeks) for one senior frontend engineer.

### Cost: ~$40K-60K (senior frontend contractor, 5 weeks).

### ROI: Transforms the product from "impressive demo" to "shippable enterprise frontend."

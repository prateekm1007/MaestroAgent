/**
 * Maestro Cognitive Council — Frontend API Router (upgraded).
 *
 * Per the surface migration roadmap (Steps 3-5): this file is now the single
 * entry point for all API calls. It:
 *   1. Reads the server-injected MAESTRO_USE_COUNCIL flag
 *   2. Routes calls to /api/council/* (with ?legacy_compatible=true) or /api/oem/*
 *   3. Provides fetchWithFallback() — if a Council route fails, falls back
 *      transparently to the legacy route
 *
 * The flag is set server-side by _serve_app_html_with_flags() in main.py.
 * Before this fix, the flag was dead code (0 callers, 0 server injection).
 *
 * USAGE (replaces all hardcoded fetch('/api/oem/...') calls):
 *
 *   // GET
 *   const data = await MaestroAPI.get('/ceo-briefing');
 *   // → fetches /api/council/briefing?legacy_compatible=true (if flag=true)
 *   //   or /api/oem/ceo-briefing (if flag=false)
 *   //   with automatic fallback to legacy on Council failure
 *
 *   // POST
 *   const result = await MaestroAPI.post('/ask/conversation', { query: '...' });
 *   // → fetches /api/council/ask?legacy_compatible=true (if flag=true)
 *   //   or /api/oem/ask/conversation (if flag=false)
 */

(function() {
    'use strict';

    function isCouncilEnabled() {
        if (new URLSearchParams(window.location.search).get('use_council') === 'true') return true;
        if (localStorage.getItem('maestro_use_council') === 'true') return true;
        if (window.MAESTRO_USE_COUNCIL === true) return true;
        const meta = document.querySelector('meta[name="maestro-use-council"]');
        if (meta && meta.getAttribute('content') === 'true') return true;
        return false;
    }

    const USE_COUNCIL = isCouncilEnabled();
    const OEM_BASE = (window.MAESTRO_API || '') + '/api/oem';
    const COUNCIL_BASE = (window.MAESTRO_API || '') + '/api/council';

    // The base that all surfaces use (backward compat with existing code)
    const API_BASE = USE_COUNCIL ? COUNCIL_BASE : OEM_BASE;
    window.MAESTRO_USE_COUNCIL = USE_COUNCIL;
    window.MAESTRO_API_BASE = API_BASE;

    /**
     * Map legacy OEM paths to Council paths.
     * The Council routes accept ?legacy_compatible=true to return legacy-shaped
     * responses via the adapters in council_adapters.py.
     */
    const PATH_MAP = {
        // Ask
        '/ask/conversation': { council: '/ask', method: 'POST', legacyCompatible: true },
        '/ask':              { council: '/ask', method: 'POST', legacyCompatible: true },
        // Briefing
        '/ceo-briefing':     { council: '/briefing', method: 'POST', legacyCompatible: true },
        // Preparation
        '/preparation/tomorrow': { council: '/prepare', method: 'POST', legacyCompatible: true },
        // Whisper
        '/whisper':          { council: '/whisper', method: 'POST', legacyCompatible: false },
    };

    /**
     * fetchWithFallback — try Council first (if enabled), fall back to legacy.
     *
     * Per roadmap Step 5: if a Council route returns non-2xx or throws,
     * transparently fall back to the legacy route. This makes the migration
     * safe — Council failures don't break the user experience.
     */
    async function fetchWithFallback(legacyPath, options, councilPath, legacyCompatible) {
        const legacyUrl = OEM_BASE + legacyPath;
        const councilUrl = COUNCIL_BASE + councilPath + (legacyCompatible ? '?legacy_compatible=true' : '');

        // If Council mode is off, just hit legacy
        if (!USE_COUNCIL) {
            const resp = await fetch(legacyUrl, options);
            return resp;
        }

        // Council mode is on — try Council first
        try {
            // For Council POST routes that need a body, ensure the body matches
            // the Council request schema. The adapters handle response shape;
            // for request shape, we pass through the same body (the Council
            // routes accept {query, org_id} which is compatible enough).
            const councilOptions = options ? { ...options } : {};
            // Add ?legacy_compatible=true to the URL
            const resp = await fetch(councilUrl, councilOptions);
            if (resp.ok) {
                return resp;
            }
            // Non-2xx — fall back to legacy
            console.warn(`[MaestroAPI] Council route ${councilPath} returned ${resp.status}, falling back to legacy ${legacyPath}`);
            return fetch(legacyUrl, options);
        } catch (e) {
            console.warn(`[MaestroAPI] Council route ${councilPath} threw ${e.message}, falling back to legacy ${legacyPath}`);
            return fetch(legacyUrl, options);
        }
    }

    /**
     * Build the URL for a given legacy path. Returns the full URL.
     */
    function buildUrl(legacyPath) {
        if (USE_COUNCIL && PATH_MAP[legacyPath]) {
            const mapping = PATH_MAP[legacyPath];
            const url = COUNCIL_BASE + mapping.council;
            return url + (mapping.legacyCompatible ? '?legacy_compatible=true' : '');
        }
        return OEM_BASE + legacyPath;
    }

    // Expose globally
    window.MaestroAPI = {
        USE_COUNCIL: USE_COUNCIL,
        OEM_BASE: OEM_BASE,
        COUNCIL_BASE: COUNCIL_BASE,

        isCouncilMode: function() { return USE_COUNCIL; },

        buildUrl: buildUrl,

        /**
         * GET request with automatic Council/legacy routing + fallback.
         * @param {string} legacyPath - e.g. '/ceo-briefing'
         */
        get: async function(legacyPath) {
            const mapping = PATH_MAP[legacyPath];
            if (mapping && mapping.method === 'POST') {
                // This path needs POST (e.g., Council briefing is POST not GET)
                return fetchWithFallback(legacyPath, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }, mapping.council, mapping.legacyCompatible);
            }
            // Pure GET
            if (USE_COUNCIL && mapping) {
                return fetchWithFallback(legacyPath, { method: 'GET' }, mapping.council, mapping.legacyCompatible);
            }
            return fetch(OEM_BASE + legacyPath);
        },

        /**
         * POST request with automatic Council/legacy routing + fallback.
         * @param {string} legacyPath - e.g. '/ask/conversation'
         * @param {object} body - request body
         */
        post: async function(legacyPath, body) {
            const mapping = PATH_MAP[legacyPath];
            const options = {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body || {}),
            };
            if (USE_COUNCIL && mapping) {
                return fetchWithFallback(legacyPath, options, mapping.council, mapping.legacyCompatible);
            }
            return fetch(OEM_BASE + legacyPath, options);
        },

        /**
         * fetchWithFallback — exposed for call sites that need raw control.
         */
        fetchWithFallback: fetchWithFallback,

        // Legacy helpers (kept for backward compat with any code that uses them)
        askUrl: function(query) {
            if (USE_COUNCIL) return COUNCIL_BASE + '/ask?legacy_compatible=true';
            return OEM_BASE + '/ask?q=' + encodeURIComponent(query);
        },
        whisperUrl: function(context, entity, topic) {
            if (USE_COUNCIL) return COUNCIL_BASE + '/whisper';
            var url = OEM_BASE + '/whisper?context=' + (context || '');
            if (entity) url += '&entity=' + entity;
            if (topic) url += '&topic=' + topic;
            return url;
        },
        briefingUrl: function() {
            if (USE_COUNCIL) return COUNCIL_BASE + '/briefing?legacy_compatible=true';
            return OEM_BASE + '/ceo-briefing';
        },
        preparationUrl: function() {
            if (USE_COUNCIL) return COUNCIL_BASE + '/prepare?legacy_compatible=true';
            return OEM_BASE + '/preparation/tomorrow';
        },
        situationsUrl: function() { return COUNCIL_BASE + '/situations'; },
        copilotPreCallUrl: function() { return COUNCIL_BASE + '/copilot/pre-call'; },
        copilotPostCallUrl: function() { return COUNCIL_BASE + '/copilot/post-call'; },
        getBase: function() { return API_BASE; },
    };

    console.log('[Maestro API] Using ' + (USE_COUNCIL ? 'Cognitive Council' : 'OEM') + ' API (fallback enabled)');
})();

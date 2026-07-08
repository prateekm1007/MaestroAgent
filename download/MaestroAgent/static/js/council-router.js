/**
 * Maestro Cognitive Council — Frontend API Router.
 *
 * Per the audit: "Frontend calls /api/council 0 times, /api/oem 20+ times.
 * No feature flag exists to swap them."
 *
 * This shim provides a feature flag that repoints API calls from
 * /api/oem/* to /api/council/* when MAESTRO_USE_COUNCIL=true.
 *
 * Usage:
 *   // Instead of: fetch('/api/oem/ask?q=...')
 *   // Use:        fetch(MaestroAPI.ask(q))
 *   // Or:         fetch(MAESTRO_API_BASE + '/ask?q=...')
 *
 * The flag is set via:
 *   1. URL parameter: ?use_council=true
 *   2. localStorage: localStorage.setItem('maestro_use_council', 'true')
 *   3. Server-side: injected as window.MAESTRO_USE_COUNCIL = true
 */

(function() {
    'use strict';

    // Check if council mode is enabled
    function isCouncilEnabled() {
        // Check URL parameter
        if (new URLSearchParams(window.location.search).get('use_council') === 'true') {
            return true;
        }
        // Check localStorage
        if (localStorage.getItem('maestro_use_council') === 'true') {
            return true;
        }
        // Check server-injected flag
        if (window.MAESTRO_USE_COUNCIL === true) {
            return true;
        }
        // Check meta tag
        const meta = document.querySelector('meta[name="maestro-use-council"]');
        if (meta && meta.getAttribute('content') === 'true') {
            return true;
        }
        return false;
    }

    const USE_COUNCIL = isCouncilEnabled();

    // API base paths
    const OEM_BASE = (window.MAESTRO_API || '') + '/api/oem';
    const COUNCIL_BASE = (window.MAESTRO_API || '') + '/api/council';

    // The base that all surfaces use
    const API_BASE = USE_COUNCIL ? COUNCIL_BASE : OEM_BASE;

    // Expose globally so all JS files can use it
    window.MAESTRO_API_BASE = API_BASE;
    window.MAESTRO_USE_COUNCIL = USE_COUNCIL;

    // Helper functions for common API calls
    window.MaestroAPI = {
        // Ask
        askUrl: function(query) {
            if (USE_COUNCIL) {
                return COUNCIL_BASE + '/ask';
            }
            return OEM_BASE + '/ask?q=' + encodeURIComponent(query);
        },

        // Whisper
        whisperUrl: function(context, entity, topic) {
            if (USE_COUNCIL) {
                return COUNCIL_BASE + '/whisper';
            }
            var url = OEM_BASE + '/whisper?context=' + (context || '');
            if (entity) url += '&entity=' + entity;
            if (topic) url += '&topic=' + topic;
            return url;
        },

        // Briefing
        briefingUrl: function(type) {
            return COUNCIL_BASE + '/briefing';
        },

        // Preparation
        preparationUrl: function(situationId) {
            if (USE_COUNCIL) {
                return COUNCIL_BASE + '/prepare';
            }
            return OEM_BASE + '/preparation/tomorrow';
        },

        // Situations
        situationsUrl: function() {
            return COUNCIL_BASE + '/situations';
        },

        // Copilot
        copilotPreCallUrl: function() {
            return COUNCIL_BASE + '/copilot/pre-call';
        },

        copilotPostCallUrl: function() {
            return COUNCIL_BASE + '/copilot/post-call';
        },

        // Check if council mode is on
        isCouncilMode: function() {
            return USE_COUNCIL;
        },

        // Get the base path
        getBase: function() {
            return API_BASE;
        }
    };

    // Log which mode is active
    console.log('[Maestro API] Using ' + (USE_COUNCIL ? 'Cognitive Council' : 'OEM') + ' API at ' + API_BASE);
})();

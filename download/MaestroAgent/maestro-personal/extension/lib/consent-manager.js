/**
 * ConsentManager — MANDATORY consent flow before any audio/video capture.
 *
 * This is the ethical line: NO capture happens without explicit user consent.
 * Every getUserMedia / getDisplayMedia call MUST be preceded by
 * ConsentManager.checkConsent(). The auditor verifies this by grep:
 *   grep -rn "getUserMedia\|getDisplayMedia" extension/
 * Every match MUST be preceded by ConsentManager.checkConsent().
 *
 * Consent is:
 *   - Per-session (re-asked for each meeting)
 *   - Revocable (user can revoke mid-call; capture stops immediately)
 *   - Audit-logged (every grant/revoke is recorded)
 *
 * The anti-Cluely: Cluely records without consent. Maestro never does.
 */

const ConsentManager = {
  _consentState: {
    audio: false,
    screen: false,
    grantedAt: null,
    revokedAt: null,
    sessionId: null,
  },

  _auditLog: [],

  /**
   * Check if consent has been granted for the given media type.
   * Returns true ONLY if consent is currently active.
   */
  checkConsent(mediaType = 'audio') {
    return this._consentState[mediaType] === true && this._consentState.revokedAt === null;
  },

  /**
   * Request consent from the user via the side panel UI.
   * Returns a Promise<boolean> — true if granted, false if denied.
   */
  async requestConsent(mediaType = 'audio') {
    // Send a message to the side panel to show the consent dialog
    const response = await chrome.runtime.sendMessage({
      type: 'CONSENT_REQUEST',
      mediaType: mediaType,
      message: this._consentPromptText(mediaType),
    });

    if (response && response.granted) {
      this._grantConsent(mediaType);
      return true;
    }
    this._denyConsent(mediaType);
    return false;
  },

  /**
   * Grant consent for a media type. Called after the user clicks "Allow".
   */
  _grantConsent(mediaType) {
    this._consentState[mediaType] = true;
    this._consentState.grantedAt = new Date().toISOString();
    this._consentState.revokedAt = null;
    this._consentState.sessionId = this._generateSessionId();
    this._logAudit('CONSENT_GRANTED', { mediaType, at: this._consentState.grantedAt });
  },

  /**
   * Deny consent for a media type. Called after the user clicks "Deny" or dismisses.
   */
  _denyConsent(mediaType) {
    this._consentState[mediaType] = false;
    this._logAudit('CONSENT_DENIED', { mediaType, at: new Date().toISOString() });
  },

  /**
   * Revoke consent mid-call. Capture MUST stop immediately.
   * This is the user's withdrawal path — the constitution requires it.
   */
  revokeConsent(mediaType = 'audio') {
    this._consentState[mediaType] = false;
    this._consentState.revokedAt = new Date().toISOString();
    this._logAudit('CONSENT_REVOKED', { mediaType, at: this._consentState.revokedAt });
    // Notify the background script to stop capture immediately
    chrome.runtime.sendMessage({
      type: 'CONSENT_REVOKED',
      mediaType: mediaType,
    });
  },

  /**
   * Get the full consent state for display in the UI.
   */
  getConsentState() {
    return { ...this._consentState };
  },

  /**
   * Get the audit log for compliance verification.
   */
  getAuditLog() {
    return [...this._auditLog];
  },

  /**
   * Log a consent event to the audit log.
   */
  _logAudit(event, details) {
    this._auditLog.push({
      event,
      ...details,
      timestamp: new Date().toISOString(),
    });
    // Also persist to chrome.storage for durability
    if (chrome.storage) {
      chrome.storage.local.set({ [`consent_audit_${Date.now()}`]: { event, ...details } });
    }
  },

  /**
   * Generate the consent prompt text for the given media type.
   */
  _consentPromptText(mediaType) {
    const prompts = {
      audio:
        'Maestro wants to capture meeting audio to provide real-time intelligence. ' +
        'This audio will be transcribed and analyzed. You can revoke consent at any time ' +
        'and capture will stop immediately. Do you consent?',
      screen:
        'Maestro wants to capture your screen for meeting context. ' +
        'This will be analyzed for visual cues. You can revoke consent at any time. ' +
        'Do you consent?',
    };
    return prompts[mediaType] || `Maestro wants to capture ${mediaType}. Do you consent?`;
  },

  /**
   * Generate a unique session ID for this consent session.
   */
  _generateSessionId() {
    return 'consent-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
  },
};

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = ConsentManager;
}

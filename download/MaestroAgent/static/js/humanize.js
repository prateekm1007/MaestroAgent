// HUMANIZE — universal vocabulary hiding for the Invisible Maestro
// ═══════════════════════════════════════════════════════════════════════════
// Constitution v2: "Never expose Learning Objects, Patterns, Evidence Graph,
// Judgment Graph, OEM, Signals, Receipts, Prediction Market, Hypothesis
// Engine, Laws. Replace them with natural language."
//
// This function is the SINGLE source of truth for vocabulary hiding.
// Every surface that displays OEM-derived text to the user must pass it
// through humanize() before rendering. The function:
//   1. Strips law codes (L-0001, L-0002, etc.)
//   2. Strips confidence numbers ((confidence: 1.00), confidence: 0.85)
//   3. Replaces internal terms with human language
//   4. Cleans up whitespace
//
// Usage:
//   element.innerHTML = humanize(rawApiText);
//   element.textContent = humanize(rawApiText);
//
// The function is pure (no side effects, no DOM access) so it can be
// unit-tested in isolation.
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Humanize raw OEM text by stripping internal vocabulary and confidence numbers.
 *
 * @param {string} text - The raw text from an OEM API response.
 * @returns {string} The humanized text, safe to display to users.
 */
function humanize(text) {
  if (!text) return '';
  return String(text)
    // ── Strip law codes (L-0001, L-0002, L-XXXX) ──────────────────────────
    .replace(/\bL-\d{4}\b/g, '')
    // ── Strip confidence numbers ──────────────────────────────────────────
    // Constitution: "Never expose confidence numbers alone."
    // Patterns: "(confidence: 1.00)", "confidence: 0.85", "conf: 0.92"
    .replace(/\(confidence:\s*[\d.]+\s*\)/gi, '')
    .replace(/\(conf:\s*[\d.]+\s*\)/gi, '')
    .replace(/\bconfidence:\s*[\d.]+\b/gi, '')
    .replace(/\bconf:\s*[\d.]+\b/gi, '')
    // ── Replace internal terms with human language ────────────────────────
    .replace(/learning object/gi, 'pattern')
    .replace(/evidence graph/gi, 'organizational memory')
    .replace(/judgment graph/gi, 'organizational judgment')
    .replace(/receipt/gi, 'signal')
    .replace(/\blaw\b/gi, 'pattern')
    .replace(/\blaws\b/gi, 'patterns')
    .replace(/OEM/g, 'Maestro')
    .replace(/prediction market/gi, 'calibration ranking')
    .replace(/hypothesis engine/gi, 'prediction system')
    .replace(/hypothesis/gi, 'prediction')
    .replace(/signal type/gi, 'event type')
    // ── Clean up whitespace left by replacements ──────────────────────────
    .replace(/\(\s*\)/g, '')           // Remove empty parens "(: priya)"
    .replace(/:\s*:/g, ':')             // Fix double colons "::"
    .replace(/\s+\)/g, ')')            // Fix trailing space before )
    .replace(/\(\s+/g, '(')            // Fix leading space after (
    .replace(/\s{2,}/g, ' ')           // Collapse multiple spaces
    .replace(/^\s*[•·-]\s*$/gm, '')    // Remove empty bullet lines
    .trim();
}

// ═══════════════════════════════════════════════════════════════════════════

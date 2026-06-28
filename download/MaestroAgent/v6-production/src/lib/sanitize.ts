// Input sanitization — DOMPurify-based.
// All user-generated text (transcript, decision descriptions, debate theses) passes through here.

import DOMPurify from 'isomorphic-dompurify';

/**
 * Sanitize text for safe HTML rendering.
 * Strips all tags except a safe whitelist, escapes HTML entities.
 */
export function sanitizeText(input: string, options?: { maxLength?: number }): string {
  if (typeof input !== 'string') return '';
  const maxLength = options?.maxLength ?? 10000;
  const truncated = input.slice(0, maxLength);
  return DOMPurify.sanitize(truncated, {
    ALLOWED_TAGS: [], // Strip all tags — we only want text
    ALLOWED_ATTR: [],
    KEEP_CONTENT: true,
  });
}

/**
 * Sanitize text that may contain limited markdown (bold, italic, code).
 * Used for decision descriptions and debate theses.
 */
export function sanitizeMarkdown(input: string, options?: { maxLength?: number }): string {
  if (typeof input !== 'string') return '';
  const maxLength = options?.maxLength ?? 50000;
  const truncated = input.slice(0, maxLength);
  return DOMPurify.sanitize(truncated, {
    ALLOWED_TAGS: ['b', 'strong', 'i', 'em', 'code', 'br', 'p', 'ul', 'ol', 'li'],
    ALLOWED_ATTR: [],
  });
}

/**
 * Sanitize a transcript line — preserves speaker attribution, strips anything dangerous.
 */
export function sanitizeTranscript(input: string): string {
  return sanitizeText(input, { maxLength: 5000 });
}

/**
 * Validate and sanitize an email.
 */
export function sanitizeEmail(input: string): string | null {
  const email = sanitizeText(input).toLowerCase().trim();
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return emailRegex.test(email) ? email : null;
}

/**
 * Sanitize a URL — only allow http/https protocols.
 */
export function sanitizeUrl(input: string): string | null {
  const url = sanitizeText(input).trim();
  try {
    const parsed = new URL(url);
    if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
      return parsed.toString();
    }
  } catch {
    // Invalid URL
  }
  return null;
}

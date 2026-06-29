// src/security.js — Enterprise security middleware and utilities.
//
// Provides:
//   - TLS/HTTPS enforcement and security headers
//   - Field-level encryption for sensitive data (OAuth tokens, credentials, PII)
//   - Encrypted integration credential storage/retrieval
//   - PII detection and redaction before LLM calls
//   - Rate limiting middleware
//   - Request audit logging middleware
//   - Content Security Policy
//   - CORS security hardening
//
// Environment variables:
//   FORCE_TLS          — 'true' to enforce HTTPS (redirect HTTP → HTTPS)
//   CSP_REPORT_ONLY    — 'true' for CSP report-only mode
//   RATE_LIMIT_WINDOW  — Rate limit window in ms (default: 60000 = 1 min)
//   RATE_LIMIT_MAX     — Max requests per window (default: 100)
//   PII_REDACTION      — 'true' to enable PII redaction (default: true)

import crypto from 'node:crypto';
import { envelopeEncrypt, envelopeDecrypt, reencryptField } from './kms.js';
import { query } from './db.js';

const FORCE_TLS = process.env.FORCE_TLS === 'true';
const CSP_REPORT_ONLY = process.env.CSP_REPORT_ONLY === 'true';
const RATE_LIMIT_WINDOW = parseInt(process.env.RATE_LIMIT_WINDOW || '60000', 10);
const RATE_LIMIT_MAX = parseInt(process.env.RATE_LIMIT_MAX || '100', 10);
const PII_REDACTION = process.env.PII_REDACTION !== 'false';

// ============================================================================
// TLS / HTTPS ENFORCEMENT
// ============================================================================

/**
 * Middleware: Force HTTPS redirect.
 * If FORCE_TLS is true, redirects all HTTP requests to HTTPS.
 */
export function tlsRedirectMiddleware(req, res, next) {
  if (!FORCE_TLS) return next();

  // Check if request is already HTTPS (via proxy header or direct)
  const isHttps = req.headers['x-forwarded-proto'] === 'https' || req.secure;

  if (!isHttps) {
    const httpsUrl = `https://${req.headers.host}${req.originalUrl}`;
    return res.redirect(301, httpsUrl);
  }

  // Add Strict-Transport-Security header
  res.setHeader('Strict-Transport-Security', 'max-age=31536000; includeSubDomains; preload');

  next();
}

/**
 * Middleware: Security headers.
 * Adds standard security headers to all responses.
 */
export function securityHeadersMiddleware(req, res, next) {
  // Prevent clickjacking
  res.setHeader('X-Frame-Options', 'DENY');

  // Prevent MIME-type sniffing
  res.setHeader('X-Content-Type-Options', 'nosniff');

  // XSS protection (legacy browsers)
  res.setHeader('X-XSS-Protection', '1; mode=block');

  // Referrer policy
  res.setHeader('Referrer-Policy', 'strict-origin-when-cross-origin');

  // Permissions policy (disable unnecessary browser features)
  res.setHeader('Permissions-Policy', 'geolocation=(), microphone=(), camera=(), payment=()');

  // Content Security Policy
  const cspDirectives = [
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data: https:",
    "connect-src 'self' wss: ws:",
    "frame-ancestors 'none'",
    "form-action 'self'",
    "base-uri 'self'",
    "object-src 'none'",
  ];
  const cspHeader = CSP_REPORT_ONLY ? 'Content-Security-Policy-Report-Only' : 'Content-Security-Policy';
  res.setHeader(cspHeader, cspDirectives.join('; '));

  next();
}

// ============================================================================
// FIELD-LEVEL ENCRYPTION
// ============================================================================

/**
 * Encrypt a sensitive field using envelope encryption.
 * Use for: OAuth tokens, API credentials, PII, connection strings.
 *
 * @param {string} plaintext - The sensitive value
 * @returns {Promise<string>} Encrypted JSON envelope
 */
export async function encryptField(plaintext) {
  return envelopeEncrypt(plaintext);
}

/**
 * Decrypt an encrypted field.
 *
 * @param {string} encryptedJson - The encrypted JSON envelope
 * @returns {Promise<string>} Plaintext value
 */
export async function decryptField(encryptedJson) {
  return envelopeDecrypt(encryptedJson);
}

/**
 * Encrypt an object's sensitive fields.
 *
 * @param {object} obj - The object containing sensitive data
 * @param {string[]} fields - Field names to encrypt
 * @returns {Promise<object>} New object with encrypted fields
 */
export async function encryptFields(obj, fields) {
  const result = { ...obj };
  for (const field of fields) {
    if (result[field] !== undefined && result[field] !== null && result[field] !== '') {
      result[field] = await encryptField(String(result[field]));
    }
  }
  return result;
}

/**
 * Decrypt an object's encrypted fields.
 *
 * @param {object} obj - The object with encrypted fields
 * @param {string[]} fields - Field names to decrypt
 * @returns {Promise<object>} New object with decrypted fields
 */
export async function decryptFields(obj, fields) {
  const result = { ...obj };
  for (const field of fields) {
    if (result[field]) {
      try {
        result[field] = await decryptField(result[field]);
      } catch (err) {
        console.warn(`[security] Failed to decrypt field ${field}:`, err.message);
      }
    }
  }
  return result;
}

// ============================================================================
// INTEGRATION CREDENTIAL MANAGEMENT
// ============================================================================

/**
 * Store integration credentials securely (encrypted).
 * The credentials column stores the encrypted envelope.
 *
 * @param {string} integrationId - Integration record ID
 * @param {object} credentials - Credential object (OAuth tokens, API keys, etc.)
 */
export async function storeIntegrationCredentials(integrationId, credentials) {
  const encrypted = await encryptField(JSON.stringify(credentials));
  await query(
    'UPDATE integrations SET credentials = $1 WHERE id = $2',
    [encrypted, integrationId]
  );
}

/**
 * Retrieve and decrypt integration credentials.
 *
 * @param {string} integrationId - Integration record ID
 * @returns {Promise<object|null>} Decrypted credentials object
 */
export async function getIntegrationCredentials(integrationId) {
  const result = await query('SELECT credentials FROM integrations WHERE id = $1', [integrationId]);
  if (!result.rows[0]?.credentials) return null;

  const decrypted = await decryptField(result.rows[0].credentials);
  return JSON.parse(decrypted);
}

/**
 * Update integration credentials (e.g., after OAuth token refresh).
 *
 * @param {string} integrationId
 * @param {object} credentials - New credentials
 */
export async function updateIntegrationCredentials(integrationId, credentials) {
  await storeIntegrationCredentials(integrationId, credentials);
}

// Fields that should be encrypted when storing integration data
export const ENCRYPTED_INTEGRATION_FIELDS = ['credentials', 'config'];

// Fields that should be encrypted when storing user data
export const ENCRYPTED_USER_FIELDS = ['mfa_secret'];

// ============================================================================
// PII DETECTION AND REDACTION
// ============================================================================

const PII_PATTERNS = [
  // SSN: 123-45-6789
  { pattern: /\b\d{3}-\d{2}-\d{4}\b/g, replacement: '[SSN-REDACTED]' },
  // Email addresses
  { pattern: /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z]{2,}\b/gi, replacement: '[EMAIL-REDACTED]' },
  // Credit card numbers (16 digits, optionally grouped)
  { pattern: /\b(?:\d[ -]*?){13,16}\b/g, replacement: '[CARD-REDACTED]' },
  // Phone numbers: (123) 456-7890, 123-456-7890
  { pattern: /\b\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b/g, replacement: '[PHONE-REDACTED]' },
  // API keys (mstr_, sk-, Bearer tokens)
  { pattern: /\bmstr_[a-f0-9]{64}\b/gi, replacement: '[API-KEY-REDACTED]' },
  { pattern: /\bsk-[a-zA-Z0-9]{20,}\b/g, replacement: '[API-KEY-REDACTED]' },
  { pattern: /\bBearer\s+[a-zA-Z0-9._-]+/gi, replacement: '[TOKEN-REDACTED]' },
  // IP addresses (private)
  { pattern: /\b(?:10|172|192)\.\d{1,3}\.\d{1,3}\.\d{1,3}\b/g, replacement: '[IP-REDACTED]' },
];

/**
 * Redact PII from text before sending to LLM or storing in logs.
 *
 * @param {string} text - Input text that may contain PII
 * @returns {string} Text with PII replaced by [TYPE-REDACTED] placeholders
 */
export function redactPII(text) {
  if (!PII_REDACTION || !text || typeof text !== 'string') return text;

  let redacted = text;
  for (const { pattern, replacement } of PII_PATTERNS) {
    redacted = redacted.replace(pattern, replacement);
  }
  return redacted;
}

/**
 * Check if text contains PII.
 *
 * @param {string} text
 * @returns {boolean}
 */
export function containsPII(text) {
  if (!text || typeof text !== 'string') return false;
  return PII_PATTERNS.some(({ pattern }) => pattern.test(text));
}

/**
 * Redact PII from an object's string fields (deep scan).
 *
 * @param {object} obj - Object to scan
 * @param {string[]} skipFields - Fields to skip (e.g., ['email'] for user records)
 * @returns {object} New object with PII redacted
 */
export function redactPIIFromObject(obj, skipFields = []) {
  if (!obj || typeof obj !== 'object') return obj;

  const result = Array.isArray(obj) ? [...obj] : { ...obj };

  for (const key of Object.keys(result)) {
    if (skipFields.includes(key)) continue;

    if (typeof result[key] === 'string') {
      result[key] = redactPII(result[key]);
    } else if (typeof result[key] === 'object' && result[key] !== null) {
      result[key] = redactPIIFromObject(result[key], skipFields);
    }
  }

  return result;
}

// ============================================================================
// RATE LIMITING
// ============================================================================

const rateLimitStore = new Map(); // ip -> { count, windowStart }

/**
 * Middleware: Simple in-memory rate limiting.
 * For production, use Redis-backed rate limiting.
 */
export function rateLimitMiddleware(req, res, next) {
  const ip = req.headers['x-forwarded-for']?.split(',')[0]?.trim() || req.socket?.remoteAddress || 'unknown';

  const now = Date.now();
  let entry = rateLimitStore.get(ip);

  if (!entry || now - entry.windowStart > RATE_LIMIT_WINDOW) {
    entry = { count: 0, windowStart: now };
    rateLimitStore.set(ip, entry);
  }

  entry.count++;

  // Set rate limit headers
  const remaining = Math.max(0, RATE_LIMIT_MAX - entry.count);
  const resetAt = entry.windowStart + RATE_LIMIT_WINDOW;
  res.setHeader('X-RateLimit-Limit', RATE_LIMIT_MAX);
  res.setHeader('X-RateLimit-Remaining', remaining);
  res.setHeader('X-RateLimit-Reset', Math.floor(resetAt / 1000));

  if (entry.count > RATE_LIMIT_MAX) {
    return res.status(429).json({
      error: 'Rate limit exceeded',
      retry_after: Math.ceil((resetAt - now) / 1000),
    });
  }

  // Clean up old entries periodically
  if (rateLimitStore.size > 10000) {
    for (const [key, val] of rateLimitStore) {
      if (now - val.windowStart > RATE_LIMIT_WINDOW * 2) {
        rateLimitStore.delete(key);
      }
    }
  }

  next();
}

/**
 * Stricter rate limit for auth endpoints.
 */
export function authRateLimitMiddleware(req, res, next) {
  const ip = req.headers['x-forwarded-for']?.split(',')[0]?.trim() || req.socket?.remoteAddress || 'unknown';
  const key = `auth:${ip}`;

  const now = Date.now();
  const window = 15 * 60 * 1000; // 15 minutes
  const max = 20; // 20 auth attempts per 15 minutes

  let entry = rateLimitStore.get(key);

  if (!entry || now - entry.windowStart > window) {
    entry = { count: 0, windowStart: now };
    rateLimitStore.set(key, entry);
  }

  entry.count++;

  if (entry.count > max) {
    return res.status(429).json({
      error: 'Too many authentication attempts. Please try again later.',
      retry_after: Math.ceil((entry.windowStart + window - now) / 1000),
    });
  }

  next();
}

// ============================================================================
// AUDIT LOGGING MIDDLEWARE
// ============================================================================

/**
 * Middleware: Audit log all API requests.
 * Logs method, path, status, duration, user, org, IP.
 */
export function requestAuditMiddleware(req, res, next) {
  const startTime = Date.now();
  const ip = req.headers['x-forwarded-for']?.split(',')[0]?.trim() || req.socket?.remoteAddress || null;
  const userAgent = req.headers['user-agent'] || null;

  // Log after response is sent
  res.on('finish', () => {
    const duration = Date.now() - startTime;
    const method = req.method;
    const path = req.originalUrl || req.path;
    const status = res.statusCode;
    const userId = req.user?.id || null;
    const orgId = req.user?.org_id || null;

    // Skip health checks and static assets
    if (path === '/api/health' || path === '/' || path.match(/\.(html|js|css|png|ico)$/)) {
      return;
    }

    // Log to audit table (async, non-blocking)
    const action = `api.${method.toLowerCase()}`;
    const metadata = {
      method,
      path,
      status,
      duration_ms: duration,
    };

    // Only log mutations and errors (not every GET)
    if (method !== 'GET' || status >= 400) {
      query(
        `INSERT INTO audit_log (org_id, user_id, action, resource_type, resource_id, metadata, ip_address, user_agent, success, error_message)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)`,
        [
          orgId, userId, action, 'api', path,
          JSON.stringify(metadata), ip, userAgent,
          status < 400, status >= 400 ? `HTTP ${status}` : null,
        ]
      ).catch(err => console.error('[security] Audit log write failed:', err.message));
    }

    // Log slow requests
    if (duration > 5000) {
      console.warn('[security] Slow request', { method, path, status, duration: `${duration}ms`, userId, orgId });
    }
  });

  next();
}

// ============================================================================
// WEBHOOK SIGNATURE VERIFICATION
// ============================================================================

/**
 * Verify a webhook signature using HMAC-SHA256.
 *
 * @param {string} secret - The webhook signing secret
 * @param {string|Buffer} payload - The raw request body
 * @param {string} signature - The signature from the header
 * @param {string} prefix - Optional prefix (e.g. 'sha256=' for GitHub)
 * @returns {boolean}
 */
export function verifyWebhookSignature(secret, payload, signature, prefix = '') {
  if (!secret || !payload || !signature) return false;

  const expected = prefix + crypto
    .createHmac('sha256', secret)
    .update(payload)
    .digest('hex');

  // Constant-time comparison
  const bufA = Buffer.from(signature);
  const bufB = Buffer.from(expected);

  if (bufA.length !== bufB.length) return false;
  return crypto.timingSafeEqual(bufA, bufB);
}

/**
 * GitHub webhook signature verification.
 * GitHub sends: x-hub-signature-256: sha256=<hex>
 */
export function verifyGitHubWebhook(req, secret) {
  const signature = req.headers['x-hub-signature-256'];
  if (!signature) return false;
  return verifyWebhookSignature(secret, req.rawBody || JSON.stringify(req.body), signature, 'sha256=');
}

/**
 * Slack webhook signature verification.
 * Slack sends: X-Slack-Signature: v0=<hex>
 * Also requires timestamp verification.
 */
export function verifySlackWebhook(req, secret) {
  const signature = req.headers['x-slack-signature'];
  const timestamp = req.headers['x-slack-request-timestamp'];
  if (!signature || !timestamp) return false;

  // Reject requests older than 5 minutes
  const now = Math.floor(Date.now() / 1000);
  if (Math.abs(now - parseInt(timestamp, 10)) > 300) {
    return false;
  }

  const rawBody = req.rawBody || JSON.stringify(req.body);
  const sigBase = `v0:${timestamp}:${rawBody}`;
  return verifyWebhookSignature(secret, sigBase, signature, 'v0=');
}

/**
 * Atlassian/Jira webhook signature verification.
 */
export function verifyJiraWebhook(req, secret) {
  const signature = req.headers['x-atlassian-webhook-identifier'];
  if (!signature) return false;
  return verifyWebhookSignature(secret, req.rawBody || JSON.stringify(req.body), signature);
}

// ============================================================================
// INPUT SANITIZATION
// ============================================================================

/**
 * Sanitize a string input to prevent injection attacks.
 * Removes null bytes, limits length, trims whitespace.
 *
 * @param {string} input
 * @param {number} maxLength - Maximum allowed length (default: 10000)
 * @returns {string} Sanitized string
 */
export function sanitizeInput(input, maxLength = 10000) {
  if (!input || typeof input !== 'string') return '';
  return input
    .replace(/\0/g, '') // Remove null bytes
    .slice(0, maxLength)
    .trim();
}

/**
 * Validate and sanitize a goal text before sending to LLM.
 * Removes potential prompt injection markers.
 *
 * @param {string} goal
 * @returns {string} Sanitized goal
 */
export function sanitizeGoal(goal) {
  if (!goal) return '';
  let sanitized = sanitizeInput(goal, 4000);
  // Remove common prompt injection patterns
  sanitized = sanitized
    .replace(/```[\s\S]*?```/g, '[CODE-BLOCK-REMOVED]') // Remove embedded code blocks
    .replace(/<script[\s\S]*?<\/script>/gi, '[SCRIPT-REMOVED]')
    .replace(/<iframe[\s\S]*?<\/iframe>/gi, '[IFRAME-REMOVED]');
  return sanitized;
}

// ============================================================================
// SECURITY STATUS
// ============================================================================

export function getSecurityStatus() {
  return {
    tls: {
      force_tls: FORCE_TLS,
      hsts: FORCE_TLS,
    },
    encryption: {
      algorithm: 'aes-256-gcm',
      envelope_encryption: true,
      kms_provider: process.env.KMS_PROVIDER || 'local',
      key_rotation: true,
    },
    pii_redaction: PII_REDACTION,
    rate_limiting: {
      enabled: true,
      window_ms: RATE_LIMIT_WINDOW,
      max_requests: RATE_LIMIT_MAX,
      auth_max: 20,
      auth_window_ms: 15 * 60 * 1000,
    },
    security_headers: true,
    audit_logging: true,
    webhook_verification: true,
    csp: true,
    csp_report_only: CSP_REPORT_ONLY,
  };
}

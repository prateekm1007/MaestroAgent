// src/crypto.js — Encryption and hashing utilities.
//
// Provides:
//   - AES-256-GCM encryption for sensitive data (integration credentials, etc.)
//   - bcrypt hashing for API keys
//   - SHA-256 hashing for receipt integrity
//   - HMAC signing for webhooks
//
// Environment variables:
//   ENCRYPTION_KEY — 64-char hex string (32 bytes) for AES-256-GCM
//                    Generate with: openssl rand -hex 32

import crypto from 'node:crypto';
import bcrypt from 'bcryptjs';

const ALGORITHM = 'aes-256-gcm';
const IV_LENGTH = 16;
const AUTH_TAG_LENGTH = 16;
const BCRYPT_ROUNDS = 12;

/**
 * Get the encryption key from environment.
 * Falls back to a development key (NOT for production).
 * @returns {Buffer}
 */
function getEncryptionKey() {
  const key = process.env.ENCRYPTION_KEY;
  if (!key) {
    if (process.env.NODE_ENV === 'production') {
      throw new Error('ENCRYPTION_KEY must be set in production. Generate with: openssl rand -hex 32');
    }
    // Development fallback — DO NOT use in production
    console.warn('[crypto] WARNING: Using development encryption key. Set ENCRYPTION_KEY for production.');
    return crypto.scryptSync('maestro-dev-key', 'maestro-salt', 32);
  }
  return Buffer.from(key, 'hex');
}

/**
 * Encrypt plaintext using AES-256-GCM.
 * Returns a JSON string containing iv, encrypted data, and auth tag.
 * @param {string} plaintext
 * @returns {string} JSON-encoded encrypted payload
 */
export function encrypt(plaintext) {
  if (!plaintext) return null;
  const key = getEncryptionKey();
  const iv = crypto.randomBytes(IV_LENGTH);
  const cipher = crypto.createCipheriv(ALGORITHM, key, iv);
  const encrypted = Buffer.concat([
    cipher.update(plaintext, 'utf8'),
    cipher.final(),
  ]);
  const authTag = cipher.getAuthTag();
  return JSON.stringify({
    v: 1, // version for future migration
    iv: iv.toString('hex'),
    data: encrypted.toString('hex'),
    tag: authTag.toString('hex'),
  });
}

/**
 * Decrypt a JSON-encoded encrypted payload.
 * @param {string} encryptedJson
 * @returns {string} plaintext
 */
export function decrypt(encryptedJson) {
  if (!encryptedJson) return null;
  const payload = JSON.parse(encryptedJson);
  if (payload.v !== 1) {
    throw new Error(`Unsupported encryption version: ${payload.v}`);
  }
  const key = getEncryptionKey();
  const decipher = crypto.createDecipheriv(
    ALGORITHM,
    key,
    Buffer.from(payload.iv, 'hex')
  );
  decipher.setAuthTag(Buffer.from(payload.tag, 'hex'));
  const decrypted = Buffer.concat([
    decipher.update(Buffer.from(payload.data, 'hex')),
    decipher.final(),
  ]);
  return decrypted.toString('utf8');
}

/**
 * Hash a value using bcrypt (for API keys).
 * @param {string} value
 * @returns {Promise<string>} bcrypt hash
 */
export async function hashValue(value) {
  return bcrypt.hash(value, BCRYPT_ROUNDS);
}

/**
 * Verify a value against a bcrypt hash.
 * @param {string} value
 * @param {string} hash
 * @returns {Promise<boolean>}
 */
export async function verifyHash(value, hash) {
  return bcrypt.compare(value, hash);
}

/**
 * Compute SHA-256 hash of content (for receipt integrity).
 * @param {string|object} content
 * @returns {string} hex-encoded hash
 */
export function sha256(content) {
  const text = typeof content === 'string' ? content : JSON.stringify(content);
  return crypto.createHash('sha256').update(text).digest('hex');
}

/**
 * Compute HMAC-SHA256 signature (for webhook verification).
 * @param {string} secret
 * @param {string|Buffer} payload
 * @returns {string} hex-encoded signature
 */
export function hmacSha256(secret, payload) {
  return crypto
    .createHmac('sha256', secret)
    .update(payload)
    .digest('hex');
}

/**
 * Generate a cryptographically random token.
 * @param {number} bytes - Number of random bytes (default: 32)
 * @returns {string} hex-encoded token
 */
export function generateToken(bytes = 32) {
  return crypto.randomBytes(bytes).toString('hex');
}

/**
 * Constant-time string comparison (to prevent timing attacks).
 * @param {string} a
 * @param {string} b
 * @returns {boolean}
 */
export function safeEqual(a, b) {
  const bufA = Buffer.from(a, 'utf8');
  const bufB = Buffer.from(b, 'utf8');
  if (bufA.length !== bufB.length) return false;
  return crypto.timingSafeEqual(bufA, bufB);
}

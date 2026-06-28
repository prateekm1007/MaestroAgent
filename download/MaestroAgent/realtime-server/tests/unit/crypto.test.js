// tests/unit/crypto.test.js — Unit tests for src/crypto.js

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { encrypt, decrypt, hashValue, verifyHash, sha256, hmacSha256, generateToken, safeEqual } from '../../src/crypto.js';

describe('crypto', () => {
  describe('encrypt / decrypt', () => {
    it('should encrypt and decrypt a string', () => {
      const plaintext = 'my secret integration token';
      const encrypted = encrypt(plaintext);
      expect(encrypted).not.toBe(plaintext);
      expect(encrypted).toContain('"iv"');
      expect(encrypted).toContain('"data"');
      expect(encrypted).toContain('"tag"');

      const decrypted = decrypt(encrypted);
      expect(decrypted).toBe(plaintext);
    });

    it('should produce different ciphertexts for the same input (random IV)', () => {
      const plaintext = 'same input';
      const enc1 = encrypt(plaintext);
      const enc2 = encrypt(plaintext);
      expect(enc1).not.toBe(enc2);
      expect(decrypt(enc1)).toBe(plaintext);
      expect(decrypt(enc2)).toBe(plaintext);
    });

    it('should handle empty input', () => {
      expect(encrypt(null)).toBeNull();
      expect(encrypt('')).toBeNull(); // empty string is falsy, returns null
    });

    it('should handle unicode', () => {
      const plaintext = 'héllo wörld 你好世界 🔐';
      const decrypted = decrypt(encrypt(plaintext));
      expect(decrypted).toBe(plaintext);
    });
  });

  describe('hashValue / verifyHash', () => {
    it('should hash and verify a value', async () => {
      const value = 'my_api_key_12345';
      const hash = await hashValue(value);
      expect(hash).not.toBe(value);
      expect(await verifyHash(value, hash)).toBe(true);
      expect(await verifyHash('wrong_value', hash)).toBe(false);
    });

    it('should produce different hashes for the same input (bcrypt salt)', async () => {
      const value = 'same_password';
      const hash1 = await hashValue(value);
      const hash2 = await hashValue(value);
      expect(hash1).not.toBe(hash2);
      expect(await verifyHash(value, hash1)).toBe(true);
      expect(await verifyHash(value, hash2)).toBe(true);
    });
  });

  describe('sha256', () => {
    it('should produce a consistent hash', () => {
      const content = { test: 'data', num: 42 };
      const hash1 = sha256(content);
      const hash2 = sha256(content);
      expect(hash1).toBe(hash2);
      expect(hash1).toHaveLength(64); // 32 bytes hex = 64 chars
    });

    it('should produce different hashes for different content', () => {
      expect(sha256('a')).not.toBe(sha256('b'));
    });
  });

  describe('hmacSha256', () => {
    it('should produce a valid HMAC', () => {
      const sig = hmacSha256('secret', 'payload');
      expect(sig).toHaveLength(64);
      expect(sig).toMatch(/^[0-9a-f]+$/);
    });

    it('should produce different HMACs for different secrets', () => {
      expect(hmacSha256('secret1', 'payload')).not.toBe(hmacSha256('secret2', 'payload'));
    });
  });

  describe('generateToken', () => {
    it('should generate a random hex token', () => {
      const token = generateToken(32);
      expect(token).toHaveLength(64); // 32 bytes hex = 64 chars
      expect(token).toMatch(/^[0-9a-f]+$/);
    });

    it('should generate unique tokens', () => {
      const tokens = new Set();
      for (let i = 0; i < 100; i++) {
        tokens.add(generateToken(16));
      }
      expect(tokens.size).toBe(100);
    });
  });

  describe('safeEqual', () => {
    it('should return true for equal strings', () => {
      expect(safeEqual('hello', 'hello')).toBe(true);
    });

    it('should return false for different strings', () => {
      expect(safeEqual('hello', 'world')).toBe(false);
    });

    it('should return false for different-length strings', () => {
      expect(safeEqual('short', 'longer')).toBe(false);
    });
  });
});

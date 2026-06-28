// tests/unit/kms.test.js — Unit tests for src/kms.js

import { describe, it, expect, beforeEach } from 'vitest';
import { envelopeEncrypt, envelopeDecrypt, getKMSStatus } from '../../src/kms.js';

describe('kms (local provider)', () => {
  describe('envelopeEncrypt / envelopeDecrypt', () => {
    it('should encrypt and decrypt with envelope encryption', async () => {
      const plaintext = 'my-super-secret-oauth-token';
      const encrypted = await envelopeEncrypt(plaintext);

      expect(encrypted).not.toBe(plaintext);
      const envelope = JSON.parse(encrypted);
      expect(envelope.v).toBe(2);
      expect(envelope.iv).toBeTruthy();
      expect(envelope.data).toBeTruthy();
      expect(envelope.tag).toBeTruthy();
      expect(envelope.encryptedKey).toBeTruthy();
      expect(envelope.keyId).toBeTruthy();

      const decrypted = await envelopeDecrypt(encrypted);
      expect(decrypted).toBe(plaintext);
    });

    it('should produce different ciphertexts for same input (random IV)', async () => {
      const plaintext = 'same secret';
      const enc1 = await envelopeEncrypt(plaintext);
      const enc2 = await envelopeEncrypt(plaintext);
      expect(enc1).not.toBe(enc2);

      expect(await envelopeDecrypt(enc1)).toBe(plaintext);
      expect(await envelopeDecrypt(enc2)).toBe(plaintext);
    });

    it('should handle null input', async () => {
      expect(await envelopeEncrypt(null)).toBeNull();
      expect(await envelopeDecrypt(null)).toBeNull();
    });

    it('should handle unicode', async () => {
      const plaintext = 'héllo wörld 你好世界 🔐';
      const decrypted = await envelopeDecrypt(await envelopeEncrypt(plaintext));
      expect(decrypted).toBe(plaintext);
    });

    it('should handle long strings', async () => {
      const plaintext = 'x'.repeat(100000);
      const decrypted = await envelopeDecrypt(await envelopeEncrypt(plaintext));
      expect(decrypted).toBe(plaintext);
    });

    it('should handle JSON objects', async () => {
      const obj = JSON.stringify({ token: 'abc123', refresh: 'def456', expires: 1234567890 });
      const decrypted = await envelopeDecrypt(await envelopeEncrypt(obj));
      expect(JSON.parse(decrypted)).toEqual(JSON.parse(obj));
    });
  });

  describe('getKMSStatus', () => {
    it('should return KMS configuration', () => {
      const status = getKMSStatus();
      expect(status).toHaveProperty('provider');
      expect(status).toHaveProperty('keyId');
      expect(status).toHaveProperty('envelopeEncryption');
      expect(status).toHaveProperty('keyRotationEnabled');
      expect(status.envelopeEncryption).toBe(true);
      expect(status.keyRotationEnabled).toBe(true);
    });
  });
});

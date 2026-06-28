// Maestro v6 — Unit tests for server utilities
// Tests auth context, encryption, audit logging, SHR computation.

import { encrypt, decrypt, confidenceBucket, computeShr, isWithinShrBand, validateDecisionQuestion, ApiError } from '@/lib/server';

describe('Server utilities', () => {

  describe('Encryption', () => {
    const originalKey = process.env.ENCRYPTION_KEY;
    beforeAll(() => {
      process.env.ENCRYPTION_KEY = 'a'.repeat(64); // 32-byte hex
    });
    afterAll(() => {
      process.env.ENCRYPTION_KEY = originalKey;
    });

    it('encrypts and decrypts round-trip', () => {
      const plaintext = 'sk-super-secret-oauth-token-12345';
      const encrypted = encrypt(plaintext);
      const decrypted = decrypt(encrypted);
      expect(decrypted).toBe(plaintext);
    });

    it('produces different ciphertexts for same plaintext (random IV)', () => {
      const a = encrypt('same-text');
      const b = encrypt('same-text');
      expect(a.ciphertext.equals(b.ciphertext)).toBe(false);
      expect(a.iv.equals(b.iv)).toBe(false);
    });
  });

  describe('confidenceBucket()', () => {
    it('returns 0 for confidence 0.0–0.1', () => {
      expect(confidenceBucket(0.05)).toBe(0);
    });
    it('returns 9 for confidence 0.9–1.0', () => {
      expect(confidenceBucket(0.95)).toBe(9);
      expect(confidenceBucket(1.0)).toBe(9); // clamped
    });
    it('returns correct bucket for middle values', () => {
      expect(confidenceBucket(0.71)).toBe(7);
      expect(confidenceBucket(0.78)).toBe(7);
      expect(confidenceBucket(0.84)).toBe(8);
    });
  });

  describe('computeShr()', () => {
    it('returns 0 when no predictions', () => {
      expect(computeShr(0, 0)).toBe(0);
    });
    it('returns hits/total ratio', () => {
      expect(computeShr(19, 4)).toBeCloseTo(0.826, 2);
    });
    it('returns 1.0 when all hits', () => {
      expect(computeShr(10, 0)).toBe(1);
    });
  });

  describe('isWithinShrBand()', () => {
    it('returns true for 0.80–0.88', () => {
      expect(isWithinShrBand(0.80)).toBe(true);
      expect(isWithinShrBand(0.83)).toBe(true);
      expect(isWithinShrBand(0.88)).toBe(true);
    });
    it('returns false outside band', () => {
      expect(isWithinShrBand(0.79)).toBe(false);
      expect(isWithinShrBand(0.89)).toBe(false);
      expect(isWithinShrBand(0.95)).toBe(false);
    });
  });

  describe('validateDecisionQuestion()', () => {
    it('accepts valid DQ', () => {
      expect(() => validateDecisionQuestion('What must I decide today?')).not.toThrow();
    });
    it('rejects too-short DQ', () => {
      expect(() => validateDecisionQuestion('short?')).toThrow(ApiError);
    });
    it('rejects DQ without question mark', () => {
      expect(() => validateDecisionQuestion('what must i decide today')).toThrow(ApiError);
    });
  });

  describe('ApiError', () => {
    it('carries status, code, message', () => {
      const err = new ApiError(404, 'NOT_FOUND', 'Decision not found');
      expect(err.status).toBe(404);
      expect(err.code).toBe('NOT_FOUND');
      expect(err.message).toBe('Decision not found');
    });
  });
});

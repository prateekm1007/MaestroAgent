// tests/unit/security.test.js — Unit tests for src/security.js

import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  redactPII,
  containsPII,
  redactPIIFromObject,
  sanitizeInput,
  sanitizeGoal,
  verifyWebhookSignature,
  getSecurityStatus,
} from '../../src/security.js';

describe('security', () => {
  describe('redactPII', () => {
    it('should redact SSN', () => {
      const input = 'My SSN is 123-45-6789';
      const result = redactPII(input);
      expect(result).toBe('My SSN is [SSN-REDACTED]');
    });

    it('should redact email', () => {
      const input = 'Contact me at john@example.com';
      const result = redactPII(input);
      expect(result).toBe('Contact me at [EMAIL-REDACTED]');
    });

    it('should redact credit card numbers', () => {
      const input = 'Card: 4532015112830366';
      const result = redactPII(input);
      expect(result).toBe('Card: [CARD-REDACTED]');
    });

    it('should redact phone numbers', () => {
      const input = 'Call (555) 123-4567';
      const result = redactPII(input);
      expect(result).toContain('[PHONE-REDACTED]');
      expect(result).not.toContain('555');
    });

    it('should redact API keys', () => {
      const input = 'Key: mstr_' + 'a'.repeat(64);
      const result = redactPII(input);
      expect(result).toContain('[API-KEY-REDACTED]');
    });

    it('should redact OpenAI-style keys', () => {
      const input = 'Key: sk-' + 'a'.repeat(20);
      const result = redactPII(input);
      expect(result).toContain('[API-KEY-REDACTED]');
    });

    it('should redact Bearer tokens', () => {
      const input = 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.test';
      const result = redactPII(input);
      expect(result).toContain('[TOKEN-REDACTED]');
    });

    it('should redact private IP addresses', () => {
      const input = 'Server at 192.168.1.100';
      const result = redactPII(input);
      expect(result).toContain('[IP-REDACTED]');
    });

    it('should handle non-string input', () => {
      expect(redactPII(null)).toBeNull();
      expect(redactPII(undefined)).toBeUndefined();
      expect(redactPII(123)).toBe(123);
    });

    it('should redact multiple PII types in one string', () => {
      const input = 'Email: john@test.com, Phone: 555-123-4567, SSN: 111-22-3333';
      const result = redactPII(input);
      expect(result).toContain('[EMAIL-REDACTED]');
      expect(result).toContain('[PHONE-REDACTED]');
      expect(result).toContain('[SSN-REDACTED]');
    });
  });

  describe('containsPII', () => {
    it('should detect PII', () => {
      expect(containsPII('My email is test@example.com')).toBe(true);
      expect(containsPII('SSN: 123-45-6789')).toBe(true);
    });

    it('should return false for clean text', () => {
      expect(containsPII('Hello world')).toBe(false);
    });

    it('should handle non-string', () => {
      expect(containsPII(null)).toBe(false);
      expect(containsPII(123)).toBe(false);
    });
  });

  describe('redactPIIFromObject', () => {
    it('should redact PII in object fields', () => {
      const obj = { name: 'John', email: 'john@test.com', meta: { ssn: '123-45-6789' } };
      const result = redactPIIFromObject(obj);
      expect(result.email).toBe('[EMAIL-REDACTED]');
      expect(result.meta.ssn).toBe('[SSN-REDACTED]');
    });

    it('should skip specified fields', () => {
      const obj = { email: 'john@test.com', name: 'John' };
      const result = redactPIIFromObject(obj, ['email']);
      expect(result.email).toBe('john@test.com');
    });

    it('should handle arrays', () => {
      const arr = [{ email: 'a@test.com' }, { email: 'b@test.com' }];
      const result = redactPIIFromObject(arr);
      expect(result[0].email).toBe('[EMAIL-REDACTED]');
      expect(result[1].email).toBe('[EMAIL-REDACTED]');
    });
  });

  describe('sanitizeInput', () => {
    it('should remove null bytes', () => {
      expect(sanitizeInput('hello\0world')).toBe('helloworld');
    });

    it('should trim whitespace', () => {
      expect(sanitizeInput('  hello  ')).toBe('hello');
    });

    it('should limit length', () => {
      const long = 'a'.repeat(20000);
      expect(sanitizeInput(long, 100)).toHaveLength(100);
    });

    it('should handle non-string', () => {
      expect(sanitizeInput(null)).toBe('');
      expect(sanitizeInput(undefined)).toBe('');
    });
  });

  describe('sanitizeGoal', () => {
    it('should remove script tags', () => {
      const result = sanitizeGoal('Write <script>alert(1)</script> code');
      expect(result).not.toContain('<script>');
      expect(result).toContain('[SCRIPT-REMOVED]');
    });

    it('should remove iframe tags', () => {
      const result = sanitizeGoal('Test <iframe src="evil.com"></iframe> page');
      expect(result).not.toContain('<iframe>');
    });

    it('should remove code blocks', () => {
      const result = sanitizeGoal('Test ```javascript\nalert(1)\n``` code');
      expect(result).toContain('[CODE-BLOCK-REMOVED]');
    });
  });

  describe('verifyWebhookSignature', () => {
    it('should verify a valid signature', () => {
      const crypto = require('node:crypto');
      const secret = 'test-secret';
      const payload = '{"event":"test"}';
      const signature = crypto.createHmac('sha256', secret).update(payload).digest('hex');

      expect(verifyWebhookSignature(secret, payload, signature)).toBe(true);
    });

    it('should verify with prefix', () => {
      const crypto = require('node:crypto');
      const secret = 'test-secret';
      const payload = '{"event":"test"}';
      const signature = 'sha256=' + crypto.createHmac('sha256', secret).update(payload).digest('hex');

      expect(verifyWebhookSignature(secret, payload, signature, 'sha256=')).toBe(true);
    });

    it('should reject invalid signature', () => {
      expect(verifyWebhookSignature('secret', 'payload', 'invalid')).toBe(false);
    });

    it('should reject missing parameters', () => {
      expect(verifyWebhookSignature(null, 'payload', 'sig')).toBe(false);
      expect(verifyWebhookSignature('secret', null, 'sig')).toBe(false);
      expect(verifyWebhookSignature('secret', 'payload', null)).toBe(false);
    });
  });

  describe('getSecurityStatus', () => {
    it('should return security configuration', () => {
      const status = getSecurityStatus();
      expect(status).toHaveProperty('tls');
      expect(status).toHaveProperty('encryption');
      expect(status).toHaveProperty('pii_redaction');
      expect(status).toHaveProperty('rate_limiting');
      expect(status).toHaveProperty('security_headers');
      expect(status).toHaveProperty('audit_logging');
      expect(status.encryption.algorithm).toBe('aes-256-gcm');
      expect(status.encryption.envelope_encryption).toBe(true);
    });
  });
});

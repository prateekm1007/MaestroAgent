// tests/unit/sso.test.js — Unit tests for src/sso.js (non-network parts)

import { describe, it, expect } from 'vitest';
import { getSSOStatus, SSO_ENABLED } from '../../src/sso.js';

describe('sso', () => {
  describe('SSO_ENABLED', () => {
    it('should be a boolean', () => {
      expect(typeof SSO_ENABLED).toBe('boolean');
    });

    it('should be false when AUTH0_DOMAIN is not set', () => {
      // In test environment, AUTH0_DOMAIN is not set
      expect(SSO_ENABLED).toBe(false);
    });
  });

  describe('getSSOStatus', () => {
    it('should return enabled=false when not configured', () => {
      const status = getSSOStatus();
      expect(status.enabled).toBe(false);
      expect(status.domain).toBeNull();
      expect(status.client_id).toBeNull();
      expect(status.callback_url).toBeNull();
    });
  });
});

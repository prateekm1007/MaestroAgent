// tests/unit/auth.test.js — Unit tests for src/auth.js (non-DB parts)

import { describe, it, expect } from 'vitest';
import {
  PERMISSIONS,
  getPermissionsForRole,
  hasPermission,
  AuthError,
  generateAccessToken,
} from '../../src/auth.js';

describe('auth (non-DB)', () => {
  describe('PERMISSIONS', () => {
    it('should export all expected permissions', () => {
      expect(PERMISSIONS.RUN_CREATE).toBe('runs:create');
      expect(PERMISSIONS.RUN_READ_OWN).toBe('runs:read:own');
      expect(PERMISSIONS.POLICY_MANAGE).toBe('policy:manage');
      expect(PERMISSIONS.USER_MANAGE).toBe('user:manage');
      expect(PERMISSIONS.API_KEY_MANAGE).toBe('api_key:manage');
      expect(PERMISSIONS.RECEIPT_EXPORT).toBe('receipt:export');
    });
  });

  describe('getPermissionsForRole', () => {
    it('should return all permissions for org_admin', () => {
      const perms = getPermissionsForRole('org_admin');
      expect(perms).toContain(PERMISSIONS.RUN_CREATE);
      expect(perms).toContain(PERMISSIONS.POLICY_MANAGE);
      expect(perms).toContain(PERMISSIONS.USER_MANAGE);
      expect(perms).toContain(PERMISSIONS.BILLING_MANAGE);
      expect(perms.length).toBeGreaterThan(10);
    });

    it('should return limited permissions for org_member', () => {
      const perms = getPermissionsForRole('org_member');
      expect(perms).toContain(PERMISSIONS.RUN_CREATE);
      expect(perms).toContain(PERMISSIONS.FEEDBACK_GIVE);
      expect(perms).not.toContain(PERMISSIONS.POLICY_MANAGE);
      expect(perms).not.toContain(PERMISSIONS.USER_MANAGE);
    });

    it('should return minimal permissions for org_viewer', () => {
      const perms = getPermissionsForRole('org_viewer');
      expect(perms).toContain(PERMISSIONS.METRICS_READ);
      expect(perms).toContain(PERMISSIONS.RECEIPT_READ);
      expect(perms).not.toContain(PERMISSIONS.RUN_CREATE);
      expect(perms).not.toContain(PERMISSIONS.FEEDBACK_GIVE);
    });

    it('should return empty array for unknown role', () => {
      expect(getPermissionsForRole('unknown')).toEqual([]);
    });
  });

  describe('hasPermission', () => {
    it('should return true if user has the permission', () => {
      const user = {
        role: 'org_member',
        permissions: getPermissionsForRole('org_member'),
      };
      expect(hasPermission(user, PERMISSIONS.RUN_CREATE)).toBe(true);
      expect(hasPermission(user, PERMISSIONS.FEEDBACK_GIVE)).toBe(true);
    });

    it('should return false if user does not have the permission', () => {
      const user = {
        role: 'org_member',
        permissions: getPermissionsForRole('org_member'),
      };
      expect(hasPermission(user, PERMISSIONS.POLICY_MANAGE)).toBe(false);
      expect(hasPermission(user, PERMISSIONS.USER_MANAGE)).toBe(false);
    });

    it('should always return true for org_admin', () => {
      const user = {
        role: 'org_admin',
        permissions: [],
      };
      expect(hasPermission(user, PERMISSIONS.RUN_CREATE)).toBe(true);
      expect(hasPermission(user, PERMISSIONS.USER_MANAGE)).toBe(true);
      expect(hasPermission(user, 'any:permission')).toBe(true);
    });
  });

  describe('AuthError', () => {
    it('should create an error with message and status code', () => {
      const err = new AuthError('Not authorized', 403);
      expect(err.message).toBe('Not authorized');
      expect(err.statusCode).toBe(403);
      expect(err.name).toBe('AuthError');
    });

    it('should default to 401 status code', () => {
      const err = new AuthError('Unauthorized');
      expect(err.statusCode).toBe(401);
    });
  });

  describe('generateAccessToken', () => {
    it('should generate a valid JWT', () => {
      const user = {
        id: 'test-user-id',
        email: 'test@example.com',
        name: 'Test User',
        org_id: 'test-org-id',
        org_slug: 'test-org',
        org_name: 'Test Org',
        role: 'org_admin',
        department: null,
        team: null,
        permissions: getPermissionsForRole('org_admin'),
        auth_method: 'jwt',
      };

      const token = generateAccessToken(user);
      expect(token).toBeTruthy();
      expect(typeof token).toBe('string');
      expect(token.split('.')).toHaveLength(3); // header.payload.signature
    });
  });
});

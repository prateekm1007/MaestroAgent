// tests/unit/rbac.test.js — Unit tests for src/rbac.js

import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock db
vi.mock('../../src/db.js', () => ({
  query: vi.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
  withTransaction: vi.fn(async (fn) => fn({
    query: vi.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
  })),
  pool: {},
}));

// Mock auth
vi.mock('../../src/auth.js', () => ({
  PERMISSIONS: {
    RUN_CREATE: 'runs:create', RUN_READ_OWN: 'runs:read:own', RUN_READ_DEPT: 'runs:read:dept',
    RUN_READ_ORG: 'runs:read:org', FEEDBACK_GIVE: 'feedback:give', POLICY_MANAGE: 'policy:manage',
    INTEGRATION_MANAGE: 'integration:manage', USER_MANAGE: 'user:manage',
    BILLING_MANAGE: 'billing:manage', METRICS_READ: 'metrics:read',
    RECEIPT_READ: 'receipt:read', RECEIPT_EXPORT: 'receipt:export', API_KEY_MANAGE: 'api_key:manage',
  },
  getPermissionsForRole: vi.fn((role) => {
    const map = {
      org_admin: ['runs:create', 'runs:read:own', 'runs:read:dept', 'runs:read:org', 'policy:manage', 'user:manage', 'billing:manage', 'api_key:manage'],
      dept_lead: ['runs:create', 'runs:read:own', 'runs:read:dept', 'policy:manage', 'metrics:read'],
      org_member: ['runs:create', 'runs:read:own', 'feedback:give', 'metrics:read'],
      org_viewer: ['runs:read:own', 'metrics:read'],
    };
    return map[role] || [];
  }),
  hasPermission: vi.fn((user, perm) => {
    if (user.role === 'org_admin') return true;
    return (user.permissions || []).includes(perm);
  }),
  auditLog: vi.fn().mockResolvedValue(undefined),
}));

import {
  ALL_PERMISSIONS,
  BUILT_IN_ROLES,
  can, canAny, canAll,
  canAccessResource,
  requirePerm, requireAnyPerm, requireAllPerms,
  requireRole, requireAdmin, requireDeptLeadOrHigher,
  authorize, authorizeRole,
  getRBACInfo,
} from '../../src/rbac.js';

describe('rbac', () => {
  describe('ALL_PERMISSIONS', () => {
    it('should contain all expected permissions', () => {
      const permValues = ALL_PERMISSIONS.map(p => p.value);
      expect(permValues).toContain('runs:create');
      expect(permValues).toContain('runs:read:own');
      expect(permValues).toContain('policy:manage');
      expect(permValues).toContain('user:manage');
      expect(permValues).toContain('role:manage');
      expect(permValues).toContain('simulation:run');
      expect(permValues).toContain('audit_log:view');
      expect(permValues.length).toBeGreaterThanOrEqual(20);
    });

    it('should have key, value, and description for each', () => {
      for (const perm of ALL_PERMISSIONS) {
        expect(perm.key).toBeTruthy();
        expect(perm.value).toBeTruthy();
        expect(perm.description).toBeTruthy();
      }
    });
  });

  describe('BUILT_IN_ROLES', () => {
    it('should have 4 built-in roles', () => {
      expect(Object.keys(BUILT_IN_ROLES)).toHaveLength(4);
      expect(BUILT_IN_ROLES.org_admin).toBeDefined();
      expect(BUILT_IN_ROLES.dept_lead).toBeDefined();
      expect(BUILT_IN_ROLES.org_member).toBeDefined();
      expect(BUILT_IN_ROLES.org_viewer).toBeDefined();
    });

    it('org_admin should have all permissions', () => {
      expect(BUILT_IN_ROLES.org_admin.permissions.length).toBe(ALL_PERMISSIONS.length);
    });

    it('org_viewer should have minimal permissions', () => {
      expect(BUILT_IN_ROLES.org_viewer.permissions).not.toContain('runs:create');
      expect(BUILT_IN_ROLES.org_viewer.permissions).not.toContain('policy:manage');
    });

    it('all built-in roles should have is_system=true', () => {
      for (const role of Object.values(BUILT_IN_ROLES)) {
        expect(role.is_system).toBe(true);
      }
    });
  });

  describe('can()', () => {
    it('should return true for org_admin on any permission', () => {
      const admin = { role: 'org_admin', permissions: [] };
      expect(can(admin, 'runs:create')).toBe(true);
      expect(can(admin, 'anything:whatever')).toBe(true);
    });

    it('should check permissions for non-admin', () => {
      const member = { role: 'org_member', permissions: ['runs:create', 'runs:read:own'] };
      expect(can(member, 'runs:create')).toBe(true);
      expect(can(member, 'policy:manage')).toBe(false);
    });

    it('should return false for null user', () => {
      expect(can(null, 'runs:create')).toBe(false);
    });
  });

  describe('canAny()', () => {
    it('should return true if user has any of the permissions', () => {
      const user = { role: 'org_member', permissions: ['runs:create'] };
      expect(canAny(user, ['runs:create', 'policy:manage'])).toBe(true);
    });

    it('should return false if user has none', () => {
      const user = { role: 'org_member', permissions: ['runs:create'] };
      expect(canAny(user, ['policy:manage', 'user:manage'])).toBe(false);
    });
  });

  describe('canAll()', () => {
    it('should return true if user has all permissions', () => {
      const user = { role: 'org_member', permissions: ['runs:create', 'runs:read:own'] };
      expect(canAll(user, ['runs:create', 'runs:read:own'])).toBe(true);
    });

    it('should return false if user is missing any', () => {
      const user = { role: 'org_member', permissions: ['runs:create'] };
      expect(canAll(user, ['runs:create', 'policy:manage'])).toBe(false);
    });
  });

  describe('canAccessResource()', () => {
    it('should allow org_admin access to any resource', () => {
      const admin = { id: 'admin-1', role: 'org_admin' };
      const resource = { owner_user_id: 'someone-else' };
      expect(canAccessResource(admin, resource)).toBe(true);
    });

    it('should allow owner access to own resource', () => {
      const user = { id: 'user-1', role: 'org_member' };
      const resource = { owner_user_id: 'user-1' };
      expect(canAccessResource(user, resource)).toBe(true);
    });

    it('should allow department access for same department', () => {
      const user = { id: 'user-1', role: 'dept_lead', department: 'Engineering', permissions: ['runs:read:dept'] };
      const resource = { owner_department: 'Engineering' };
      expect(canAccessResource(user, resource)).toBe(true);
    });

    it('should deny access for different department without org permission', () => {
      const user = { id: 'user-1', role: 'org_member', department: 'Engineering', permissions: ['runs:read:own'] };
      const resource = { owner_department: 'Marketing' };
      expect(canAccessResource(user, resource)).toBe(false);
    });

    it('should allow team access for same team', () => {
      const user = { id: 'user-1', role: 'org_member', team: 'Platform', permissions: ['runs:read:dept'] };
      const resource = { owner_team: 'Platform' };
      expect(canAccessResource(user, resource)).toBe(true);
    });

    it('should deny for null user or resource', () => {
      expect(canAccessResource(null, {})).toBe(false);
      expect(canAccessResource({}, null)).toBe(false);
    });
  });

  describe('requirePerm() middleware', () => {
    it('should call next() if user has permission', () => {
      const req = { user: { role: 'org_member', permissions: ['runs:create'] } };
      const res = { status: vi.fn().mockReturnThis(), json: vi.fn() };
      const next = vi.fn();
      requirePerm('runs:create')(req, res, next);
      expect(next).toHaveBeenCalled();
      expect(res.status).not.toHaveBeenCalled();
    });

    it('should return 403 if user lacks permission', () => {
      const req = { user: { role: 'org_member', permissions: ['runs:create'] } };
      const res = { status: vi.fn().mockReturnThis(), json: vi.fn() };
      const next = vi.fn();
      requirePerm('policy:manage')(req, res, next);
      expect(res.status).toHaveBeenCalledWith(403);
      expect(next).not.toHaveBeenCalled();
    });

    it('should return 401 if no user', () => {
      const req = {};
      const res = { status: vi.fn().mockReturnThis(), json: vi.fn() };
      const next = vi.fn();
      requirePerm('runs:create')(req, res, next);
      expect(res.status).toHaveBeenCalledWith(401);
    });
  });

  describe('requireAnyPerm() middleware', () => {
    it('should pass if user has any of the permissions', () => {
      const req = { user: { role: 'org_member', permissions: ['runs:create'] } };
      const res = { status: vi.fn().mockReturnThis(), json: vi.fn() };
      const next = vi.fn();
      requireAnyPerm(['runs:create', 'policy:manage'])(req, res, next);
      expect(next).toHaveBeenCalled();
    });

    it('should fail if user has none', () => {
      const req = { user: { role: 'org_member', permissions: ['runs:read:own'] } };
      const res = { status: vi.fn().mockReturnThis(), json: vi.fn() };
      const next = vi.fn();
      requireAnyPerm(['runs:create', 'policy:manage'])(req, res, next);
      expect(res.status).toHaveBeenCalledWith(403);
    });
  });

  describe('requireAllPerms() middleware', () => {
    it('should pass if user has all permissions', () => {
      const req = { user: { role: 'org_member', permissions: ['runs:create', 'runs:read:own'] } };
      const res = { status: vi.fn().mockReturnThis(), json: vi.fn() };
      const next = vi.fn();
      requireAllPerms(['runs:create', 'runs:read:own'])(req, res, next);
      expect(next).toHaveBeenCalled();
    });

    it('should fail if user is missing any', () => {
      const req = { user: { role: 'org_member', permissions: ['runs:create'] } };
      const res = { status: vi.fn().mockReturnThis(), json: vi.fn() };
      const next = vi.fn();
      requireAllPerms(['runs:create', 'policy:manage'])(req, res, next);
      expect(res.status).toHaveBeenCalledWith(403);
    });
  });

  describe('requireRole() middleware', () => {
    it('should pass if user has one of the required roles', () => {
      const req = { user: { role: 'org_admin' } };
      const res = { status: vi.fn().mockReturnThis(), json: vi.fn() };
      const next = vi.fn();
      requireRole('org_admin', 'dept_lead')(req, res, next);
      expect(next).toHaveBeenCalled();
    });

    it('should fail if user does not have any required role', () => {
      const req = { user: { role: 'org_member' } };
      const res = { status: vi.fn().mockReturnThis(), json: vi.fn() };
      const next = vi.fn();
      requireRole('org_admin')(req, res, next);
      expect(res.status).toHaveBeenCalledWith(403);
    });
  });

  describe('requireAdmin() middleware', () => {
    it('should pass for org_admin', () => {
      const req = { user: { role: 'org_admin' } };
      const res = { status: vi.fn().mockReturnThis(), json: vi.fn() };
      const next = vi.fn();
      requireAdmin(req, res, next);
      expect(next).toHaveBeenCalled();
    });

    it('should fail for non-admin', () => {
      const req = { user: { role: 'org_member' } };
      const res = { status: vi.fn().mockReturnThis(), json: vi.fn() };
      const next = vi.fn();
      requireAdmin(req, res, next);
      expect(res.status).toHaveBeenCalledWith(403);
    });
  });

  describe('requireDeptLeadOrHigher() middleware', () => {
    it('should pass for org_admin', () => {
      const req = { user: { role: 'org_admin' } };
      const res = { status: vi.fn().mockReturnThis(), json: vi.fn() };
      const next = vi.fn();
      requireDeptLeadOrHigher(req, res, next);
      expect(next).toHaveBeenCalled();
    });

    it('should pass for dept_lead', () => {
      const req = { user: { role: 'dept_lead' } };
      const res = { status: vi.fn().mockReturnThis(), json: vi.fn() };
      const next = vi.fn();
      requireDeptLeadOrHigher(req, res, next);
      expect(next).toHaveBeenCalled();
    });

    it('should fail for org_member', () => {
      const req = { user: { role: 'org_member' } };
      const res = { status: vi.fn().mockReturnThis(), json: vi.fn() };
      const next = vi.fn();
      requireDeptLeadOrHigher(req, res, next);
      expect(res.status).toHaveBeenCalledWith(403);
    });
  });

  describe('authorize() decorator', () => {
    it('should wrap a method with permission checking', () => {
      const handler = vi.fn();
      const descriptor = { value: handler };
      const decorator = authorize('runs:create');
      decorator(null, 'method', descriptor);

      const req = { user: { role: 'org_member', permissions: ['runs:create'] } };
      const res = { status: vi.fn().mockReturnThis(), json: vi.fn() };
      descriptor.value(req, res);
      expect(handler).toHaveBeenCalled();
    });

    it('should block if permission missing', () => {
      const handler = vi.fn();
      const descriptor = { value: handler };
      const decorator = authorize('policy:manage');
      decorator(null, 'method', descriptor);

      const req = { user: { role: 'org_member', permissions: ['runs:create'] } };
      const res = { status: vi.fn().mockReturnThis(), json: vi.fn() };
      descriptor.value(req, res);
      expect(res.status).toHaveBeenCalledWith(403);
      expect(handler).not.toHaveBeenCalled();
    });
  });

  describe('authorizeRole() decorator', () => {
    it('should wrap a method with role checking', () => {
      const handler = vi.fn();
      const descriptor = { value: handler };
      const decorator = authorizeRole('org_admin');
      decorator(null, 'method', descriptor);

      const req = { user: { role: 'org_admin' } };
      const res = { status: vi.fn().mockReturnThis(), json: vi.fn() };
      descriptor.value(req, res);
      expect(handler).toHaveBeenCalled();
    });
  });

  describe('getRBACInfo()', () => {
    it('should return complete RBAC configuration', () => {
      const info = getRBACInfo();
      expect(info.built_in_roles).toHaveLength(4);
      expect(info.all_permissions.length).toBeGreaterThanOrEqual(20);
      expect(info.custom_roles_supported).toBe(true);
      expect(info.role_hierarchy_supported).toBe(true);
      expect(info.department_hierarchy_supported).toBe(true);
      expect(info.team_hierarchy_supported).toBe(true);
      expect(info.context_specific_roles).toBe(true);
      expect(info.resource_ownership).toBe(true);
    });
  });
});

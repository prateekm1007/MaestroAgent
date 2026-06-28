// src/rbac.js — Enterprise Role-Based Access Control.
//
// Extends the basic RBAC in auth.js with:
//   - Custom org-defined roles (beyond the 4 built-in)
//   - Role hierarchy (parent roles inherit child permissions)
//   - Department/team hierarchy (parent departments contain child departments)
//   - Context-specific role assignments (user can be admin in dept A, member in dept B)
//   - Resource ownership checks (own | department | team | org)
//   - Authorization decorators for route protection
//   - Permission resolution (merge built-in + custom + context roles)
//
// Built-in roles (immutable, always available):
//   org_admin, dept_lead, org_member, org_viewer
//
// Custom roles (org-defined via custom_roles table):
//   Any org can create custom roles with specific permissions.
//   Custom roles can have parent roles (inherit permissions).
//
// Permission resolution order:
//   1. Built-in role permissions (from ROLE_PERMISSIONS in auth.js)
//   2. Custom role permissions (from role_permissions table)
//   3. Context-specific role assignments (from role_assignments table)
//   4. Effective permissions = union of all applicable roles

import { query } from './db.js';
import {
  PERMISSIONS,
  getPermissionsForRole,
  hasPermission as baseHasPermission,
  auditLog,
} from './auth.js';

// ============================================================================
// ALL PERMISSIONS (canonical list)
// ============================================================================

export const ALL_PERMISSIONS = [
  { key: 'RUN_CREATE', value: 'runs:create', description: 'Create new executions' },
  { key: 'RUN_READ_OWN', value: 'runs:read:own', description: 'Read own executions' },
  { key: 'RUN_READ_DEPT', value: 'runs:read:dept', description: 'Read department executions' },
  { key: 'RUN_READ_ORG', value: 'runs:read:org', description: 'Read all org executions' },
  { key: 'RUN_INTERRUPT', value: 'runs:interrupt', description: 'Interrupt a running execution' },
  { key: 'RUN_CANCEL', value: 'runs:cancel', description: 'Cancel a running execution' },
  { key: 'FEEDBACK_GIVE', value: 'feedback:give', description: 'Give feedback on executions' },
  { key: 'POLICY_MANAGE', value: 'policy:manage', description: 'Create, update, delete policies' },
  { key: 'POLICY_VIEW', value: 'policy:view', description: 'View policies' },
  { key: 'INTEGRATION_MANAGE', value: 'integration:manage', description: 'Connect, disconnect integrations' },
  { key: 'INTEGRATION_VIEW', value: 'integration:view', description: 'View integrations' },
  { key: 'USER_MANAGE', value: 'user:manage', description: 'Invite, remove, change roles of users' },
  { key: 'USER_VIEW', value: 'user:view', description: 'View org members' },
  { key: 'BILLING_MANAGE', value: 'billing:manage', description: 'Manage billing and subscription' },
  { key: 'BILLING_VIEW', value: 'billing:view', description: 'View billing information' },
  { key: 'METRICS_READ', value: 'metrics:read', description: 'View execution metrics' },
  { key: 'RECEIPT_READ', value: 'receipt:read', description: 'Read execution receipts' },
  { key: 'RECEIPT_EXPORT', value: 'receipt:export', description: 'Export receipts as PDF/CSV' },
  { key: 'API_KEY_MANAGE', value: 'api_key:manage', description: 'Create, revoke API keys' },
  { key: 'ROLE_MANAGE', value: 'role:manage', description: 'Create, update, delete custom roles' },
  { key: 'GOVERNANCE_VIEW', value: 'governance:view', description: 'View governance controls' },
  { key: 'GOVERNANCE_MANAGE', value: 'governance:manage', description: 'Manage governance controls' },
  { key: 'AUDIT_LOG_VIEW', value: 'audit_log:view', description: 'View audit log' },
  { key: 'SIMULATION_RUN', value: 'simulation:run', description: 'Run organizational simulations' },
  { key: 'BENCHMARK_VIEW', value: 'benchmark:view', description: 'View benchmark comparisons' },
  { key: 'OBSERVATORY_CONTRIBUTE', value: 'observatory:contribute', description: 'Contribute to observatory' },
];

// ============================================================================
// BUILT-IN ROLE DEFINITIONS (enhanced from auth.js)
// ============================================================================

export const BUILT_IN_ROLES = {
  org_admin: {
    name: 'Organization Admin',
    description: 'Full access to all organization resources and settings',
    permissions: ALL_PERMISSIONS.map(p => p.value),
    is_system: true,
  },
  dept_lead: {
    name: 'Department Lead',
    description: 'Manage department policies, view department executions and metrics',
    permissions: [
      'runs:create', 'runs:read:own', 'runs:read:dept', 'runs:interrupt',
      'feedback:give', 'policy:manage', 'policy:view',
      'metrics:read', 'receipt:read', 'user:view',
      'governance:view', 'audit_log:view',
    ],
    is_system: true,
  },
  org_member: {
    name: 'Organization Member',
    description: 'Create executions, give feedback, view own metrics',
    permissions: [
      'runs:create', 'runs:read:own', 'runs:interrupt',
      'feedback:give', 'metrics:read', 'receipt:read', 'policy:view',
      'integration:view', 'user:view',
    ],
    is_system: true,
  },
  org_viewer: {
    name: 'Organization Viewer',
    description: 'Read-only access to executions, metrics, and receipts',
    permissions: [
      'runs:read:own', 'metrics:read', 'receipt:read', 'policy:view',
      'integration:view', 'user:view',
    ],
    is_system: true,
  },
};

// ============================================================================
// CUSTOM ROLE MANAGEMENT
// ============================================================================

/**
 * Create a custom role for an organization.
 * @param {string} orgId
 * @param {string} name - Display name
 * @param {string} slug - URL-safe identifier
 * @param {string[]} permissions - List of permission strings
 * @param {string|null} parentRoleSlug - Parent role to inherit from
 * @param {string|null} description
 * @returns {Promise<object>} Created role
 */
export async function createCustomRole(orgId, name, slug, permissions, parentRoleSlug = null, description = null) {
  return await query(async (client) => {
    // Resolve parent role
    let parentRoleId = null;
    if (parentRoleSlug) {
      const parentResult = await client.query(
        'SELECT id FROM custom_roles WHERE org_id = $1 AND slug = $2',
        [orgId, parentRoleSlug]
      );
      if (parentResult.rows.length > 0) {
        parentRoleId = parentResult.rows[0].id;
      }
    }

    // Insert role
    const roleResult = await client.query(
      `INSERT INTO custom_roles (org_id, name, slug, description, parent_role_id, is_system)
       VALUES ($1, $2, $3, $4, $5, false)
       RETURNING *`,
      [orgId, name, slug, description, parentRoleId]
    );
    const role = roleResult.rows[0];

    // Insert permissions
    for (const permission of permissions) {
      await client.query(
        `INSERT INTO role_permissions (org_id, role_id, permission)
         VALUES ($1, $2, $3) ON CONFLICT DO NOTHING`,
        [orgId, role.id, permission]
      );
    }

    // If parent role exists, inherit its permissions too
    if (parentRoleId) {
      const parentPerms = await client.query(
        'SELECT permission FROM role_permissions WHERE role_id = $1',
        [parentRoleId]
      );
      for (const row of parentPerms.rows) {
        await client.query(
          `INSERT INTO role_permissions (org_id, role_id, permission)
           VALUES ($1, $2, $3) ON CONFLICT DO NOTHING`,
          [orgId, role.id, row.permission]
        );
      }
    }

    return role;
  });
}

/**
 * List all roles for an organization (built-in + custom).
 * @param {string} orgId
 * @returns {Promise<object[]>}
 */
export async function listRoles(orgId) {
  // Get custom roles with their permissions
  const customResult = await query(
    `SELECT cr.*, array_agg(rp.permission) as permissions
     FROM custom_roles cr
     LEFT JOIN role_permissions rp ON rp.role_id = cr.id
     WHERE cr.org_id = $1
     GROUP BY cr.id
     ORDER BY cr.is_system DESC, cr.name`,
    [orgId]
  );

  const roles = [];

  // Add built-in roles
  for (const [slug, def] of Object.entries(BUILT_IN_ROLES)) {
    roles.push({
      id: null,
      slug,
      name: def.name,
      description: def.description,
      permissions: def.permissions,
      is_system: true,
      parent_role_id: null,
    });
  }

  // Add custom roles
  for (const row of customResult.rows) {
    roles.push({
      id: row.id,
      slug: row.slug,
      name: row.name,
      description: row.description,
      permissions: row.permissions?.filter(Boolean) || [],
      is_system: row.is_system,
      parent_role_id: row.parent_role_id,
    });
  }

  return roles;
}

/**
 * Get effective permissions for a user in an org context.
 * Merges built-in role + custom role + context-specific assignments.
 *
 * @param {string} userId
 * @param {string} orgId
 * @param {string} baseRole - The user's base role from organization_members
 * @param {string|null} department - Department name
 * @param {string|null} team - Team name
 * @returns {Promise<string[]>} Effective permissions
 */
export async function getEffectivePermissions(userId, orgId, baseRole, department = null, team = null) {
  let permissions = new Set();

  // 1. Built-in role permissions
  const builtInPerms = getPermissionsForRole(baseRole);
  builtInPerms.forEach(p => permissions.add(p));

  // 2. Custom role permissions (if user has a custom role assignment)
  const customAssignments = await query(
    `SELECT rp.permission
     FROM role_assignments ra
     JOIN role_permissions rp ON rp.role_id = ra.role_id
     WHERE ra.org_id = $1 AND ra.user_id = $2
     AND (ra.scope_type = 'org' OR ra.scope_id IS NULL)`,
    [orgId, userId]
  );
  customAssignments.rows.forEach(r => permissions.add(r.permission));

  // 3. Context-specific role assignments (department/team level)
  if (department || team) {
    const contextAssignments = await query(
      `SELECT rp.permission, ra.role_name
       FROM role_assignments ra
       JOIN role_permissions rp ON rp.role_id = ra.role_id
       WHERE ra.org_id = $1 AND ra.user_id = $2
       AND ra.scope_type IN ('department', 'team')`,
      [orgId, userId]
    );
    contextAssignments.rows.forEach(r => permissions.add(r.permission));

    // Also get built-in permissions from context role names
    const contextRoles = await query(
      `SELECT DISTINCT role_name FROM role_assignments
       WHERE org_id = $1 AND user_id = $2 AND scope_type IN ('department', 'team')`,
      [orgId, userId]
    );
    contextRoles.rows.forEach(r => {
      const rolePerms = getPermissionsForRole(r.role_name);
      rolePerms.forEach(p => permissions.add(p));
    });
  }

  // 4. If org_admin, grant everything
  if (baseRole === 'org_admin') {
    ALL_PERMISSIONS.forEach(p => permissions.add(p.value));
  }

  return Array.from(permissions);
}

// ============================================================================
// AUTHORIZATION CHECKS
// ============================================================================

/**
 * Check if a user has a specific permission.
 * Uses cached permissions from the JWT/API key.
 *
 * @param {object} user - The authenticated user from authMiddleware
 * @param {string} permission - Permission string (e.g. 'runs:create')
 * @returns {boolean}
 */
export function can(user, permission) {
  if (!user) return false;
  if (user.role === 'org_admin') return true;
  return (user.permissions || []).includes(permission);
}

/**
 * Check if a user has ANY of the specified permissions.
 * @param {object} user
 * @param {string[]} permissions
 * @returns {boolean}
 */
export function canAny(user, permissions) {
  return permissions.some(p => can(user, p));
}

/**
 * Check if a user has ALL of the specified permissions.
 * @param {object} user
 * @param {string[]} permissions
 * @returns {boolean}
 */
export function canAll(user, permissions) {
  return permissions.every(p => can(user, p));
}

/**
 * Check if a user can access a specific resource.
 * Considers ownership, department, and team scope.
 *
 * @param {object} user - Authenticated user
 * @param {object} resource - The resource to check (must have owner_user_id or owner_department)
 * @param {string} readPermission - The permission needed for non-own resources
 * @returns {boolean}
 */
export function canAccessResource(user, resource, readPermission = 'runs:read:org') {
  if (!user || !resource) return false;
  if (user.role === 'org_admin') return true;

  // Own resource
  if (resource.owner_user_id === user.id || resource.user_id === user.id) {
    return true;
  }

  // Same department
  if (resource.owner_department && user.department === resource.owner_department) {
    return can(user, 'runs:read:dept') || can(user, readPermission);
  }

  // Same team
  if (resource.owner_team && user.team === resource.owner_team) {
    return can(user, 'runs:read:dept') || can(user, readPermission);
  }

  // Org-wide access
  return can(user, readPermission);
}

// ============================================================================
// AUTHORIZATION MIDDLEWARE (Express)
// ============================================================================

/**
 * Middleware: Require a specific permission.
 * @param {string} permission
 */
export function requirePerm(permission) {
  return (req, res, next) => {
    if (!req.user) {
      return res.status(401).json({ error: 'Authentication required' });
    }
    if (!can(req.user, permission)) {
      return res.status(403).json({
        error: 'Insufficient permissions',
        required: permission,
        user_role: req.user.role,
      });
    }
    next();
  };
}

/**
 * Middleware: Require ANY of the specified permissions.
 * @param {string[]} permissions
 */
export function requireAnyPerm(permissions) {
  return (req, res, next) => {
    if (!req.user) {
      return res.status(401).json({ error: 'Authentication required' });
    }
    if (!canAny(req.user, permissions)) {
      return res.status(403).json({
        error: 'Insufficient permissions',
        required_any_of: permissions,
        user_role: req.user.role,
      });
    }
    next();
  };
}

/**
 * Middleware: Require ALL of the specified permissions.
 * @param {string[]} permissions
 */
export function requireAllPerms(permissions) {
  return (req, res, next) => {
    if (!req.user) {
      return res.status(401).json({ error: 'Authentication required' });
    }
    if (!canAll(req.user, permissions)) {
      return res.status(403).json({
        error: 'Insufficient permissions',
        required_all_of: permissions,
        user_role: req.user.role,
      });
    }
    next();
  };
}

/**
 * Middleware: Require one of the specified roles.
 * @param {string[]} roles
 */
export function requireRole(...roles) {
  return (req, res, next) => {
    if (!req.user) {
      return res.status(401).json({ error: 'Authentication required' });
    }
    if (!roles.includes(req.user.role)) {
      return res.status(403).json({
        error: 'Insufficient role',
        required_roles: roles,
        user_role: req.user.role,
      });
    }
    next();
  };
}

/**
 * Middleware: Require org admin or higher.
 */
export function requireAdmin(req, res, next) {
  if (!req.user) {
    return res.status(401).json({ error: 'Authentication required' });
  }
  if (req.user.role !== 'org_admin') {
    return res.status(403).json({
      error: 'Organization admin role required',
      user_role: req.user.role,
    });
  }
  next();
}

/**
 * Middleware: Require department lead or higher.
 */
export function requireDeptLeadOrHigher(req, res, next) {
  if (!req.user) {
    return res.status(401).json({ error: 'Authentication required' });
  }
  const allowedRoles = ['org_admin', 'dept_lead'];
  if (!allowedRoles.includes(req.user.role)) {
    return res.status(403).json({
      error: 'Department lead or admin role required',
      user_role: req.user.role,
    });
  }
  next();
}

/**
 * Middleware: Resource ownership check.
 * Loads the resource and verifies the user can access it.
 *
 * @param {string} resourceType - Type of resource
 * @param {string} idParam - URL parameter name containing the resource ID
 * @param {string} readPermission - Permission for non-owned resources
 */
export function requireResourceAccess(resourceType, idParam = 'id', readPermission = 'runs:read:org') {
  return async (req, res, next) => {
    if (!req.user) {
      return res.status(401).json({ error: 'Authentication required' });
    }

    const resourceId = req.params[idParam];
    if (!resourceId) {
      return res.status(400).json({ error: `Missing parameter: ${idParam}` });
    }

    // Check resource ownership
    const ownership = await query(
      `SELECT * FROM resource_ownership
       WHERE org_id = $1 AND resource_type = $2 AND resource_id = $3`,
      [req.user.org_id, resourceType, resourceId]
    );

    if (ownership.rows.length === 0) {
      // No ownership record — fall back to permission check
      if (!can(req.user, readPermission)) {
        return res.status(403).json({ error: 'Access denied to this resource' });
      }
      return next();
    }

    const resource = ownership.rows[0];

    if (!canAccessResource(req.user, resource, readPermission)) {
      return res.status(403).json({ error: 'Access denied to this resource' });
    }

    req.resource = resource;
    next();
  };
}

// ============================================================================
// AUTHORIZATION DECORATORS (for route definitions)
// ============================================================================

/**
 * Wrap a route handler with permission checking.
 * Usage:
 *   router.post('/runs', authorize('runs:create'), createRun)
 *
 * @param {string} permission
 */
export function authorize(permission) {
  return function(target, propertyKey, descriptor) {
    const originalMethod = descriptor.value;
    descriptor.value = function(req, res, next) {
      if (!req.user) {
        return res.status(401).json({ error: 'Authentication required' });
      }
      if (!can(req.user, permission)) {
        return res.status(403).json({
          error: 'Insufficient permissions',
          required: permission,
        });
      }
      return originalMethod.call(this, req, res, next);
    };
    return descriptor;
  };
}

/**
 * Wrap a route handler with role checking.
 * Usage:
 *   router.delete('/users/:id', authorizeRole('org_admin'), removeUser)
 *
 * @param {...string} roles
 */
export function authorizeRole(...roles) {
  return function(target, propertyKey, descriptor) {
    const originalMethod = descriptor.value;
    descriptor.value = function(req, res, next) {
      if (!req.user) {
        return res.status(401).json({ error: 'Authentication required' });
      }
      if (!roles.includes(req.user.role)) {
        return res.status(403).json({
          error: 'Insufficient role',
          required_roles: roles,
        });
      }
      return originalMethod.call(this, req, res, next);
    };
    return descriptor;
  };
}

// ============================================================================
// DEPARTMENT / TEAM HIERARCHY MANAGEMENT
// ============================================================================

/**
 * Create a department (optionally as child of a parent department).
 */
export async function createDepartment(orgId, name, parentId = null, description = null, headUserId = null) {
  const result = await query(
    `INSERT INTO departments (org_id, name, parent_id, description, head_user_id)
     VALUES ($1, $2, $3, $4, $5)
     ON CONFLICT (org_id, name) DO UPDATE SET parent_id = $3, description = $4, head_user_id = $5
     RETURNING *`,
    [orgId, name, parentId, description, headUserId]
  );
  return result.rows[0];
}

/**
 * Get a department and all its descendants (recursive).
 */
export async function getDepartmentTree(orgId, departmentId = null) {
  if (departmentId) {
    // Get specific department and its children
    const result = await query(
      `WITH RECURSIVE dept_tree AS (
         SELECT id, org_id, name, parent_id, description, head_user_id, 0 as depth
         FROM departments WHERE org_id = $1 AND id = $2
         UNION ALL
         SELECT d.id, d.org_id, d.name, d.parent_id, d.description, d.head_user_id, dt.depth + 1
         FROM departments d
         JOIN dept_tree dt ON d.parent_id = dt.id
       )
       SELECT * FROM dept_tree ORDER BY depth, name`,
      [orgId, departmentId]
    );
    return result.rows;
  }

  // Get all departments for org
  const result = await query(
    `SELECT * FROM departments WHERE org_id = $1 ORDER BY name`,
    [orgId]
  );
  return result.rows;
}

/**
 * Create a team (optionally as child of a parent team).
 */
export async function createTeam(orgId, name, departmentId = null, parentId = null, description = null, leadUserId = null) {
  const result = await query(
    `INSERT INTO teams (org_id, department_id, name, parent_id, description, lead_user_id)
     VALUES ($1, $2, $3, $4, $5, $6)
     ON CONFLICT (org_id, name) DO UPDATE SET department_id = $2, parent_id = $4, description = $5, lead_user_id = $6
     RETURNING *`,
    [orgId, departmentId, name, parentId, description, leadUserId]
  );
  return result.rows[0];
}

/**
 * Get all teams in a department (including sub-teams).
 */
export async function getTeamsInDepartment(orgId, departmentId) {
  const result = await query(
    `WITH RECURSIVE team_tree AS (
       SELECT id, org_id, department_id, name, parent_id, description, lead_user_id, 0 as depth
       FROM teams WHERE org_id = $1 AND department_id = $2
       UNION ALL
       SELECT t.id, t.org_id, t.department_id, t.name, t.parent_id, t.description, t.lead_user_id, tt.depth + 1
       FROM teams t
       JOIN team_tree tt ON t.parent_id = tt.id
     )
     SELECT * FROM team_tree ORDER BY depth, name`,
    [orgId, departmentId]
  );
  return result.rows;
}

/**
 * Check if a user belongs to a department (directly or via team).
 */
export async function isUserInDepartment(userId, orgId, departmentName) {
  const result = await query(
    `SELECT 1 FROM organization_members
     WHERE user_id = $1 AND org_id = $2 AND department = $3 AND status = 'active'
     UNION
     SELECT 1 FROM organization_members om
     JOIN teams t ON t.org_id = om.org_id AND t.name = om.team
     JOIN departments d ON d.id = t.department_id
     WHERE om.user_id = $1 AND om.org_id = $2 AND d.name = $3 AND om.status = 'active'`,
    [userId, orgId, departmentName]
  );
  return result.rows.length > 0;
}

// ============================================================================
// RESOURCE OWNERSHIP REGISTRATION
// ============================================================================

/**
 * Register resource ownership when a resource is created.
 * @param {string} orgId
 * @param {string} resourceType - run | receipt | artifact | etc.
 * @param {string} resourceId
 * @param {string|null} ownerUserId
 * @param {string|null} ownerDepartment
 * @param {string|null} ownerTeam
 * @param {boolean} isShared
 */
export async function registerResourceOwnership(orgId, resourceType, resourceId, ownerUserId = null, ownerDepartment = null, ownerTeam = null, isShared = false) {
  await query(
    `INSERT INTO resource_ownership (org_id, resource_type, resource_id, owner_user_id, owner_department, owner_team, is_shared)
     VALUES ($1, $2, $3, $4, $5, $6, $7)
     ON CONFLICT (org_id, resource_type, resource_id) DO UPDATE SET
       owner_user_id = $4, owner_department = $5, owner_team = $6, is_shared = $7`,
    [orgId, resourceType, resourceId, ownerUserId, ownerDepartment, ownerTeam, isShared]
  );
}

/**
 * Get resource ownership.
 */
export async function getResourceOwnership(orgId, resourceType, resourceId) {
  const result = await query(
    `SELECT * FROM resource_ownership WHERE org_id = $1 AND resource_type = $2 AND resource_id = $3`,
    [orgId, resourceType, resourceId]
  );
  return result.rows[0] || null;
}

// ============================================================================
// ROLE ASSIGNMENT MANAGEMENT
// ============================================================================

/**
 * Assign a role to a user in a specific context (org, department, or team).
 */
export async function assignRole(orgId, userId, roleName, scopeType = 'org', scopeId = null, assignedBy = null) {
  // Look up custom role if exists
  const customRole = await query(
    'SELECT id FROM custom_roles WHERE org_id = $1 AND slug = $2',
    [orgId, roleName]
  );
  const roleId = customRole.rows[0]?.id || null;

  await query(
    `INSERT INTO role_assignments (org_id, user_id, role_id, role_name, scope_type, scope_id, assigned_by)
     VALUES ($1, $2, $3, $4, $5, $6, $7)
     ON CONFLICT (org_id, user_id, role_name, scope_type, scope_id) DO NOTHING`,
    [orgId, userId, roleId, roleName, scopeType, scopeId, assignedBy]
  );

  await auditLog(orgId, assignedBy, 'user.role_assigned', {
    target_user: userId, role: roleName, scope_type: scopeType, scope_id: scopeId,
  });
}

/**
 * Remove a role assignment.
 */
export async function removeRoleAssignment(orgId, userId, roleName, scopeType = 'org', scopeId = null) {
  await query(
    `DELETE FROM role_assignments
     WHERE org_id = $1 AND user_id = $2 AND role_name = $3 AND scope_type = $4 AND scope_id = $5`,
    [orgId, userId, roleName, scopeType, scopeId]
  );
}

/**
 * Get all role assignments for a user.
 */
export async function getUserRoleAssignments(orgId, userId) {
  const result = await query(
    `SELECT * FROM role_assignments WHERE org_id = $1 AND user_id = $2 ORDER BY created_at`,
    [orgId, userId]
  );
  return result.rows;
}

// ============================================================================
// RBAC STATUS / INFO
// ============================================================================

export function getRBACInfo() {
  return {
    built_in_roles: Object.keys(BUILT_IN_ROLES).map(slug => ({
      slug,
      name: BUILT_IN_ROLES[slug].name,
      description: BUILT_IN_ROLES[slug].description,
      permissions: BUILT_IN_ROLES[slug].permissions,
      is_system: true,
    })),
    all_permissions: ALL_PERMISSIONS,
    custom_roles_supported: true,
    role_hierarchy_supported: true,
    department_hierarchy_supported: true,
    team_hierarchy_supported: true,
    context_specific_roles: true,
    resource_ownership: true,
  };
}

// src/routes/rbac.js — RBAC management API routes.
//
// Endpoints:
//   GET    /api/rbac/info                    — List all roles and permissions
//   GET    /api/rbac/roles                   — List org roles (built-in + custom)
//   POST   /api/rbac/roles                   — Create custom role (admin)
//   DELETE /api/rbac/roles/:slug             — Delete custom role (admin)
//   GET    /api/rbac/roles/:slug/permissions — List role permissions
//   POST   /api/rbac/roles/:slug/permissions — Add permission to role (admin)
//   DELETE /api/rbac/roles/:slug/permissions/:perm — Remove permission (admin)
//   GET    /api/rbac/departments             — List departments (tree)
//   POST   /api/rbac/departments             — Create department (admin)
//   GET    /api/rbac/departments/:id/tree    — Department subtree
//   GET    /api/rbac/teams                   — List teams
//   POST   /api/rbac/teams                   — Create team (admin)
//   GET    /api/rbac/teams?department_id=X   — Teams in department
//   GET    /api/rbac/assignments/:userId     — User's role assignments
//   POST   /api/rbac/assignments             — Assign role (admin)
//   DELETE /api/rbac/assignments             — Remove role assignment (admin)
//   POST   /api/rbac/ownership               — Register resource ownership
//   GET    /api/rbac/ownership/:type/:id     — Get resource ownership

import express from 'express';
import { authMiddleware } from '../auth.js';
import { requireAdmin, requirePerm } from '../rbac.js';
import {
  getRBACInfo,
  listRoles,
  createCustomRole,
  getEffectivePermissions,
  createDepartment,
  getDepartmentTree,
  createTeam,
  getTeamsInDepartment,
  assignRole,
  removeRoleAssignment,
  getUserRoleAssignments,
  registerResourceOwnership,
  getResourceOwnership,
} from '../rbac.js';
import { query } from '../db.js';

const router = express.Router();

// All routes require authentication
router.use(authMiddleware);

// ============================================================================
// RBAC INFO
// ============================================================================

router.get('/info', (req, res) => {
  res.json(getRBACInfo());
});

// ============================================================================
// ROLES
// ============================================================================

router.get('/roles', async (req, res) => {
  try {
    const roles = await listRoles(req.user.org_id);
    res.json({ roles });
  } catch (err) {
    console.error('[rbac] List roles error:', err);
    res.status(500).json({ error: 'Failed to list roles' });
  }
});

router.post('/roles', requireAdmin, async (req, res) => {
  const { name, slug, permissions, parent_role_slug, description } = req.body;
  if (!name || !slug || !permissions) {
    return res.status(400).json({ error: 'name, slug, and permissions are required' });
  }
  try {
    const role = await createCustomRole(req.user.org_id, name, slug, permissions, parent_role_slug, description);
    res.status(201).json(role);
  } catch (err) {
    console.error('[rbac] Create role error:', err);
    res.status(500).json({ error: 'Failed to create role' });
  }
});

router.delete('/roles/:slug', requireAdmin, async (req, res) => {
  try {
    await query(
      `DELETE FROM custom_roles WHERE org_id = $1 AND slug = $2 AND is_system = false`,
      [req.user.org_id, req.params.slug]
    );
    res.json({ ok: true });
  } catch (err) {
    console.error('[rbac] Delete role error:', err);
    res.status(500).json({ error: 'Failed to delete role' });
  }
});

// ============================================================================
// ROLE PERMISSIONS
// ============================================================================

router.get('/roles/:slug/permissions', async (req, res) => {
  try {
    const result = await query(
      `SELECT rp.permission FROM role_permissions rp
       JOIN custom_roles cr ON cr.id = rp.role_id
       WHERE cr.org_id = $1 AND cr.slug = $2`,
      [req.user.org_id, req.params.slug]
    );
    res.json({ permissions: result.rows.map(r => r.permission) });
  } catch (err) {
    console.error('[rbac] Get permissions error:', err);
    res.status(500).json({ error: 'Failed to get permissions' });
  }
});

router.post('/roles/:slug/permissions', requireAdmin, async (req, res) => {
  const { permission } = req.body;
  if (!permission) return res.status(400).json({ error: 'permission is required' });

  try {
    const roleResult = await query(
      'SELECT id FROM custom_roles WHERE org_id = $1 AND slug = $2',
      [req.user.org_id, req.params.slug]
    );
    if (roleResult.rows.length === 0) {
      return res.status(404).json({ error: 'Role not found' });
    }
    await query(
      'INSERT INTO role_permissions (org_id, role_id, permission) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING',
      [req.user.org_id, roleResult.rows[0].id, permission]
    );
    res.status(201).json({ ok: true });
  } catch (err) {
    console.error('[rbac] Add permission error:', err);
    res.status(500).json({ error: 'Failed to add permission' });
  }
});

router.delete('/roles/:slug/permissions/:perm', requireAdmin, async (req, res) => {
  try {
    const roleResult = await query(
      'SELECT id FROM custom_roles WHERE org_id = $1 AND slug = $2',
      [req.user.org_id, req.params.slug]
    );
    if (roleResult.rows.length === 0) {
      return res.status(404).json({ error: 'Role not found' });
    }
    await query(
      'DELETE FROM role_permissions WHERE role_id = $1 AND permission = $2',
      [roleResult.rows[0].id, req.params.perm]
    );
    res.json({ ok: true });
  } catch (err) {
    console.error('[rbac] Remove permission error:', err);
    res.status(500).json({ error: 'Failed to remove permission' });
  }
});

// ============================================================================
// DEPARTMENTS
// ============================================================================

router.get('/departments', async (req, res) => {
  try {
    const tree = await getDepartmentTree(req.user.org_id);
    res.json({ departments: tree });
  } catch (err) {
    console.error('[rbac] List departments error:', err);
    res.status(500).json({ error: 'Failed to list departments' });
  }
});

router.post('/departments', requireAdmin, async (req, res) => {
  const { name, parent_id, description, head_user_id } = req.body;
  if (!name) return res.status(400).json({ error: 'name is required' });
  try {
    const dept = await createDepartment(req.user.org_id, name, parent_id, description, head_user_id);
    res.status(201).json(dept);
  } catch (err) {
    console.error('[rbac] Create department error:', err);
    res.status(500).json({ error: 'Failed to create department' });
  }
});

router.get('/departments/:id/tree', async (req, res) => {
  try {
    const tree = await getDepartmentTree(req.user.org_id, req.params.id);
    res.json({ departments: tree });
  } catch (err) {
    console.error('[rbac] Department tree error:', err);
    res.status(500).json({ error: 'Failed to get department tree' });
  }
});

// ============================================================================
// TEAMS
// ============================================================================

router.get('/teams', async (req, res) => {
  try {
    const { department_id } = req.query;
    if (department_id) {
      const teams = await getTeamsInDepartment(req.user.org_id, department_id);
      return res.json({ teams });
    }
    const result = await query('SELECT * FROM teams WHERE org_id = $1 ORDER BY name', [req.user.org_id]);
    res.json({ teams: result.rows });
  } catch (err) {
    console.error('[rbac] List teams error:', err);
    res.status(500).json({ error: 'Failed to list teams' });
  }
});

router.post('/teams', requireAdmin, async (req, res) => {
  const { name, department_id, parent_id, description, lead_user_id } = req.body;
  if (!name) return res.status(400).json({ error: 'name is required' });
  try {
    const team = await createTeam(req.user.org_id, name, department_id, parent_id, description, lead_user_id);
    res.status(201).json(team);
  } catch (err) {
    console.error('[rbac] Create team error:', err);
    res.status(500).json({ error: 'Failed to create team' });
  }
});

// ============================================================================
// ROLE ASSIGNMENTS
// ============================================================================

router.get('/assignments/:userId', async (req, res) => {
  try {
    const assignments = await getUserRoleAssignments(req.user.org_id, req.params.userId);
    res.json({ assignments });
  } catch (err) {
    console.error('[rbac] Get assignments error:', err);
    res.status(500).json({ error: 'Failed to get assignments' });
  }
});

router.post('/assignments', requireAdmin, async (req, res) => {
  const { user_id, role_name, scope_type, scope_id } = req.body;
  if (!user_id || !role_name) {
    return res.status(400).json({ error: 'user_id and role_name are required' });
  }
  try {
    await assignRole(req.user.org_id, user_id, role_name, scope_type || 'org', scope_id, req.user.id);
    res.status(201).json({ ok: true });
  } catch (err) {
    console.error('[rbac] Assign role error:', err);
    res.status(500).json({ error: 'Failed to assign role' });
  }
});

router.delete('/assignments', requireAdmin, async (req, res) => {
  const { user_id, role_name, scope_type, scope_id } = req.body;
  if (!user_id || !role_name) {
    return res.status(400).json({ error: 'user_id and role_name are required' });
  }
  try {
    await removeRoleAssignment(req.user.org_id, user_id, role_name, scope_type || 'org', scope_id);
    res.json({ ok: true });
  } catch (err) {
    console.error('[rbac] Remove assignment error:', err);
    res.status(500).json({ error: 'Failed to remove assignment' });
  }
});

// ============================================================================
// RESOURCE OWNERSHIP
// ============================================================================

router.post('/ownership', async (req, res) => {
  const { resource_type, resource_id, owner_user_id, owner_department, owner_team, is_shared } = req.body;
  if (!resource_type || !resource_id) {
    return res.status(400).json({ error: 'resource_type and resource_id are required' });
  }
  try {
    await registerResourceOwnership(
      req.user.org_id, resource_type, resource_id,
      owner_user_id, owner_department, owner_team, is_shared
    );
    res.status(201).json({ ok: true });
  } catch (err) {
    console.error('[rbac] Register ownership error:', err);
    res.status(500).json({ error: 'Failed to register ownership' });
  }
});

router.get('/ownership/:type/:id', async (req, res) => {
  try {
    const ownership = await getResourceOwnership(req.user.org_id, req.params.type, req.params.id);
    if (!ownership) return res.status(404).json({ error: 'No ownership record found' });
    res.json(ownership);
  } catch (err) {
    console.error('[rbac] Get ownership error:', err);
    res.status(500).json({ error: 'Failed to get ownership' });
  }
});

// ============================================================================
// EFFECTIVE PERMISSIONS
// ============================================================================

router.get('/permissions/:userId', requireAdmin, async (req, res) => {
  try {
    // Get user's base role
    const memberResult = await query(
      `SELECT role, department, team FROM organization_members
       WHERE org_id = $1 AND user_id = $2 AND status = 'active'`,
      [req.user.org_id, req.params.userId]
    );
    if (memberResult.rows.length === 0) {
      return res.status(404).json({ error: 'User not found in this org' });
    }
    const { role, department, team } = memberResult.rows[0];
    const permissions = await getEffectivePermissions(req.params.userId, req.user.org_id, role, department, team);
    res.json({ role, department, team, permissions });
  } catch (err) {
    console.error('[rbac] Get effective permissions error:', err);
    res.status(500).json({ error: 'Failed to get effective permissions' });
  }
});

export default router;

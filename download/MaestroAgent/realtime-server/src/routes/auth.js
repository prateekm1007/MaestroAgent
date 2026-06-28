// src/routes/auth.js — Authentication API routes.
//
// Endpoints:
//   POST   /api/auth/register           — Register new user + org
//   POST   /api/auth/login              — Login with email + password
//   POST   /api/auth/refresh            — Refresh access token
//   POST   /api/auth/logout             — Logout (revoke refresh token)
//   POST   /api/auth/logout-all         — Logout all sessions
//   GET    /api/auth/me                 — Get current user
//   GET    /api/auth/orgs               — List user's organizations
//   POST   /api/auth/api-keys           — Create API key
//   GET    /api/auth/api-keys           — List API keys
//   DELETE /api/auth/api-keys/:id       — Revoke API key
//   POST   /api/auth/invite             — Invite user to org (admin)
//   POST   /api/auth/accept-invite      — Accept invitation
//   GET    /api/auth/audit-log          — View audit log (admin)
//   GET    /api/auth/users              — List org members (admin)
//   PATCH  /api/auth/users/:id/role     — Change member role (admin)
//   DELETE /api/auth/users/:id          — Remove member from org (admin)

import express from 'express';
import {
  authMiddleware,
  requirePermission,
  AuthError,
  PERMISSIONS,
  generateAccessToken,
  generateRefreshToken,
  rotateRefreshToken,
  revokeRefreshToken,
  revokeAllUserSessions,
  loginWithPassword,
  createUser,
  createOrganization,
  addOrgMember,
  getAuthUser,
  getUserOrganizations,
  findUserByEmail,
  createApiKey,
  listApiKeys,
  revokeApiKey,
  createInvitation,
  acceptInvitation,
  auditLog,
  getPermissionsForRole,
} from '../auth.js';
import { query } from '../db.js';
import cookieParser from 'cookie-parser';
import { generateToken } from '../crypto.js';

const router = express.Router();
router.use(cookieParser());

// Helper: extract client IP
function getIp(req) {
  return req.headers['x-forwarded-for']?.split(',')[0]?.trim() || req.socket?.remoteAddress || null;
}

function getUA(req) {
  return req.headers['user-agent'] || null;
}

// Helper: set auth cookies
function setAuthCookies(res, tokens) {
  const isProduction = process.env.NODE_ENV === 'production';
  res.cookie('access_token', tokens.access_token, {
    httpOnly: true,
    secure: isProduction,
    sameSite: 'strict',
    maxAge: 60 * 60 * 1000,
  });
  res.cookie('refresh_token', tokens.refresh_token, {
    httpOnly: true,
    secure: isProduction,
    sameSite: 'strict',
    maxAge: 30 * 24 * 60 * 60 * 1000,
  });
}

function clearAuthCookies(res) {
  res.clearCookie('access_token');
  res.clearCookie('refresh_token');
}

// ============================================================================
// REGISTER — Create new user + organization
// ============================================================================

router.post('/register', async (req, res) => {
  const { email, password, name, org_name, org_slug, industry } = req.body;

  if (!email || !password || !org_name || !org_slug) {
    return res.status(400).json({ error: 'email, password, org_name, and org_slug are required' });
  }
  if (password.length < 8) {
    return res.status(400).json({ error: 'Password must be at least 8 characters' });
  }
  if (!/^[a-z0-9-]+$/.test(org_slug.toLowerCase())) {
    return res.status(400).json({ error: 'org_slug must be lowercase alphanumeric with hyphens' });
  }

  const ipAddress = getIp(req);
  const userAgent = getUA(req);

  try {
    const existing = await findUserByEmail(email);
    if (existing) {
      return res.status(409).json({ error: 'Email already registered' });
    }

    const slugCheck = await query('SELECT id FROM organizations WHERE slug = $1', [org_slug.toLowerCase()]);
    if (slugCheck.rows.length > 0) {
      return res.status(409).json({ error: 'Organization slug already taken' });
    }

    const user = await createUser(email, password, name);
    const org = await createOrganization(org_name, org_slug, industry);
    await addOrgMember(org.id, user.id, 'org_admin');

    const authUser = await getAuthUser(user.id, org.id);

    const accessToken = generateAccessToken(authUser);
    const refreshToken = await generateRefreshToken(authUser, ipAddress, userAgent);

    await auditLog(org.id, user.id, 'auth.register', { email, org_slug });

    setAuthCookies(res, { access_token: accessToken, refresh_token: refreshToken });

    return res.status(201).json({
      user: {
        id: authUser.id,
        email: authUser.email,
        name: authUser.name,
        role: authUser.role,
      },
      organization: {
        id: org.id,
        name: org.name,
        slug: org.slug,
      },
      tokens: {
        access_token: accessToken,
        refresh_token: refreshToken,
        expires_in: 3600,
        token_type: 'Bearer',
      },
    });
  } catch (err) {
    console.error('[auth] Register error:', err);
    return res.status(500).json({ error: 'Registration failed' });
  }
});

// ============================================================================
// LOGIN
// ============================================================================

router.post('/login', async (req, res) => {
  const { email, password, org_slug } = req.body;

  if (!email || !password) {
    return res.status(400).json({ error: 'email and password are required' });
  }

  const ipAddress = getIp(req);
  const userAgent = getUA(req);

  try {
    const { tokens, user } = await loginWithPassword(email, password, org_slug || null, ipAddress, userAgent);
    setAuthCookies(res, tokens);
    return res.json({
      user: {
        id: user.id,
        email: user.email,
        name: user.name,
        role: user.role,
        org_id: user.org_id,
        org_name: user.org_name,
        org_slug: user.org_slug,
      },
      tokens,
    });
  } catch (err) {
    if (err instanceof AuthError) {
      return res.status(err.statusCode).json({ error: err.message });
    }
    console.error('[auth] Login error:', err);
    return res.status(500).json({ error: 'Login failed' });
  }
});

// ============================================================================
// REFRESH TOKEN
// ============================================================================

router.post('/refresh', async (req, res) => {
  const refreshToken = req.body.refresh_token || req.cookies?.refresh_token;

  if (!refreshToken) {
    return res.status(400).json({ error: 'refresh_token is required' });
  }

  const ipAddress = getIp(req);
  const userAgent = getUA(req);

  try {
    const tokens = await rotateRefreshToken(refreshToken, ipAddress, userAgent);
    setAuthCookies(res, tokens);
    return res.json(tokens);
  } catch (err) {
    if (err instanceof AuthError) {
      clearAuthCookies(res);
      return res.status(err.statusCode).json({ error: err.message });
    }
    console.error('[auth] Refresh error:', err);
    return res.status(500).json({ error: 'Token refresh failed' });
  }
});

// ============================================================================
// LOGOUT
// ============================================================================

router.post('/logout', async (req, res) => {
  const refreshToken = req.body.refresh_token || req.cookies?.refresh_token;
  if (refreshToken) {
    try { await revokeRefreshToken(refreshToken); } catch {}
  }
  clearAuthCookies(res);
  return res.json({ ok: true });
});

router.post('/logout-all', authMiddleware, async (req, res) => {
  try {
    await revokeAllUserSessions(req.user.id);
    await auditLog(req.user.org_id, req.user.id, 'auth.logout_all', {});
    clearAuthCookies(res);
    return res.json({ ok: true });
  } catch (err) {
    console.error('[auth] Logout all error:', err);
    return res.status(500).json({ error: 'Logout failed' });
  }
});

// ============================================================================
// CURRENT USER
// ============================================================================

router.get('/me', authMiddleware, async (req, res) => {
  return res.json({
    user: {
      id: req.user.id,
      email: req.user.email,
      name: req.user.name,
      role: req.user.role,
      department: req.user.department,
      team: req.user.team,
      org_id: req.user.org_id,
      org_name: req.user.org_name,
      org_slug: req.user.org_slug,
      permissions: req.user.permissions,
      auth_method: req.user.auth_method,
    },
  });
});

// ============================================================================
// USER ORGANIZATIONS
// ============================================================================

router.get('/orgs', authMiddleware, async (req, res) => {
  try {
    const orgs = await getUserOrganizations(req.user.id);
    return res.json({ organizations: orgs });
  } catch (err) {
    console.error('[auth] Get orgs error:', err);
    return res.status(500).json({ error: 'Failed to fetch organizations' });
  }
});

// ============================================================================
// API KEYS
// ============================================================================

router.post('/api-keys', authMiddleware, requirePermission(PERMISSIONS.API_KEY_MANAGE), async (req, res) => {
  const { name, scopes, expires_in_days } = req.body;
  if (!name) return res.status(400).json({ error: 'name is required' });

  try {
    const apiKey = await createApiKey(req.user.org_id, req.user.id, name, scopes || [], expires_in_days || null);
    return res.status(201).json(apiKey);
  } catch (err) {
    console.error('[auth] Create API key error:', err);
    return res.status(500).json({ error: 'Failed to create API key' });
  }
});

router.get('/api-keys', authMiddleware, requirePermission(PERMISSIONS.API_KEY_MANAGE), async (req, res) => {
  try {
    const keys = await listApiKeys(req.user.org_id, req.user.id);
    return res.json({ api_keys: keys });
  } catch (err) {
    console.error('[auth] List API keys error:', err);
    return res.status(500).json({ error: 'Failed to list API keys' });
  }
});

router.delete('/api-keys/:id', authMiddleware, requirePermission(PERMISSIONS.API_KEY_MANAGE), async (req, res) => {
  try {
    await revokeApiKey(req.user.org_id, req.user.id, req.params.id);
    return res.json({ ok: true });
  } catch (err) {
    console.error('[auth] Revoke API key error:', err);
    return res.status(500).json({ error: 'Failed to revoke API key' });
  }
});

// ============================================================================
// INVITATIONS
// ============================================================================

router.post('/invite', authMiddleware, requirePermission(PERMISSIONS.USER_MANAGE), async (req, res) => {
  const { email, role, department, team } = req.body;
  if (!email || !role) return res.status(400).json({ error: 'email and role are required' });

  const validRoles = ['org_admin', 'dept_lead', 'org_member', 'org_viewer'];
  if (!validRoles.includes(role)) {
    return res.status(400).json({ error: `role must be one of: ${validRoles.join(', ')}` });
  }

  try {
    const token = await createInvitation(req.user.org_id, email, role, req.user.id, department, team);
    return res.status(201).json({ ok: true, token, message: 'Invitation created. Share the token with the invitee.' });
  } catch (err) {
    console.error('[auth] Create invitation error:', err);
    return res.status(500).json({ error: 'Failed to create invitation' });
  }
});

router.post('/accept-invite', async (req, res) => {
  const { token, email, password, name } = req.body;
  if (!token || !email || !password || !name) {
    return res.status(400).json({ error: 'token, email, password, and name are required' });
  }
  if (password.length < 8) {
    return res.status(400).json({ error: 'Password must be at least 8 characters' });
  }

  const ipAddress = getIp(req);

  try {
    const { tokens, user } = await acceptInvitation(token, email, password, name, ipAddress);
    setAuthCookies(res, tokens);
    return res.json({
      user: { id: user.id, email: user.email, name: user.name, role: user.role, org_id: user.org_id, org_name: user.org_name },
      tokens,
    });
  } catch (err) {
    if (err instanceof AuthError) return res.status(err.statusCode).json({ error: err.message });
    console.error('[auth] Accept invitation error:', err);
    return res.status(500).json({ error: 'Failed to accept invitation' });
  }
});

// ============================================================================
// ORG MEMBERS (admin)
// ============================================================================

router.get('/users', authMiddleware, requirePermission(PERMISSIONS.USER_MANAGE), async (req, res) => {
  try {
    const result = await query(
      `SELECT u.id, u.email, u.name, u.status, om.role, om.department, om.team, om.joined_at, u.last_login_at, u.avatar_url
       FROM organization_members om
       JOIN users u ON u.id = om.user_id
       WHERE om.org_id = $1 AND om.status = 'active'
       ORDER BY om.joined_at DESC`,
      [req.user.org_id]
    );
    return res.json({ members: result.rows });
  } catch (err) {
    console.error('[auth] List users error:', err);
    return res.status(500).json({ error: 'Failed to list users' });
  }
});

router.patch('/users/:id/role', authMiddleware, requirePermission(PERMISSIONS.USER_MANAGE), async (req, res) => {
  const { role } = req.body;
  if (!role) return res.status(400).json({ error: 'role is required' });

  const validRoles = ['org_admin', 'dept_lead', 'org_member', 'org_viewer'];
  if (!validRoles.includes(role)) {
    return res.status(400).json({ error: `role must be one of: ${validRoles.join(', ')}` });
  }

  try {
    const result = await query(
      `UPDATE organization_members SET role = $1 WHERE user_id = $2 AND org_id = $3 AND status = 'active' RETURNING id`,
      [role, req.params.id, req.user.org_id]
    );
    if (result.rows.length === 0) return res.status(404).json({ error: 'Member not found' });

    await auditLog(req.user.org_id, req.user.id, 'user.role_change', { target_user: req.params.id, new_role: role });
    return res.json({ ok: true });
  } catch (err) {
    console.error('[auth] Update role error:', err);
    return res.status(500).json({ error: 'Failed to update role' });
  }
});

router.delete('/users/:id', authMiddleware, requirePermission(PERMISSIONS.USER_MANAGE), async (req, res) => {
  if (req.params.id === req.user.id) return res.status(400).json({ error: 'Cannot remove yourself' });

  try {
    const result = await query(
      `UPDATE organization_members SET status = 'removed' WHERE user_id = $1 AND org_id = $2 AND status = 'active' RETURNING id`,
      [req.params.id, req.user.org_id]
    );
    if (result.rows.length === 0) return res.status(404).json({ error: 'Member not found' });

    await auditLog(req.user.org_id, req.user.id, 'user.remove', { target_user: req.params.id });
    return res.json({ ok: true });
  } catch (err) {
    console.error('[auth] Remove user error:', err);
    return res.status(500).json({ error: 'Failed to remove user' });
  }
});

// ============================================================================
// AUDIT LOG (admin)
// ============================================================================

router.get('/audit-log', authMiddleware, requirePermission(PERMISSIONS.USER_MANAGE), async (req, res) => {
  const limit = Math.min(parseInt(req.query.limit) || 100, 500);
  const offset = parseInt(req.query.offset) || 0;

  try {
    const result = await query(
      `SELECT a.id, a.action, a.resource_type, a.resource_id, a.metadata, a.success, a.error_message, a.ip_address, a.ts,
              u.email as user_email, u.name as user_name
       FROM audit_log a
       LEFT JOIN users u ON u.id = a.user_id
       WHERE a.org_id = $1
       ORDER BY a.ts DESC
       LIMIT $2 OFFSET $3`,
      [req.user.org_id, limit, offset]
    );
    return res.json({ entries: result.rows });
  } catch (err) {
    console.error('[auth] Audit log error:', err);
    return res.status(500).json({ error: 'Failed to fetch audit log' });
  }
});

// ============================================================================
// AVAILABLE PERMISSIONS (for UI)
// ============================================================================

router.get('/permissions', authMiddleware, (req, res) => {
  return res.json({
    permissions: Object.entries(PERMISSIONS).map(([key, value]) => ({ key, value })),
    roles: {
      org_admin: getPermissionsForRole('org_admin'),
      dept_lead: getPermissionsForRole('dept_lead'),
      org_member: getPermissionsForRole('org_member'),
      org_viewer: getPermissionsForRole('org_viewer'),
    },
  });
});

// ============================================================================
// SSO / Auth0
// ============================================================================

import {
  getAuth0AuthUrl,
  ssoLogin,
  verifyAuth0AccessToken,
  getSSOStatus,
  SSO_ENABLED,
} from '../sso.js';

/**
 * GET /api/auth/sso/status
 * Check if SSO is configured.
 */
router.get('/sso/status', (req, res) => {
  return res.json(getSSOStatus());
});

/**
 * GET /api/auth/sso/login
 * Redirect to Auth0 for SSO login.
 * Query params:
 *   - org_slug: optional org to log into
 *   - connection: optional Auth0 connection name (e.g. "google-oauth2", "github")
 */
router.get('/sso/login', (req, res) => {
  if (!SSO_ENABLED) {
    return res.status(503).json({ error: 'SSO is not configured' });
  }

  const state = generateToken(16);
  const { org_slug, connection } = req.query;

  // Store state in cookie for CSRF protection
  res.cookie('sso_state', state, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    maxAge: 10 * 60 * 1000, // 10 minutes
  });

  const authUrl = getAuth0AuthUrl(state, connection || null, org_slug || null);
  return res.redirect(authUrl);
});

/**
 * GET /api/auth/sso/callback
 * Auth0 redirects here after user authenticates.
 * Exchanges code for tokens, creates/links user, redirects to frontend with tokens.
 */
router.get('/sso/callback', async (req, res) => {
  const { code, state, error, error_description } = req.query;

  // Check for Auth0 error
  if (error) {
    const frontendUrl = process.env.FRONTEND_URL || '/';
    return res.redirect(`${frontendUrl}?sso_error=${encodeURIComponent(error_description || error)}`);
  }

  if (!code) {
    return res.status(400).json({ error: 'Missing authorization code' });
  }

  // Verify state (CSRF protection)
  const cookieState = req.cookies?.sso_state;
  if (!cookieState || cookieState !== state) {
    return res.status(400).json({ error: 'Invalid state parameter — possible CSRF attack' });
  }

  // Clear state cookie
  res.clearCookie('sso_state');

  const ipAddress = getIp(req);
  const userAgent = getUA(req);

  // Extract org_slug from app_state if present
  let orgSlug = null;
  try {
    const appState = JSON.parse(req.query.app_state || '{}');
    orgSlug = appState.org_slug || null;
  } catch {}

  try {
    const { tokens, user } = await ssoLogin(code, orgSlug, ipAddress, userAgent);

    setAuthCookies(res, tokens);

    // Redirect to frontend with success
    const frontendUrl = process.env.FRONTEND_URL || '/';
    return res.redirect(`${frontendUrl}?sso_success=1`);
  } catch (err) {
    console.error('[auth] SSO callback error:', err);
    const frontendUrl = process.env.FRONTEND_URL || '/';
    return res.redirect(`${frontendUrl}?sso_error=${encodeURIComponent(err.message)}`);
  }
});

/**
 * POST /api/auth/sso/token
 * Exchange an Auth0 access token for Maestro tokens.
 * For SPAs that handle the Auth0 flow client-side.
 * Body: { access_token, org_slug }
 */
router.post('/sso/token', async (req, res) => {
  const { access_token, org_slug } = req.body;

  if (!access_token) {
    return res.status(400).json({ error: 'access_token is required' });
  }

  const ipAddress = getIp(req);
  const userAgent = getUA(req);

  try {
    const authUser = await verifyAuth0AccessToken(access_token, ipAddress);

    // Generate Maestro tokens
    const accessToken = generateAccessToken(authUser);
    const refreshToken = await generateRefreshToken(authUser, ipAddress, userAgent);

    setAuthCookies(res, { access_token: accessToken, refresh_token: refreshToken });

    return res.json({
      user: {
        id: authUser.id,
        email: authUser.email,
        name: authUser.name,
        role: authUser.role,
        org_id: authUser.org_id,
        org_name: authUser.org_name,
        org_slug: authUser.org_slug,
      },
      tokens: {
        access_token: accessToken,
        refresh_token: refreshToken,
        expires_in: 3600,
        token_type: 'Bearer',
      },
    });
  } catch (err) {
    if (err instanceof AuthError) {
      return res.status(err.statusCode).json({ error: err.message });
    }
    console.error('[auth] SSO token exchange error:', err);
    return res.status(500).json({ error: 'SSO authentication failed' });
  }
});

export default router;

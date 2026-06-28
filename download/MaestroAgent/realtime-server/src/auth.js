// src/auth.js — Authentication, authorization, and session management.
//
// Provides:
//   - JWT access token generation and verification (RS256 or HS256)
//   - Refresh token rotation (with theft detection)
//   - API key authentication (bcrypt-hashed, scoped)
//   - RBAC middleware (role + permission checks)
//   - Audit logging
//   - Rate limiting for auth endpoints
//
// Environment variables:
//   JWT_SECRET          — HMAC secret for JWT signing (HS256). Required in dev.
//   JWT_PRIVATE_KEY     — PEM private key for RS256 (production).
//   JWT_PUBLIC_KEY      — PEM public key for RS256 verification.
//   JWT_ALGORITHM       — 'HS256' (default) or 'RS256'
//   JWT_ACCESS_EXPIRY   — Access token expiry (default: '1h')
//   JWT_REFRESH_EXPIRY  — Refresh token expiry in days (default: 30)
//   JWT_ISSUER          — Token issuer (default: 'maestro')
//   JWT_AUDIENCE        — Token audience (default: 'maestro-api')
//   MAX_FAILED_LOGINS   — Account lock threshold (default: 5)
//   LOCK_DURATION_MINUTES — Account lock duration (default: 15)

import jwt from 'jsonwebtoken';
import crypto from 'node:crypto';
import { query } from './db.js';
import { hashValue, verifyHash, generateToken } from './crypto.js';

// ============================================================================
// CONFIGURATION
// ============================================================================

const ALGORITHM = process.env.JWT_ALGORITHM || 'HS256';
const ACCESS_EXPIRY = process.env.JWT_ACCESS_EXPIRY || '1h';
const REFRESH_EXPIRY_DAYS = parseInt(process.env.JWT_REFRESH_EXPIRY || '30', 10);
const ISSUER = process.env.JWT_ISSUER || 'maestro';
const AUDIENCE = process.env.JWT_AUDIENCE || 'maestro-api';
const MAX_FAILED_LOGINS = parseInt(process.env.MAX_FAILED_LOGINS || '5', 10);
const LOCK_DURATION_MINUTES = parseInt(process.env.LOCK_DURATION_MINUTES || '15', 10);

// P0-4 FIX: No hardcoded fallback. Always require a real secret.
function getSignKey() {
  if (ALGORITHM === 'RS256') {
    const key = process.env.JWT_PRIVATE_KEY;
    if (!key) throw new Error('JWT_PRIVATE_KEY required for RS256');
    return key;
  }
  const secret = process.env.JWT_SECRET;
  if (!secret) {
    throw new Error('JWT_SECRET is required. Generate with: openssl rand -hex 32');
  }
  if (secret.length < 32) {
    throw new Error('JWT_SECRET must be at least 32 characters.');
  }
  return secret;
}

function getVerifyKey() {
  if (ALGORITHM === 'RS256') {
    const key = process.env.JWT_PUBLIC_KEY;
    if (!key) throw new Error('JWT_PUBLIC_KEY required for RS256');
    return key;
  }
  const secret = process.env.JWT_SECRET;
  if (!secret) {
    throw new Error('JWT_SECRET is required.');
  }
  return secret;
}

// ============================================================================
// PERMISSION DEFINITIONS
// ============================================================================

export const PERMISSIONS = {
  RUN_CREATE: 'runs:create',
  RUN_READ_OWN: 'runs:read:own',
  RUN_READ_DEPT: 'runs:read:dept',
  RUN_READ_ORG: 'runs:read:org',
  FEEDBACK_GIVE: 'feedback:give',
  POLICY_MANAGE: 'policy:manage',
  INTEGRATION_MANAGE: 'integration:manage',
  USER_MANAGE: 'user:manage',
  BILLING_MANAGE: 'billing:manage',
  METRICS_READ: 'metrics:read',
  RECEIPT_READ: 'receipt:read',
  RECEIPT_EXPORT: 'receipt:export',
  API_KEY_MANAGE: 'api_key:manage',
};

const ROLE_PERMISSIONS = {
  org_admin: [
    'runs:create', 'runs:read:own', 'runs:read:dept', 'runs:read:org',
    'feedback:give', 'policy:manage', 'integration:manage', 'user:manage',
    'billing:manage', 'metrics:read', 'receipt:read', 'receipt:export',
    'api_key:manage',
  ],
  dept_lead: [
    'runs:create', 'runs:read:own', 'runs:read:dept',
    'feedback:give', 'policy:manage', 'metrics:read', 'receipt:read',
  ],
  org_member: [
    'runs:create', 'runs:read:own', 'feedback:give', 'metrics:read', 'receipt:read',
  ],
  org_viewer: [
    'runs:read:own', 'metrics:read', 'receipt:read',
  ],
};

export function getPermissionsForRole(role) {
  return ROLE_PERMISSIONS[role] || [];
}

export function hasPermission(user, permission) {
  if (user.role === 'org_admin') return true;
  return (user.permissions || []).includes(permission);
}

// ============================================================================
// ERROR CLASS
// ============================================================================

export class AuthError extends Error {
  constructor(message, statusCode = 401) {
    super(message);
    this.name = 'AuthError';
    this.statusCode = statusCode;
  }
}

// ============================================================================
// TOKEN MANAGEMENT
// ============================================================================

/**
 * Generate a JWT access token for a user.
 * @param {object} user - The authenticated user
 * @returns {string} JWT access token
 */
export function generateAccessToken(user) {
  const payload = {
    sub: user.id,
    email: user.email,
    name: user.name,
    org_id: user.org_id,
    org_slug: user.org_slug,
    role: user.role,
    department: user.department,
    team: user.team,
    permissions: user.permissions,
    auth_method: user.auth_method,
  };
  return jwt.sign(payload, getSignKey(), {
    algorithm: ALGORITHM,
    expiresIn: ACCESS_EXPIRY,
    issuer: ISSUER,
    audience: AUDIENCE,
  });
}

/**
 * Generate a refresh token and store its hash.
 * @param {object} user
 * @param {string|null} ipAddress
 * @param {string|null} userAgent
 * @returns {Promise<string>} Raw refresh token
 */
// P0-1 FIX: Store a token_prefix for O(1) index lookup instead of O(n) bcrypt scan.
export async function generateRefreshToken(user, ipAddress, userAgent) {
  const token = generateToken(48);
  const tokenHash = await hashValue(token);
  const tokenPrefix = sha256(token).slice(0, 16);
  const tokenFamily = crypto.randomUUID();
  const expiresAt = new Date(Date.now() + REFRESH_EXPIRY_DAYS * 24 * 60 * 60 * 1000);

  await query(
    `INSERT INTO refresh_tokens (user_id, org_id, token_hash, token_prefix, token_family, expires_at, ip_address, user_agent)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8)`,
    [user.id, user.org_id, tokenHash, tokenPrefix, tokenFamily, expiresAt, ipAddress, userAgent]
  );

  return token;
}

/**
 * Verify a refresh token and rotate it.
 * If the token has already been used (rotation detected), revokes the entire
 * family (potential token theft).
 * @param {string} refreshToken
 * @param {string|null} ipAddress
 * @param {string|null} userAgent
 * @returns {Promise<object>} New token pair
 */
// P0-1 FIX: O(1) index lookup by token_prefix, then single bcrypt verify.
export async function rotateRefreshToken(refreshToken, ipAddress, userAgent) {
  const prefix = sha256(refreshToken).slice(0, 16);

  const result = await query(
    `SELECT id, user_id, org_id, token_hash, token_family, expires_at
     FROM refresh_tokens
     WHERE token_prefix = $1 AND revoked_at IS NULL AND expires_at > now()
     LIMIT 1`,
    [prefix]
  );

  if (result.rows.length === 0) {
    throw new AuthError('Invalid or expired refresh token', 401);
  }

  const matchedToken = result.rows[0];

  // Single bcrypt verify — O(1)
  const valid = await verifyHash(refreshToken, matchedToken.token_hash);
  if (!valid) {
    throw new AuthError('Invalid or expired refresh token', 401);
  }

  // Check expiry
  if (new Date(matchedToken.expires_at) < new Date()) {
    throw new AuthError('Refresh token expired', 401);
  }

  // Check for token reuse (theft detection)
  const alreadyRevoked = await query(
    `SELECT id FROM refresh_tokens
     WHERE token_family = $1 AND revoked_at IS NOT NULL AND revoked_reason = 'rotation'`,
    [matchedToken.token_family]
  );

  if (alreadyRevoked.rows.length > 0) {
    // Token reuse detected — revoke entire family
    console.warn('[auth] Refresh token reuse detected — revoking family', {
      token_family: matchedToken.token_family,
      user_id: matchedToken.user_id,
    });
    await query(
      `UPDATE refresh_tokens
       SET revoked_at = now(), revoked_reason = 'compromised'
       WHERE token_family = $1`,
      [matchedToken.token_family]
    );
    await auditLog(matchedToken.org_id, matchedToken.user_id, 'auth.token_reuse_detected', {
      token_family: matchedToken.token_family,
    }, ipAddress);
    throw new AuthError('Token reuse detected — all sessions revoked for security', 401);
  }

  // Revoke the old token
  await query(
    `UPDATE refresh_tokens
     SET revoked_at = now(), revoked_reason = 'rotation'
     WHERE id = $1`,
    [matchedToken.id]
  );

  // Get user info for new token
  const authUser = await getAuthUser(matchedToken.user_id, matchedToken.org_id);
  if (!authUser) {
    throw new AuthError('User or organization not found', 401);
  }

  // Generate new tokens
  const newAccessToken = generateAccessToken(authUser);
  const newRefreshToken = await generateRefreshToken(authUser, ipAddress, userAgent);

  return {
    access_token: newAccessToken,
    refresh_token: newRefreshToken,
    expires_in: 3600,
    token_type: 'Bearer',
  };
}

/**
 * Revoke all refresh tokens for a user (logout all sessions).
 * @param {string} userId
 */
export async function revokeAllUserSessions(userId) {
  await query(
    `UPDATE refresh_tokens
     SET revoked_at = now(), revoked_reason = 'logout'
     WHERE user_id = $1 AND revoked_at IS NULL`,
    [userId]
  );
}

/**
 * Revoke a specific refresh token (logout).
 * @param {string} refreshToken
 */
export async function revokeRefreshToken(refreshToken) {
  const activeTokens = await query(
    `SELECT id, token_hash FROM refresh_tokens
     WHERE revoked_at IS NULL
     ORDER BY created_at DESC LIMIT 200`
  );

  for (const row of activeTokens.rows) {
    if (await verifyHash(refreshToken, row.token_hash)) {
      await query(
        `UPDATE refresh_tokens SET revoked_at = now(), revoked_reason = 'logout' WHERE id = $1`,
        [row.id]
      );
      return;
    }
  }
}

// ============================================================================
// USER / ORGANIZATION MANAGEMENT
// ============================================================================

/**
 * Create a new user (local auth, not SSO).
 * @param {string} email
 * @param {string} password
 * @param {string} name
 * @returns {Promise<object>} Created user
 */
export async function createUser(email, password, name) {
  const passwordHash = await hashValue(password);
  const result = await query(
    `INSERT INTO users (email, password_hash, name, email_verified)
     VALUES ($1, $2, $3, false)
     RETURNING id, email, name, email_verified, created_at`,
    [email.toLowerCase(), passwordHash, name || null]
  );
  return result.rows[0];
}

/**
 * Find a user by email.
 * @param {string} email
 * @returns {Promise<object|null>}
 */
export async function findUserByEmail(email) {
  const result = await query(
    `SELECT * FROM users WHERE email = $1 AND status = 'active'`,
    [email.toLowerCase()]
  );
  return result.rows[0] || null;
}

/**
 * Find a user by ID.
 * @param {string} id
 * @returns {Promise<object|null>}
 */
export async function findUserById(id) {
  const result = await query(
    `SELECT id, email, name, email_verified, mfa_enabled, status, created_at, last_login_at
     FROM users WHERE id = $1`,
    [id]
  );
  return result.rows[0] || null;
}

/**
 * Create a new organization.
 * @param {string} name
 * @param {string} slug
 * @param {string} industry
 * @returns {Promise<object>}
 */
export async function createOrganization(name, slug, industry) {
  const result = await query(
    `INSERT INTO organizations (name, slug, industry)
     VALUES ($1, $2, $3)
     RETURNING id, name, slug, industry, plan, created_at`,
    [name, slug.toLowerCase(), industry || 'technology']
  );
  return result.rows[0];
}

/**
 * Add a user to an organization with a role.
 */
export async function addOrgMember(orgId, userId, role = 'org_member', department = null, team = null, invitedBy = null) {
  await query(
    `INSERT INTO organization_members (org_id, user_id, role, department, team, invited_by, joined_at, status)
     VALUES ($1, $2, $3, $4, $5, $6, now(), 'active')
     ON CONFLICT (org_id, user_id) DO UPDATE SET role = $3, status = 'active', joined_at = now()`,
    [orgId, userId, role, department, team, invitedBy]
  );
}

/**
 * Get the AuthUser for a given user + org combination.
 * @param {string} userId
 * @param {string} orgId
 * @returns {Promise<object|null>}
 */
export async function getAuthUser(userId, orgId) {
  const result = await query(
    `SELECT u.id, u.email, u.name, om.role, om.department, om.team,
            o.id as org_id, o.slug as org_slug, o.name as org_name
     FROM users u
     JOIN organization_members om ON om.user_id = u.id AND om.status = 'active'
     JOIN organizations o ON o.id = om.org_id AND o.status = 'active'
     WHERE u.id = $1 AND o.id = $2 AND u.status = 'active'`,
    [userId, orgId]
  );
  if (result.rows.length === 0) return null;

  const row = result.rows[0];
  return {
    id: row.id,
    email: row.email,
    name: row.name,
    org_id: row.org_id,
    org_slug: row.org_slug,
    org_name: row.org_name,
    role: row.role,
    department: row.department,
    team: row.team,
    permissions: getPermissionsForRole(row.role),
    auth_method: 'jwt',
  };
}

/**
 * Get all organizations a user belongs to.
 * @param {string} userId
 */
export async function getUserOrganizations(userId) {
  const result = await query(
    `SELECT o.id, o.name, o.slug, o.industry, o.plan, om.role
     FROM organizations o
     JOIN organization_members om ON om.org_id = o.id
     WHERE om.user_id = $1 AND om.status = 'active' AND o.status = 'active'`,
    [userId]
  );
  return result.rows;
}

// ============================================================================
// PASSWORD AUTHENTICATION
// ============================================================================

/**
 * Authenticate a user with email + password.
 * Handles account lockout after too many failed attempts.
 * @param {string} email
 * @param {string} password
 * @param {string|null} orgSlug
 * @param {string|null} ipAddress
 * @param {string|null} userAgent
 * @returns {Promise<object>} { tokens, user }
 */
export async function loginWithPassword(email, password, orgSlug, ipAddress, userAgent) {
  const user = await findUserByEmail(email);
  if (!user) {
    await auditLog(null, null, 'auth.failed_login', { email, reason: 'user_not_found' }, ipAddress, userAgent, false, 'User not found');
    throw new AuthError('Invalid email or password', 401);
  }

  // Check account lock
  if (user.locked_until && new Date(user.locked_until) > new Date()) {
    await auditLog(null, user.id, 'auth.failed_login', { email, reason: 'account_locked' }, ipAddress, userAgent, false, 'Account locked');
    throw new AuthError('Account temporarily locked due to too many failed attempts', 423);
  }

  // Verify password
  if (!user.password_hash) {
    throw new AuthError('This account uses SSO. Please log in with your identity provider.', 401);
  }

  const passwordValid = await verifyHash(password, user.password_hash);
  if (!passwordValid) {
    const newFailedCount = (user.failed_logins || 0) + 1;
    const shouldLock = newFailedCount >= MAX_FAILED_LOGINS;
    await query(
      `UPDATE users SET failed_logins = $1, locked_until = $2 WHERE id = $3`,
      [newFailedCount, shouldLock ? new Date(Date.now() + LOCK_DURATION_MINUTES * 60 * 1000) : null, user.id]
    );

    await auditLog(null, user.id, 'auth.failed_login', { email, reason: 'wrong_password', attempts: newFailedCount }, ipAddress, userAgent, false, 'Wrong password');

    throw new AuthError(
      shouldLock ? 'Account locked due to too many failed attempts' : 'Invalid email or password',
      shouldLock ? 423 : 401
    );
  }

  // Reset failed login count
  await query(
    `UPDATE users
     SET failed_logins = 0, locked_until = NULL, last_login_at = now(),
         last_login_ip = $1, login_count = login_count + 1
     WHERE id = $2`,
    [ipAddress, user.id]
  );

  // Determine org
  let orgId;
  if (orgSlug) {
    const orgResult = await query(
      `SELECT o.id FROM organizations o
       JOIN organization_members om ON om.org_id = o.id
       WHERE o.slug = $1 AND om.user_id = $2 AND om.status = 'active'`,
      [orgSlug, user.id]
    );
    if (orgResult.rows.length === 0) {
      throw new AuthError('You are not a member of this organization', 403);
    }
    orgId = orgResult.rows[0].id;
  } else {
    const orgs = await getUserOrganizations(user.id);
    if (orgs.length === 0) {
      throw new AuthError('No organization found for this user', 403);
    }
    orgId = orgs[0].id;
  }

  const authUser = await getAuthUser(user.id, orgId);
  if (!authUser) {
    throw new AuthError('Failed to load user profile', 500);
  }

  const accessToken = generateAccessToken(authUser);
  const refreshToken = await generateRefreshToken(authUser, ipAddress, userAgent);

  await auditLog(orgId, user.id, 'auth.login', { method: 'password', email }, ipAddress, userAgent);

  return {
    tokens: { access_token: accessToken, refresh_token: refreshToken, expires_in: 3600, token_type: 'Bearer' },
    user: authUser,
  };
}

// ============================================================================
// API KEY MANAGEMENT
// ============================================================================

/**
 * Create a new API key. The full key is only returned once.
 * @param {string} orgId
 * @param {string} userId
 * @param {string} name
 * @param {string[]} scopes
 * @param {number|null} expiresInDays
 * @returns {Promise<object>}
 */
export async function createApiKey(orgId, userId, name, scopes = [], expiresInDays = null) {
  const rawKey = 'mstr_' + generateToken(32);
  const keyHash = await hashValue(rawKey);
  const prefix = rawKey.slice(0, 12);
  const suffix = rawKey.slice(-4);
  const expiresAt = expiresInDays ? new Date(Date.now() + expiresInDays * 24 * 60 * 60 * 1000) : null;

  const result = await query(
    `INSERT INTO api_keys (org_id, user_id, name, key_hash, key_prefix, key_suffix, scopes, expires_at)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
     RETURNING id, created_at`,
    [orgId, userId, name, keyHash, prefix, suffix, scopes, expiresAt]
  );

  await auditLog(orgId, userId, 'api_key.create', { key_id: result.rows[0].id, name, scopes });

  return {
    id: result.rows[0].id,
    key: rawKey,
    name,
    prefix,
    suffix,
    scopes,
    expires_at: expiresAt?.toISOString() || null,
    created_at: result.rows[0].created_at,
  };
}

/**
 * List API keys for a user.
 */
export async function listApiKeys(orgId, userId) {
  const result = await query(
    `SELECT id, name, key_prefix, key_suffix, scopes, last_used_at, last_used_ip,
            expires_at, status, created_at
     FROM api_keys
     WHERE org_id = $1 AND user_id = $2 AND status = 'active'
     ORDER BY created_at DESC`,
    [orgId, userId]
  );
  return result.rows;
}

/**
 * Revoke an API key.
 */
export async function revokeApiKey(orgId, userId, keyId) {
  await query(
    `UPDATE api_keys SET status = 'revoked' WHERE id = $1 AND org_id = $2 AND user_id = $3`,
    [keyId, orgId, userId]
  );
  await auditLog(orgId, userId, 'api_key.revoke', { key_id: keyId });
}

/**
 * Authenticate using an API key.
 * @param {string} apiKey
 * @param {string|null} ipAddress
 * @returns {Promise<object>} AuthUser
 */
export async function authenticateApiKey(apiKey, ipAddress) {
  if (!apiKey.startsWith('mstr_')) {
    throw new AuthError('Invalid API key format', 401);
  }

  const prefix = apiKey.slice(0, 12);
  // P0-2 FIX: LIMIT to 5 (rare prefix collisions), single bcrypt verify in most cases.
  const result = await query(
    `SELECT id, user_id, org_id, key_hash, scopes, expires_at, status
     FROM api_keys
     WHERE key_prefix = $1 AND status = 'active'
     LIMIT 5`,
    [prefix]
  );

  if (result.rows.length === 0) {
    throw new AuthError('Invalid API key', 401);
  }

  let matchedKey = null;
  for (const row of result.rows) {
    if (await verifyHash(apiKey, row.key_hash)) {
      matchedKey = row;
      break;
    }
  }

  if (!matchedKey) {
    throw new AuthError('Invalid API key', 401);
  }

  if (matchedKey.expires_at && new Date(matchedKey.expires_at) < new Date()) {
    throw new AuthError('API key expired', 401);
  }

  await query(
    `UPDATE api_keys SET last_used_at = now(), last_used_ip = $1 WHERE id = $2`,
    [ipAddress, matchedKey.id]
  );

  const authUser = await getAuthUser(matchedKey.user_id, matchedKey.org_id);
  if (!authUser) {
    throw new AuthError('User or organization not found', 401);
  }

  authUser.permissions = matchedKey.scopes || [];
  authUser.auth_method = 'api_key';

  return authUser;
}

// ============================================================================
// INVITATIONS
// ============================================================================

/**
 * Create an invitation for a user to join an org.
 * @returns {Promise<string>} Invitation token (only returned once)
 */
export async function createInvitation(orgId, email, role, invitedBy, department = null, team = null) {
  const token = generateToken(32);
  const tokenHash = await hashValue(token);
  const expiresAt = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000);

  const result = await query(
    `INSERT INTO invitations (org_id, email, role, department, team, invited_by, token_hash, token_expires_at)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
     RETURNING id`,
    [orgId, email.toLowerCase(), role, department, team, invitedBy, tokenHash, expiresAt]
  );

  await auditLog(orgId, invitedBy, 'user.invite', { invitation_id: result.rows[0].id, email, role });
  return token;
}

/**
 * Accept an invitation. Creates or links the user account.
 */
export async function acceptInvitation(token, email, password, name, ipAddress) {
  const invitations = await query(
    `SELECT * FROM invitations
     WHERE status = 'pending' AND token_expires_at > now()
     ORDER BY created_at DESC LIMIT 100`
  );

  let invitation = null;
  for (const row of invitations.rows) {
    if (await verifyHash(token, row.token_hash)) {
      invitation = row;
      break;
    }
  }

  if (!invitation) {
    throw new AuthError('Invalid or expired invitation', 401);
  }

  if (invitation.email !== email.toLowerCase()) {
    throw new AuthError('Email does not match invitation', 401);
  }

  let user = await findUserByEmail(email);
  if (!user) {
    user = await createUser(email, password, name);
  }

  await addOrgMember(invitation.org_id, user.id, invitation.role, invitation.department, invitation.team, invitation.invited_by);

  await query(
    `UPDATE invitations SET status = 'accepted', accepted_at = now(), accepted_by = $1 WHERE id = $2`,
    [user.id, invitation.id]
  );

  await auditLog(invitation.org_id, user.id, 'user.invite_accepted', { invitation_id: invitation.id, email }, ipAddress);

  const authUser = await getAuthUser(user.id, invitation.org_id);
  if (!authUser) throw new AuthError('Failed to load user profile', 500);

  const accessToken = generateAccessToken(authUser);
  const refreshToken = await generateRefreshToken(authUser, ipAddress, null);

  return {
    tokens: { access_token: accessToken, refresh_token: refreshToken, expires_in: 3600, token_type: 'Bearer' },
    user: authUser,
  };
}

// ============================================================================
// AUDIT LOG
// ============================================================================

/**
 * Write an entry to the audit log.
 */
export async function auditLog(orgId, userId, action, metadata = {}, ipAddress = null, userAgent = null, success = true, errorMessage = null) {
  try {
    await query(
      `INSERT INTO audit_log (org_id, user_id, action, metadata, ip_address, user_agent, success, error_message)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8)`,
      [orgId, userId, action, JSON.stringify(metadata), ipAddress, userAgent, success, errorMessage]
    );
  } catch (err) {
    console.error('[auth] Failed to write audit log:', err.message);
  }
}

// ============================================================================
// MIDDLEWARE
// ============================================================================

/**
 * Extract client IP from request.
 */
function getClientIp(req) {
  return req.headers['x-forwarded-for']?.split(',')[0]?.trim() || req.socket?.remoteAddress || null;
}

function getUserAgent(req) {
  return req.headers['user-agent'] || null;
}

/**
 * Authentication middleware.
 * Validates JWT from Authorization header or API key from x-api-key header.
 * Attaches user to req.user.
 */
export async function authMiddleware(req, res, next) {
  const ipAddress = getClientIp(req);
  const userAgent = getUserAgent(req);

  try {
    // Check for API key
    const apiKey = req.headers['x-api-key'];
    if (apiKey) {
      const user = await authenticateApiKey(apiKey, ipAddress);
      req.user = user;
      req.ipAddress = ipAddress;
      req.userAgent = userAgent;

      // P1-13 FIX: RLS context is set by tenantMiddleware (dedicated connection).
      // Do NOT set RLS here — query() uses pool connections where SET LOCAL is lost.

      return next();
    }

    // Check for JWT
    const authHeader = req.headers.authorization;
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return res.status(401).json({ error: 'Authentication required' });
    }

    const token = authHeader.slice(7);

    try {
      const decoded = jwt.verify(token, getVerifyKey(), {
        algorithms: [ALGORITHM],
        issuer: ISSUER,
        audience: AUDIENCE,
      });

      // Reconstruct auth user from JWT claims
      req.user = {
        id: decoded.sub,
        email: decoded.email,
        name: decoded.name,
        org_id: decoded.org_id,
        org_slug: decoded.org_slug,
        role: decoded.role,
        department: decoded.department,
        team: decoded.team,
        permissions: decoded.permissions || [],
        auth_method: decoded.auth_method || 'jwt',
      };
      req.ipAddress = ipAddress;
      req.userAgent = userAgent;

      // P1-13 FIX: RLS context is set by tenantMiddleware (dedicated connection).
    } catch (err) {
      if (err.name === 'TokenExpiredError') {
        return res.status(401).json({ error: 'Access token expired', code: 'token_expired' });
      }
      return res.status(401).json({ error: 'Invalid access token' });
    }

    next();
  } catch (err) {
    if (err instanceof AuthError) {
      return res.status(err.statusCode).json({ error: err.message });
    }
    console.error('[auth] Middleware error:', err);
    return res.status(500).json({ error: 'Authentication failed' });
  }
}

/**
 * Optional auth middleware — authenticates if token present, but doesn't require it.
 */
export async function optionalAuthMiddleware(req, res, next) {
  const authHeader = req.headers.authorization;
  const apiKey = req.headers['x-api-key'];

  if (!authHeader && !apiKey) {
    return next();
  }

  return authMiddleware(req, res, next);
}

/**
 * Require a specific permission.
 * @param {string} permission
 */
export function requirePermission(permission) {
  return (req, res, next) => {
    if (!req.user) {
      return res.status(401).json({ error: 'Authentication required' });
    }
    if (!hasPermission(req.user, permission)) {
      return res.status(403).json({ error: `Insufficient permissions. Required: ${permission}` });
    }
    next();
  };
}

/**
 * Require org admin role.
 */
export function requireOrgAdmin(req, res, next) {
  if (!req.user) {
    return res.status(401).json({ error: 'Authentication required' });
  }
  if (req.user.role !== 'org_admin') {
    return res.status(403).json({ error: 'Org admin role required' });
  }
  next();
}

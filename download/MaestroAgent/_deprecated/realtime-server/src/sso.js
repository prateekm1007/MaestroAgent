// src/sso.js — Auth0 / SSO integration.
//
// Handles:
//   - Auth0 OAuth 2.0 authorization code flow
//   - SAML SSO (via Auth0 connections)
//   - JWKS-based JWT verification (Auth0 RS256 tokens)
//   - Just-In-Time (JIT) user provisioning
//   - Organization detection from Auth0 org_id claim
//   - Linking Auth0 identities to local users
//
// Environment variables:
//   AUTH0_DOMAIN         — e.g. maestro.us.auth0.com
//   AUTH0_CLIENT_ID      — Auth0 application client ID
//   AUTH0_CLIENT_SECRET  — Auth0 application client secret
//   AUTH0_AUDIENCE       — API audience (e.g. https://maestro.api)
//   AUTH0_CALLBACK_URL   — e.g. https://maestro.app/api/auth/sso/callback
//
// If AUTH0_DOMAIN is not set, SSO is disabled and the system falls back
// to local JWT auth only.

import { createRemoteJWKSet, jwtVerify } from 'jose';
import { query } from './db.js';
import { hashValue, generateToken } from './crypto.js';
import {
  AuthError,
  generateAccessToken,
  generateRefreshToken,
  getAuthUser,
  addOrgMember,
  auditLog,
} from './auth.js';

const AUTH0_DOMAIN = process.env.AUTH0_DOMAIN || '';
const AUTH0_CLIENT_ID = process.env.AUTH0_CLIENT_ID || '';
const AUTH0_CLIENT_SECRET = process.env.AUTH0_CLIENT_SECRET || '';
const AUTH0_AUDIENCE = process.env.AUTH0_AUDIENCE || '';
const AUTH0_CALLBACK_URL = process.env.AUTH0_CALLBACK_URL || '';

export const SSO_ENABLED = Boolean(AUTH0_DOMAIN && AUTH0_CLIENT_ID);

// JWKS cache for Auth0 token verification
let jwks = null;
function getJWKS() {
  if (!jwks && AUTH0_DOMAIN) {
    const jwksUri = `https://${AUTH0_DOMAIN}/.well-known/jwks.json`;
    jwks = createRemoteJWKSet(new URL(jwksUri));
  }
  return jwks;
}

/**
 * Generate the Auth0 authorization URL for SSO login.
 * @param {string} state - CSRF state token
 * @param {string|null} connection - Optional Auth0 connection name (for specific IdP)
 * @param {string|null} orgSlug - Optional org slug for org-specific login
 * @returns {string} Auth0 authorization URL
 */
export function getAuth0AuthUrl(state, connection = null, orgSlug = null) {
  if (!SSO_ENABLED) {
    throw new AuthError('SSO is not configured', 503);
  }

  const params = new URLSearchParams({
    response_type: 'code',
    client_id: AUTH0_CLIENT_ID,
    redirect_uri: AUTH0_CALLBACK_URL,
    audience: AUTH0_AUDIENCE,
    scope: 'openid profile email',
    state,
  });

  if (connection) {
    params.set('connection', connection);
  }

  if (orgSlug) {
    // Pass org slug as a custom parameter for post-login org detection
    params.set('app_state', JSON.stringify({ org_slug: orgSlug }));
  }

  return `https://${AUTH0_DOMAIN}/authorize?${params.toString()}`;
}

/**
 * Exchange an Auth0 authorization code for tokens.
 * @param {string} code - Authorization code from Auth0 callback
 * @returns {Promise<object>} { access_token, id_token, expires_in }
 */
export async function exchangeAuth0Code(code) {
  if (!SSO_ENABLED) {
    throw new AuthError('SSO is not configured', 503);
  }

  const response = await fetch(`https://${AUTH0_DOMAIN}/oauth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      grant_type: 'authorization_code',
      client_id: AUTH0_CLIENT_ID,
      client_secret: AUTH0_CLIENT_SECRET,
      code,
      redirect_uri: AUTH0_CALLBACK_URL,
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    console.error('[sso] Auth0 token exchange failed:', error);
    throw new AuthError('SSO authentication failed', 401);
  }

  return response.json();
}

/**
 * Verify an Auth0 ID token and extract user info.
 * Uses JWKS for RS256 verification.
 * @param {string} idToken - Auth0 ID token (JWT)
 * @returns {Promise<object>} { sub, email, name, picture, ... }
 */
export async function verifyAuth0IdToken(idToken) {
  if (!SSO_ENABLED) {
    throw new AuthError('SSO is not configured', 503);
  }

  const JWKS = getJWKS();
  const issuer = `https://${AUTH0_DOMAIN}/`;

  try {
    const { payload } = await jwtVerify(idToken, JWKS, {
      issuer,
      audience: AUTH0_CLIENT_ID,
      algorithms: ['RS256'],
    });

    return {
      sub: payload.sub,
      email: payload.email,
      email_verified: payload.email_verified,
      name: payload.name,
      picture: payload.picture,
      nickname: payload.nickname,
      auth0_org_id: payload.org_id || payload['https://maestro.app/org_id'] || null,
      auth0_org_name: payload.org_name || payload['https://maestro.app/org_name'] || null,
      connection: payload.identities?.[0]?.connection || null,
    };
  } catch (err) {
    console.error('[sso] ID token verification failed:', err.message);
    throw new AuthError('Invalid SSO token', 401);
  }
}

/**
 * Get user info from Auth0 using an access token.
 * @param {string} accessToken - Auth0 access token
 * @returns {Promise<object>} User info from Auth0
 */
export async function getAuth0UserInfo(accessToken) {
  const response = await fetch(`https://${AUTH0_DOMAIN}/userinfo`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });

  if (!response.ok) {
    throw new AuthError('Failed to fetch user info from Auth0', 401);
  }

  return response.json();
}

/**
 * Link or create a local user from an Auth0 identity.
 * Just-In-Time (JIT) provisioning: if the user doesn't exist, create them.
 * @param {object} auth0User - User info from Auth0
 * @param {string|null} orgSlug - Optional org slug from app_state
 * @param {string|null} ipAddress
 * @returns {Promise<object>} AuthUser
 */
export async function linkOrCreateSSOUser(auth0User, orgSlug, ipAddress) {
  const email = auth0User.email?.toLowerCase();
  if (!email) {
    throw new AuthError('SSO provider did not return an email address', 400);
  }

  // Check if user already exists (by email)
  let userResult = await query(
    `SELECT id, email, name FROM users WHERE email = $1 AND status = 'active'`,
    [email]
  );

  let userId;
  let isNewUser = false;

  if (userResult.rows.length === 0) {
    // JIT: Create new user (no password — SSO only)
    const name = auth0User.name || auth0User.nickname || email.split('@')[0];
    const insertResult = await query(
      `INSERT INTO users (email, name, email_verified, avatar_url)
       VALUES ($1, $2, $3, $4)
       RETURNING id, email, name`,
      [email, name, auth0User.email_verified || false, auth0User.picture || null]
    );
    userId = insertResult.rows[0].id;
    isNewUser = true;

    await auditLog(null, userId, 'auth.sso_user_created', {
      email, auth0_sub: auth0User.sub, name,
    }, ipAddress);
  } else {
    userId = userResult.rows[0].id;

    // Update avatar/name if changed
    if (auth0User.picture || auth0User.name) {
      await query(
        `UPDATE users SET avatar_url = COALESCE($1, avatar_url), name = COALESCE($2, name) WHERE id = $3`,
        [auth0User.picture || null, auth0User.name || null, userId]
      );
    }
  }

  // Determine org
  let orgId;

  if (orgSlug) {
    // Check if user is already a member of this org
    const orgResult = await query(
      `SELECT o.id FROM organizations o
       JOIN organization_members om ON om.org_id = o.id
       WHERE o.slug = $1 AND om.user_id = $2 AND om.status = 'active'`,
      [orgSlug, userId]
    );

    if (orgResult.rows.length > 0) {
      orgId = orgResult.rows[0].id;
    } else {
      // Check if org exists — if so, auto-join as member (org admin must approve)
      const orgCheck = await query('SELECT id FROM organizations WHERE slug = $1 AND status = $2', [orgSlug, 'active']);
      if (orgCheck.rows.length > 0) {
        orgId = orgCheck.rows[0].id;
        await addOrgMember(orgId, userId, 'org_member', null, null, null);
        await auditLog(orgId, userId, 'auth.sso_auto_join', { org_slug: orgSlug }, ipAddress);
      }
    }
  }

  if (!orgId) {
    // Fall back to user's first org
    const orgs = await query(
      `SELECT o.id FROM organizations o
       JOIN organization_members om ON om.org_id = o.id
       WHERE om.user_id = $1 AND om.status = 'active' AND o.status = 'active'
       ORDER BY om.joined_at ASC LIMIT 1`,
      [userId]
    );

    if (orgs.rows.length === 0) {
      // No org — if this is a new user, auto-create a personal org
      const slug = email.split('@')[0].replace(/[^a-z0-9-]/g, '-').toLowerCase();
      const orgName = `${auth0User.name || email.split('@')[0]}'s Workspace`;

      try {
        const orgResult = await query(
          `INSERT INTO organizations (name, slug, industry)
           VALUES ($1, $2, 'technology')
           RETURNING id`,
          [orgName, slug]
        );
        orgId = orgResult.rows[0].id;
        await addOrgMember(orgId, userId, 'org_admin');
        await auditLog(orgId, userId, 'auth.sso_org_auto_created', { org_slug: slug }, ipAddress);
      } catch (err) {
        // Slug collision — append random suffix
        const orgResult = await query(
          `INSERT INTO organizations (name, slug, industry)
           VALUES ($1, $2, 'technology')
           RETURNING id`,
          [orgName, `${slug}-${Date.now().toString(36)}`]
        );
        orgId = orgResult.rows[0].id;
        await addOrgMember(orgId, userId, 'org_admin');
      }
    } else {
      orgId = orgs.rows[0].id;
    }
  }

  // Get full auth user
  const authUser = await getAuthUser(userId, orgId);
  if (!authUser) {
    throw new AuthError('Failed to load user profile after SSO', 500);
  }

  // Update last login
  await query(
    `UPDATE users SET last_login_at = now(), last_login_ip = $1, login_count = login_count + 1 WHERE id = $2`,
    [ipAddress, userId]
  );

  await auditLog(orgId, userId, 'auth.sso_login', {
    email, auth0_sub: auth0User.sub,
    connection: auth0User.connection, is_new_user: isNewUser,
  }, ipAddress);

  return authUser;
}

/**
 * Full SSO login flow: exchange code → verify token → link/create user → generate Maestro tokens.
 * @param {string} code - Authorization code from Auth0
 * @param {string|null} orgSlug - Optional org slug from app_state
 * @param {string|null} ipAddress
 * @param {string|null} userAgent
 * @returns {Promise<object>} { tokens, user }
 */
export async function ssoLogin(code, orgSlug, ipAddress, userAgent) {
  // Exchange code for Auth0 tokens
  const auth0Tokens = await exchangeAuth0Code(code);

  // Verify ID token and extract user info
  const auth0User = await verifyAuth0IdToken(auth0Tokens.id_token);

  // Link or create local user
  const authUser = await linkOrCreateSSOUser(auth0User, orgSlug, ipAddress);

  // Generate Maestro tokens (our own JWT + refresh token)
  const accessToken = generateAccessToken(authUser);
  const refreshToken = await generateRefreshToken(authUser, ipAddress, userAgent);

  return {
    tokens: {
      access_token: accessToken,
      refresh_token: refreshToken,
      expires_in: 3600,
      token_type: 'Bearer',
    },
    user: authUser,
  };
}

/**
 * Verify an Auth0 access token directly (for API calls with Auth0 tokens).
 * This allows clients that already have Auth0 tokens to use Maestro API
 * without going through the Maestro login flow.
 * @param {string} auth0Token - Auth0 access token
 * @param {string|null} ipAddress
 * @returns {Promise<object>} AuthUser
 */
export async function verifyAuth0AccessToken(auth0Token, ipAddress) {
  if (!SSO_ENABLED) {
    throw new AuthError('SSO is not configured', 503);
  }

  const JWKS = getJWKS();
  const issuer = `https://${AUTH0_DOMAIN}/`;

  try {
    const { payload } = await jwtVerify(auth0Token, JWKS, {
      issuer,
      audience: AUTH0_AUDIENCE,
      algorithms: ['RS256'],
    });

    // Extract email from token
    const email = payload.email || payload['https://maestro.app/email'];
    if (!email) {
      throw new AuthError('Auth0 token does not contain email', 401);
    }

    // Find local user by email
    const userResult = await query(
      `SELECT id FROM users WHERE email = $1 AND status = 'active'`,
      [email.toLowerCase()]
    );

    if (userResult.rows.length === 0) {
      throw new AuthError('User not found. Please complete SSO login first.', 401);
    }

    const userId = userResult.rows[0].id;

    // Determine org from token or default
    let orgId;
    const orgs = await query(
      `SELECT o.id FROM organizations o
       JOIN organization_members om ON om.org_id = o.id
       WHERE om.user_id = $1 AND om.status = 'active' AND o.status = 'active'
       ORDER BY om.joined_at ASC LIMIT 1`,
      [userId]
    );

    if (orgs.rows.length === 0) {
      throw new AuthError('No organization found for this user', 403);
    }

    orgId = orgs.rows[0].id;

    const authUser = await getAuthUser(userId, orgId);
    if (!authUser) {
      throw new AuthError('Failed to load user profile', 401);
    }

    authUser.auth_method = 'sso';

    return authUser;
  } catch (err) {
    if (err instanceof AuthError) throw err;
    console.error('[sso] Access token verification failed:', err.message);
    throw new AuthError('Invalid SSO token', 401);
  }
}

/**
 * Get SSO configuration status.
 * @returns {object} SSO status
 */
export function getSSOStatus() {
  return {
    enabled: SSO_ENABLED,
    domain: AUTH0_DOMAIN || null,
    client_id: AUTH0_CLIENT_ID || null,
    callback_url: AUTH0_CALLBACK_URL || null,
  };
}

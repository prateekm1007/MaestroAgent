// tests/integration/auth.test.js — Integration tests for auth API routes.
//
// These tests require a running PostgreSQL instance.
// Set DATABASE_URL environment variable to run.
//
// Run: DATABASE_URL=postgresql://localhost/maestro_test npx vitest run tests/integration/

import { describe, it, expect, beforeAll, afterAll, beforeEach, afterEach } from 'vitest';
import express from 'express';
import request from 'supertest';
import { query, withTransaction, closePool } from '../../src/db.js';

const DATABASE_AVAILABLE = process.env.DATABASE_URL && process.env.DATABASE_URL.includes('localhost');

const describeIfDb = DATABASE_AVAILABLE ? describe : describe.skip;

describeIfDb('Auth API Integration', () => {
  let app;

  beforeAll(async () => {
    // Create test app
    const authRouter = (await import('../../src/routes/auth.js')).default;
    app = express();
    app.use(express.json());
    app.use((req, res, next) => {
      req.headers['x-forwarded-for'] = '127.0.0.1';
      next();
    });
    app.use('/api/auth', authRouter);
  });

  afterAll(async () => {
    await closePool();
  });

  beforeEach(async () => {
    // Clean up test data
    try {
      await query('DELETE FROM audit_log WHERE org_id IN (SELECT id FROM organizations WHERE slug LIKE $1)', ['test-%']);
      await query('DELETE FROM organization_members WHERE org_id IN (SELECT id FROM organizations WHERE slug LIKE $1)', ['test-%']);
      await query('DELETE FROM api_keys WHERE org_id IN (SELECT id FROM organizations WHERE slug LIKE $1)', ['test-%']);
      await query('DELETE FROM refresh_tokens WHERE org_id IN (SELECT id FROM organizations WHERE slug LIKE $1)', ['test-%']);
      await query('DELETE FROM users WHERE email LIKE $1', ['test-%@example.com']);
      await query('DELETE FROM organizations WHERE slug LIKE $1', ['test-%']);
    } catch {}
  });

  describe('POST /api/auth/register', () => {
    it('should register a new user and organization', async () => {
      const res = await request(app)
        .post('/api/auth/register')
        .send({
          email: 'test-register@example.com',
          password: 'SecurePassword123!',
          name: 'Test User',
          org_name: 'Test Org',
          org_slug: 'test-register',
          industry: 'technology',
        })
        .expect(201);

      expect(res.body).toHaveProperty('user');
      expect(res.body).toHaveProperty('organization');
      expect(res.body).toHaveProperty('tokens');
      expect(res.body.tokens).toHaveProperty('access_token');
      expect(res.body.tokens).toHaveProperty('refresh_token');
      expect(res.body.user.email).toBe('test-register@example.com');
      expect(res.body.user.role).toBe('org_admin');
      expect(res.body.organization.slug).toBe('test-register');
    });

    it('should reject duplicate email', async () => {
      await request(app)
        .post('/api/auth/register')
        .send({
          email: 'test-dup@example.com',
          password: 'SecurePassword123!',
          org_name: 'Test Org 1',
          org_slug: 'test-dup-1',
        })
        .expect(201);

      const res = await request(app)
        .post('/api/auth/register')
        .send({
          email: 'test-dup@example.com',
          password: 'SecurePassword123!',
          org_name: 'Test Org 2',
          org_slug: 'test-dup-2',
        })
        .expect(409);

      expect(res.body.error).toContain('already registered');
    });

    it('should reject short password', async () => {
      const res = await request(app)
        .post('/api/auth/register')
        .send({
          email: 'test-short@example.com',
          password: '123',
          org_name: 'Test Org',
          org_slug: 'test-short',
        })
        .expect(400);

      expect(res.body.error).toContain('at least 8 characters');
    });

    it('should reject invalid slug', async () => {
      const res = await request(app)
        .post('/api/auth/register')
        .send({
          email: 'test-slug@example.com',
          password: 'SecurePassword123!',
          org_name: 'Test Org',
          org_slug: 'Invalid Slug!',
        })
        .expect(400);

      expect(res.body.error).toContain('lowercase alphanumeric');
    });
  });

  describe('POST /api/auth/login', () => {
    it('should login with correct credentials', async () => {
      // Register first
      await request(app)
        .post('/api/auth/register')
        .send({
          email: 'test-login@example.com',
          password: 'SecurePassword123!',
          org_name: 'Test Org',
          org_slug: 'test-login',
        });

      // Login
      const res = await request(app)
        .post('/api/auth/login')
        .send({
          email: 'test-login@example.com',
          password: 'SecurePassword123!',
        })
        .expect(200);

      expect(res.body.user.email).toBe('test-login@example.com');
      expect(res.body.tokens.access_token).toBeTruthy();
    });

    it('should reject wrong password', async () => {
      await request(app)
        .post('/api/auth/register')
        .send({
          email: 'test-wrongpw@example.com',
          password: 'SecurePassword123!',
          org_name: 'Test Org',
          org_slug: 'test-wrongpw',
        });

      const res = await request(app)
        .post('/api/auth/login')
        .send({
          email: 'test-wrongpw@example.com',
          password: 'WrongPassword!',
        })
        .expect(401);

      expect(res.body.error).toContain('Invalid email or password');
    });

    it('should reject non-existent user', async () => {
      const res = await request(app)
        .post('/api/auth/login')
        .send({
          email: 'nonexistent@example.com',
          password: 'whatever',
        })
        .expect(401);

      expect(res.body.error).toContain('Invalid email or password');
    });
  });

  describe('GET /api/auth/me', () => {
    it('should return current user with valid token', async () => {
      const regRes = await request(app)
        .post('/api/auth/register')
        .send({
          email: 'test-me@example.com',
          password: 'SecurePassword123!',
          org_name: 'Test Org',
          org_slug: 'test-me',
        });

      const token = regRes.body.tokens.access_token;

      const res = await request(app)
        .get('/api/auth/me')
        .set('Authorization', `Bearer ${token}`)
        .expect(200);

      expect(res.body.user.email).toBe('test-me@example.com');
      expect(res.body.user.role).toBe('org_admin');
      expect(res.body.user.permissions).toContain('runs:create');
    });

    it('should reject without token', async () => {
      const res = await request(app)
        .get('/api/auth/me')
        .expect(401);

      expect(res.body.error).toContain('Authentication required');
    });

    it('should reject with invalid token', async () => {
      const res = await request(app)
        .get('/api/auth/me')
        .set('Authorization', 'Bearer invalidtoken')
        .expect(401);

      expect(res.body.error).toContain('Invalid access token');
    });
  });

  describe('API Keys', () => {
    it('should create and use an API key', async () => {
      // Register
      const regRes = await request(app)
        .post('/api/auth/register')
        .send({
          email: 'test-apikey@example.com',
          password: 'SecurePassword123!',
          org_name: 'Test Org',
          org_slug: 'test-apikey',
        });

      const token = regRes.body.tokens.access_token;

      // Create API key
      const createRes = await request(app)
        .post('/api/auth/api-keys')
        .set('Authorization', `Bearer ${token}`)
        .send({ name: 'Test Key', scopes: ['runs:create', 'receipts:read'] })
        .expect(201);

      expect(createRes.body.key).toMatch(/^mstr_/);
      expect(createRes.body.name).toBe('Test Key');

      const apiKey = createRes.body.key;

      // Use API key
      const meRes = await request(app)
        .get('/api/auth/me')
        .set('x-api-key', apiKey)
        .expect(200);

      expect(meRes.body.user.auth_method).toBe('api_key');
    });

    it('should list and revoke API keys', async () => {
      const regRes = await request(app)
        .post('/api/auth/register')
        .send({
          email: 'test-revoke@example.com',
          password: 'SecurePassword123!',
          org_name: 'Test Org',
          org_slug: 'test-revoke',
        });

      const token = regRes.body.tokens.access_token;

      const createRes = await request(app)
        .post('/api/auth/api-keys')
        .set('Authorization', `Bearer ${token}`)
        .send({ name: 'Test Key' });

      const keyId = createRes.body.id;

      // List
      const listRes = await request(app)
        .get('/api/auth/api-keys')
        .set('Authorization', `Bearer ${token}`)
        .expect(200);

      expect(listRes.body.api_keys).toHaveLength(1);
      expect(listRes.body.api_keys[0].name).toBe('Test Key');

      // Revoke
      await request(app)
        .delete(`/api/auth/api-keys/${keyId}`)
        .set('Authorization', `Bearer ${token}`)
        .expect(200);

      // Verify revoked key no longer works
      await request(app)
        .get('/api/auth/me')
        .set('x-api-key', createRes.body.key)
        .expect(401);
    });
  });

  describe('Token Refresh', () => {
    it('should refresh a valid token', async () => {
      const regRes = await request(app)
        .post('/api/auth/register')
        .send({
          email: 'test-refresh@example.com',
          password: 'SecurePassword123!',
          org_name: 'Test Org',
          org_slug: 'test-refresh',
        });

      const refreshToken = regRes.body.tokens.refresh_token;

      const res = await request(app)
        .post('/api/auth/refresh')
        .send({ refresh_token: refreshToken })
        .expect(200);

      expect(res.body.access_token).toBeTruthy();
      expect(res.body.refresh_token).toBeTruthy();
      expect(res.body.refresh_token).not.toBe(refreshToken); // rotated
    });

    it('should reject reused refresh token', async () => {
      const regRes = await request(app)
        .post('/api/auth/register')
        .send({
          email: 'test-reuse@example.com',
          password: 'SecurePassword123!',
          org_name: 'Test Org',
          org_slug: 'test-reuse',
        });

      const refreshToken = regRes.body.tokens.refresh_token;

      // First refresh — succeeds
      await request(app)
        .post('/api/auth/refresh')
        .send({ refresh_token: refreshToken })
        .expect(200);

      // Second refresh with same token — should fail (rotation)
      const res = await request(app)
        .post('/api/auth/refresh')
        .send({ refresh_token: refreshToken })
        .expect(401);

      expect(res.body.error).toContain('Invalid or expired');
    });
  });

  describe('Invitations', () => {
    it('should invite a user and they accept', async () => {
      // Admin registers
      const adminRes = await request(app)
        .post('/api/auth/register')
        .send({
          email: 'test-admin@example.com',
          password: 'SecurePassword123!',
          org_name: 'Test Org',
          org_slug: 'test-invite',
        });

      const adminToken = adminRes.body.tokens.access_token;

      // Invite a user
      const inviteRes = await request(app)
        .post('/api/auth/invite')
        .set('Authorization', `Bearer ${adminToken}`)
        .send({ email: 'test-invited@example.com', role: 'org_member' })
        .expect(201);

      expect(inviteRes.body.token).toBeTruthy();

      const inviteToken = inviteRes.body.token;

      // Accept invitation
      const acceptRes = await request(app)
        .post('/api/auth/accept-invite')
        .send({
          token: inviteToken,
          email: 'test-invited@example.com',
          password: 'InvitedPassword123!',
          name: 'Invited User',
        })
        .expect(200);

      expect(acceptRes.body.user.email).toBe('test-invited@example.com');
      expect(acceptRes.body.user.role).toBe('org_member');
    });
  });

  describe('Audit Log', () => {
    it('should log auth events', async () => {
      const regRes = await request(app)
        .post('/api/auth/register')
        .send({
          email: 'test-audit@example.com',
          password: 'SecurePassword123!',
          org_name: 'Test Org',
          org_slug: 'test-audit',
        });

      const token = regRes.body.tokens.access_token;

      // Do a login (creates audit entry)
      await request(app)
        .post('/api/auth/login')
        .send({ email: 'test-audit@example.com', password: 'SecurePassword123!' });

      // Fetch audit log
      const res = await request(app)
        .get('/api/auth/audit-log')
        .set('Authorization', `Bearer ${token}`)
        .expect(200);

      expect(res.body.entries.length).toBeGreaterThan(0);

      const actions = res.body.entries.map(e => e.action);
      expect(actions).toContain('auth.register');
      expect(actions).toContain('auth.login');
    });
  });

  describe('RBAC', () => {
    it('should enforce permission checks', async () => {
      // Register as admin
      const adminRes = await request(app)
        .post('/api/auth/register')
        .send({
          email: 'test-rbac-admin@example.com',
          password: 'SecurePassword123!',
          org_name: 'Test Org',
          org_slug: 'test-rbac',
        });

      const adminToken = adminRes.body.tokens.access_token;

      // Invite a viewer
      const inviteRes = await request(app)
        .post('/api/auth/invite')
        .set('Authorization', `Bearer ${adminToken}`)
        .send({ email: 'test-rbac-viewer@example.com', role: 'org_viewer' });

      const acceptRes = await request(app)
        .post('/api/auth/accept-invite')
        .send({
          token: inviteRes.body.token,
          email: 'test-rbac-viewer@example.com',
          password: 'ViewerPassword123!',
          name: 'Viewer',
        });

      const viewerToken = acceptRes.body.tokens.access_token;

      // Viewer should not be able to create API keys
      await request(app)
        .post('/api/auth/api-keys')
        .set('Authorization', `Bearer ${viewerToken}`)
        .send({ name: 'Test' })
        .expect(403);

      // Viewer should not be able to invite users
      await request(app)
        .post('/api/auth/invite')
        .set('Authorization', `Bearer ${viewerToken}`)
        .send({ email: 'someone@example.com', role: 'org_member' })
        .expect(403);

      // Viewer CAN read their own profile
      await request(app)
        .get('/api/auth/me')
        .set('Authorization', `Bearer ${viewerToken}`)
        .expect(200);
    });
  });
});

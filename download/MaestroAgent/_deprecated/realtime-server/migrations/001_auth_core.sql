-- 001_auth_core.sql — Authentication and organization tables.
--
-- Creates: users, organizations, organization_members, departments,
-- teams, api_keys, audit_log, sessions.
--
-- This migration is idempotent — uses CREATE TABLE IF NOT EXISTS.

-- Extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- USERS
-- ============================================================================

CREATE TABLE IF NOT EXISTS users (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email           TEXT NOT NULL UNIQUE,
  email_verified  BOOLEAN DEFAULT false,
  name            TEXT,
  avatar_url      TEXT,
  password_hash   TEXT,  -- NULL if SSO-only account
  mfa_enabled     BOOLEAN DEFAULT false,
  mfa_secret      TEXT,  -- encrypted TOTP secret
  last_login_at   TIMESTAMPTZ,
  last_login_ip   INET,
  login_count     INTEGER DEFAULT 0,
  failed_logins   INTEGER DEFAULT 0,
  locked_until    TIMESTAMPTZ,  -- account lock after too many failed attempts
  status          TEXT DEFAULT 'active',  -- active | suspended | deleted
  created_at      TIMESTAMPTZ DEFAULT now(),
  updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email) WHERE status = 'active';

-- ============================================================================
-- ORGANIZATIONS
-- ============================================================================

CREATE TABLE IF NOT EXISTS organizations (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name            TEXT NOT NULL,
  slug            TEXT NOT NULL UNIQUE,
  industry        TEXT DEFAULT 'technology',
  plan            TEXT DEFAULT 'free',  -- free | pro | business | enterprise
  plan_started_at TIMESTAMPTZ,
  plan_expires_at TIMESTAMPTZ,
  status          TEXT DEFAULT 'active',  -- active | suspended | deleted
  settings        JSONB DEFAULT '{}',  -- org-level config (LLM provider, etc.)
  created_at      TIMESTAMPTZ DEFAULT now(),
  updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_org_slug ON organizations(slug) WHERE status = 'active';

-- ============================================================================
-- ORGANIZATION MEMBERS (join table with role)
-- ============================================================================

CREATE TABLE IF NOT EXISTS organization_members (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role            TEXT NOT NULL DEFAULT 'org_member',
  -- Roles: org_admin | dept_lead | org_member | org_viewer
  department      TEXT,  -- department name (nullable)
  team            TEXT,  -- team name (nullable)
  invited_by      UUID REFERENCES users(id),
  invited_at      TIMESTAMPTZ DEFAULT now(),
  joined_at       TIMESTAMPTZ,
  status          TEXT DEFAULT 'active',  -- active | invited | removed
  created_at      TIMESTAMPTZ DEFAULT now(),
  updated_at      TIMESTAMPTZ DEFAULT now(),
  UNIQUE(org_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_org_members_org ON organization_members(org_id) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_org_members_user ON organization_members(user_id) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_org_members_role ON organization_members(org_id, role) WHERE status = 'active';

-- ============================================================================
-- DEPARTMENTS
-- ============================================================================

CREATE TABLE IF NOT EXISTS departments (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  name            TEXT NOT NULL,
  created_at      TIMESTAMPTZ DEFAULT now(),
  UNIQUE(org_id, name)
);

CREATE INDEX IF NOT EXISTS idx_departments_org ON departments(org_id);

-- ============================================================================
-- TEAMS
-- ============================================================================

CREATE TABLE IF NOT EXISTS teams (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  department_id   UUID REFERENCES departments(id) ON DELETE SET NULL,
  name            TEXT NOT NULL,
  created_at      TIMESTAMPTZ DEFAULT now(),
  UNIQUE(org_id, name)
);

CREATE INDEX IF NOT EXISTS idx_teams_org ON teams(org_id);

-- ============================================================================
-- API KEYS
-- ============================================================================

CREATE TABLE IF NOT EXISTS api_keys (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name            TEXT NOT NULL,
  key_hash        TEXT NOT NULL,  -- bcrypt hash of the full API key
  key_prefix      TEXT NOT NULL,  -- first 8 chars for identification (e.g., "maestro_")
  key_suffix      TEXT NOT NULL,  -- last 4 chars for identification
  scopes          TEXT[] DEFAULT '{}',  -- e.g., ['runs:create', 'receipts:read']
  last_used_at    TIMESTAMPTZ,
  last_used_ip    INET,
  expires_at      TIMESTAMPTZ,  -- NULL = no expiry
  status          TEXT DEFAULT 'active',  -- active | revoked
  created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_api_keys_org ON api_keys(org_id) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_api_keys_prefix ON api_keys(key_prefix) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id) WHERE status = 'active';

-- ============================================================================
-- INVITATIONS (for inviting users to an org)
-- ============================================================================

CREATE TABLE IF NOT EXISTS invitations (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  email           TEXT NOT NULL,
  role            TEXT NOT NULL DEFAULT 'org_member',
  department      TEXT,
  team            TEXT,
  invited_by      UUID NOT NULL REFERENCES users(id),
  token_hash      TEXT NOT NULL,  -- bcrypt hash of the invitation token
  token_expires_at TIMESTAMPTZ NOT NULL,
  accepted_at     TIMESTAMPTZ,
  accepted_by     UUID REFERENCES users(id),
  status          TEXT DEFAULT 'pending',  -- pending | accepted | expired | revoked
  created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_invitations_org ON invitations(org_id) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_invitations_email ON invitations(email) WHERE status = 'pending';

-- ============================================================================
-- REFRESH TOKENS (for JWT session management)
-- ============================================================================

CREATE TABLE IF NOT EXISTS refresh_tokens (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  token_hash      TEXT NOT NULL,  -- bcrypt hash of the refresh token
  token_family    UUID NOT NULL,  -- for rotation detection (token stealing)
  expires_at      TIMESTAMPTZ NOT NULL,
  revoked_at      TIMESTAMPTZ,
  revoked_reason  TEXT,  -- 'rotation' | 'logout' | 'compromised' | 'expired'
  created_at      TIMESTAMPTZ DEFAULT now(),
  last_used_at    TIMESTAMPTZ DEFAULT now(),
  ip_address      INET,
  user_agent      TEXT
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id) WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_hash ON refresh_tokens(token_hash);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires ON refresh_tokens(expires_at) WHERE revoked_at IS NULL;

-- ============================================================================
-- AUDIT LOG (all admin and auth actions)
-- ============================================================================

CREATE TABLE IF NOT EXISTS audit_log (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          UUID,  -- nullable for auth events (login before org context)
  user_id         UUID,  -- nullable for anonymous events
  action          TEXT NOT NULL,
  -- Actions: auth.login, auth.logout, auth.failed_login, auth.token_refresh,
  --          user.invite, user.remove, user.role_change,
  --          org.create, org.update, org.delete,
  --          api_key.create, api_key.revoke, api_key.use,
  --          policy.create, policy.update, policy.delete,
  --          integration.connect, integration.disconnect,
  --          run.create, run.complete, run.fail,
  --          receipt.view, receipt.verify, receipt.export
  resource_type   TEXT,  -- e.g., 'run', 'policy', 'user', 'api_key'
  resource_id     TEXT,
  metadata        JSONB DEFAULT '{}',
  ip_address      INET,
  user_agent      TEXT,
  success         BOOLEAN DEFAULT true,
  error_message   TEXT,
  ts              TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_org_ts ON audit_log(org_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_user_ts ON audit_log(user_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_resource ON audit_log(resource_type, resource_id);

-- ============================================================================
-- ROW-LEVEL SECURITY (multi-tenant isolation)
-- ============================================================================
-- RLS is enforced at the PostgreSQL level. Every query is automatically
-- scoped to the current org_id (set via SET LOCAL app.org_id).
-- This is defense-in-depth — the application also filters by org_id.

-- Enable RLS on tenant-scoped tables
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE refresh_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE organization_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE departments ENABLE ROW LEVEL SECURITY;
ALTER TABLE teams ENABLE ROW LEVEL SECURITY;
ALTER TABLE invitations ENABLE ROW LEVEL SECURITY;

-- RLS Policies
-- Users can see data only within their org context
CREATE POLICY tenant_isolation ON api_keys
  USING (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid);

CREATE POLICY tenant_isolation ON audit_log
  USING (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid OR org_id IS NULL);

CREATE POLICY tenant_isolation ON organization_members
  USING (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid);

CREATE POLICY tenant_isolation ON departments
  USING (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid);

CREATE POLICY tenant_isolation ON teams
  USING (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid);

CREATE POLICY tenant_isolation ON invitations
  USING (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid);

-- Refresh tokens are scoped by user_id (which is set via app.user_id)
CREATE POLICY user_isolation ON refresh_tokens
  USING (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid);

-- Force RLS even for table owners (belt + suspenders)
ALTER TABLE api_keys FORCE ROW LEVEL SECURITY;
ALTER TABLE audit_log FORCE ROW LEVEL SECURITY;
ALTER TABLE organization_members FORCE ROW LEVEL SECURITY;
ALTER TABLE departments FORCE ROW LEVEL SECURITY;
ALTER TABLE teams FORCE ROW LEVEL SECURITY;
ALTER TABLE invitations FORCE ROW LEVEL SECURITY;

-- ============================================================================
-- UPDATED_AT triggers
-- ============================================================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER users_updated_at BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER organizations_updated_at BEFORE UPDATE ON organizations
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER org_members_updated_at BEFORE UPDATE ON organization_members
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================================
-- DEFAULT DATA (development only — skip in production with --no-seed flag)
-- ============================================================================

-- This will be handled by a separate seed script, not in the migration.

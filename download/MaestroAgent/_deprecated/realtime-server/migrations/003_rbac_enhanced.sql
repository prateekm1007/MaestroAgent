-- 003_rbac_enhanced.sql — Enhanced RBAC: custom roles, role hierarchy,
-- resource ownership, department/team hierarchy.
--
-- Extends 001_auth_core.sql with:
--   - custom_roles table (org-specific roles beyond the 4 built-in)
--   - role_permissions table (many-to-many role <-> permission)
--   - resource_ownership table (who can access what resource)
--   - department parent-child hierarchy
--   - team parent-child hierarchy
--   - role_assignments (user can have different roles in different departments/teams)

-- ============================================================================
-- CUSTOM ROLES (org-defined, beyond the 4 built-in)
-- ============================================================================

CREATE TABLE IF NOT EXISTS custom_roles (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  name            TEXT NOT NULL,
  slug            TEXT NOT NULL,
  description     TEXT,
  is_system       BOOLEAN DEFAULT false,  -- true for built-in roles (immutable)
  parent_role_id  UUID REFERENCES custom_roles(id) ON DELETE SET NULL, -- role hierarchy
  created_at      TIMESTAMPTZ DEFAULT now(),
  updated_at      TIMESTAMPTZ DEFAULT now(),
  UNIQUE(org_id, slug)
);
CREATE INDEX IF NOT EXISTS idx_custom_roles_org ON custom_roles(org_id);
ALTER TABLE custom_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE custom_roles FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON custom_roles
  USING (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid);

-- ============================================================================
-- ROLE PERMISSIONS (many-to-many: role <-> permission)
-- ============================================================================

CREATE TABLE IF NOT EXISTS role_permissions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  role_id         UUID NOT NULL REFERENCES custom_roles(id) ON DELETE CASCADE,
  permission      TEXT NOT NULL,
  created_at      TIMESTAMPTZ DEFAULT now(),
  UNIQUE(role_id, permission)
);
CREATE INDEX IF NOT EXISTS idx_role_perms_role ON role_permissions(role_id);
CREATE INDEX IF NOT EXISTS idx_role_perms_org ON role_permissions(org_id);
ALTER TABLE role_permissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE role_permissions FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON role_permissions
  USING (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid);

-- ============================================================================
-- DEPARTMENT HIERARCHY (parent-child)
-- ============================================================================

ALTER TABLE departments ADD COLUMN IF NOT EXISTS parent_id UUID REFERENCES departments(id) ON DELETE SET NULL;
ALTER TABLE departments ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE departments ADD COLUMN IF NOT EXISTS head_user_id UUID REFERENCES users(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_departments_parent ON departments(parent_id);

-- ============================================================================
-- TEAM HIERARCHY (parent-child)
-- ============================================================================

ALTER TABLE teams ADD COLUMN IF NOT EXISTS parent_id UUID REFERENCES teams(id) ON DELETE SET NULL;
ALTER TABLE teams ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE teams ADD COLUMN IF NOT EXISTS lead_user_id UUID REFERENCES users(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_teams_parent ON teams(parent_id);

-- ============================================================================
-- ROLE ASSIGNMENTS (context-specific roles)
-- A user can be org_admin globally but dept_lead in a specific department.
-- ============================================================================

CREATE TABLE IF NOT EXISTS role_assignments (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role_id         UUID REFERENCES custom_roles(id) ON DELETE CASCADE,
  role_name       TEXT NOT NULL,  -- denormalized for built-in roles
  scope_type      TEXT NOT NULL DEFAULT 'org',  -- org | department | team
  scope_id        UUID,  -- department or team id (null = org-wide)
  assigned_by     UUID REFERENCES users(id),
  created_at      TIMESTAMPTZ DEFAULT now(),
  UNIQUE(org_id, user_id, role_name, scope_type, scope_id)
);
CREATE INDEX IF NOT EXISTS idx_role_assignments_user ON role_assignments(user_id);
CREATE INDEX IF NOT EXISTS idx_role_assignments_org ON role_assignments(org_id);
CREATE INDEX IF NOT EXISTS idx_role_assignments_scope ON role_assignments(scope_type, scope_id);
ALTER TABLE role_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE role_assignments FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON role_assignments
  USING (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid);

-- ============================================================================
-- RESOURCE OWNERSHIP (who owns what resource)
-- ============================================================================

CREATE TABLE IF NOT EXISTS resource_ownership (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  resource_type   TEXT NOT NULL,  -- run | receipt | policy | artifact | etc.
  resource_id     UUID NOT NULL,
  owner_user_id   UUID REFERENCES users(id) ON DELETE SET NULL,
  owner_department TEXT,
  owner_team       TEXT,
  is_shared       BOOLEAN DEFAULT false,
  created_at      TIMESTAMPTZ DEFAULT now(),
  UNIQUE(org_id, resource_type, resource_id)
);
CREATE INDEX IF NOT EXISTS idx_ownership_org_type ON resource_ownership(org_id, resource_type);
CREATE INDEX IF NOT EXISTS idx_ownership_user ON resource_ownership(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_ownership_dept ON resource_ownership(owner_department);
CREATE INDEX IF NOT EXISTS idx_ownership_team ON resource_ownership(owner_team);
ALTER TABLE resource_ownership ENABLE ROW LEVEL SECURITY;
ALTER TABLE resource_ownership FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON resource_ownership
  USING (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid);

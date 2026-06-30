-- 005_rls_fix.sql — Fix RLS policy edge case for global data access.
--
-- P0-7 FIX: NULLIF(current_setting('app.org_id', true), '') returns NULL
-- when the setting is empty string, which matches rows where org_id IS NULL
-- (global patterns/policies). This is a cross-tenant data leakage vector.
--
-- Fix: Use a validated function that returns NULL for empty/invalid values.

-- Safe function to get current org_id from session context
CREATE OR REPLACE FUNCTION get_current_org_id()
RETURNS UUID AS $$
DECLARE
  v text;
BEGIN
  v := current_setting('app.org_id', true);
  IF v IS NULL OR v = '' THEN
    RETURN NULL;
  END IF;
  RETURN v::uuid;
EXCEPTION WHEN invalid_text_representation THEN
  RETURN NULL;
END;
$$ LANGUAGE plpgsql STABLE;

-- Safe function to get current user_id from session context
CREATE OR REPLACE FUNCTION get_current_user_id()
RETURNS UUID AS $$
DECLARE
  v text;
BEGIN
  v := current_setting('app.user_id', true);
  IF v IS NULL OR v = '' THEN
    RETURN NULL;
  END IF;
  RETURN v::uuid;
EXCEPTION WHEN invalid_text_representation THEN
  RETURN NULL;
END;
$$ LANGUAGE plpgsql STABLE;

-- =============================================================================
-- Update ALL tenant_isolation policies to use the safe function
-- =============================================================================

-- Drop old policies and recreate with safe function
-- runs
DROP POLICY IF EXISTS tenant_isolation ON runs;
CREATE POLICY tenant_isolation ON runs
  USING (org_id = get_current_org_id());
DROP POLICY IF EXISTS tenant_isolation_check ON runs;
CREATE POLICY tenant_isolation_check ON runs
  WITH CHECK (org_id = get_current_org_id());

-- artifacts
DROP POLICY IF EXISTS tenant_isolation ON artifacts;
CREATE POLICY tenant_isolation ON artifacts
  USING (org_id = get_current_org_id());
DROP POLICY IF EXISTS tenant_isolation_check ON artifacts;
CREATE POLICY tenant_isolation_check ON artifacts
  WITH CHECK (org_id = get_current_org_id());

-- events
DROP POLICY IF EXISTS tenant_isolation ON events;
CREATE POLICY tenant_isolation ON events
  USING (org_id = get_current_org_id());
DROP POLICY IF EXISTS tenant_isolation_check ON events;
CREATE POLICY tenant_isolation_check ON events
  WITH CHECK (org_id = get_current_org_id());

-- learning_objects
DROP POLICY IF EXISTS tenant_isolation ON learning_objects;
CREATE POLICY tenant_isolation ON learning_objects
  USING (org_id = get_current_org_id());
DROP POLICY IF EXISTS tenant_isolation_check ON learning_objects;
CREATE POLICY tenant_isolation_check ON learning_objects
  WITH CHECK (org_id = get_current_org_id());

-- execution_patterns (cross-org: org_id can be NULL for global patterns)
DROP POLICY IF EXISTS tenant_isolation ON execution_patterns;
CREATE POLICY tenant_isolation ON execution_patterns
  USING (org_id IS NULL OR org_id = get_current_org_id());
DROP POLICY IF EXISTS tenant_isolation_check ON execution_patterns;
CREATE POLICY tenant_isolation_check ON execution_patterns
  WITH CHECK (org_id IS NULL OR org_id = get_current_org_id());

-- operating_policies (cross-org for global policies)
DROP POLICY IF EXISTS tenant_isolation ON operating_policies;
CREATE POLICY tenant_isolation ON operating_policies
  USING (org_id IS NULL OR org_id = get_current_org_id());
DROP POLICY IF EXISTS tenant_isolation_check ON operating_policies;
CREATE POLICY tenant_isolation_check ON operating_policies
  WITH CHECK (org_id IS NULL OR org_id = get_current_org_id());

-- execution_receipts
DROP POLICY IF EXISTS tenant_isolation ON execution_receipts;
CREATE POLICY tenant_isolation ON execution_receipts
  USING (org_id = get_current_org_id());
DROP POLICY IF EXISTS tenant_isolation_check ON execution_receipts;
CREATE POLICY tenant_isolation_check ON execution_receipts
  WITH CHECK (org_id = get_current_org_id());

-- evidence_items
DROP POLICY IF EXISTS tenant_isolation ON evidence_items;
CREATE POLICY tenant_isolation ON evidence_items
  USING (org_id = get_current_org_id());
DROP POLICY IF EXISTS tenant_isolation_check ON evidence_items;
CREATE POLICY tenant_isolation_check ON evidence_items
  WITH CHECK (org_id = get_current_org_id());

-- cases
DROP POLICY IF EXISTS tenant_isolation ON cases;
CREATE POLICY tenant_isolation ON cases
  USING (org_id = get_current_org_id());
DROP POLICY IF EXISTS tenant_isolation_check ON cases;
CREATE POLICY tenant_isolation_check ON cases
  WITH CHECK (org_id = get_current_org_id());

-- integrations
DROP POLICY IF EXISTS tenant_isolation ON integrations;
CREATE POLICY tenant_isolation ON integrations
  USING (org_id = get_current_org_id());
DROP POLICY IF EXISTS tenant_isolation_check ON integrations;
CREATE POLICY tenant_isolation_check ON integrations
  WITH CHECK (org_id = get_current_org_id());

-- webhook_events
DROP POLICY IF EXISTS tenant_isolation ON webhook_events;
CREATE POLICY tenant_isolation ON webhook_events
  USING (org_id = get_current_org_id());
DROP POLICY IF EXISTS tenant_isolation_check ON webhook_events;
CREATE POLICY tenant_isolation_check ON webhook_events
  WITH CHECK (org_id = get_current_org_id());

-- api_keys
DROP POLICY IF EXISTS tenant_isolation ON api_keys;
CREATE POLICY tenant_isolation ON api_keys
  USING (org_id = get_current_org_id());
DROP POLICY IF EXISTS tenant_isolation_check ON api_keys;
CREATE POLICY tenant_isolation_check ON api_keys
  WITH CHECK (org_id = get_current_org_id());

-- audit_log (org_id can be NULL for auth events before org context)
DROP POLICY IF EXISTS tenant_isolation ON audit_log;
CREATE POLICY tenant_isolation ON audit_log
  USING (org_id IS NULL OR org_id = get_current_org_id());
DROP POLICY IF EXISTS tenant_isolation_check ON audit_log;
CREATE POLICY tenant_isolation_check ON audit_log
  WITH CHECK (org_id IS NULL OR org_id = get_current_org_id());

-- organization_members
DROP POLICY IF EXISTS tenant_isolation ON organization_members;
CREATE POLICY tenant_isolation ON organization_members
  USING (org_id = get_current_org_id());
DROP POLICY IF EXISTS tenant_isolation_check ON organization_members;
CREATE POLICY tenant_isolation_check ON organization_members
  WITH CHECK (org_id = get_current_org_id());

-- departments
DROP POLICY IF EXISTS tenant_isolation ON departments;
CREATE POLICY tenant_isolation ON departments
  USING (org_id = get_current_org_id());
DROP POLICY IF EXISTS tenant_isolation_check ON departments;
CREATE POLICY tenant_isolation_check ON departments
  WITH CHECK (org_id = get_current_org_id());

-- teams
DROP POLICY IF EXISTS tenant_isolation ON teams;
CREATE POLICY tenant_isolation ON teams
  USING (org_id = get_current_org_id());
DROP POLICY IF EXISTS tenant_isolation_check ON teams;
CREATE POLICY tenant_isolation_check ON teams
  WITH CHECK (org_id = get_current_org_id());

-- invitations
DROP POLICY IF EXISTS tenant_isolation ON invitations;
CREATE POLICY tenant_isolation ON invitations
  USING (org_id = get_current_org_id());
DROP POLICY IF EXISTS tenant_isolation_check ON invitations;
CREATE POLICY tenant_isolation_check ON invitations
  WITH CHECK (org_id = get_current_org_id());

-- refresh_tokens (scoped by user_id)
DROP POLICY IF EXISTS user_isolation ON refresh_tokens;
CREATE POLICY user_isolation ON refresh_tokens
  USING (user_id = get_current_user_id());

-- role_assignments
DROP POLICY IF EXISTS tenant_isolation ON role_assignments;
CREATE POLICY tenant_isolation ON role_assignments
  USING (org_id = get_current_org_id());
DROP POLICY IF EXISTS tenant_isolation_check ON role_assignments;
CREATE POLICY tenant_isolation_check ON role_assignments
  WITH CHECK (org_id = get_current_org_id());

-- resource_ownership
DROP POLICY IF EXISTS tenant_isolation ON resource_ownership;
CREATE POLICY tenant_isolation ON resource_ownership
  USING (org_id = get_current_org_id());
DROP POLICY IF EXISTS tenant_isolation_check ON resource_ownership;
CREATE POLICY tenant_isolation_check ON resource_ownership
  WITH CHECK (org_id = get_current_org_id());

-- custom_roles
DROP POLICY IF EXISTS tenant_isolation ON custom_roles;
CREATE POLICY tenant_isolation ON custom_roles
  USING (org_id = get_current_org_id());
DROP POLICY IF EXISTS tenant_isolation_check ON custom_roles;
CREATE POLICY tenant_isolation_check ON custom_roles
  WITH CHECK (org_id = get_current_org_id());

-- role_permissions
DROP POLICY IF EXISTS tenant_isolation ON role_permissions;
CREATE POLICY tenant_isolation ON role_permissions
  USING (org_id = get_current_org_id());
DROP POLICY IF EXISTS tenant_isolation_check ON role_permissions;
CREATE POLICY tenant_isolation_check ON role_permissions
  WITH CHECK (org_id = get_current_org_id());

-- Add token_prefix column to refresh_tokens (for P0-1 fix)
ALTER TABLE refresh_tokens ADD COLUMN IF NOT EXISTS token_prefix TEXT;
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_prefix ON refresh_tokens(token_prefix) WHERE revoked_at IS NULL;

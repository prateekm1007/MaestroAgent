-- 002_core_data.sql — Core data tables for runs, learning, patterns, policies,
-- receipts, evidence, integrations, design partners, evidence ledger, observatory.
--
-- Replaces all JSONL file storage with PostgreSQL tables.
-- All tenant-scoped tables have Row-Level Security enabled.

-- ============================================================================
-- RUNS
-- ============================================================================

CREATE TABLE IF NOT EXISTS runs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  user_id         UUID REFERENCES users(id),
  goal            TEXT NOT NULL,
  goal_class      TEXT,
  status          TEXT NOT NULL DEFAULT 'pending',
  team            JSONB,
  avg_confidence  INTEGER,
  duration_ms     INTEGER,
  started_at      TIMESTAMPTZ DEFAULT now(),
  ended_at        TIMESTAMPTZ,
  error           TEXT,
  scope           JSONB DEFAULT '{}',
  current_agent_id TEXT,
  interrupt_queue JSONB DEFAULT '[]',
  consumed_interrupts JSONB DEFAULT '[]',
  created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_runs_org ON runs(org_id);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(org_id, created_at DESC);
ALTER TABLE runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE runs FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON runs USING (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid);

-- ============================================================================
-- ARTIFACTS
-- ============================================================================

CREATE TABLE IF NOT EXISTS artifacts (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id          UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  agent_id        TEXT NOT NULL,
  agent_name      TEXT NOT NULL,
  filename        TEXT NOT NULL,
  content         TEXT NOT NULL,
  bytes           INTEGER NOT NULL,
  confidence      INTEGER,
  is_final        BOOLEAN DEFAULT false,
  is_debate_resolution BOOLEAN DEFAULT false,
  preview         TEXT,
  created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_artifacts_run ON artifacts(run_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_org ON artifacts(org_id);
ALTER TABLE artifacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE artifacts FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON artifacts USING (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid);

-- ============================================================================
-- EVENTS (run event stream)
-- ============================================================================

CREATE TABLE IF NOT EXISTS events (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id          UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  type            TEXT NOT NULL,
  payload         JSONB NOT NULL DEFAULT '{}',
  event_id        UUID NOT NULL,
  ts              TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id, ts);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(org_id, type);
CREATE INDEX IF NOT EXISTS idx_events_org_ts ON events(org_id, ts DESC);
ALTER TABLE events ENABLE ROW LEVEL SECURITY;
ALTER TABLE events FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON events USING (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid);

-- ============================================================================
-- LEARNING OBJECTS
-- ============================================================================

CREATE TABLE IF NOT EXISTS learning_objects (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id                  UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  org_id                  UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  goal                    TEXT NOT NULL,
  goal_class              TEXT NOT NULL,
  team_template           TEXT[],
  specialists             JSONB DEFAULT '[]',
  interrupts              JSONB DEFAULT '[]',
  predicted_confidence    INTEGER,
  outcome                 TEXT DEFAULT 'pending',
  outcome_notes           TEXT,
  lessons                 TEXT,
  workflow_score_delta    INTEGER DEFAULT 0,
  deliverable_count       INTEGER,
  duration_ms             INTEGER,
  scope                   JSONB DEFAULT '{}',
  scope_key               TEXT,
  scope_level             TEXT,
  created_at              TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_lo_org ON learning_objects(org_id);
CREATE INDEX IF NOT EXISTS idx_lo_scope ON learning_objects(scope_key);
CREATE INDEX IF NOT EXISTS idx_lo_class ON learning_objects(goal_class);
CREATE INDEX IF NOT EXISTS idx_lo_outcome ON learning_objects(org_id, outcome);
CREATE INDEX IF NOT EXISTS idx_lo_run ON learning_objects(run_id);
ALTER TABLE learning_objects ENABLE ROW LEVEL SECURITY;
ALTER TABLE learning_objects FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON learning_objects USING (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid);

-- ============================================================================
-- EXECUTION PATTERNS
-- ============================================================================

CREATE TABLE IF NOT EXISTS execution_patterns (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id                  UUID REFERENCES organizations(id) ON DELETE CASCADE,
  goal_class              TEXT NOT NULL,
  goal_class_keywords     TEXT[] DEFAULT '{}',
  scope_key               TEXT NOT NULL,
  scope_level             TEXT NOT NULL,
  scope                   JSONB DEFAULT '{}',
  winning_workflow        JSONB DEFAULT '[]',
  observed_failures       JSONB DEFAULT '[]',
  successful_corrections  JSONB DEFAULT '[]',
  confidence_calibration  JSONB DEFAULT '{}',
  acceptance_rate         FLOAT,
  project_count           INTEGER DEFAULT 0,
  source_run_ids          UUID[] DEFAULT '{}',
  source_pattern_ids      UUID[] DEFAULT '{}',
  is_promoted             BOOLEAN DEFAULT false,
  case_count              INTEGER DEFAULT 0,
  success_rate            FLOAT,
  typical_evidence        JSONB DEFAULT '[]',
  version                 INTEGER DEFAULT 0,
  last_updated            TIMESTAMPTZ DEFAULT now(),
  created_at              TIMESTAMPTZ DEFAULT now(),
  UNIQUE(goal_class, scope_key)
);
CREATE INDEX IF NOT EXISTS idx_patterns_class ON execution_patterns(goal_class);
CREATE INDEX IF NOT EXISTS idx_patterns_scope ON execution_patterns(scope_key);
CREATE INDEX IF NOT EXISTS idx_patterns_org ON execution_patterns(org_id);
ALTER TABLE execution_patterns ENABLE ROW LEVEL SECURITY;
ALTER TABLE execution_patterns FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON execution_patterns
  USING (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid OR org_id IS NULL);

-- ============================================================================
-- OPERATING POLICIES (includes governance controls)
-- ============================================================================

CREATE TABLE IF NOT EXISTS operating_policies (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              UUID REFERENCES organizations(id) ON DELETE CASCADE,
  rule                TEXT NOT NULL,
  scope_key           TEXT NOT NULL,
  scope_level         TEXT NOT NULL,
  scope               JSONB DEFAULT '{}',
  category            TEXT DEFAULT 'custom',
  enforcement         TEXT DEFAULT 'recommended',
  evidence_required   TEXT,
  reviewer            TEXT,
  approval_required   BOOLEAN DEFAULT false,
  block_execution     BOOLEAN DEFAULT false,
  exception_allowed   BOOLEAN DEFAULT true,
  violation_action    TEXT DEFAULT 'warn',
  promoted_from       UUID,
  reinforcement_count INTEGER DEFAULT 0,
  violation_count     INTEGER DEFAULT 0,
  status              TEXT DEFAULT 'active',
  created_at          TIMESTAMPTZ DEFAULT now(),
  last_reinforced     TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_policies_org ON operating_policies(org_id);
CREATE INDEX IF NOT EXISTS idx_policies_scope ON operating_policies(scope_key);
CREATE INDEX IF NOT EXISTS idx_policies_enforcement ON operating_policies(enforcement) WHERE status = 'active';
ALTER TABLE operating_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE operating_policies FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON operating_policies
  USING (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid OR org_id IS NULL);

-- ============================================================================
-- EXECUTION RECEIPTS (includes evidence items)
-- ============================================================================

CREATE TABLE IF NOT EXISTS execution_receipts (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id            UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  org_id            UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  goal              TEXT NOT NULL,
  goal_class        TEXT,
  scope             JSONB DEFAULT '{}',
  plan              JSONB DEFAULT '{}',
  policies_applied  JSONB DEFAULT '[]',
  patterns_used     JSONB DEFAULT '[]',
  evidence          JSONB DEFAULT '[]',
  approvals         JSONB DEFAULT '[]',
  exceptions        JSONB DEFAULT '[]',
  confidence        JSONB DEFAULT '{}',
  outcome           JSONB DEFAULT '{}',
  execution         JSONB DEFAULT '{}',
  lessons           TEXT,
  receipt_hash      TEXT NOT NULL,
  created_at        TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_receipts_run ON execution_receipts(run_id);
CREATE INDEX IF NOT EXISTS idx_receipts_org ON execution_receipts(org_id);
CREATE INDEX IF NOT EXISTS idx_receipts_hash ON execution_receipts(receipt_hash);
CREATE INDEX IF NOT EXISTS idx_receipts_created ON execution_receipts(org_id, created_at DESC);
ALTER TABLE execution_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE execution_receipts FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON execution_receipts
  USING (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid);

-- ============================================================================
-- EVIDENCE ITEMS
-- ============================================================================

CREATE TABLE IF NOT EXISTS evidence_items (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  receipt_id      UUID NOT NULL REFERENCES execution_receipts(id) ON DELETE CASCADE,
  run_id          UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  type            TEXT NOT NULL,
  description     TEXT,
  reviewer        TEXT,
  artifacts       JSONB DEFAULT '[]',
  policy_addressed TEXT,
  policy_enforcement TEXT,
  timestamp       TIMESTAMPTZ DEFAULT now(),
  hash            TEXT,
  scope           JSONB DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_evidence_receipt ON evidence_items(receipt_id);
CREATE INDEX IF NOT EXISTS idx_evidence_org ON evidence_items(org_id);
CREATE INDEX IF NOT EXISTS idx_evidence_type ON evidence_items(org_id, type);
ALTER TABLE evidence_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_items FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON evidence_items
  USING (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid);

-- ============================================================================
-- CASES
-- ============================================================================

CREATE TABLE IF NOT EXISTS cases (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  receipt_id      UUID NOT NULL REFERENCES execution_receipts(id) ON DELETE CASCADE,
  run_id          UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  goal            TEXT NOT NULL,
  goal_class      TEXT,
  evidence        UUID[] DEFAULT '{}',
  evidence_types  TEXT[] DEFAULT '{}',
  policies_addressed TEXT[] DEFAULT '{}',
  outcome         TEXT DEFAULT 'pending',
  scope           JSONB DEFAULT '{}',
  scope_key       TEXT,
  precedent_strength FLOAT DEFAULT 0,
  created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cases_org ON cases(org_id);
CREATE INDEX IF NOT EXISTS idx_cases_class ON cases(goal_class);
CREATE INDEX IF NOT EXISTS idx_cases_scope ON cases(scope_key);
ALTER TABLE cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE cases FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON cases
  USING (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid);

-- ============================================================================
-- PRECEDENTS
-- ============================================================================

CREATE TABLE IF NOT EXISTS precedents (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          UUID REFERENCES organizations(id) ON DELETE CASCADE,
  goal_class      TEXT NOT NULL,
  scope_key       TEXT NOT NULL,
  scope_level     TEXT NOT NULL,
  case_ids        UUID[] DEFAULT '{}',
  case_count      INTEGER DEFAULT 0,
  success_rate    FLOAT,
  typical_evidence JSONB DEFAULT '[]',
  pattern         TEXT,
  created_at      TIMESTAMPTZ DEFAULT now(),
  last_updated    TIMESTAMPTZ DEFAULT now(),
  UNIQUE(goal_class, scope_key)
);
CREATE INDEX IF NOT EXISTS idx_precedents_class ON precedents(goal_class);
CREATE INDEX IF NOT EXISTS idx_precedents_scope ON precedents(scope_key);
ALTER TABLE precedents ENABLE ROW LEVEL SECURITY;
ALTER TABLE precedents FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON precedents
  USING (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid OR org_id IS NULL);

-- ============================================================================
-- INTEGRATIONS
-- ============================================================================

CREATE TABLE IF NOT EXISTS integrations (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  provider_id     TEXT NOT NULL,
  provider_name   TEXT NOT NULL,
  capabilities    TEXT[] DEFAULT '{}',
  config          JSONB DEFAULT '{}',
  credentials     TEXT,
  status          TEXT DEFAULT 'connected',
  connected_at    TIMESTAMPTZ DEFAULT now(),
  disconnected_at TIMESTAMPTZ,
  last_sync_at    TIMESTAMPTZ,
  events_received INTEGER DEFAULT 0,
  events_sent     INTEGER DEFAULT 0,
  created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_integrations_org ON integrations(org_id);
CREATE INDEX IF NOT EXISTS idx_integrations_provider ON integrations(org_id, provider_id) WHERE status = 'connected';
ALTER TABLE integrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE integrations FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON integrations
  USING (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid);

-- ============================================================================
-- WEBHOOK EVENTS (deduplication)
-- ============================================================================

CREATE TABLE IF NOT EXISTS webhook_events (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          UUID NOT NULL,
  provider        TEXT NOT NULL,
  event_id        TEXT NOT NULL,
  payload         JSONB DEFAULT '{}',
  processed       BOOLEAN DEFAULT false,
  processed_at    TIMESTAMPTZ,
  created_at      TIMESTAMPTZ DEFAULT now(),
  UNIQUE(org_id, provider, event_id)
);
CREATE INDEX IF NOT EXISTS idx_webhook_org_provider ON webhook_events(org_id, provider);
ALTER TABLE webhook_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE webhook_events FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON webhook_events
  USING (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid);

-- ============================================================================
-- OPERATING MODELS (SDK)
-- ============================================================================

CREATE TABLE IF NOT EXISTS operating_models (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          TEXT NOT NULL,
  name            TEXT NOT NULL,
  industry        TEXT DEFAULT 'technology',
  hierarchy       JSONB DEFAULT '[]',
  approval_chains JSONB DEFAULT '[]',
  policies        JSONB DEFAULT '[]',
  workflow_templates JSONB DEFAULT '[]',
  compliance_mappings JSONB DEFAULT '[]',
  integration_bindings JSONB DEFAULT '[]',
  status          TEXT DEFAULT 'active',
  version         INTEGER DEFAULT 1,
  registered_at   TIMESTAMPTZ DEFAULT now(),
  UNIQUE(org_id)
);
CREATE INDEX IF NOT EXISTS idx_models_org ON operating_models(org_id);

-- ============================================================================
-- DESIGN PARTNERS
-- ============================================================================

CREATE TABLE IF NOT EXISTS design_partners (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          TEXT NOT NULL,
  name            TEXT NOT NULL,
  industry        TEXT DEFAULT 'technology',
  contact_name    TEXT,
  contact_email   TEXT,
  stage           TEXT DEFAULT 'organization_setup',
  stages          JSONB DEFAULT '{}',
  operating_model JSONB,
  first_run_id    UUID,
  roi_report      JSONB,
  onboarded_at    TIMESTAMPTZ,
  created_at      TIMESTAMPTZ DEFAULT now(),
  UNIQUE(org_id)
);
CREATE INDEX IF NOT EXISTS idx_partners_org ON design_partners(org_id);

-- ============================================================================
-- HYPOTHESES (Evidence Ledger)
-- ============================================================================

CREATE TABLE IF NOT EXISTS hypotheses (
  id              TEXT PRIMARY KEY,
  hypothesis      TEXT NOT NULL,
  category        TEXT DEFAULT 'general',
  confidence      TEXT DEFAULT 'low',
  evidence_for    JSONB DEFAULT '[]',
  evidence_against JSONB DEFAULT '[]',
  decision        TEXT DEFAULT 'continue',
  next_experiment TEXT,
  status          TEXT DEFAULT 'testing',
  created_at      TIMESTAMPTZ DEFAULT now(),
  last_updated    TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_hypotheses_status ON hypotheses(status);
CREATE INDEX IF NOT EXISTS idx_hypotheses_confidence ON hypotheses(confidence);

-- ============================================================================
-- FRIDAY DASHBOARDS
-- ============================================================================

CREATE TABLE IF NOT EXISTS friday_dashboards (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  date            TEXT NOT NULL,
  responses       JSONB DEFAULT '{}',
  saved_at        TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_friday_date ON friday_dashboards(date DESC);

-- ============================================================================
-- OBSERVATORY OBSERVATIONS (anonymous, cross-org)
-- ============================================================================

CREATE TABLE IF NOT EXISTS observatory_observations (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id_hash     TEXT NOT NULL,
  size_bucket     TEXT NOT NULL,
  industry        TEXT DEFAULT 'technology',
  metrics         JSONB DEFAULT '{}',
  operational     JSONB DEFAULT '{}',
  contributed_at  TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_observatory_bucket ON observatory_observations(size_bucket);
CREATE INDEX IF NOT EXISTS idx_observatory_industry ON observatory_observations(industry);

-- ============================================================================
-- PARTNER PROMISES (CPR)
-- ============================================================================

CREATE TABLE IF NOT EXISTS partner_promises (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          TEXT NOT NULL UNIQUE,
  promised_outcome TEXT NOT NULL DEFAULT '15% cycle time reduction',
  target_reduction FLOAT DEFAULT 15,
  baseline        JSONB DEFAULT '{}',
  start_date      TIMESTAMPTZ DEFAULT now(),
  days_to_prove   INTEGER DEFAULT 90,
  created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_promises_org ON partner_promises(org_id);

-- ============================================================================
-- MIGRATION TRACKING
-- ============================================================================

-- Already created in 001_auth_core.sql, but ensure it exists
CREATE TABLE IF NOT EXISTS schema_migrations (
  filename    TEXT PRIMARY KEY,
  executed_at TIMESTAMPTZ DEFAULT now()
);

// src/repository.js — PostgreSQL repository layer.
//
// Replaces ALL JSONL file storage and in-memory Maps with PostgreSQL queries.
// Every storage module in the codebase calls through this layer.
//
// Structure:
//   - runs: insert, getById, listByOrg, update, delete
//   - artifacts: insert, getByRun, getByFilename
//   - events: insert, getByRun, getByOrg
//   - learningObjects: insert, getById, getByRunId, listByOrg, update, retrieveSimilar
//   - patterns: insert, getOrCreate, getById, listAll, listByGoalClass, update
//   - policies: insert, getById, listAll, listByScope, update
//   - receipts: insert, getByRunId, getById, listByOrg, listAll, update
//   - evidenceItems: insert, getByReceipt, getByOrg
//   - cases: insert, getById, listAll
//   - precedents: insert, getOrCreate, listAll, update
//   - integrations: insert, getByOrg, getById, update, delete
//   - webhookEvents: insert, checkDuplicate
//   - operatingModels: insert, getByOrgId, listAll
//   - designPartners: insert, getByOrgId, listAll, update
//   - hypotheses: insert, getById, listAll, update
//   - fridayDashboards: insert, listAll
//   - observatoryObservations: insert, listAll
//   - partnerPromises: upsert, getByOrgId, listAll
//
// All functions use parameterized queries (no SQL injection).
// Tenant-scoped queries include org_id filter.
// JSONB columns use $1::jsonb for proper type casting.

import { query, withTransaction } from './db.js';

// ============================================================================
// RUNS
// ============================================================================

export const runsRepo = {
  async insert(data) {
    const result = await query(
      `INSERT INTO runs (id, org_id, user_id, goal, goal_class, status, team, scope, current_agent_id, interrupt_queue, consumed_interrupts, started_at)
       VALUES (COALESCE($1, gen_random_uuid()), $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9, $10::jsonb, $11::jsonb, COALESCE($12, now()))
       RETURNING *`,
      [
        data.id || null, data.org_id, data.user_id || null, data.goal,
        data.goal_class || null, data.status || 'pending',
        JSON.stringify(data.team || {}), JSON.stringify(data.scope || {}),
        data.current_agent_id || null,
        JSON.stringify(data.interrupt_queue || []),
        JSON.stringify(data.consumed_interrupts || []),
        data.started_at || null,
      ]
    );
    return result.rows[0];
  },

  async getById(id) {
    const result = await query('SELECT * FROM runs WHERE id = $1', [id]);
    return result.rows[0] || null;
  },

  async listByOrg(orgId, limit = 50, offset = 0) {
    const result = await query(
      'SELECT * FROM runs WHERE org_id = $1 ORDER BY created_at DESC LIMIT $2 OFFSET $3',
      [orgId, limit, offset]
    );
    return result.rows;
  },

  async update(id, updates) {
    const setClauses = [];
    const params = [id];
    let paramIdx = 2;

    for (const [key, value] of Object.entries(updates)) {
      if (value === undefined) continue;
      if (['team', 'scope', 'interrupt_queue', 'consumed_interrupts'].includes(key)) {
        setClauses.push(`${key} = $${paramIdx}::jsonb`);
        params.push(JSON.stringify(value));
      } else {
        setClauses.push(`${key} = $${paramIdx}`);
        params.push(value);
      }
      paramIdx++;
    }

    if (setClauses.length === 0) return await this.getById(id);

    const result = await query(
      `UPDATE runs SET ${setClauses.join(', ')} WHERE id = $1 RETURNING *`,
      params
    );
    return result.rows[0] || null;
  },

  async listAll(limit = 100) {
    const result = await query('SELECT * FROM runs ORDER BY created_at DESC LIMIT $1', [limit]);
    return result.rows;
  },
};

// ============================================================================
// ARTIFACTS
// ============================================================================

export const artifactsRepo = {
  async insert(data) {
    const result = await query(
      `INSERT INTO artifacts (run_id, org_id, agent_id, agent_name, filename, content, bytes, confidence, is_final, is_debate_resolution, preview)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
       RETURNING *`,
      [data.run_id, data.org_id, data.agent_id, data.agent_name, data.filename, data.content,
       data.bytes, data.confidence || null, data.is_final || false, data.is_debate_resolution || false,
       data.preview || null]
    );
    return result.rows[0];
  },

  async getByRun(runId) {
    const result = await query('SELECT * FROM artifacts WHERE run_id = $1 ORDER BY created_at', [runId]);
    return result.rows;
  },

  async getByFilename(runId, filename) {
    const result = await query(
      'SELECT * FROM artifacts WHERE run_id = $1 AND filename = $2',
      [runId, filename]
    );
    return result.rows[0] || null;
  },
};

// ============================================================================
// EVENTS
// ============================================================================

export const eventsRepo = {
  async insert(data) {
    const result = await query(
      `INSERT INTO events (run_id, org_id, type, payload, event_id, ts)
       VALUES ($1, $2, $3, $4::jsonb, COALESCE($5, gen_random_uuid()), COALESCE($6, now()))
       RETURNING *`,
      [data.run_id, data.org_id, data.type, JSON.stringify(data.payload || {}),
       data.event_id || null, data.ts || null]
    );
    return result.rows[0];
  },

  async getByRun(runId) {
    const result = await query('SELECT * FROM events WHERE run_id = $1 ORDER BY ts', [runId]);
    return result.rows;
  },

  async getByOrg(orgId, limit = 100) {
    const result = await query(
      'SELECT * FROM events WHERE org_id = $1 ORDER BY ts DESC LIMIT $2',
      [orgId, limit]
    );
    return result.rows;
  },
};

// ============================================================================
// LEARNING OBJECTS
// ============================================================================

export const learningObjectsRepo = {
  async insert(data) {
    const result = await query(
      `INSERT INTO learning_objects
        (run_id, org_id, goal, goal_class, team_template, specialists, interrupts,
         predicted_confidence, outcome, outcome_notes, lessons, workflow_score_delta,
         deliverable_count, duration_ms, scope, scope_key, scope_level)
       VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8, $9, $10, $11, $12, $13, $14, $15::jsonb, $16, $17)
       RETURNING *`,
      [data.run_id, data.org_id, data.goal, data.goal_class,
       data.team_template || [], JSON.stringify(data.specialists || []),
       JSON.stringify(data.interrupts || []), data.predicted_confidence || null,
       data.outcome || 'pending', data.outcome_notes || '', data.lessons || '',
       data.workflow_score_delta || 0, data.deliverable_count || 0,
       data.duration_ms || 0, JSON.stringify(data.scope || {}),
       data.scope_key || null, data.scope_level || null]
    );
    return result.rows[0];
  },

  async getByRunId(runId) {
    const result = await query('SELECT * FROM learning_objects WHERE run_id = $1', [runId]);
    return result.rows[0] || null;
  },

  async listByOrg(orgId) {
    const result = await query('SELECT * FROM learning_objects WHERE org_id = $1 ORDER BY created_at DESC', [orgId]);
    return result.rows;
  },

  async listAll() {
    const result = await query('SELECT * FROM learning_objects ORDER BY created_at DESC');
    return result.rows;
  },

  async update(id, updates) {
    const setClauses = [];
    const params = [id];
    let paramIdx = 2;
    for (const [key, value] of Object.entries(updates)) {
      if (value === undefined) continue;
      if (['specialists', 'interrupts', 'scope'].includes(key)) {
        setClauses.push(`${key} = $${paramIdx}::jsonb`);
        params.push(JSON.stringify(value));
      } else {
        setClauses.push(`${key} = $${paramIdx}`);
        params.push(value);
      }
      paramIdx++;
    }
    if (setClauses.length === 0) return null;
    const result = await query(`UPDATE learning_objects SET ${setClauses.join(', ')} WHERE id = $1 RETURNING *`, params);
    return result.rows[0] || null;
  },

  async retrieveSimilar(goal, limit = 3) {
    // Simple keyword overlap search.
    // In production, use PostgreSQL full-text search or pgvector.
    const tokens = goal.toLowerCase().replace(/[^a-z0-9\s]/g, ' ').split(/\s+/).filter(t => t.length > 2);
    if (tokens.length === 0) return [];
    const result = await query(
      `SELECT *, goal FROM learning_objects
       WHERE lessons IS NOT NULL AND lessons != ''
       AND (${tokens.map((_, i) => `LOWER(goal) LIKE '%' || $${i + 1} || '%'`).join(' OR ')})
       ORDER BY created_at DESC LIMIT $${tokens.length + 1}`,
      [...tokens, limit]
    );
    return result.rows;
  },
};

// ============================================================================
// EXECUTION PATTERNS
// ============================================================================

export const patternsRepo = {
  async getOrCreate(goalClass, scopeLvl) {
    const scopeKey = scopeLvl.scopeKey || 'global';
    const result = await query(
      `INSERT INTO execution_patterns (goal_class, scope_key, scope_level, scope, version, last_updated)
       VALUES ($1, $2, $3, $4::jsonb, 0, now())
       ON CONFLICT (goal_class, scope_key) DO UPDATE SET last_updated = now()
       RETURNING *`,
      [goalClass, scopeKey, scopeLvl.level || 'global',
       JSON.stringify(scopeLvl)]
    );
    return result.rows[0];
  },

  async getById(id) {
    const result = await query('SELECT * FROM execution_patterns WHERE id = $1', [id]);
    return result.rows[0] || null;
  },

  async listAll() {
    const result = await query('SELECT * FROM execution_patterns ORDER BY last_updated DESC');
    return result.rows;
  },

  async listByGoalClass(goalClass) {
    const result = await query('SELECT * FROM execution_patterns WHERE goal_class = $1 ORDER BY last_updated DESC', [goalClass]);
    return result.rows;
  },

  async update(id, updates) {
    const setClauses = ['last_updated = now()'];
    const params = [id];
    let paramIdx = 2;
    for (const [key, value] of Object.entries(updates)) {
      if (value === undefined) continue;
      const jsonbFields = ['winning_workflow', 'observed_failures', 'successful_corrections', 'confidence_calibration', 'scope', 'typical_evidence', 'source_run_ids', 'source_pattern_ids', 'goal_class_keywords'];
      if (jsonbFields.includes(key)) {
        setClauses.push(`${key} = $${paramIdx}::jsonb`);
        params.push(JSON.stringify(value));
      } else {
        setClauses.push(`${key} = $${paramIdx}`);
        params.push(value);
      }
      paramIdx++;
    }
    const result = await query(`UPDATE execution_patterns SET ${setClauses.join(', ')} WHERE id = $1 RETURNING *`, params);
    return result.rows[0] || null;
  },

  async findByGoalClassAndScope(goalClass, scopeKey) {
    const result = await query(
      'SELECT * FROM execution_patterns WHERE goal_class = $1 AND scope_key = $2 AND project_count > 0',
      [goalClass, scopeKey]
    );
    return result.rows[0] || null;
  },
};

// ============================================================================
// OPERATING POLICIES
// ============================================================================

export const policiesRepo = {
  async insert(data) {
    const result = await query(
      `INSERT INTO operating_policies
        (org_id, rule, scope_key, scope_level, scope, category, enforcement,
         evidence_required, reviewer, approval_required, block_execution,
         exception_allowed, violation_action, promoted_from, reinforcement_count,
         violation_count, status)
       VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
       RETURNING *`,
      [data.org_id || null, data.rule, data.scope_key, data.scope_level,
       JSON.stringify(data.scope || {}), data.category || 'custom',
       data.enforcement || 'recommended', data.evidence_required || null,
       data.reviewer || null, data.approval_required || false,
       data.block_execution || false, data.exception_allowed !== false,
       data.violation_action || 'warn', data.promoted_from || null,
       data.reinforcement_count || 0, data.violation_count || 0,
       data.status || 'active']
    );
    return result.rows[0];
  },

  async getById(id) {
    const result = await query('SELECT * FROM operating_policies WHERE id = $1', [id]);
    return result.rows[0] || null;
  },

  async listAll() {
    const result = await query("SELECT * FROM operating_policies WHERE status != 'deprecated' ORDER BY created_at DESC");
    return result.rows;
  },

  async listByScopeKey(scopeKey) {
    const result = await query(
      "SELECT * FROM operating_policies WHERE scope_key = $1 AND status != 'deprecated'",
      [scopeKey]
    );
    return result.rows;
  },

  async findByRuleAndScope(rulePrefix, scopeKey) {
    const result = await query(
      `SELECT * FROM operating_policies
       WHERE scope_key = $1 AND status != 'deprecated'
       AND LOWER(LEFT(rule, 60)) = LOWER(LEFT($2, 60))`,
      [scopeKey, rulePrefix]
    );
    return result.rows[0] || null;
  },

  async update(id, updates) {
    const setClauses = ['last_reinforced = now()'];
    const params = [id];
    let paramIdx = 2;
    for (const [key, value] of Object.entries(updates)) {
      if (value === undefined) continue;
      if (['scope'].includes(key)) {
        setClauses.push(`${key} = $${paramIdx}::jsonb`);
        params.push(JSON.stringify(value));
      } else {
        setClauses.push(`${key} = $${paramIdx}`);
        params.push(value);
      }
      paramIdx++;
    }
    const result = await query(`UPDATE operating_policies SET ${setClauses.join(', ')} WHERE id = $1 RETURNING *`, params);
    return result.rows[0] || null;
  },
};

// ============================================================================
// EXECUTION RECEIPTS
// ============================================================================

export const receiptsRepo = {
  async insert(data) {
    const result = await query(
      `INSERT INTO execution_receipts
        (run_id, org_id, goal, goal_class, scope, plan, policies_applied,
         patterns_used, evidence, approvals, exceptions, confidence, outcome,
         execution, lessons, receipt_hash)
       VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7::jsonb, $8::jsonb,
               $9::jsonb, $10::jsonb, $11::jsonb, $12::jsonb, $13::jsonb,
               $14::jsonb, $15, $16)
       RETURNING *`,
      [data.run_id, data.org_id, data.goal, data.goal_class || null,
       JSON.stringify(data.scope || {}), JSON.stringify(data.plan || {}),
       JSON.stringify(data.policies_applied || []),
       JSON.stringify(data.patterns_used || []),
       JSON.stringify(data.evidence || []),
       JSON.stringify(data.approvals || []),
       JSON.stringify(data.exceptions || []),
       JSON.stringify(data.confidence || {}),
       JSON.stringify(data.outcome || {}),
       JSON.stringify(data.execution || {}),
       data.lessons || '', data.receipt_hash]
    );
    return result.rows[0];
  },

  async getByRunId(runId) {
    const result = await query('SELECT * FROM execution_receipts WHERE run_id = $1', [runId]);
    return result.rows[0] || null;
  },

  async getById(id) {
    const result = await query('SELECT * FROM execution_receipts WHERE id = $1', [id]);
    return result.rows[0] || null;
  },

  async listByOrg(orgId, limit = 1000) {
    const result = await query(
      'SELECT * FROM execution_receipts WHERE org_id = $1 ORDER BY created_at DESC LIMIT $2',
      [orgId, limit]
    );
    return result.rows;
  },

  async listAll(limit = 10000) {
    const result = await query('SELECT * FROM execution_receipts ORDER BY created_at DESC LIMIT $1', [limit]);
    return result.rows;
  },
};

// ============================================================================
// EVIDENCE ITEMS
// ============================================================================

export const evidenceItemsRepo = {
  async insert(data) {
    const result = await query(
      `INSERT INTO evidence_items
        (receipt_id, run_id, org_id, type, description, reviewer, artifacts,
         policy_addressed, policy_enforcement, hash, scope)
       VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10, $11::jsonb)
       RETURNING *`,
      [data.receipt_id, data.run_id, data.org_id, data.type,
       data.description || null, data.reviewer || null,
       JSON.stringify(data.artifacts || []),
       data.policy_addressed || null, data.policy_enforcement || null,
       data.hash || null, JSON.stringify(data.scope || {})]
    );
    return result.rows[0];
  },

  async getByReceipt(receiptId) {
    const result = await query('SELECT * FROM evidence_items WHERE receipt_id = $1', [receiptId]);
    return result.rows;
  },

  async listByOrg(orgId, limit = 50) {
    const result = await query(
      'SELECT * FROM evidence_items WHERE org_id = $1 ORDER BY timestamp DESC LIMIT $2',
      [orgId, limit]
    );
    return result.rows;
  },

  async listAll(limit = 10000) {
    const result = await query('SELECT * FROM evidence_items ORDER BY timestamp DESC LIMIT $1', [limit]);
    return result.rows;
  },
};

// ============================================================================
// CASES
// ============================================================================

export const casesRepo = {
  async insert(data) {
    const result = await query(
      `INSERT INTO cases
        (receipt_id, run_id, org_id, goal, goal_class, evidence, evidence_types,
         policies_addressed, outcome, scope, scope_key, precedent_strength)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11, $12)
       RETURNING *`,
      [data.receipt_id, data.run_id, data.org_id, data.goal,
       data.goal_class || null, data.evidence || [], data.evidence_types || [],
       data.policies_addressed || [], data.outcome || 'pending',
       JSON.stringify(data.scope || {}), data.scope_key || null,
       data.precedent_strength || 0]
    );
    return result.rows[0];
  },

  async listAll(limit = 10000) {
    const result = await query('SELECT * FROM cases ORDER BY created_at DESC LIMIT $1', [limit]);
    return result.rows;
  },
};

// ============================================================================
// PRECEDENTS
// ============================================================================

export const precedentsRepo = {
  async getOrCreate(goalClass, scopeKey, scopeLevel) {
    const result = await query(
      `INSERT INTO precedents (goal_class, scope_key, scope_level)
       VALUES ($1, $2, $3)
       ON CONFLICT (goal_class, scope_key) DO UPDATE SET last_updated = now()
       RETURNING *`,
      [goalClass, scopeKey, scopeLevel]
    );
    return result.rows[0];
  },

  async listAll() {
    const result = await query('SELECT * FROM precedents ORDER BY case_count DESC');
    return result.rows;
  },

  async update(id, updates) {
    const setClauses = ['last_updated = now()'];
    const params = [id];
    let paramIdx = 2;
    for (const [key, value] of Object.entries(updates)) {
      if (value === undefined) continue;
      const jsonbFields = ['case_ids', 'typical_evidence'];
      if (jsonbFields.includes(key)) {
        setClauses.push(`${key} = $${paramIdx}::jsonb`);
        params.push(JSON.stringify(value));
      } else {
        setClauses.push(`${key} = $${paramIdx}`);
        params.push(value);
      }
      paramIdx++;
    }
    const result = await query(`UPDATE precedents SET ${setClauses.join(', ')} WHERE id = $1 RETURNING *`, params);
    return result.rows[0] || null;
  },

  async findByGoalClassAndScope(goalClass, scopeKey) {
    const result = await query(
      'SELECT * FROM precedents WHERE goal_class = $1 AND scope_key = $2 AND case_count > 0',
      [goalClass, scopeKey]
    );
    return result.rows[0] || null;
  },
};

// ============================================================================
// INTEGRATIONS
// ============================================================================

export const integrationsRepo = {
  async insert(data) {
    const result = await query(
      `INSERT INTO integrations (org_id, provider_id, provider_name, capabilities, config, credentials, status)
       VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)
       RETURNING *`,
      [data.org_id, data.provider_id, data.provider_name, data.capabilities || [],
       JSON.stringify(data.config || {}), data.credentials || null,
       data.status || 'connected']
    );
    return result.rows[0];
  },

  async listByOrg(orgId) {
    const result = await query(
      "SELECT * FROM integrations WHERE org_id = $1 AND status = 'connected' ORDER BY connected_at DESC",
      [orgId]
    );
    return result.rows;
  },

  async getById(id) {
    const result = await query('SELECT * FROM integrations WHERE id = $1', [id]);
    return result.rows[0] || null;
  },

  async findByOrgAndProvider(orgId, providerId) {
    const result = await query(
      "SELECT * FROM integrations WHERE org_id = $1 AND provider_id = $2 AND status = 'connected'",
      [orgId, providerId]
    );
    return result.rows[0] || null;
  },

  async update(id, updates) {
    const setClauses = [];
    const params = [id];
    let paramIdx = 2;
    for (const [key, value] of Object.entries(updates)) {
      if (value === undefined) continue;
      if (['config', 'capabilities'].includes(key)) {
        setClauses.push(`${key} = $${paramIdx}::jsonb`);
        params.push(JSON.stringify(value));
      } else {
        setClauses.push(`${key} = $${paramIdx}`);
        params.push(value);
      }
      paramIdx++;
    }
    if (setClauses.length === 0) return null;
    const result = await query(`UPDATE integrations SET ${setClauses.join(', ')} WHERE id = $1 RETURNING *`, params);
    return result.rows[0] || null;
  },

  async delete(id) {
    await query("UPDATE integrations SET status = 'disconnected', disconnected_at = now() WHERE id = $1", [id]);
  },
};

// ============================================================================
// WEBHOOK EVENTS (deduplication)
// ============================================================================

export const webhookEventsRepo = {
  async isDuplicate(orgId, provider, eventId) {
    const result = await query(
      'SELECT id FROM webhook_events WHERE org_id = $1 AND provider = $2 AND event_id = $3',
      [orgId, provider, eventId]
    );
    return result.rows.length > 0;
  },

  async markProcessed(orgId, provider, eventId, payload = {}) {
    await query(
      `INSERT INTO webhook_events (org_id, provider, event_id, payload, processed, processed_at)
       VALUES ($1, $2, $3, $4::jsonb, true, now())
       ON CONFLICT (org_id, provider, event_id) DO NOTHING`,
      [orgId, provider, eventId, JSON.stringify(payload)]
    );
  },
};

// ============================================================================
// OPERATING MODELS (SDK)
// ============================================================================

export const operatingModelsRepo = {
  async upsert(data) {
    const result = await query(
      `INSERT INTO operating_models
        (org_id, name, industry, hierarchy, approval_chains, policies,
         workflow_templates, compliance_mappings, integration_bindings, status, version)
       VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6::jsonb, $7::jsonb, $8::jsonb, $9::jsonb, 'active', 1)
       ON CONFLICT (org_id) DO UPDATE SET
         name = EXCLUDED.name, industry = EXCLUDED.industry,
         hierarchy = EXCLUDED.hierarchy, approval_chains = EXCLUDED.approval_chains,
         policies = EXCLUDED.policies, workflow_templates = EXCLUDED.workflow_templates,
         compliance_mappings = EXCLUDED.compliance_mappings,
         integration_bindings = EXCLUDED.integration_bindings,
         version = operating_models.version + 1
       RETURNING *`,
      [data.org_id, data.name, data.industry || 'technology',
       JSON.stringify(data.hierarchy || []),
       JSON.stringify(data.approval_chains || []),
       JSON.stringify(data.policies || []),
       JSON.stringify(data.workflow_templates || []),
       JSON.stringify(data.compliance_mappings || []),
       JSON.stringify(data.integration_bindings || [])]
    );
    return result.rows[0];
  },

  async getByOrgId(orgId) {
    const result = await query('SELECT * FROM operating_models WHERE org_id = $1', [orgId]);
    return result.rows[0] || null;
  },

  async listAll() {
    const result = await query('SELECT * FROM operating_models ORDER BY registered_at DESC');
    return result.rows;
  },
};

// ============================================================================
// DESIGN PARTNERS
// ============================================================================

export const designPartnersRepo = {
  async insert(data) {
    const result = await query(
      `INSERT INTO design_partners (org_id, name, industry, contact_name, contact_email, stage, stages)
       VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
       ON CONFLICT (org_id) DO UPDATE SET name = EXCLUDED.name
       RETURNING *`,
      [data.org_id, data.name, data.industry || 'technology',
       data.contact_name || null, data.contact_email || null,
       data.stage || 'organization_setup',
       JSON.stringify(data.stages || {})]
    );
    return result.rows[0];
  },

  async getByOrgId(orgId) {
    const result = await query('SELECT * FROM design_partners WHERE org_id = $1', [orgId]);
    return result.rows[0] || null;
  },

  async listAll() {
    const result = await query('SELECT * FROM design_partners ORDER BY created_at DESC');
    return result.rows;
  },

  async update(orgId, updates) {
    const setClauses = [];
    const params = [orgId];
    let paramIdx = 2;
    for (const [key, value] of Object.entries(updates)) {
      if (value === undefined) continue;
      if (['stages', 'operating_model', 'roi_report'].includes(key)) {
        setClauses.push(`${key} = $${paramIdx}::jsonb`);
        params.push(JSON.stringify(value));
      } else {
        setClauses.push(`${key} = $${paramIdx}`);
        params.push(value);
      }
      paramIdx++;
    }
    if (setClauses.length === 0) return null;
    const result = await query(`UPDATE design_partners SET ${setClauses.join(', ')} WHERE org_id = $1 RETURNING *`, params);
    return result.rows[0] || null;
  },
};

// ============================================================================
// HYPOTHESES (Evidence Ledger)
// ============================================================================

export const hypothesesRepo = {
  async insert(data) {
    const result = await query(
      `INSERT INTO hypotheses (id, hypothesis, category, confidence, evidence_for, evidence_against, decision, next_experiment, status)
       VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8, $9)
       ON CONFLICT (id) DO NOTHING
       RETURNING *`,
      [data.id, data.hypothesis, data.category || 'general',
       data.confidence || 'low', JSON.stringify(data.evidence_for || []),
       JSON.stringify(data.evidence_against || []),
       data.decision || 'continue', data.next_experiment || '',
       data.status || 'testing']
    );
    return result.rows[0];
  },

  async getById(id) {
    const result = await query('SELECT * FROM hypotheses WHERE id = $1', [id]);
    return result.rows[0] || null;
  },

  async listAll() {
    const result = await query('SELECT * FROM hypotheses ORDER BY id');
    return result.rows;
  },

  async update(id, updates) {
    const setClauses = ['last_updated = now()'];
    const params = [id];
    let paramIdx = 2;
    for (const [key, value] of Object.entries(updates)) {
      if (value === undefined) continue;
      if (['evidence_for', 'evidence_against'].includes(key)) {
        setClauses.push(`${key} = $${paramIdx}::jsonb`);
        params.push(JSON.stringify(value));
      } else {
        setClauses.push(`${key} = $${paramIdx}`);
        params.push(value);
      }
      paramIdx++;
    }
    const result = await query(`UPDATE hypotheses SET ${setClauses.join(', ')} WHERE id = $1 RETURNING *`, params);
    return result.rows[0] || null;
  },

  async count() {
    const result = await query('SELECT COUNT(*) as count FROM hypotheses');
    return parseInt(result.rows[0].count, 10);
  },
};

// ============================================================================
// FRIDAY DASHBOARDS
// ============================================================================

export const fridayDashboardsRepo = {
  async insert(data) {
    const result = await query(
      `INSERT INTO friday_dashboards (date, responses) VALUES ($1, $2::jsonb) RETURNING *`,
      [data.date, JSON.stringify(data.responses || {})]
    );
    return result.rows[0];
  },

  async listAll() {
    const result = await query('SELECT * FROM friday_dashboards ORDER BY date DESC');
    return result.rows;
  },
};

// ============================================================================
// OBSERVATORY OBSERVATIONS
// ============================================================================

export const observatoryRepo = {
  async insert(data) {
    const result = await query(
      `INSERT INTO observatory_observations (org_id_hash, size_bucket, industry, metrics, operational)
       VALUES ($1, $2, $3, $4::jsonb, $5::jsonb) RETURNING *`,
      [data.org_id_hash, data.size_bucket, data.industry || 'technology',
       JSON.stringify(data.metrics || {}), JSON.stringify(data.operational || {})]
    );
    return result.rows[0];
  },

  async listAll() {
    const result = await query('SELECT * FROM observatory_observations ORDER BY contributed_at DESC');
    return result.rows;
  },

  async count() {
    const result = await query('SELECT COUNT(*) as count FROM observatory_observations');
    return parseInt(result.rows[0].count, 10);
  },
};

// ============================================================================
// PARTNER PROMISES (CPR)
// ============================================================================

export const partnerPromisesRepo = {
  async upsert(data) {
    const result = await query(
      `INSERT INTO partner_promises (org_id, promised_outcome, target_reduction, baseline, start_date, days_to_prove)
       VALUES ($1, $2, $3, $4::jsonb, $5, $6)
       ON CONFLICT (org_id) DO UPDATE SET
         promised_outcome = EXCLUDED.promised_outcome,
         target_reduction = EXCLUDED.target_reduction,
         baseline = EXCLUDED.baseline,
         start_date = EXCLUDED.start_date,
         days_to_prove = EXCLUDED.days_to_prove
       RETURNING *`,
      [data.org_id, data.promised_outcome || '15% cycle time reduction',
       data.target_reduction || 15, JSON.stringify(data.baseline || {}),
       data.start_date || new Date().toISOString(), data.days_to_prove || 90]
    );
    return result.rows[0];
  },

  async getByOrgId(orgId) {
    const result = await query('SELECT * FROM partner_promises WHERE org_id = $1', [orgId]);
    return result.rows[0] || null;
  },

  async listAll() {
    const result = await query('SELECT * FROM partner_promises ORDER BY created_at DESC');
    return result.rows;
  },
};

// ============================================================================
// MIGRATION HELPER: JSONL to PostgreSQL
// ============================================================================

export async function migrateJsonlRecords(tableName, records, mapper) {
  if (!records || records.length === 0) return 0;
  let count = 0;
  for (const record of records) {
    try {
      const mapped = mapper(record);
      // Use INSERT ... ON CONFLICT DO NOTHING for idempotency
      const columns = Object.keys(mapped).join(', ');
      const placeholders = Object.keys(mapped).map((_, i) => `$${i + 1}`).join(', ');
      const values = Object.values(mapped);
      await query(
        `INSERT INTO ${tableName} (${columns}) VALUES (${placeholders}) ON CONFLICT DO NOTHING`,
        values
      );
      count++;
    } catch (err) {
      console.warn(`[repository] migration skip for ${tableName}:`, err.message);
    }
  }
  return count;
}

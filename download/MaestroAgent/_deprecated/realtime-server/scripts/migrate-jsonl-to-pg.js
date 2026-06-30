// scripts/migrate-jsonl-to-pg.js — One-time migration from JSONL to PostgreSQL.
//
// Usage:
//   DATABASE_URL=postgresql://localhost/maestro node scripts/migrate-jsonl-to-pg.js
//
// Reads all JSONL files and inserts records into PostgreSQL tables.
// Idempotent: uses ON CONFLICT DO NOTHING so re-running is safe.

import { promises as fs } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { query, closePool } from '../src/db.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

async function readJsonl(filename) {
  try {
    const data = await fs.readFile(filename, 'utf8');
    return data.split('\n').filter(Boolean).map(line => JSON.parse(line));
  } catch (err) {
    if (err.code === 'ENOENT') return [];
    throw err;
  }
}

async function migrate() {
  console.log('[migrate-jsonl] Starting JSONL to PostgreSQL migration...\n');

  // 1. Learning Objects
  const learningObjects = await readJsonl(path.join(__dirname, '..', 'learning-objects.jsonl'));
  console.log(`[migrate-jsonl] learning-objects.jsonl: ${learningObjects.length} records`);
  for (const obj of learningObjects) {
    try {
      await query(
        `INSERT INTO learning_objects (id, run_id, org_id, goal, goal_class, team_template, specialists,
          interrupts, predicted_confidence, outcome, outcome_notes, lessons, workflow_score_delta,
          deliverable_count, duration_ms, scope, scope_key, scope_level, created_at)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19)
         ON CONFLICT DO NOTHING`,
        [obj.id, obj.runId, obj.org_id || '00000000-0000-0000-0000-000000000000',
         obj.goal, obj.goalCategory || 'General Task', obj.teamTemplate || [],
         JSON.stringify(obj.specialists || []), JSON.stringify(obj.interrupts || []),
         obj.predictedConfidence || null, obj.outcome || 'pending',
         obj.outcomeNotes || '', obj.lessons || '', obj.workflowScoreDelta || 0,
         obj.deliverableCount || 0, obj.durationMs || 0,
         JSON.stringify(obj.scope || {}), obj.scopeKey || 'global',
         obj.scopeLevel || 'global', obj.createdAt || new Date().toISOString()]
      );
    } catch (err) { console.warn(`  skip: ${err.message}`); }
  }

  // 2. Execution Patterns
  const patterns = await readJsonl(path.join(__dirname, '..', 'execution-patterns.jsonl'));
  console.log(`[migrate-jsonl] execution-patterns.jsonl: ${patterns.length} records`);
  for (const obj of patterns) {
    try {
      await query(
        `INSERT INTO execution_patterns (id, org_id, goal_class, goal_class_keywords, scope_key, scope_level,
          scope, winning_workflow, observed_failures, successful_corrections, confidence_calibration,
          acceptance_rate, project_count, source_run_ids, is_promoted, version, last_updated, created_at)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
         ON CONFLICT (goal_class, scope_key) DO NOTHING`,
        [obj.id, obj.org_id || null, obj.goalClass, obj.goalClassKeywords || [],
         obj.scopeKey, obj.scopeLevel || 'global', JSON.stringify(obj.scope || {}),
         JSON.stringify(obj.winningWorkflow || []), JSON.stringify(obj.observedFailures || []),
         JSON.stringify(obj.successfulCorrections || []), JSON.stringify(obj.confidenceCalibration || {}),
         obj.acceptanceRate, obj.projectCount || 0, obj.sourceRunIds || [],
         obj.isPromoted || false, obj.version || 0, obj.lastUpdated || new Date().toISOString(),
         obj.createdAt || new Date().toISOString()]
      );
    } catch (err) { console.warn(`  skip: ${err.message}`); }
  }

  // 3. Operating Policies
  const policies = await readJsonl(path.join(__dirname, '..', 'operating-policies.jsonl'));
  console.log(`[migrate-jsonl] operating-policies.jsonl: ${policies.length} records`);
  for (const obj of policies) {
    try {
      await query(
        `INSERT INTO operating_policies (id, org_id, rule, scope_key, scope_level, scope, category,
          enforcement, evidence_required, reviewer, approval_required, block_execution,
          exception_allowed, violation_action, promoted_from, reinforcement_count,
          violation_count, status, created_at, last_reinforced)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20)
         ON CONFLICT DO NOTHING`,
        [obj.id, obj.org_id || null, obj.rule, obj.scopeKey, obj.scopeLevel,
         JSON.stringify(obj.scope || {}), obj.category || 'custom',
         obj.enforcement || 'recommended', obj.evidenceRequired || null,
         obj.reviewer || null, obj.approvalRequired || false, obj.blockExecution || false,
         obj.exceptionAllowed !== false, obj.violationAction || 'warn',
         obj.promotedFrom || null, obj.reinforcementCount || 0,
         obj.violationCount || 0, obj.status || 'active',
         obj.createdAt || new Date().toISOString(), obj.lastReinforced || new Date().toISOString()]
      );
    } catch (err) { console.warn(`  skip: ${err.message}`); }
  }

  // 4. Execution Receipts
  const receipts = await readJsonl(path.join(__dirname, '..', 'execution-receipts.jsonl'));
  console.log(`[migrate-jsonl] execution-receipts.jsonl: ${receipts.length} records`);
  for (const obj of receipts) {
    try {
      await query(
        `INSERT INTO execution_receipts (id, run_id, org_id, goal, goal_class, scope, plan,
          policies_applied, patterns_used, evidence, approvals, exceptions, confidence,
          outcome, execution, lessons, receipt_hash, created_at)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
         ON CONFLICT DO NOTHING`,
        [obj.receiptId || obj.id, obj.runId, obj.org_id || '00000000-0000-0000-0000-000000000000',
         obj.goal, obj.goalClass, JSON.stringify(obj.scope || {}),
         JSON.stringify(obj.plan || {}), JSON.stringify(obj.policiesApplied || []),
         JSON.stringify(obj.patternsUsed || []), JSON.stringify(obj.evidence || []),
         JSON.stringify(obj.approvals || []), JSON.stringify(obj.exceptions || []),
         JSON.stringify(obj.confidence || {}), JSON.stringify(obj.outcome || {}),
         JSON.stringify(obj.execution || {}), obj.lessons || '', obj.receiptHash,
         obj.createdAt || new Date().toISOString()]
      );
    } catch (err) { console.warn(`  skip: ${err.message}`); }
  }

  // 5. Integrations
  const integrations = await readJsonl(path.join(__dirname, '..', 'integrations.jsonl'));
  console.log(`[migrate-jsonl] integrations.jsonl: ${integrations.length} records`);
  for (const obj of integrations) {
    try {
      await query(
        `INSERT INTO integrations (id, org_id, provider_id, provider_name, capabilities, config, credentials, status, connected_at, last_sync_at, events_received, events_sent)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
         ON CONFLICT DO NOTHING`,
        [obj.id, obj.orgId || 'default', obj.providerId, obj.providerName,
         obj.capabilities || [], JSON.stringify(obj.config || {}),
         obj.credentials ? JSON.stringify(obj.credentials) : null,
         obj.status || 'connected', obj.connectedAt || new Date().toISOString(),
         obj.lastSyncAt || null, obj.eventsReceived || 0, obj.eventsSent || 0]
      );
    } catch (err) { console.warn(`  skip: ${err.message}`); }
  }

  // 6. Evidence Ledger
  const hypotheses = await readJsonl(path.join(__dirname, '..', 'evidence-ledger.jsonl'));
  console.log(`[migrate-jsonl] evidence-ledger.jsonl: ${hypotheses.length} records`);
  for (const obj of hypotheses) {
    try {
      await query(
        `INSERT INTO hypotheses (id, hypothesis, category, confidence, evidence_for, evidence_against, decision, next_experiment, status, created_at, last_updated)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
         ON CONFLICT (id) DO NOTHING`,
        [obj.id, obj.hypothesis, obj.category || 'general', obj.confidence || 'low',
         JSON.stringify(obj.evidenceFor || []), JSON.stringify(obj.evidenceAgainst || []),
         obj.decision || 'continue', obj.nextExperiment || '', obj.status || 'testing',
         obj.createdAt || new Date().toISOString(), obj.lastUpdated || new Date().toISOString()]
      );
    } catch (err) { console.warn(`  skip: ${err.message}`); }
  }

  // 7. Operating Models
  const models = await readJsonl(path.join(__dirname, '..', 'operating-models.jsonl'));
  console.log(`[migrate-jsonl] operating-models.jsonl: ${models.length} records`);
  for (const obj of models) {
    try {
      await query(
        `INSERT INTO operating_models (org_id, name, industry, hierarchy, approval_chains, policies, workflow_templates, compliance_mappings, integration_bindings, status, version, registered_at)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
         ON CONFLICT (org_id) DO NOTHING`,
        [obj.orgId, obj.name, obj.industry || 'technology',
         JSON.stringify(obj.hierarchy || []), JSON.stringify(obj.approvalChains || []),
         JSON.stringify(obj.policies || []), JSON.stringify(obj.workflowTemplates || []),
         JSON.stringify(obj.complianceMappings || []),
         JSON.stringify(obj.integrationBindings || []),
         obj.status || 'active', obj.version || 1, obj.registeredAt || new Date().toISOString()]
      );
    } catch (err) { console.warn(`  skip: ${err.message}`); }
  }

  // 8. Design Partners
  const partners = await readJsonl(path.join(__dirname, '..', 'design-partners.jsonl'));
  console.log(`[migrate-jsonl] design-partners.jsonl: ${partners.length} records`);
  for (const obj of partners) {
    try {
      await query(
        `INSERT INTO design_partners (org_id, name, industry, contact_name, contact_email, stage, stages, operating_model, first_run_id, roi_report, onboarded_at, created_at)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
         ON CONFLICT (org_id) DO NOTHING`,
        [obj.orgId, obj.name, obj.industry || 'technology', obj.contactName, obj.contactEmail,
         obj.stage, JSON.stringify(obj.stages || {}),
         obj.operatingModel ? JSON.stringify(obj.operatingModel) : null,
         obj.firstRunId || null, obj.roiReport ? JSON.stringify(obj.roiReport) : null,
         obj.onboardedAt || null, obj.createdAt || new Date().toISOString()]
      );
    } catch (err) { console.warn(`  skip: ${err.message}`); }
  }

  // 9. Observatory
  const observations = await readJsonl(path.join(__dirname, '..', 'execution-observatory.jsonl'));
  console.log(`[migrate-jsonl] execution-observatory.jsonl: ${observations.length} records`);
  for (const obj of observations) {
    try {
      await query(
        `INSERT INTO observatory_observations (org_id_hash, size_bucket, industry, metrics, operational, contributed_at)
         VALUES ($1, $2, $3, $4, $5, $6)
         ON CONFLICT DO NOTHING`,
        [obj.orgIdHash, obj.sizeBucket, obj.industry || 'technology',
         JSON.stringify(obj.metrics || {}), JSON.stringify(obj.operational || {}),
         obj.contributedAt || new Date().toISOString()]
      );
    } catch (err) { console.warn(`  skip: ${err.message}`); }
  }

  // 10. Friday Dashboards
  const dashboards = await readJsonl(path.join(__dirname, '..', 'friday-dashboards.jsonl'));
  console.log(`[migrate-jsonl] friday-dashboards.jsonl: ${dashboards.length} records`);
  for (const obj of dashboards) {
    try {
      await query(
        `INSERT INTO friday_dashboards (date, responses, saved_at)
         VALUES ($1, $2, $3)
         ON CONFLICT DO NOTHING`,
        [obj.date, JSON.stringify(obj.responses || {}), obj.savedAt || new Date().toISOString()]
      );
    } catch (err) { console.warn(`  skip: ${err.message}`); }
  }

  console.log('\n[migrate-jsonl] Migration complete.');
  console.log('[migrate-jsonl] You can now safely delete the .jsonl files.');
}

migrate().catch(err => {
  console.error('[migrate-jsonl] Error:', err);
  process.exit(1);
}).finally(async () => {
  await closePool();
});

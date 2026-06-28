// server.js — MaestroAgent realtime backend (Phase 4).
//
// Provides:
//   POST /api/runs              { goal } -> { run_id, status }
//   GET  /api/runs              -> [{ id, goal, status, ... }]
//   GET  /api/runs/:id          -> { id, goal, status, artifacts, ... }
//   GET  /api/runs/:id/events   -> [event, event, ...]   (replay)
//   POST /api/runs/:id/interrupt { message } -> { ok }   (Phase 4)
//   GET  /api/runs/:id/artifacts/:filename -> file download
//   GET  /api/health            -> { ok, providers }
//   WS   /ws/:run_id            -> live event stream
//
// Serves app.html (and assets) from ../  as the default UI.
//
// Port defaults to 8765 — the same port the mock app used, so existing
// bookmarks keep working.

import express from 'express';
import cors from 'cors';
import { WebSocketServer } from 'ws';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { promises as fs } from 'node:fs';

import {
  createRun,
  runGoal,
  getRun,
  listRuns,
  subscribe,
  interruptRun,
} from './src/engine.js';
import { recordOutcome, getStats as getLearningStats } from './src/learning.js';
import { getPatternStats } from './src/patterns.js';
import { getCurrentScope, setCurrentScope, getScopeHierarchy, formatScopeContext } from './src/scope.js';
import { getPolicyStats, listPolicies } from './src/policies.js';
import { getGovernanceStats, listControls, createControlForPolicy } from './src/governance.js';
import { getReceiptByRunId, getReceipt, listReceipts, getReceiptStats, verifyReceipt } from './src/receipts.js';
import { getEvidenceStats, listEvidence, listCases, listPrecedents } from './src/evidence.js';
import { computeMetrics, computeROIReport } from './src/metrics.js';
import { registerOperatingModel, getOperatingModel, listOperatingModels, validateOperatingModel, findWorkflowTemplate, getApprovalChain } from './src/sdk.js';
import { startOnboarding, advanceStage, getOnboardingStatus, getOnboardingGuide, listDesignPartners } from './src/design-partner.js';
import { connectIntegration, listIntegrations, disconnectIntegration, handleWebhookEvent, getIntegrationStats, listProviders, PROVIDERS } from './src/integrations.js';
import { runSimulation, listSimulationTypes } from './src/simulation.js';
import { computeBenchmarks, getBenchmarkStats } from './src/benchmarks.js';
import { getProductDeliveryTemplate, getTemplateSummary } from './src/product-delivery-template.js';
import { explainRecommendation, computeEII } from './src/explanation.js';
import { contributeObservation, getObservatoryStats, compare_toPeers, computeOED, initObservatoryStore } from './src/observatory.js';
import { computeTTV, computeCOI, computeCustomerHealth } from './src/customer-metrics.js';
import { initEvidenceLedger, getLedger, getHypothesis, addHypothesis, updateHypothesis, getLedgerStats, getFridayDashboard, saveFridayDashboard, listFridayDashboards } from './src/evidence-ledger.js';
import { setPartnerPromise, computeCPR, getPartnerProof, listPartnerPromises } from './src/cpr.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const PROJECT_ROOT = path.resolve(__dirname, '..'); // /home/z/my-project/download/MaestroAgent

const PORT = parseInt(process.env.PORT || '8765', 10);
// Initialize observatory + evidence ledger on startup.
initObservatoryStore().catch(err => console.warn('[server] observatory init failed:', err.message));
initEvidenceLedger().catch(err => console.warn('[server] evidence ledger init failed:', err.message));

const app = express();
app.use(cors({ origin: true, credentials: true }));
app.use(express.json({ limit: '1mb' }));

// --- Auth Routes ---
import authRouter from './src/routes/auth.js';
app.use('/api/auth', authRouter);

// --- Static UI ---
// Serve the new app.html at /, and the mock backup at /mock.
app.get('/', async (req, res) => {
  res.sendFile(path.join(PROJECT_ROOT, 'app.html'));
});
app.get('/app.html', async (req, res) => {
  res.sendFile(path.join(PROJECT_ROOT, 'app.html'));
});
app.get('/mock', async (req, res) => {
  res.sendFile(path.join(PROJECT_ROOT, 'app-mock.html'));
});

// --- API ---
app.get('/api/health', (req, res) => {
  res.json({
    ok: true,
    version: '1.0.0-realtime',
    providers: ['zai'],
    uptime: process.uptime(),
    runs: listRuns().length,
  });
});

app.post('/api/runs', async (req, res) => {
  const goal = (req.body?.goal || '').trim();
  if (!goal) return res.status(400).json({ error: 'goal is required' });
  if (goal.length > 4000) return res.status(400).json({ error: 'goal too long (max 4000 chars)' });

  const run = createRun(goal);
  // Fire and forget — the run streams events to subscribers.
  runGoal(run.id, goal).catch(err => console.error(`[run ${run.id}] failed:`, err));

  res.json({
    run_id: run.id,
    status: run.status,
    goal: run.goal,
    startedAt: run.startedAt,
  });
});

app.get('/api/runs', (req, res) => {
  res.json(listRuns());
});

app.get('/api/runs/:id', (req, res) => {
  const run = getRun(req.params.id);
  if (!run) return res.status(404).json({ error: 'run not found' });
  res.json({
    id: run.id,
    goal: run.goal,
    status: run.status,
    startedAt: run.startedAt,
    endedAt: run.endedAt,
    durationMs: run.durationMs,
    team: run.team,
    avgConfidence: run.avgConfidence,
    artifacts: run.artifacts.map(a => ({
      agent_id: a.agent_id,
      agent_name: a.agent_name,
      filename: a.filename,
      bytes: a.bytes,
      isFinal: !!a.isFinal,
      isDebateResolution: !!a.isDebateResolution,
      preview: a.preview,
      confidence: a.confidence ?? null,
    })),
    error: run.error,
  });
});

app.get('/api/runs/:id/events', (req, res) => {
  const run = getRun(req.params.id);
  if (!run) return res.status(404).json({ error: 'run not found' });
  res.json(run.events);
});

// Phase 4: Interrupt a running run with a user message.
// The message is queued and injected before the NEXT specialist runs.
// The currently-running specialist is not cancelled — its work is preserved.
app.post('/api/runs/:id/interrupt', (req, res) => {
  const run = getRun(req.params.id);
  if (!run) return res.status(404).json({ error: 'run not found' });
  const message = (req.body?.message || '').trim();
  if (!message) return res.status(400).json({ error: 'message is required' });
  if (message.length > 2000) return res.status(400).json({ error: 'message too long (max 2000 chars)' });

  const ok = interruptRun(req.params.id, message);
  if (!ok) return res.status(500).json({ error: 'failed to queue interrupt' });

  res.json({
    ok: true,
    run_id: req.params.id,
    queued: message,
    note: 'Message will be incorporated before the next specialist runs.',
  });
});

// Phase 4 + Learning: Record user outcome feedback for a completed run.
// This closes the learning loop. Without outcome measurement, there is no
// learning — only data. The user must accept, reject, or edit the deliverable.
// Outcome: 'accepted' | 'rejected' | 'edited'
app.post('/api/runs/:id/feedback', async (req, res) => {
  const run = getRun(req.params.id);
  if (!run) return res.status(404).json({ error: 'run not found' });
  const outcome = (req.body?.outcome || '').trim();
  const notes = (req.body?.notes || '').trim();
  if (!['accepted', 'rejected', 'edited'].includes(outcome)) {
    return res.status(400).json({ error: 'outcome must be accepted | rejected | edited' });
  }
  try {
    const obj = await recordOutcome(req.params.id, outcome, notes);
    if (!obj) return res.status(404).json({ error: 'learning object not found for this run' });
    res.json({
      ok: true,
      run_id: req.params.id,
      outcome: obj.outcome,
      workflow_score_delta: obj.workflowScoreDelta,
      message: outcome === 'accepted'
        ? 'Recorded as accepted. This workflow will be preferred for similar future goals.'
        : outcome === 'rejected'
        ? 'Recorded as rejected. This workflow will be deprioritized for similar future goals.'
        : 'Recorded as edited. Maestro will incorporate your corrections for similar future goals.',
    });
  } catch (err) {
    res.status(500).json({ error: 'failed to record feedback', detail: err.message });
  }
});

// Learning stats — shows the flywheel state.
app.get('/api/learning/stats', (req, res) => {
  res.json(getLearningStats());
});

// Execution Pattern stats — shows the pattern registry.
app.get('/api/patterns/stats', (req, res) => {
  res.json(getPatternStats());
});

// === OPERATING POLICIES API (the governance layer) ===
app.get('/api/policies/stats', (req, res) => {
  res.json(getPolicyStats());
});

app.get('/api/policies', (req, res) => {
  res.json(listPolicies());
});

// === GOVERNANCE CONTROLS API ===
app.get('/api/governance/stats', (req, res) => {
  res.json(getGovernanceStats());
});

app.get('/api/governance/controls', (req, res) => {
  res.json(listControls());
});

// Create governance controls for all mandatory/constitutional policies
// that don't have one yet. This is the "make policies executable" endpoint.
app.post('/api/governance/seed', async (req, res) => {
  const policies = listPolicies();
  const created = [];
  for (const p of policies) {
    if (p.enforcement === 'mandatory' || p.enforcement === 'constitutional') {
      try {
        const control = await createControlForPolicy(p);
        created.push({ policyRule: p.rule, enforcement: p.enforcement, controlId: control.id });
      } catch (err) {
        // Control may already exist — that's fine.
      }
    }
  }
  res.json({ ok: true, created: created.length, controls: created });
});

// === EXECUTION RECEIPTS API (the audit trail) ===
app.get('/api/receipts', (req, res) => {
  const limit = parseInt(req.query.limit) || 50;
  res.json(listReceipts(limit));
});

app.get('/api/receipts/stats', (req, res) => {
  res.json(getReceiptStats());
});

app.get('/api/runs/:id/receipt', (req, res) => {
  const receipt = getReceiptByRunId(req.params.id);
  if (!receipt) return res.status(404).json({ error: 'receipt not found for this run' });
  res.json(receipt);
});

app.get('/api/receipts/:receiptId', (req, res) => {
  const receipt = getReceipt(req.params.receiptId);
  if (!receipt) return res.status(404).json({ error: 'receipt not found' });
  res.json(receipt);
});

app.get('/api/receipts/:receiptId/verify', (req, res) => {
  const result = verifyReceipt(req.params.receiptId);
  res.json(result);
});

// === EVIDENCE, CASES & PRECEDENTS API (active governance) ===
app.get('/api/evidence/stats', (req, res) => {
  res.json(getEvidenceStats());
});

app.get('/api/evidence', (req, res) => {
  const limit = parseInt(req.query.limit) || 50;
  res.json(listEvidence(limit));
});

app.get('/api/cases', (req, res) => {
  const limit = parseInt(req.query.limit) || 50;
  res.json(listCases(limit));
});

app.get('/api/precedents', (req, res) => {
  res.json(listPrecedents());
});

// === EXECUTION METRICS API (the dashboard a CIO buys) ===
// This is NOT a cognitive layer. This is the COMMERCIAL layer.
// Turns receipts into the metrics executives buy: cycle time, rework %,
// knowledge reuse, compliance score, hours saved, violations prevented.
app.get('/api/metrics', (req, res) => {
  const scope = getCurrentScope();
  res.json(computeMetrics(scope));
});

// Before/After ROI report — the pitch deck slide.
app.get('/api/roi-report', (req, res) => {
  const scope = getCurrentScope();
  res.json(computeROIReport(scope));
});

// === ENTERPRISE OPERATING MODEL SDK ===
// POST /api/sdk/operating-model — register an enterprise's operating model
// GET /api/sdk/operating-models — list all registered models
// GET /api/sdk/operating-model/:orgId — get a specific model
// POST /api/sdk/validate — validate an operating model before registering
app.post('/api/sdk/operating-model', async (req, res) => {
  try {
    const result = await registerOperatingModel(req.body);
    res.json(result);
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

app.get('/api/sdk/operating-models', (req, res) => {
  res.json(listOperatingModels());
});

app.get('/api/sdk/operating-model/:orgId', (req, res) => {
  const model = getOperatingModel(req.params.orgId);
  if (!model) return res.status(404).json({ error: 'operating model not found' });
  res.json(model);
});

app.post('/api/sdk/validate', (req, res) => {
  res.json(validateOperatingModel(req.body));
});

// === DESIGN PARTNER MODE (enterprise onboarding framework) ===
// POST /api/design-partner/start — start onboarding a new design partner
// GET /api/design-partner/:orgId/status — get onboarding status
// GET /api/design-partner/:orgId/guide — get the current stage guide
// POST /api/design-partner/:orgId/advance — advance to the next stage
// GET /api/design-partners — list all design partners
app.post('/api/design-partner/start', async (req, res) => {
  try {
    const partner = await startOnboarding(req.body);
    res.json(partner);
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

app.get('/api/design-partner/:orgId/status', (req, res) => {
  const status = getOnboardingStatus(req.params.orgId);
  if (!status) return res.status(404).json({ error: 'design partner not found' });
  res.json(status);
});

app.get('/api/design-partner/:orgId/guide', (req, res) => {
  const guide = getOnboardingGuide(req.params.orgId);
  if (!guide) return res.status(404).json({ error: 'design partner not found' });
  res.json(guide);
});

app.post('/api/design-partner/:orgId/advance', async (req, res) => {
  try {
    const partner = await advanceStage(req.params.orgId, req.body);
    res.json(partner);
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

app.get('/api/design-partners', (req, res) => {
  res.json(listDesignPartners());
});

// === INTEGRATIONS API ===
// GET /api/integrations/providers — list available integration providers
// GET /api/integrations — list connected integrations for current org
// POST /api/integrations/:provider/connect — connect a provider
// DELETE /api/integrations/:id — disconnect an integration
// POST /api/integrations/:provider/webhook — receive a webhook from an external tool
// GET /api/integrations/stats — integration stats for current org
app.get('/api/integrations/providers', (req, res) => {
  res.json(listProviders());
});

app.get('/api/integrations', (req, res) => {
  const scope = getCurrentScope();
  const orgId = scope.organization || 'default';
  res.json(listIntegrations(orgId));
});

app.post('/api/integrations/:provider/connect', async (req, res) => {
  try {
    const scope = getCurrentScope();
    const orgId = scope.organization || req.body.orgId || 'default';
    const integration = await connectIntegration(orgId, req.params.provider, req.body.config || {});
    res.json(integration);
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

app.delete('/api/integrations/:id', async (req, res) => {
  const ok = await disconnectIntegration(req.params.id);
  if (!ok) return res.status(404).json({ error: 'integration not found' });
  res.json({ ok: true, disconnected: req.params.id });
});

app.post('/api/integrations/:provider/webhook', async (req, res) => {
  try {
    const scope = getCurrentScope();
    const orgId = scope.organization || req.body.orgId || 'default';
    const result = await handleWebhookEvent(req.params.provider, req.body, orgId);
    res.json(result);
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

app.get('/api/integrations/stats', (req, res) => {
  const scope = getCurrentScope();
  const orgId = scope.organization || 'default';
  res.json(getIntegrationStats(orgId));
});

// === PRODUCT DELIVERY TEMPLATE (the wedge) ===
// The pre-configured operating model for software product teams.
// "Reduce software delivery cycle time while maintaining governance."
app.get('/api/templates/product-delivery', (req, res) => {
  res.json(getProductDeliveryTemplate());
});

app.get('/api/templates/product-delivery/summary', (req, res) => {
  res.json(getTemplateSummary());
});

// Adopt the Product Delivery template for an organization.
// This is the one-call onboarding for software teams.
app.post('/api/templates/product-delivery/adopt', async (req, res) => {
  try {
    const { orgId, name, industry } = req.body;
    if (!orgId) return res.status(400).json({ error: 'orgId is required' });

    const template = getProductDeliveryTemplate();
    const model = {
      ...template,
      orgId,
      name: name || `${orgId} (Product Delivery)`,
      industry: industry || 'technology',
    };

    const result = await registerOperatingModel(model);
    res.json({
      ...result,
      template: 'product-delivery',
      message: `Product Delivery Operating Model adopted. ${result.registeredPolicies} governance controls are now executable. Your team can start executing immediately.`,
    });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

// === SIMULATION ENGINE ===
// "What if we remove security review?"
// POST /api/simulate — run a simulation
// GET /api/simulate/types — list available simulation types
app.get('/api/simulate/types', (req, res) => {
  res.json(listSimulationTypes());
});

app.post('/api/simulate', (req, res) => {
  const scope = getCurrentScope();
  const result = runSimulation(req.body, scope);
  res.json(result);
});

// === BENCHMARK NETWORK ===
// Anonymous cross-company intelligence.
// "Top 10% of organizations complete executions in X hours."
app.get('/api/benchmarks', (req, res) => {
  const scope = getCurrentScope();
  res.json(computeBenchmarks(scope));
});

app.get('/api/benchmarks/stats', (req, res) => {
  res.json(getBenchmarkStats());
});

// === EXPLANATION ENGINE (the trust layer) ===
// Every recommendation answers "Why?"
// POST /api/explain — explain a recommendation with evidence + confidence
// GET /api/eii — Execution Improvement Index (the one metric to obsess over)
// GET /api/eii/:orgId — EII for a specific org
app.post('/api/explain', (req, res) => {
  const scope = getCurrentScope();
  const result = explainRecommendation(req.body, scope);
  res.json(result);
});

app.get('/api/eii', (req, res) => {
  const scope = getCurrentScope();
  const orgId = scope.organization || null;
  res.json(computeEII(orgId));
});

app.get('/api/eii/:orgId', (req, res) => {
  res.json(computeEII(req.params.orgId));
});

// === EXECUTION OBSERVATORY (anonymous cross-company intelligence) ===
// POST /api/observatory/contribute — contribute anonymous metrics
// GET /api/observatory — get aggregate stats
// GET /api/observatory/compare — compare your org against peers
// GET /api/oed/:orgId — Organizational Execution Delta (North Star)
app.post('/api/observatory/contribute', async (req, res) => {
  try {
    const scope = getCurrentScope();
    const orgId = scope.organization || req.body.orgId;
    if (!orgId) return res.status(400).json({ error: 'orgId required (set scope or pass in body)' });
    const result = await contributeObservation(orgId, req.body);
    res.json(result);
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

app.get('/api/observatory', (req, res) => {
  res.json(getObservatoryStats());
});

app.get('/api/observatory/compare', (req, res) => {
  const scope = getCurrentScope();
  const orgId = scope.organization;
  if (!orgId) return res.status(400).json({ error: 'set scope first (POST /api/scope)' });
  const result = compare_toPeers(orgId, { engineerCount: parseInt(req.query.engineers) || 50 });
  res.json(result);
});

// Organizational Execution Delta — the North Star Metric
app.get('/api/oed/:orgId', (req, res) => {
  // Baseline metrics can be passed as query params or body.
  const baseline = req.query.baseline ? JSON.parse(req.query.baseline) : null;
  res.json(computeOED(req.params.orgId, baseline));
});

app.post('/api/oed/:orgId', (req, res) => {
  res.json(computeOED(req.params.orgId, req.body.baseline));
});

// === CUSTOMER METRICS (TTV + COI + Health) ===
// Time-to-Value: days until first measurable improvement
// Cognitive Overhead Index: the anti-metric (lower is better)
// Customer Health: combined TTV + COI + OED score
app.get('/api/ttv', (req, res) => {
  const scope = getCurrentScope();
  res.json(computeTTV(scope.organization));
});

app.get('/api/ttv/:orgId', (req, res) => {
  res.json(computeTTV(req.params.orgId));
});

app.get('/api/coi', (req, res) => {
  const scope = getCurrentScope();
  res.json(computeCOI(scope.organization));
});

app.get('/api/coi/:orgId', (req, res) => {
  res.json(computeCOI(req.params.orgId));
});

app.get('/api/customer-health', (req, res) => {
  const scope = getCurrentScope();
  res.json(computeCustomerHealth(scope.organization));
});

app.get('/api/customer-health/:orgId', (req, res) => {
  res.json(computeCustomerHealth(req.params.orgId));
});

// === EVIDENCE LEDGER (the company's learning system) ===
// Every hypothesis gets a page. Evidence for/against. Confidence. Decision.
// The company learns the same way the product learns.
app.get('/api/evidence-ledger', (req, res) => {
  res.json(getLedger());
});

app.get('/api/evidence-ledger/stats', (req, res) => {
  res.json(getLedgerStats());
});

app.get('/api/evidence-ledger/:id', (req, res) => {
  const h = getHypothesis(req.params.id);
  if (!h) return res.status(404).json({ error: 'hypothesis not found' });
  res.json(h);
});

app.post('/api/evidence-ledger', async (req, res) => {
  try {
    const h = await addHypothesis(req.body);
    res.json(h);
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

app.post('/api/evidence-ledger/:id/update', async (req, res) => {
  try {
    const h = await updateHypothesis(req.params.id, req.body);
    if (!h) return res.status(404).json({ error: 'hypothesis not found' });
    res.json(h);
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

// === CEO FRIDAY DASHBOARD ===
// Weekly self-assessment. Every Friday, the founder answers honestly.
app.get('/api/friday-dashboard', (req, res) => {
  res.json(getFridayDashboard());
});

app.post('/api/friday-dashboard', async (req, res) => {
  try {
    const dashboard = await saveFridayDashboard(req.body.responses || req.body);
    res.json(dashboard);
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

app.get('/api/friday-dashboard/history', (req, res) => {
  res.json(listFridayDashboards());
});

// === CUSTOMER PROOF RATE (CPR) — the one external metric ===
// Percentage of design partners that achieve their promised outcome within 90 days.
// This is the only metric that goes in the pitch deck, board update, and homepage.
app.get('/api/cpr', (req, res) => {
  res.json(computeCPR());
});

app.get('/api/cpr/:orgId', (req, res) => {
  res.json(getPartnerProof(req.params.orgId));
});

app.get('/api/cpr/partners/list', (req, res) => {
  res.json(listPartnerPromises());
});

app.post('/api/cpr/promise', (req, res) => {
  try {
    const { orgId, promisedOutcome, targetReduction, baseline, startDate, daysToProve } = req.body;
    if (!orgId) return res.status(400).json({ error: 'orgId is required' });
    const promise = setPartnerPromise(orgId, { promisedOutcome, targetReduction, baseline, startDate, daysToProve });
    res.json({ ok: true, ...promise });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

// === SCOPE API (hierarchical execution context) ===
// GET /api/scope — returns current scope + hierarchy
// POST /api/scope — set the current scope (organization, department, team, etc.)
app.get('/api/scope', (req, res) => {
  const scope = getCurrentScope();
  const hierarchy = getScopeHierarchy(scope);
  res.json({
    current: scope,
    hierarchy: hierarchy,
    formatted: formatScopeContext(scope),
  });
});

app.post('/api/scope', (req, res) => {
  const { organization, industry, department, team, userId } = req.body || {};
  const scope = setCurrentScope({ organization, industry, department, team, userId });
  res.json({
    ok: true,
    scope,
    hierarchy: getScopeHierarchy(scope),
    message: `Execution context set: ${formatScopeContext(scope) || 'global'}`,
  });
});

app.get('/api/runs/:id/artifacts/:filename', async (req, res) => {
  const run = getRun(req.params.id);
  if (!run) return res.status(404).json({ error: 'run not found' });
  const artifact = run.artifacts.find(a => a.filename === req.params.filename);
  if (!artifact) return res.status(404).json({ error: 'artifact not found' });

  try {
    const data = await fs.readFile(artifact.path);
    res.setHeader('Content-Type', 'text/markdown; charset=utf-8');
    res.setHeader('Content-Disposition', `attachment; filename="${artifact.filename}"`);
    res.send(data);
  } catch (err) {
    res.status(500).json({ error: 'failed to read artifact', detail: err.message });
  }
});

// --- HTTP + WS server on the same port ---
const server = http.createServer(app);
// Use noServer mode so we can match any /ws/* path (default `path`
// option only accepts an exact string match).
const wss = new WebSocketServer({ noServer: true });

server.on('upgrade', (req, socket, head) => {
  const match = req.url?.match(/^\/ws\/([^/?]+)/);
  if (!match) {
    socket.write('HTTP/1.1 400 Bad Request\r\n\r\n');
    socket.destroy();
    return;
  }
  wss.handleUpgrade(req, socket, head, (ws) => {
    wss.emit('connection', ws, req);
  });
});

wss.on('connection', async (ws, req) => {
  // Extract run_id from /ws/:run_id
  const match = req.url?.match(/^\/ws\/([^/?]+)/);
  const runId = match?.[1];
  if (!runId) {
    ws.close(4400, 'missing run_id');
    return;
  }
  const run = getRun(runId);
  if (!run) {
    ws.close(4404, 'run not found');
    return;
  }

  // Ack — also tell client how many events we already have (for replay).
  ws.send(JSON.stringify({
    type: 'connected',
    run_id: runId,
    status: run.status,
    event_count: run.events.length,
  }));

  // Replay past events (in case the client connects late).
  for (const ev of run.events) {
    ws.send(JSON.stringify(ev));
  }

  // Subscribe to future events.
  const unsub = subscribe(runId, (event) => {
    if (ws.readyState === ws.OPEN) {
      ws.send(JSON.stringify(event));
    }
  });

  ws.on('close', () => unsub());
  ws.on('error', () => unsub());
});

server.listen(PORT, () => {
  console.log(`\n  MaestroAgent realtime server`);
  console.log(`  ============================`);
  console.log(`  UI:        http://localhost:${PORT}/`);
  console.log(`  Mock UI:   http://localhost:${PORT}/mock`);
  console.log(`  Health:    http://localhost:${PORT}/api/health`);
  console.log(`  WebSocket: ws://localhost:${PORT}/ws/{run_id}`);
  console.log(`  Deliverables: ${path.resolve(__dirname, 'deliverables')}/`);
  console.log();
});

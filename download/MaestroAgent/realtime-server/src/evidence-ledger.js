// evidence-ledger.js — The Evidence Ledger.
//
// The company itself learns the same way the product learns.
//
// Every assumption the company makes gets one page:
//   - Hypothesis
//   - Confidence (low/medium/high)
//   - Evidence For
//   - Evidence Against
//   - Decision (continue/pivot/stop)
//   - Next Experiment
//   - Last Updated
//
// This is NOT a product feature. It's a company operating system.
// The Evidence Ledger is reviewed weekly. Hypotheses are updated based
// on customer conversations, not internal opinions.
//
// "One customer conversation should outweigh ten internal ideas."

import { promises as fs } from 'node:fs';
import path from 'node:path';

const LEDGER_PATH = path.resolve('./evidence-ledger.jsonl');
const hypotheses = new Map(); // id -> Hypothesis

export async function initEvidenceLedger() {
  try {
    const data = await fs.readFile(LEDGER_PATH, 'utf8');
    for (const line of data.split('\n').filter(Boolean)) {
      try {
        const obj = JSON.parse(line);
        hypotheses.set(obj.id, obj);
      } catch {}
    }
    console.log(`[evidence-ledger] loaded ${hypotheses.size} hypotheses from disk`);

    // Seed default hypotheses if empty.
    if (hypotheses.size === 0) {
      await seedDefaultHypotheses();
    }
  } catch (err) {
    if (err.code === 'ENOENT') {
      await seedDefaultHypotheses();
    } else {
      console.warn('[evidence-ledger] failed to load:', err.message);
    }
  }
}

async function persist(hypothesis) {
  try { await fs.appendFile(LEDGER_PATH, JSON.stringify(hypothesis) + '\n', 'utf8'); }
  catch (err) { console.warn('[evidence-ledger] persist failed:', err.message); }
}

// Seed the default hypotheses that the company starts with.
// These are the core assumptions from "Reasons We Might Be Wrong."
async function seedDefaultHypotheses() {
  const defaults = [
    {
      id: 'H001',
      hypothesis: 'Organizations using Maestro reduce product delivery cycle time by at least 15% within 90 days.',
      category: 'value',
      confidence: 'low',
      evidenceFor: [],
      evidenceAgainst: [],
      decision: 'continue',
      nextExperiment: 'Onboard 3 design partners and measure cycle time before/after at 90 days.',
      status: 'testing',
      createdAt: new Date().toISOString(),
      lastUpdated: new Date().toISOString(),
    },
    {
      id: 'H002',
      hypothesis: 'Customers will pay for governance controls (policies, evidence, receipts) — not just execution speed.',
      category: 'governance',
      confidence: 'low',
      evidenceFor: [],
      evidenceAgainst: [],
      decision: 'continue',
      nextExperiment: 'Ask each design partner: "Would you pay extra for governance features?" Track responses.',
      status: 'testing',
      createdAt: new Date().toISOString(),
      lastUpdated: new Date().toISOString(),
    },
    {
      id: 'H003',
      hypothesis: 'Product Delivery is the right wedge (vs. compliance, legal, sales engineering).',
      category: 'market',
      confidence: 'medium',
      evidenceFor: ['Product teams have repeated workflows with measurable cycle times'],
      evidenceAgainst: [],
      decision: 'continue',
      nextExperiment: 'Compare engagement metrics across 3 product teams vs. 1 compliance team.',
      status: 'testing',
      createdAt: new Date().toISOString(),
      lastUpdated: new Date().toISOString(),
    },
    {
      id: 'H004',
      hypothesis: 'OED (Organizational Execution Delta) correlates with customer-perceived business value.',
      category: 'metrics',
      confidence: 'low',
      evidenceFor: [],
      evidenceAgainst: [],
      decision: 'continue',
      nextExperiment: 'After 90 days, ask each partner: "Did Maestro improve your business?" Compare to OED score.',
      status: 'testing',
      createdAt: new Date().toISOString(),
      lastUpdated: new Date().toISOString(),
    },
    {
      id: 'H005',
      hypothesis: 'Cross-company benchmarks drive purchasing decisions.',
      category: 'benchmarks',
      confidence: 'low',
      evidenceFor: [],
      evidenceAgainst: [],
      decision: 'continue',
      nextExperiment: 'Show benchmark data in 3 sales conversations. Track if it advances the deal.',
      status: 'testing',
      createdAt: new Date().toISOString(),
      lastUpdated: new Date().toISOString(),
    },
    {
      id: 'H006',
      hypothesis: 'Integrations (Jira, GitHub, Slack) matter more to customers than cognitive depth.',
      category: 'product',
      confidence: 'low',
      evidenceFor: [],
      evidenceAgainst: [],
      decision: 'continue',
      nextExperiment: 'Ask each design partner: "What would make you stop using Maestro?" Track integration vs. intelligence answers.',
      status: 'testing',
      createdAt: new Date().toISOString(),
      lastUpdated: new Date().toISOString(),
    },
    {
      id: 'H007',
      hypothesis: 'The merge-gate rule (no features without customer justification) will hold for 12 months.',
      category: 'discipline',
      confidence: 'medium',
      evidenceFor: ['Written into CONTRIBUTING.md', 'Board resolution passed'],
      evidenceAgainst: [],
      decision: 'continue',
      nextExperiment: 'Monthly audit: what % of merged features satisfied the merge-gate?',
      status: 'testing',
      createdAt: new Date().toISOString(),
      lastUpdated: new Date().toISOString(),
    },
    {
      id: 'H008',
      hypothesis: 'Enterprises will buy execution infrastructure from a startup (vs. incumbents like ServiceNow, Atlassian).',
      category: 'market',
      confidence: 'low',
      evidenceFor: [],
      evidenceAgainst: [],
      decision: 'continue',
      nextExperiment: 'Track procurement/legal review timelines for each design partner conversion.',
      status: 'testing',
      createdAt: new Date().toISOString(),
      lastUpdated: new Date().toISOString(),
    },
    {
      id: 'H009',
      hypothesis: 'Time-to-Value under 14 days predicts retention.',
      category: 'retention',
      confidence: 'low',
      evidenceFor: [],
      evidenceAgainst: [],
      decision: 'continue',
      nextExperiment: 'Track TTV for each partner. At 6 months, compare retention of <14d TTV vs. >14d TTV.',
      status: 'testing',
      createdAt: new Date().toISOString(),
      lastUpdated: new Date().toISOString(),
    },
    {
      id: 'H010',
      hypothesis: 'The Execution Observatory (anonymous benchmarks) becomes a defensible moat after 50+ organizations.',
      category: 'moat',
      confidence: 'low',
      evidenceFor: [],
      evidenceAgainst: [],
      decision: 'continue',
      nextExperiment: 'Track Observatory contribution rate. Survey: do partners value the benchmark comparison?',
      status: 'testing',
      createdAt: new Date().toISOString(),
      lastUpdated: new Date().toISOString(),
    },
    {
      id: 'H011',
      hypothesis: 'Retention is a stronger signal of PMF than adoption.',
      category: 'pmf',
      confidence: 'high',
      evidenceFor: ['Standard SaaS wisdom', 'Net revenue retention drives valuation'],
      evidenceAgainst: [],
      decision: 'continue',
      nextExperiment: 'Define "renewal" criteria. Track what % of design partners renew after 90 days.',
      status: 'testing',
      createdAt: new Date().toISOString(),
      lastUpdated: new Date().toISOString(),
    },
    {
      id: 'H012',
      hypothesis: 'The founder can successfully shift from builder to customer-facing leader.',
      category: 'founder',
      confidence: 'medium',
      evidenceFor: ['Founder wrote the architecture, can explain it deeply'],
      evidenceAgainst: ['Founder may default to building when uncomfortable in sales conversations'],
      decision: 'continue',
      nextExperiment: 'Track weekly: how many customer conversations did the founder hold? Target: 5+/week.',
      status: 'testing',
      createdAt: new Date().toISOString(),
      lastUpdated: new Date().toISOString(),
    },
  ];

  for (const h of defaults) {
    hypotheses.set(h.id, h);
    await persist(h);
  }
  console.log(`[evidence-ledger] seeded ${defaults.length} default hypotheses`);
}

// Add a new hypothesis to the ledger.
export async function addHypothesis(hypothesisDef) {
  const id = 'H' + String(hypotheses.size + 1).padStart(3, '0');
  const hypothesis = {
    id,
    hypothesis: hypothesisDef.hypothesis,
    category: hypothesisDef.category || 'general',
    confidence: hypothesisDef.confidence || 'low',
    evidenceFor: hypothesisDef.evidenceFor || [],
    evidenceAgainst: hypothesisDef.evidenceAgainst || [],
    decision: hypothesisDef.decision || 'continue',
    nextExperiment: hypothesisDef.nextExperiment || '',
    status: 'testing',
    createdAt: new Date().toISOString(),
    lastUpdated: new Date().toISOString(),
  };
  hypotheses.set(id, hypothesis);
  await persist(hypothesis);
  return hypothesis;
}

// Update a hypothesis with new evidence.
export async function updateHypothesis(id, update) {
  const h = hypotheses.get(id);
  if (!h) return null;

  if (update.evidenceFor) {
    h.evidenceFor.push({ ...update.evidenceFor, timestamp: new Date().toISOString() });
  }
  if (update.evidenceAgainst) {
    h.evidenceAgainst.push({ ...update.evidenceAgainst, timestamp: new Date().toISOString() });
  }
  if (update.confidence) {
    h.confidence = update.confidence;
  }
  if (update.decision) {
    h.decision = update.decision;
  }
  if (update.nextExperiment) {
    h.nextExperiment = update.nextExperiment;
  }
  if (update.status) {
    h.status = update.status;
  }
  h.lastUpdated = new Date().toISOString();

  await persist(h);
  return h;
}

// Get the full ledger.
export function getLedger() {
  return Array.from(hypotheses.values())
    .sort((a, b) => a.id.localeCompare(b.id));
}

// Get a single hypothesis.
export function getHypothesis(id) {
  return hypotheses.get(id) || null;
}

// Get ledger summary stats.
export function getLedgerStats() {
  const all = Array.from(hypotheses.values());
  return {
    total: all.length,
    byConfidence: {
      high: all.filter(h => h.confidence === 'high').length,
      medium: all.filter(h => h.confidence === 'medium').length,
      low: all.filter(h => h.confidence === 'low').length,
    },
    byDecision: {
      continue: all.filter(h => h.decision === 'continue').length,
      pivot: all.filter(h => h.decision === 'pivot').length,
      stop: all.filter(h => h.decision === 'stop').length,
    },
    byStatus: {
      testing: all.filter(h => h.status === 'testing').length,
      confirmed: all.filter(h => h.status === 'confirmed').length,
      invalidated: all.filter(h => h.status === 'invalidated').length,
    },
    totalEvidenceFor: all.reduce((sum, h) => sum + h.evidenceFor.length, 0),
    totalEvidenceAgainst: all.reduce((sum, h) => sum + h.evidenceAgainst.length, 0),
  };
}

// === CEO FRIDAY DASHBOARD ===
// The weekly self-assessment template.
// Every Friday, the founder answers these questions honestly.
export function getFridayDashboard() {
  return {
    date: new Date().toISOString().split('T')[0],
    questions: [
      {
        id: 'conversations',
        question: 'How many customer conversations did you have this week?',
        target: '5+',
        type: 'number',
      },
      {
        id: 'requests',
        question: 'How many design partner requests did you receive or follow up on?',
        target: '3+',
        type: 'number',
      },
      {
        id: 'invalidated',
        question: 'How many assumptions were invalidated or weakened this week?',
        target: '1+ (intellectual honesty)',
        type: 'number',
      },
      {
        id: 'surprise',
        question: 'What was the biggest surprise from customer conversations?',
        target: 'Something you didn\'t expect',
        type: 'text',
      },
      {
        id: 'ignored',
        question: 'What feature requests did you ignore? Why?',
        target: 'List them with rationale (merge-gate discipline)',
        type: 'text',
      },
      {
        id: 'evidence',
        question: 'What new evidence did you collect this week?',
        target: 'At least one data point that updates a hypothesis',
        type: 'text',
      },
      {
        id: 'next_week',
        question: 'What is the single most important customer conversation for next week?',
        target: 'One name, one goal',
        type: 'text',
      },
    ],
    reminder: 'One customer conversation should outweigh ten internal ideas. If you spent more time coding than talking to customers this week, rebalance.',
  };
}

// Save a completed Friday dashboard.
const fridayDashboards = [];
const FRIDAY_PATH = path.resolve('./friday-dashboards.jsonl');

export async function saveFridayDashboard(responses) {
  const dashboard = {
    id: crypto.randomUUID(),
    date: new Date().toISOString().split('T')[0],
    responses,
    savedAt: new Date().toISOString(),
  };
  fridayDashboards.push(dashboard);
  try { await fs.appendFile(FRIDAY_PATH, JSON.stringify(dashboard) + '\n', 'utf8'); }
  catch (err) { console.warn('[evidence-ledger] friday persist failed:', err.message); }
  return dashboard;
}

export function listFridayDashboards() {
  return fridayDashboards.sort((a, b) => new Date(b.date) - new Date(a.date));
}

// Maestro v6 — Live Meeting Intelligence Engine
// Real-time transcript processing, objection detection, action item extraction,
// law invocation tracking, prediction logging, dossier enrichment.

import type {
  TranscriptLine, ActionItem, OrgLaw, Meeting, MeetingParticipant,
} from '@/types/domain';

// ============================================================
// REAL-TIME PROCESSING — called per transcript chunk
// ============================================================

export interface TranscriptChunk {
  ts: string;
  speakerId: string;
  speakerName: string;
  text: string;
}

export interface ProcessingResult {
  highlights: { text: string; type: 'TERM' | 'OBJECTION' }[];
  objections: ObjectionDetected[];
  actionItems: ActionItemDraft[];
  invokedLaws: LawInvocation[];
  predictions: PredictionDraft[];
  mentions: MentionDetected[];
  suggestions: MaestroSuggestion[];
}

export interface ObjectionDetected {
  text: string;
  reason: string;
  lawCode?: string;
  confidence: number;
}

export interface ActionItemDraft {
  text: string;
  assigneeName?: string;
  dueDate?: string;
  source: string;
}

export interface LawInvocation {
  lawCode: string;
  description: string;
  trigger: string; // what in the transcript triggered it
}

export interface PredictionDraft {
  statement: string;
  confidence: number;
  verifyDate: string; // ISO date 90 days from now
}

export interface MentionDetected {
  name: string;
  type: 'REGION' | 'PERSON' | 'PROJECT' | 'CUSTOMER' | 'PRODUCT';
  content: string;
  source: string;
}

export interface MaestroSuggestion {
  label: string;
  text: string;
  kind: 'RUN_SIMULATION' | 'ASK_MAESTRO' | 'CHECK_LAW' | 'ADD_STAKEHOLDER';
}

// ============================================================
// DETECTION RULES
// In production these are LLM-driven with rule-based fallback.
// ============================================================

const OBJECTION_PATTERNS = [
  /\b(dissent|disagree|object|oppose|against|reject|push back|pushback)\b/i,
  /\bI (don't|do not|cannot|can't) (support|endorse|approve|recommend)\b/i,
  /\bthat (won't|will not|cannot|can't) work\b/i,
];

const ACTION_ITEM_PATTERNS = [
  /\b(I'll|I will|we'll|we will|let's|let us)\s+(\w+)\s+(by|before|after)\s+(\w+)/i,
  /\b(action item|todo|to-do|follow up|followup):\s*(.+)/i,
  /\b(assign|schedule|draft|update|notify|review|prepare)\s+(.+?)\s+(by|due|before)\s+(.+)/i,
];

const TERM_HIGHLIGHTS = [
  'APAC', 'EMEA', 'NA', 'LATAM',
  'hiring', 'approve', 'dissent', 'compromise', 'reject',
  'Q1', 'Q2', 'Q3', 'Q4',
  'budget', 'headcount', 'revenue', 'churn',
];

// Law keyword triggers — maps phrases to law codes
const LAW_TRIGGERS: Record<string, { code: string; description: string }[]> = {
  'APAC': [{ code: 'L-0014', description: 'APAC support ratio below 1:14 predicts churn +14% within 2 quarters' }],
  'P1': [{ code: 'L-0007', description: 'Eng velocity drops 22% in weeks following >3 P1 incidents' }],
  'incident': [{ code: 'L-0007', description: 'Eng velocity drops 22% in weeks following >3 P1 incidents' }],
  'hiring': [{ code: 'L-0019', description: 'Hiring bursts correlate 0.84 with prior-quarter incidents, not revenue' }],
  'review': [{ code: 'L-0021', description: 'Architecture reviews with 2+ reviewers ship 31% faster than single-reviewer' }],
  'Friday': [{ code: 'L-0011', description: 'PRs merged Friday after 4pm have 2.4× the revert rate' }],
};

// Mention patterns
const MENTION_PATTERNS = {
  REGION: /\b(APAC|EMEA|NA|LATAM|North America|Europe|Asia Pacific)\b/g,
  // Persons and projects would come from the OEM's entity graph in production
};

export function processTranscriptChunk(
  chunk: TranscriptChunk,
  orgLaws: OrgLaw[],
): ProcessingResult {
  const highlights: ProcessingResult['highlights'] = [];
  const objections: ObjectionDetected[] = [];
  const actionItems: ActionItemDraft[] = [];
  const invokedLaws: LawInvocation[] = [];
  const predictions: PredictionDraft[] = [];
  const mentions: MentionDetected[] = [];
  const suggestions: MaestroSuggestion[] = [];

  // Highlight key terms
  for (const term of TERM_HIGHLIGHTS) {
    const regex = new RegExp(`\\b${term}\\b`, 'gi');
    if (regex.test(chunk.text)) {
      highlights.push({ text: term, type: 'TERM' });
    }
  }

  // Objection detection
  for (const pattern of OBJECTION_PATTERNS) {
    if (pattern.test(chunk.text)) {
      // Find linked law if any
      const linkedLaw = findLinkedLaw(chunk.text, orgLaws);
      objections.push({
        text: `${chunk.speakerName} dissents`,
        reason: extractReasoning(chunk.text),
        lawCode: linkedLaw?.code,
        confidence: 0.78,
      });
      highlights.push({ text: 'dissent', type: 'OBJECTION' });
      break;
    }
  }

  // Action item extraction
  for (const pattern of ACTION_ITEM_PATTERNS) {
    const match = chunk.text.match(pattern);
    if (match) {
      actionItems.push({
        text: match[0],
        source: `transcript:${chunk.ts}`,
      });
      break;
    }
  }

  // Law invocation
  for (const [keyword, laws] of Object.entries(LAW_TRIGGERS)) {
    if (chunk.text.toLowerCase().includes(keyword.toLowerCase())) {
      for (const law of laws) {
        if (!invokedLaws.find(l => l.lawCode === law.code)) {
          invokedLaws.push({
            lawCode: law.code,
            description: law.description,
            trigger: `keyword "${keyword}" in transcript`,
          });
        }
      }
    }
  }

  // Mention detection
  for (const [type, pattern] of Object.entries(MENTION_PATTERNS)) {
    const matches = chunk.text.matchAll(pattern);
    for (const match of matches) {
      const name = match[0].toUpperCase();
      if (!mentions.find(m => m.name === name)) {
        mentions.push({
          name,
          type: type as MentionDetected['type'],
          content: `Mentioned by ${chunk.speakerName} at ${chunk.ts}`,
          source: `transcript:${chunk.ts}`,
        });
      }
    }
  }

  // Decision approval → log predictions
  if (/\b(approve|approved|let'?s go with|decision made)\b/i.test(chunk.text)) {
    predictions.push({
      statement: 'Decision outcome will be verified in 90 days',
      confidence: 0.78,
      verifyDate: new Date(Date.now() + 90 * 24 * 60 * 60 * 1000).toISOString(),
    });
    suggestions.push({
      label: 'View synthesis',
      text: 'Press ⌘↵ to ask Maestro about predicted outcomes, or end the meeting to view synthesis.',
      kind: 'ASK_MAESTRO',
    });
  }

  // Suggest running simulation when compromise mentioned
  if (/\b(compromise|middle ground|what if we)\b/i.test(chunk.text)) {
    suggestions.push({
      label: 'Run simulation',
      text: "Maestro can run the 90-day counterfactual. Press ⌘↵ and ask \"What happens if I approve this compromise?\"",
      kind: 'RUN_SIMULATION',
    });
  }

  return {
    highlights, objections, actionItems, invokedLaws, predictions, mentions, suggestions,
  };
}

function findLinkedLaw(text: string, laws: OrgLaw[]): OrgLaw | undefined {
  const lower = text.toLowerCase();
  return laws.find(law =>
    lower.includes(law.code.toLowerCase()) ||
    lower.includes(law.statement.toLowerCase().split(' ').slice(0, 3).join(' '))
  );
}

function extractReasoning(text: string): string {
  // Strip the objection keyword and return the rest
  return text.replace(/\b(I dissent|I disagree|I object|I oppose|I'm against)\b/i, '').trim();
}

// ============================================================
// CONSENT VERIFICATION — every participant must consent before recording
// ============================================================

export interface ConsentState {
  meetingId: string;
  participants: { entityId: string; name: string; consentedAt?: string; consentMethod?: string }[];
  allConsented: boolean;
  consentLoggedAt?: string;
}

export function verifyConsent(participants: MeetingParticipant[]): boolean {
  return participants.every(p => p.consentedAt);
}

export function logConsent(meetingId: string, participants: MeetingParticipant[]): ConsentState {
  const allConsented = verifyConsent(participants);
  return {
    meetingId,
    participants: participants.map(p => ({
      entityId: p.entityId,
      name: p.name,
      consentedAt: p.consentedAt,
      consentMethod: p.consentMethod,
    })),
    allConsented,
    consentLoggedAt: allConsented ? new Date().toISOString() : undefined,
  };
}

// ============================================================
// DOSSIER ENRICHMENT — external harvesting
// In production, calls LinkedIn/Twitter/News APIs with rate limits and caching.
// ============================================================

export interface DossierEnrichmentRequest {
  entityId: string;
  name: string;
  linkedinUrl?: string;
  twitterHandle?: string;
  orgDomain?: string;
}

export interface DossierEnrichmentResult {
  entityId: string;
  linkedin?: { summary: string; url?: string; lastHarvestedAt: string };
  twitter?: { summary: string; handle?: string; lastHarvestedAt: string };
  news?: { summary: string; mentionCount: number; lastHarvestedAt: string };
  internal: { decisionsLogged: number; debatesRuled: number; influenceScore: number };
}

export async function enrichDossier(
  request: DossierEnrichmentRequest,
  // Injected for testability — in production these are real API clients
  external: {
    linkedin?: (url: string) => Promise<string>;
    twitter?: (handle: string) => Promise<string>;
    news?: (query: string) => Promise<{ summary: string; count: number }>;
  } = {},
): Promise<DossierEnrichmentResult> {
  const result: DossierEnrichmentResult = {
    entityId: request.entityId,
    internal: { decisionsLogged: 0, debatesRuled: 0, influenceScore: 0 },
  };

  if (request.linkedinUrl && external.linkedin) {
    const summary = await external.linkedin(request.linkedinUrl);
    result.linkedin = {
      summary,
      url: request.linkedinUrl,
      lastHarvestedAt: new Date().toISOString(),
    };
  }

  if (request.twitterHandle && external.twitter) {
    const summary = await external.twitter(request.twitterHandle);
    result.twitter = {
      summary,
      handle: request.twitterHandle,
      lastHarvestedAt: new Date().toISOString(),
    };
  }

  if (external.news) {
    const { summary, count } = await external.news(request.name);
    result.news = {
      summary,
      mentionCount: count,
      lastHarvestedAt: new Date().toISOString(),
    };
  }

  return result;
}

// ============================================================
// POST-MEETING SYNTHESIS — converts meeting into OEM updates
// ============================================================

export interface SynthesisResult {
  decisions: { title: string; description: string; confidence: number; verifyDate: string }[];
  predictions: { statement: string; confidence: number; verifyDate: string }[];
  actionItems: ActionItemDraft[];
  debateUpdates: { debateId?: string; status: 'OPENED' | 'RESOLVED' | 'ESCALATED'; note?: string }[];
  lawUpdates: { lawCode: string; update: 'EVIDENCE_ADDED' | 'COUNTER_EXAMPLE_LOGGED'; description: string }[];
  followUpDrafts: { type: 'SLACK' | 'EMAIL' | 'JIRA' | 'CALENDAR' | 'CONFLUENCE'; content: string }[];
  shrImpact: { currentShr: number; projectedShr: number; withinBand: boolean };
}

export function synthesizeMeeting(
  meeting: Meeting,
  processingResults: ProcessingResult[],
  currentShr: number,
): SynthesisResult {
  // Aggregate all processing results
  const allObjections = processingResults.flatMap(r => r.objections);
  const allActionItems = processingResults.flatMap(r => r.actionItems);
  const allLaws = processingResults.flatMap(r => r.invokedLaws);
  const allPredictions = processingResults.flatMap(r => r.predictions);

  // Detect decisions (approval patterns)
  const decisionLines = meeting.transcript.filter(line =>
    /\b(approve|approved|decision made|let'?s go with)\b/i.test(line.text)
  );

  const decisions = decisionLines.map(line => ({
    title: `Decision from ${meeting.title}`,
    description: line.text,
    confidence: 0.78,
    verifyDate: new Date(Date.now() + 90 * 24 * 60 * 60 * 1000).toISOString(),
  }));

  // Law updates
  const lawUpdates = allLaws.map(law => ({
    lawCode: law.lawCode,
    update: 'EVIDENCE_ADDED' as const,
    description: law.description,
  }));

  // Follow-up drafts
  const followUpDrafts = [
    {
      type: 'SLACK' as const,
      content: `Meeting summary: ${meeting.title}. ${decisions.length} decision(s), ${allActionItems.length} action items.`,
    },
    {
      type: 'EMAIL' as const,
      content: `Decision recap to all ${meeting.participants.length} participants.`,
    },
    {
      type: 'JIRA' as const,
      content: `${allActionItems.length} action items as tickets.`,
    },
    {
      type: 'CALENDAR' as const,
      content: `90-day verification review scheduled for ${new Date(Date.now() + 90 * 24 * 60 * 60 * 1000).toISOString()}`,
    },
  ];

  // SHR projection (simplified — assumes 0.78 hit rate for pending)
  const pendingCount = allPredictions.length;
  const projectedShr = pendingCount > 0
    ? (currentShr * 23 + pendingCount * 0.78) / (23 + pendingCount)
    : currentShr;

  return {
    decisions,
    predictions: allPredictions,
    actionItems: allActionItems,
    debateUpdates: allObjections.length > 0
      ? [{ status: 'OPENED', note: `${allObjections.length} objection(s) surfaced` }]
      : [],
    lawUpdates,
    followUpDrafts,
    shrImpact: {
      currentShr,
      projectedShr,
      withinBand: projectedShr >= 0.80 && projectedShr <= 0.88,
    },
  };
}

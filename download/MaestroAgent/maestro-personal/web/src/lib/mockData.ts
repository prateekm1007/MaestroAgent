import type { Commitment, Whisper, AskAnswer, ChangeItem } from './types'

// Helper: create ISO date relative to now
function hoursFromNow(h: number): string {
  return new Date(Date.now() + h * 3600 * 1000).toISOString()
}
function daysFromNow(d: number): string {
  return new Date(Date.now() + d * 24 * 3600 * 1000).toISOString()
}
function hoursAgo(h: number): string {
  return new Date(Date.now() - h * 3600 * 1000).toISOString()
}
function daysAgo(d: number): string {
  return new Date(Date.now() - d * 24 * 3600 * 1000).toISOString()
}

export const mockCommitments: Commitment[] = [
  {
    id: 'c1',
    entity: 'Maria Garcia',
    text: 'Send the Q3 budget proposal to Maria',
    dueDate: hoursFromNow(2),
    state: 'at_risk',
    confidence: 0.97,
    importance: 'high',
    isBlocking: true,
    owner: 'user',
    source: {
      type: 'email',
      snippet: 'Thanks for the call. I will send the Q3 budget proposal by Friday EOD.',
      timestamp: daysAgo(2),
      sender: 'maria.garcia@company.com',
    },
    createdAt: daysAgo(2),
  },
  {
    id: 'c2',
    entity: 'Alex Chen',
    text: 'Review the auth module pull request',
    dueDate: daysFromNow(3),
    state: 'active',
    confidence: 0.85,
    importance: 'medium',
    isBlocking: false,
    owner: 'user',
    source: {
      type: 'slack',
      snippet: "I'll review the auth module PR by Tuesday next week.",
      timestamp: daysAgo(1),
      sender: 'alex.chen',
    },
    createdAt: daysAgo(1),
  },
  {
    id: 'c3',
    entity: 'Jamie Lee',
    text: 'Deliver the design mockups',
    dueDate: daysFromNow(5),
    state: 'active',
    confidence: 0.72,
    importance: 'medium',
    isBlocking: false,
    owner: 'user',
    source: {
      type: 'email',
      snippet: 'I will deliver the design mockups by Wednesday.',
      timestamp: daysAgo(3),
      sender: 'jamie.lee@design.co',
    },
    createdAt: daysAgo(3),
  },
  {
    id: 'c4',
    entity: 'Sam Rivera',
    text: 'Finalize the Q3 roadmap presentation',
    dueDate: daysFromNow(10),
    state: 'active',
    confidence: 0.65,
    importance: 'low',
    isBlocking: false,
    owner: 'user',
    source: {
      type: 'calendar',
      snippet: "I'll finalize the Q3 roadmap presentation by next Monday.",
      timestamp: daysAgo(4),
      sender: 'Calendar',
    },
    createdAt: daysAgo(4),
  },
  {
    id: 'c5',
    entity: 'Priya Patel',
    text: 'Fix the flaky CI pipeline',
    dueDate: daysFromNow(1),
    state: 'active',
    confidence: 0.91,
    importance: 'high',
    isBlocking: true,
    owner: 'user',
    source: {
      type: 'slack',
      snippet: 'I will fix the flaky CI pipeline this week.',
      timestamp: hoursAgo(20),
      sender: 'priya.patel',
    },
    createdAt: hoursAgo(20),
  },
]

export const mockWhispers: Whisper[] = [
  {
    id: 'w1',
    type: 'at_risk',
    title: "Maria hasn't replied",
    context: 'Last promise: Budget proposal. Sent 6 days ago.',
    probability: 82,
    probabilityBasis: '6 days since last response. Maria typically responds within 2 days (based on 14 past interactions). 4 of 5 commitments past this response time have slipped.',
    suggestedActions: [
      { label: 'Send Follow-up', action: 'send_followup' },
      { label: 'Later', action: 'dismiss' },
    ],
    entity: 'Maria Garcia',
    createdAt: hoursAgo(1),
  },
  {
    id: 'w2',
    type: 'preparation',
    title: 'Meeting with Alice in 20 minutes',
    context: '3 commitments to discuss: Q3 budget, hiring plan, partnership terms.',
    suggestedActions: [
      { label: 'Review Briefing', action: 'review' },
      { label: 'Dismiss', action: 'dismiss' },
    ],
    entity: 'Alice',
    createdAt: hoursAgo(0.1),
  },
  {
    id: 'w3',
    type: 'opportunity',
    title: "You've completed 4 commitments to Maria this month",
    context: "That's 2x your average. Consider asking for a referral or testimonial.",
    suggestedActions: [
      { label: 'View Relationship', action: 'view_relationship' },
      { label: 'Dismiss', action: 'dismiss' },
    ],
    entity: 'Maria Garcia',
    createdAt: hoursAgo(3),
  },
  {
    id: 'w4',
    type: 'quiet',
    title: 'Maria typically responds within 2 days. It\u2019s been 6.',
    context: '',
    suggestedActions: [],
    createdAt: hoursAgo(2),
  },
]

export const mockChanges: ChangeItem[] = [
  {
    type: 'deadline',
    text: 'Q3 budget proposal is due in 2 hours',
    entity: 'Maria Garcia',
    timeAgo: 'just now',
  },
  {
    type: 'new',
    text: 'Priya Patel committed to fixing the CI pipeline',
    entity: 'Priya Patel',
    timeAgo: '20 min ago',
  },
  {
    type: 'transition',
    text: 'Jamie Lee marked design mockups as in progress',
    entity: 'Jamie Lee',
    timeAgo: '2 hours ago',
  },
  {
    type: 'completion',
    text: 'Alex Chen completed the auth module review',
    entity: 'Alex Chen',
    timeAgo: '5 hours ago',
  },
]

export const mockAskAnswer: AskAnswer = {
  query: 'What did I promise Maria?',
  answer: 'On Tuesday, you promised Maria you\u2019d send the Q3 budget proposal by Friday.',
  confidence: 0.97,
  evidence: [
    {
      signalId: 'sig_001',
      source: {
        type: 'email',
        snippet: 'Email from Maria Garcia',
        timestamp: daysAgo(2),
        sender: 'maria.garcia@company.com',
      },
      text: 'Thanks for the call. I will send the Q3 budget proposal by Friday EOD.',
      confidence: 0.97,
    },
  ],
  reasoning: [
    'The email explicitly states the commitment',
    'It includes a specific deadline (Friday EOD)',
    'Maria is mentioned by name',
    'You haven\u2019t marked this as completed',
  ],
  relatedCommitments: [
    {
      entity: 'Maria Garcia',
      text: 'Hiring plan discussion',
      dueDate: daysFromNow(7),
      owner: 'user',
    },
    {
      entity: 'Maria Garcia',
      text: 'Partnership terms review',
      dueDate: daysAgo(3),
      owner: 'other',
    },
  ],
}

export const mockAskAnswerLow: AskAnswer = {
  query: 'Did I promise to review the security audit?',
  answer: 'I found a possible reference to a security review, but the evidence is ambiguous.',
  confidence: 0.42,
  evidence: [
    {
      signalId: 'sig_002',
      source: {
        type: 'slack',
        snippet: 'Slack message in #engineering',
        timestamp: daysAgo(5),
        sender: 'sam.rivera',
      },
      text: 'We should probably look at the security audit at some point.',
      confidence: 0.42,
    },
  ],
  reasoning: [
    'The message uses "should probably" (tentative, not a commitment)',
    'No specific deadline mentioned',
    'No direct first-person promise',
  ],
  relatedCommitments: [],
}

export const mockAskAnswerEmpty: AskAnswer = {
  query: 'What did I promise Elon Musk?',
  answer: '',
  confidence: 0,
  evidence: [],
  reasoning: [],
  relatedCommitments: [],
}

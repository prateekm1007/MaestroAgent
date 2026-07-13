/**
 * Maestro demo data — shown when the live API is unreachable.
 *
 * These are realistic samples that match the shape of the FastAPI
 * responses documented in MaestroAgent/download/MaestroAgent/maestro-personal/
 * src/maestro_personal_shell/api.py. The CEO can see every screen working
 * without standing up the backend.
 */

export const demoTheMoment = {
  has_moment: true,
  commitment: {
    entity: "Maria Garcia",
    text: "Send Maria Garcia the pricing proposal by Friday.",
    claim_type: "commitment",
    signal_id: "sig_demo_001",
    timestamp: "2026-07-08T14:32:00Z",
  },
  situation: {
    situation_id: "sit_demo_001",
    entity: "Maria Garcia",
    state: "awaiting_outcome",
    evidence_count: 3,
  },
  why_this_one:
    "you made this promise; no follow-up in 4 days; deadline: Friday",
  source_evidence: [
    {
      text: "I will send Maria Garcia the pricing proposal by Friday.",
      entity: "Maria Garcia",
      timestamp: "2026-07-08T14:32:00Z",
      source: "gmail",
    },
  ],
};

export const demoBriefing = {
  greeting: "Good morning.",
  top_situation: {
    entity: "Maria Garcia",
    state: "awaiting_outcome",
    summary: "Pricing proposal due Friday. No movement since Monday.",
  },
  material_changes: [
    "Alex Chen moved the design review to next Tuesday.",
    "Riley raised a concern about the vendor pricing model.",
  ],
  unknowns: [
    "Whether Maria has confirmed the budget envelope internally.",
    "Whether the vendor proposal will land before Friday's deadline.",
  ],
  disputes: [],
  can_decide_now: [
    "Confirm the Friday deadline with Maria in writing.",
  ],
  cannot_decide_yet: [
    "Send the proposal — pending Riley's pricing review.",
  ],
  why_boundary:
    "Riley's review is a real blocker. Sending early risks rework.",
  next_step: "Ping Riley before Thursday EOD.",
  belief: "The Friday deadline is realistic if Riley confirms pricing today.",
  why_belief:
    "Based on your last 3 similar proposals, the deck takes ~1 day once pricing is locked.",
  what_would_change_belief:
    "If Riley flags a structural issue with the pricing model, expect a 2-day slip.",
  watching_quietly: [
    {
      entity: "Sam Patel",
      state: "observing",
      summary: "Said he would 'circle back' last week. No movement.",
    },
    {
      entity: "Acme Corp",
      state: "observing",
      summary: "Renewal due in 38 days. Quiet.",
    },
  ],
  ask_prompt: "What did I promise Maria?",
};

export const demoTheShifts = {
  the_shifts: [
    {
      entity: "Alex Chen",
      text: "Design review moved to next Tuesday (was Thursday).",
      type: "schedule_change",
      is_meaningful: true,
    },
    {
      entity: "Riley",
      text: "Raised a concern about the vendor pricing model — needs review before Friday.",
      type: "material_objection",
      is_meaningful: true,
    },
  ],
  silence_message: "",
};

export const demoCommitmentsTheOne = {
  primary: {
    entity: "Maria Garcia",
    text: "Send Maria Garcia the pricing proposal by Friday.",
    claim_type: "commitment",
    signal_id: "sig_demo_001",
    is_commitment: true,
    is_at_risk: true,
    days_stale: 4,
    deadline: "2026-07-12",
    calibration_note: "Insufficient calibration history — keep tracking outcomes.",
    outcome_history: "",
    confidence: 0.62,
  },
  why_primary:
    "no follow-up for 4 days; deadline: 2026-07-12; you made this promise",
  secondary: [
    {
      entity: "Sam Patel",
      text: "Follow up with Sam on the API contract changes.",
      claim_type: "commitment",
      signal_id: "sig_demo_002",
      is_commitment: true,
      is_at_risk: false,
      days_stale: 1,
      deadline: "2026-07-15",
      calibration_note: "",
      outcome_history: "Kept 3/5 like this",
      confidence: 0.78,
    },
    {
      entity: "Alex Chen",
      text: "Review the design deck before Tuesday's meeting.",
      claim_type: "commitment",
      signal_id: "sig_demo_003",
      is_commitment: true,
      is_at_risk: false,
      days_stale: 0,
      deadline: "2026-07-16",
      calibration_note: "",
      outcome_history: "",
      confidence: 0.84,
    },
  ],
  overall_calibration: "Insufficient calibration history",
};

export const demoCommitments = [
  {
    entity: "Maria Garcia",
    text: "Send Maria Garcia the pricing proposal by Friday.",
    claim_type: "commitment",
    signal_id: "sig_demo_001",
    is_commitment: true,
    is_at_risk: true,
    days_stale: 4,
    deadline: "2026-07-12",
    calibration_note: "Insufficient calibration history",
    outcome_history: "",
    confidence: 0.62,
  },
  {
    entity: "Sam Patel",
    text: "Follow up with Sam on the API contract changes.",
    claim_type: "commitment",
    signal_id: "sig_demo_002",
    is_commitment: true,
    is_at_risk: false,
    days_stale: 1,
    deadline: "2026-07-15",
    calibration_note: "",
    outcome_history: "Kept 3/5 like this",
    confidence: 0.78,
  },
  {
    entity: "Alex Chen",
    text: "Review the design deck before Tuesday's meeting.",
    claim_type: "commitment",
    signal_id: "sig_demo_003",
    is_commitment: true,
    is_at_risk: false,
    days_stale: 0,
    deadline: "2026-07-16",
    calibration_note: "",
    outcome_history: "",
    confidence: 0.84,
  },
];

export const demoSignals = [
  {
    signal_id: "sig_demo_001",
    entity: "Maria Garcia",
    text: "I will send Maria Garcia the pricing proposal by Friday.",
    signal_type: "commitment_made",
    timestamp: "2026-07-08T14:32:00Z",
  },
  {
    signal_id: "sig_demo_002",
    entity: "Sam Patel",
    text: "Sam mentioned he'd have the API contract changes by next week.",
    signal_type: "commitment_received",
    timestamp: "2026-07-09T11:05:00Z",
  },
  {
    signal_id: "sig_demo_003",
    entity: "Alex Chen",
    text: "Design review moved to next Tuesday.",
    signal_type: "schedule_change",
    timestamp: "2026-07-10T09:14:00Z",
  },
  {
    signal_id: "sig_demo_004",
    entity: "Riley",
    text: "Riley raised a concern about the vendor pricing model.",
    signal_type: "material_objection",
    timestamp: "2026-07-10T15:48:00Z",
  },
  {
    signal_id: "sig_demo_005",
    entity: "Acme Corp",
    text: "Acme Corp renewal is due in 38 days. No decision-maker assigned.",
    signal_type: "reported_statement",
    timestamp: "2026-07-07T08:00:00Z",
  },
  {
    signal_id: "sig_demo_006",
    entity: "Sam Patel",
    text: "Sam said the API contract will land Friday EOD.",
    signal_type: "commitment_received",
    timestamp: "2026-07-09T13:22:00Z",
  },
  {
    signal_id: "sig_demo_007",
    entity: "Maria Garcia",
    text: "Maria confirmed the Friday deadline for the pricing proposal.",
    signal_type: "follow_up_required",
    timestamp: "2026-07-09T10:11:00Z",
  },
];

export const demoAskResponse = (query: string) => {
  const q = query.toLowerCase();
  if (q.includes("alex")) {
    return {
      answer:
        "You committed to reviewing the design deck before Tuesday's meeting with Alex Chen.",
      query,
      source_sentence:
        "I'll review the design deck before Tuesday's meeting with Alex.",
      source_entity: "Alex Chen",
      source_timestamp: "2026-07-08T16:42:00Z",
      situation_state: "preparing",
      evidence_refs: [
        { entity: "Alex Chen", text: "Design review moved to next Tuesday.", timestamp: "2026-07-10T09:14:00Z" },
      ],
      confidence: 0.82,
      counterevidence: [],
      unknowns: ["Whether Alex has the latest copy of the deck."],
      as_of: "2026-07-11T00:00:00Z",
      decision_boundary: "decide now — review is a small task, do it today.",
      perspectives: [],
      reasoning_chain: [
        "Found a commitment_made signal to Alex on 2026-07-08.",
        "Design review was moved to Tuesday on 2026-07-10.",
        "No completion signal exists — commitment is still open.",
      ],
      calibration_note: "Insufficient calibration history",
      consequence_paths: [],
      llm_active: false,
      llm_provider: "none",
      intelligence_source: "rules",
    };
  }
  if (q.includes("maria") || q.includes("promis") || q.includes("pricing")) {
    return {
      answer:
        "You promised to send Maria Garcia the pricing proposal by Friday. The original commitment was made on July 8.",
      query,
      source_sentence:
        "I will send Maria Garcia the pricing proposal by Friday.",
      source_entity: "Maria Garcia",
      source_timestamp: "2026-07-08T14:32:00Z",
      situation_state: "awaiting_outcome",
      evidence_refs: [
        { entity: "Maria Garcia", text: "Maria confirmed the Friday deadline for the pricing proposal.", timestamp: "2026-07-09T10:11:00Z" },
      ],
      confidence: 0.91,
      counterevidence: [
        {
          text: "Riley raised a concern about the vendor pricing model — needs review before Friday.",
          entity: "Riley",
          timestamp: "2026-07-10T15:48:00Z",
          why_it_matters:
            "This may delay the pricing review past Friday if the model is restructured.",
        },
      ],
      unknowns: [
        "Whether Maria has confirmed the budget envelope internally.",
        "Whether Riley's pricing review will land before Friday.",
      ],
      as_of: "2026-07-11T00:00:00Z",
      decision_boundary: "wait — Riley's review is a real blocker.",
      perspectives: [
        { lens: "timeline", view: "On track if Riley confirms today; at risk if delayed past Wednesday." },
        { lens: "relationship", view: "Maria has explicitly confirmed the deadline — missing it would damage trust." },
      ],
      reasoning_chain: [
        "Matched 'Maria' + 'pricing' to commitment_made signal sig_demo_001.",
        "Cross-referenced with Maria's follow_up_required signal — deadline confirmed.",
        "Found a material objection from Riley that touches the same pricing thread.",
        "Confidence is high on the existence of the promise; lower on whether Friday is still realistic.",
      ],
      calibration_note: "Insufficient calibration history — keep tracking outcomes.",
      consequence_paths: [
        "If you send the proposal Friday: commitment kept, Maria happy, but Riley's review may force a revision.",
        "If you delay to Monday: lower rework risk, but Maria's trust takes a hit.",
      ],
      llm_active: false,
      llm_provider: "none",
      intelligence_source: "rules",
    };
  }
  if (q.includes("sam") || q.includes("api")) {
    return {
      answer:
        "Sam Patel committed to delivering the API contract changes by Friday EOD. The original commitment was received on July 9.",
      query,
      source_sentence:
        "Sam said the API contract will land Friday EOD.",
      source_entity: "Sam Patel",
      source_timestamp: "2026-07-09T13:22:00Z",
      situation_state: "awaiting_outcome",
      evidence_refs: [],
      confidence: 0.74,
      counterevidence: [],
      unknowns: ["Whether Sam is the sole owner of the contract."],
      as_of: "2026-07-11T00:00:00Z",
      decision_boundary: "wait — Sam owns this; ping Friday if no movement.",
      perspectives: [],
      reasoning_chain: [
        "Found two Sam Patel signals: a commitment_received on 2026-07-09 and a follow-up later the same day.",
        "No completion signal yet. The commitment is open but not stale.",
      ],
      calibration_note: "Kept 3/5 like this",
      consequence_paths: [],
      llm_active: false,
      llm_provider: "none",
      intelligence_source: "rules",
    };
  }
  // Generic fallback — Maestro says "I don't know" honestly.
  return {
    answer:
      "I don't have enough evidence to answer that. I can answer questions about specific people, commitments, or deadlines you've discussed. Try: \"What did I promise Maria?\"",
    query,
    source_sentence: "",
    source_entity: "",
    source_timestamp: "",
    situation_state: "unknown",
    evidence_refs: [],
    confidence: 0.18,
    counterevidence: [],
    unknowns: [
      "I couldn't find any signal matching this query.",
      "Try rephrasing with a person's name, a topic (e.g. 'pricing'), or a timeframe.",
    ],
    as_of: "2026-07-11T00:00:00Z",
    decision_boundary: "what would change this: add a signal about this topic.",
    perspectives: [],
    reasoning_chain: [
      "Searched all signals for matching entities or keywords.",
      "No direct match found. Returning honest abstention.",
    ],
    calibration_note: "",
    consequence_paths: [],
    llm_active: false,
    llm_provider: "none",
    intelligence_source: "ranker",
  };
};

export const demoAskHistory = [
  "What did I promise Maria?",
  "When is the design review with Alex?",
  "What did Sam commit to?",
  "What's at risk this week?",
];

export const demoLlmStatus = {
  configured: false,
  verified: false,
  active: false,
  llm_active: false,
  provider: "none",
  probe_latency_ms: 0,
  probe_error: "no provider configured",
  probe_cached_seconds: 60,
  available_providers: [],
  mode: "Rule-based (keyword fallback)",
  intelligence_paths: {
    ask_answer: "rule-based",
    perspectives: "keyword-counters",
    judgment_synthesis: "rule-concatenation",
    consequence_routing: "dictionary-lookup",
    ambient: "keyword-triggers",
  },
  note: "No LLM available. Set OPENAI_API_KEY, ANTHROPIC_API_KEY, OPENROUTER_API_KEY, XAI_API_KEY, run Ollama, or install the z-ai CLI to activate LLM mode.",
};

export const demoPrivacyMode = {
  mode: "local",
  description: "All processing happens on-device. Nothing leaves this machine.",
  egress_paths: [
    { destination: "none", purpose: "No external calls.", data: "n/a" },
  ],
};

export const demoCalibration = {
  message: "Insufficient calibration history — keep tracking outcomes.",
  brier_score: null,
  counts: { total: 4, resolved: 0, hits: 0, misses: 0 },
  buckets: [],
};

export const demoAuditLog = {
  events: [
    {
      timestamp: "2026-07-11T08:14:00Z",
      action: "read",
      endpoint: "/api/the-moment",
      user_email: "default@personal.local",
    },
    {
      timestamp: "2026-07-11T08:14:01Z",
      action: "read",
      endpoint: "/api/briefing",
      user_email: "default@personal.local",
    },
    {
      timestamp: "2026-07-11T08:13:50Z",
      action: "read",
      endpoint: "/api/llm-status",
      user_email: "default@personal.local",
    },
    {
      timestamp: "2026-07-11T07:55:12Z",
      action: "write",
      endpoint: "/api/signals",
      user_email: "default@personal.local",
      signal_id: "sig_demo_007",
    },
    {
      timestamp: "2026-07-11T07:30:08Z",
      action: "read",
      endpoint: "/api/commitments",
      user_email: "default@personal.local",
    },
    {
      timestamp: "2026-07-10T22:18:44Z",
      action: "correct",
      endpoint: "/api/signals/sig_demo_008/correct",
      user_email: "default@personal.local",
      signal_id: "sig_demo_008",
    },
    {
      timestamp: "2026-07-10T18:02:19Z",
      action: "read",
      endpoint: "/api/ask",
      user_email: "default@personal.local",
    },
  ],
};

export const demoCopilotWhispers = [
  {
    type: "forgotten_commitment",
    entity: "Maria Garcia",
    text: "You promised Maria the pricing proposal by Friday. Consider bringing it up.",
    priority: "high",
    confidence: 0.82,
    evidence_refs: [
      { entity: "Maria Garcia", text: "I will send Maria Garcia the pricing proposal by Friday.", timestamp: "2026-07-08T14:32:00Z" },
      { entity: "Maria Garcia", text: "Maria followed up asking for the proposal — no response in 4 days.", timestamp: "2026-07-10T09:15:00Z" },
    ],
    stale_commitments: [
      { entity: "Maria Garcia", text: "Send pricing proposal by Friday", days_stale: 4 },
    ],
    suggestions: ["Surface the proposal status proactively.", "Bring the Friday deadline into the conversation."],
  },
  {
    type: "open_question",
    entity: "Riley",
    text: "Riley's pricing concern is unresolved. Surface it if the topic comes up.",
    priority: "medium",
    confidence: 0.66,
    evidence_refs: [
      { entity: "Riley", text: "Riley raised a concern about the vendor pricing model.", timestamp: "2026-07-09T11:00:00Z" },
    ],
    stale_commitments: [],
    suggestions: ["Ask Riley directly if the vendor model concern is resolved."],
  },
  {
    type: "talk_ratio",
    entity: "—you",
    text: "You're at 68% talk time. Consider asking an open question.",
    priority: "low",
    confidence: 0.91,
    evidence_refs: [],
    stale_commitments: [],
    suggestions: ["You're talking 68% of the time. Listen more to gather information."],
  },
];

export const demoPostCallSummary = {
  hero_summary: {
    title: "Meeting with Maria Garcia",
    duration_minutes: 18.5,
    participant_count: 2,
    transcript_chunk_count: 14,
    ended_at: new Date().toISOString(),
  },
  key_stats: {
    commitments: 2,
    objections: 1,
    suggestions: 5,
    transcript_chunks: 14,
    talk_ratio_pct: 68.0,
    talk_ratio_status: "talking_too_much",
  },
  commitments_tracked: [
    {
      text: "Send the revised pricing proposal by Friday",
      actor: "you",
      day_count: 0,
      deduped: false,
      status: "Tracked",
    },
    {
      text: "Forward Riley's vendor-model concern to the product team",
      actor: "you",
      day_count: 0,
      deduped: false,
      status: "Tracked",
    },
  ],
  objections_raised: [
    {
      type: "price_too_high",
      text: "Maria mentioned the enterprise tier feels expensive relative to seats.",
      confidence: 0.78,
      confidence_label: "medium",
      action_required: "Follow up with value-anchor response pattern",
    },
  ],
  draft_email: {
    subject: "Follow-up — Meeting with Maria Garcia",
    body: "Hi Maria,\n\nThank you for the productive call today. Here's what I captured:\n\nCommitments:\n  - Send the revised pricing proposal by Friday (you)\n  - Forward Riley's vendor-model concern to the product team (you)\n\nAction items:\n  - Address the price_too_high concern raised\n\nBased on our experience:\n  - Always anchor pricing before discussing discounts\n\nNext steps:\n  - I'll follow up on each commitment above by the agreed dates\n  - Let me know if I've missed anything\n\nPlease let me know if I've missed anything. Best,\n[Your name]",
    tone: "professional",
    commitment_count: 2,
    evidence_count: 1,
    suggested_send_time: "within_4h",
  },
  what_maestro_learned: {
    new_signals_ingested: 2,
    objection_pattern_data_points: 1,
    data_points_to_validated_law: 4,
    learning_active: true,
    message: "This meeting generated 2 new signal(s) ingested into organizational memory. The objection pattern now has 1 data point(s) — 4 more and it becomes a validated organizational law.",
  },
};

export const demoTranscriptSeed = [
  { speaker: "Maria Garcia", text: "Thanks for hopping on. Did you have a chance to look at the pricing envelope?", timestamp: "2026-07-11T09:00:00Z" },
  { speaker: "you", text: "I did. Riley raised a concern about the vendor model, but I think we can still hit Friday.", timestamp: "2026-07-11T09:00:18Z" },
  { speaker: "Maria Garcia", text: "Friday works. Just keep me posted if anything slips.", timestamp: "2026-07-11T09:00:34Z" },
];

export const demoConnectors = [
  {
    provider: "gmail",
    name: "Gmail",
    icon: "email",
    category: "work",
    phase: 1,
    ingest_description: "Ingest email threads, extract commitments from your sent + received mail",
    write_description: "Draft and send commitment follow-up emails on your behalf (with approval)",
    oauth_configured: false,
    connected: true,
    connected_at: "2026-07-12T10:00:00Z",
    last_ingest_at: "2026-07-13T08:30:00Z",
    commitments_ingested: 142,
  },
  {
    provider: "slack",
    name: "Slack",
    icon: "message",
    category: "work",
    phase: 2,
    ingest_description: "Ingest DMs and channel mentions, extract commitments from conversations",
    write_description: "Draft and send Slack follow-up messages (with approval)",
    oauth_configured: false,
    connected: true,
    connected_at: "2026-07-12T11:00:00Z",
    last_ingest_at: "2026-07-13T08:30:00Z",
    commitments_ingested: 38,
  },
  {
    provider: "github",
    name: "GitHub",
    icon: "code",
    category: "work",
    phase: 3,
    ingest_description: "Ingest assigned issues and PRs, extract action items",
    write_description: "Draft issue comments and PR responses (with approval)",
    oauth_configured: false,
    connected: false,
    connected_at: "",
    last_ingest_at: "",
    commitments_ingested: 0,
  },
  {
    provider: "calendar",
    name: "Google Calendar",
    icon: "calendar",
    category: "work",
    phase: 4,
    ingest_description: "Ingest upcoming meetings, feed into pre-call intelligence",
    write_description: "Read-only — no write capability",
    oauth_configured: false,
    connected: false,
    connected_at: "",
    last_ingest_at: "",
    commitments_ingested: 0,
  },
  {
    provider: "whatsapp",
    name: "WhatsApp",
    icon: "chat",
    category: "social",
    phase: 6,
    ingest_description: "Ingest WhatsApp conversations (requires WhatsApp Business API approval)",
    write_description: "Draft and send WhatsApp messages (with approval)",
    oauth_configured: false,
    connected: false,
    connected_at: "",
    last_ingest_at: "",
    commitments_ingested: 0,
  },
  {
    provider: "facebook",
    name: "Facebook",
    icon: "social",
    category: "social",
    phase: 6,
    ingest_description: "Ingest Facebook messages (requires Meta app review)",
    write_description: "Draft and send Facebook messages (with approval)",
    oauth_configured: false,
    connected: false,
    connected_at: "",
    last_ingest_at: "",
    commitments_ingested: 0,
  },
  {
    provider: "instagram",
    name: "Instagram",
    icon: "social",
    category: "social",
    phase: 6,
    ingest_description: "Ingest Instagram DMs (requires Meta app review)",
    write_description: "Draft and send Instagram messages (with approval)",
    oauth_configured: false,
    connected: false,
    connected_at: "",
    last_ingest_at: "",
    commitments_ingested: 0,
  },
  {
    provider: "twitter",
    name: "Twitter / X",
    icon: "social",
    category: "social",
    phase: 6,
    ingest_description: "Ingest Twitter DMs (API access restricted since 2023)",
    write_description: "Draft and send Twitter DMs (with approval)",
    oauth_configured: false,
    connected: false,
    connected_at: "",
    last_ingest_at: "",
    commitments_ingested: 0,
  },
];

export const demoDrafts = [
  {
    draft_id: "draft-demo-001",
    provider: "gmail",
    recipient: "maria@example.com",
    subject: "Follow-up — Maria Garcia",
    body: "Hi Maria,\n\nThank you for the productive discussion. Here's what I captured:\n\nCommitments:\n  - I will send Maria Garcia the pricing proposal by Friday\n\nBased on our history:\n  - \"I will send Maria Garcia the pricing proposal by Friday\" — Maria Garcia\n\nNext steps:\n  - I'll follow up on the commitment above\n  - Let me know if I've missed anything\n\nBest,\n[Your name]",
    commitment_ref: "I will send Maria Garcia the pricing proposal by Friday",
    evidence_refs: [
      { entity: "Maria Garcia", text: "I will send Maria Garcia the pricing proposal by Friday" },
    ],
    status: "pending",
    created_at: "2026-07-13T09:30:00Z",
    resolved_at: "",
  },
  {
    draft_id: "draft-demo-002",
    provider: "slack",
    recipient: "sam-patel",
    subject: "",
    body: "Hey sam-patel — following up on our conversation. I committed to: review the PR by end of day. I'll have that to you by the agreed deadline. Let me know if anything's changed on your end.",
    commitment_ref: "Sam promised to review the PR by end of day",
    evidence_refs: [
      { entity: "Sam Patel", text: "Sam promised to review the PR by end of day" },
    ],
    status: "pending",
    created_at: "2026-07-13T09:15:00Z",
    resolved_at: "",
  },
];

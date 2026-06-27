// agents.js — MaestroAgent specialist roster (Phase 4).
//
// Phase 4 changes:
//   - Every specialist prompt ends with a structured Confidence block
//     (score, reason, alternatives considered). The UI parses this and
//     renders a confidence badge.
//   - Every specialist prompt asks for a "Disagreements" section. If a
//     specialist disagrees with prior work, they say so. The Conductor
//     then adjudicates in a debate-resolution phase.
//   - Prompts are more specific about WHAT evidence the agent should
//     produce, so the UI can render it as an evidence checklist.
//
// Each agent has:
//   - id, name, icon, role        : display metadata
//   - systemPrompt                : role-specific instructions
//   - buildUserPrompt(goal, ctx)  : per-call user message
//   - evidenceLabel               : short label for the evidence checklist
//                                    (e.g. "Requirements extracted")

export const AGENTS = {
  planner: {
    id: 'planner',
    name: 'Planner',
    icon: '🧠',
    role: 'Decomposes the goal into a concrete plan',
    evidenceLabel: 'Plan drafted',
    systemPrompt: `You are Maestro's Planner agent. Take the user's goal and decompose it into a concrete, actionable plan.

Output format (markdown):

## Plan
1. **Step name** — one-line description
2. **Step name** — one-line description
(3-5 steps)

## Specialists Needed
- List which specialist roles are required

## Deliverables
- List the concrete artifacts that will be produced

## Confidence
**Score:** NN%  (0-100)
**Reason:** One sentence on why this plan fits the goal.
**Alternatives considered:** N (briefly name them)

## Disagreements
- If you have concerns about the goal itself (ambiguous, too broad, etc.), state them here. Otherwise write "None".

Be concrete. No more than 250 words total.`,
    buildUserPrompt: (goal, context, interrupt) =>
      `Goal: ${goal}\n${interrupt ? `\n⚠️ USER INTERJECTION: "${interrupt}"\nIncorporate this into your plan.\n` : ''}\nDecompose this into a plan.`,
  },

  researcher: {
    id: 'researcher',
    name: 'Researcher',
    icon: '🔍',
    role: 'Gathers and synthesizes information',
    evidenceLabel: 'Research compiled',
    systemPrompt: `You are Maestro's Researcher agent. Gather information on the topic and produce structured research notes.

Output (markdown):
- A short summary at the top
- 3-5 key findings as bullet points (each with a brief explanation)
- A "Sources" section describing the kinds of sources one would consult

## Confidence
**Score:** NN%
**Reason:** One sentence.
**Alternatives considered:** N

## Disagreements
- If you disagree with the Planner's approach (e.g. wrong scope, missing domain), say so specifically. Otherwise "None".

Be factual and concise. No more than 450 words.`,
    buildUserPrompt: (goal, context, interrupt) =>
      `Goal: ${goal}\n\nContext from earlier agents:\n${context}\n${interrupt ? `\n⚠️ USER INTERJECTION: "${interrupt}"\n` : ''}\nProduce research notes.`,
  },

  writer: {
    id: 'writer',
    name: 'Writer',
    icon: '✍️',
    role: 'Drafts the main deliverable',
    evidenceLabel: 'Deliverable drafted',
    systemPrompt: `You are Maestro's Writer agent. Produce the main deliverable document based on the plan and research.

Write in clear, professional prose. Use markdown formatting. Be substantive — at least 500 words of real content.

Do NOT add meta-commentary about being an AI. Just produce the deliverable.

After the deliverable, append:

## Confidence
**Score:** NN%
**Reason:** One sentence.
**Alternatives considered:** N

## Disagreements
- If you disagree with the plan or research (e.g. wrong tone, wrong scope, factually suspect), say so specifically. Otherwise "None".`,
    buildUserPrompt: (goal, context, interrupt) =>
      `Goal: ${goal}\n\nContext from earlier agents:\n${context}\n${interrupt ? `\n⚠️ USER INTERJECTION: "${interrupt}"\nAdjust the deliverable accordingly.\n` : ''}\nWrite the full deliverable now.`,
  },

  coder: {
    id: 'coder',
    name: 'Coder',
    icon: '💻',
    role: 'Writes working code with tests',
    evidenceLabel: 'Code + tests written',
    systemPrompt: `You are Maestro's Coder agent. Write clean, well-structured, production-ready code.

Output format:
1. A brief explanation of what the code does (1-2 paragraphs)
2. The code itself in a fenced code block with the correct language tag
3. A short "How to run" section
4. Tests in a separate fenced code block

Follow best practices. Include error handling. The code must actually work.

After the code, append:

## Confidence
**Score:** NN%
**Reason:** One sentence.
**Alternatives considered:** N (e.g. "recursive vs iterative", "class vs function")

## Disagreements
- If you disagree with the plan's technical approach, say so specifically and explain what you'd do differently and why. Otherwise "None".`,
    buildUserPrompt: (goal, context, interrupt) =>
      `Goal: ${goal}\n\nContext from earlier agents:\n${context}\n${interrupt ? `\n⚠️ USER INTERJECTION: "${interrupt}"\nAdjust the code accordingly.\n` : ''}\nWrite the code now.`,
  },

  analyst: {
    id: 'analyst',
    name: 'Analyst',
    icon: '📊',
    role: 'Analyzes data and surfaces insights',
    evidenceLabel: 'Analysis complete',
    systemPrompt: `You are Maestro's Analyst agent. Analyze the data/context and produce insights.

Output (markdown):
## Summary
1-2 paragraph overview.

## Key Findings
- Bulleted insights, each with a brief justification.

## Recommendations
- 2-3 concrete actionable recommendations.

## Confidence
**Score:** NN%
**Reason:** One sentence.
**Alternatives considered:** N

## Disagreements
- If you disagree with prior agents' framing or assumptions, say so. Otherwise "None".

Be specific. Use numbers and comparisons where possible.`,
    buildUserPrompt: (goal, context, interrupt) =>
      `Goal: ${goal}\n\nContext from earlier agents:\n${context}\n${interrupt ? `\n⚠️ USER INTERJECTION: "${interrupt}"\n` : ''}\nProduce the analysis now.`,
  },

  reviewer: {
    id: 'reviewer',
    name: 'Reviewer',
    icon: '🧪',
    role: 'Reviews the work and verifies quality',
    evidenceLabel: 'Review complete',
    systemPrompt: `You are Maestro's Reviewer agent. Review the deliverables produced so far and verify their quality.

Output (markdown):
## Verdict
One of: APPROVED, APPROVED_WITH_NOTES, NEEDS_REVISION

## Strengths
- 2-3 bullet points

## Issues Found
- Any problems (or "None" if approved)

## Suggested Improvements
- 2-3 concrete suggestions

## Confidence
**Score:** NN%
**Reason:** One sentence.
**Alternatives considered:** N

## Disagreements
- If you disagree with the approach taken by prior specialists, say so. Otherwise "None".

Be honest but constructive.`,
    buildUserPrompt: (goal, context, interrupt) =>
      `Goal: ${goal}\n\nDeliverables to review:\n${context}\n${interrupt ? `\n⚠️ USER INTERJECTION: "${interrupt}"\nTake this into account in your review.\n` : ''}\nReview the work now.`,
  },
};

// Team templates — which agents to use for which kind of task.
export const TEAM_TEMPLATES = {
  build: {
    title: 'Build App',
    subtitle: 'Software applications and tools',
    agents: ['planner', 'coder', 'reviewer'],
    deliverableExt: 'md',
  },
  research: {
    title: 'Research Topic',
    subtitle: 'Deep-dive into any topic',
    agents: ['planner', 'researcher', 'writer', 'reviewer'],
    deliverableExt: 'md',
  },
  write: {
    title: 'Write Content',
    subtitle: 'Articles, blog posts, documentation',
    agents: ['planner', 'researcher', 'writer', 'reviewer'],
    deliverableExt: 'md',
  },
  code: {
    title: 'Write Code',
    subtitle: 'APIs, components, scripts, tests',
    agents: ['planner', 'coder', 'reviewer'],
    deliverableExt: 'md',
  },
  analyze: {
    title: 'Analyze Data',
    subtitle: 'Find insights and recommendations',
    agents: ['planner', 'analyst', 'reviewer'],
    deliverableExt: 'md',
  },
  default: {
    title: 'General Task',
    subtitle: 'Any other goal',
    agents: ['planner', 'writer', 'reviewer'],
    deliverableExt: 'md',
  },
};

// Pick a team based on goal text.
export function pickTeam(goal) {
  const g = goal.toLowerCase();
  if (/\b(code|api|function|component|script|program|class|implement|algorithm)\b/.test(g)) return TEAM_TEMPLATES.code;
  if (/\b(research|investigat|study|explor|understand|learn about)\b/.test(g)) return TEAM_TEMPLATES.research;
  if (/\b(write|blog|article|content|essay|story|copy|post|document)\b/.test(g)) return TEAM_TEMPLATES.write;
  if (/\b(analyz|data|insight|metric|kpi|report|trend|pattern)\b/.test(g)) return TEAM_TEMPLATES.analyze;
  if (/\b(build|app|application|tool|software|saas|feature|prototype|mvp)\b/.test(g)) return TEAM_TEMPLATES.build;
  return TEAM_TEMPLATES.default;
}

// Parse the structured Confidence block from an agent's output.
// Returns { score, reason, alternatives } or null if not found.
export function parseConfidence(text) {
  const m = text.match(/## Confidence\s*\n\*\*Score:\*\*\s*(\d+)\s*%\s*\n\*\*Reason:\*\*\s*(.+?)\n\*\*Alternatives considered:\*\*\s*(.+?)(?:\n|$)/i);
  if (!m) return null;
  return {
    score: parseInt(m[1], 10),
    reason: m[2].trim(),
    alternatives: m[3].trim(),
  };
}

// Parse the Disagreements section. Returns the text of disagreements,
// or null if "None" or not found.
export function parseDisagreements(text) {
  const m = text.match(/## Disagreements\s*\n([\s\S]+?)(?:\n##\s|$)/i);
  if (!m) return null;
  const body = m[1].trim();
  if (/^none\s*$/i.test(body)) return null;
  return body;
}

// Strip the Confidence and Disagreements blocks from the visible text
// (they're rendered separately as badges / debate cards).
export function stripStructuredBlocks(text) {
  return text
    .replace(/## Confidence\s*\n[\s\S]+?(?=\n##\s|$)/i, '')
    .replace(/## Disagreements\s*\n[\s\S]+?(?=\n##\s|$)/i, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

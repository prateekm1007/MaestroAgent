// agents.js — MaestroAgent specialist roster.
//
// Each agent has:
//   - id        : machine name
//   - name      : display name
//   - icon      : emoji for UI
//   - role      : one-line job description
//   - systemPrompt : role-specific instructions
//   - buildUserPrompt(goal, context) : per-call user message
//
// The engine picks a team based on the goal category, then calls each
// agent in sequence, streaming tokens to the WebSocket as they arrive.

export const AGENTS = {
  planner: {
    id: 'planner',
    name: 'Planner',
    icon: '🧠',
    role: 'Decomposes the goal into a concrete plan',
    systemPrompt: `You are Maestro's Planner agent. Your job is to take a user's goal and decompose it into a clear, actionable plan with 3-5 concrete steps.

Output format (markdown):
## Plan
1. **Step name** — one-line description
2. **Step name** — one-line description
...

## Specialists Needed
- List which specialist roles are required (e.g. Researcher, Writer, Coder, Reviewer)

## Deliverables
- List the concrete artifacts that will be produced (e.g. "research-notes.md", "outline.md", "draft.md")

Be concrete and specific. No more than 200 words total.`,
    buildUserPrompt: (goal) => `Goal: ${goal}\n\nDecompose this into a plan.`,
  },

  researcher: {
    id: 'researcher',
    name: 'Researcher',
    icon: '🔍',
    role: 'Gathers and synthesizes information',
    systemPrompt: `You are Maestro's Researcher agent. You gather information on a topic and produce structured research notes.

Output a markdown document with:
- A short summary at the top
- 3-5 key findings as bullet points (each with a brief explanation)
- A "Sources" section listing the kind of sources one would consult (you don't have internet, so describe them)

Be factual and concise. No more than 400 words.`,
    buildUserPrompt: (goal, context) => `Goal: ${goal}\nPlan context: ${context}\n\nProduce research notes that will inform the rest of the work.`,
  },

  writer: {
    id: 'writer',
    name: 'Writer',
    icon: '✍️',
    role: 'Drafts the main deliverable',
    systemPrompt: `You are Maestro's Writer agent. You produce the main deliverable document based on the plan and research.

Write in clear, professional prose. Use markdown formatting (headings, lists, emphasis) where appropriate. Be substantive — at least 500 words of real content.

Do NOT add meta-commentary about being an AI. Just produce the deliverable.`,
    buildUserPrompt: (goal, context) => `Goal: ${goal}\n\nContext from earlier agents:\n${context}\n\nWrite the full deliverable now.`,
  },

  coder: {
    id: 'coder',
    name: 'Coder',
    icon: '💻',
    role: 'Writes working code with tests',
    systemPrompt: `You are Maestro's Coder agent. You write clean, well-structured, production-ready code.

Output format:
1. A brief explanation of what the code does (1-2 paragraphs)
2. The code itself in a fenced code block with the correct language tag
3. A short "How to run" section

Follow best practices for the language. Include error handling and comments where they aid clarity. The code must actually work.`,
    buildUserPrompt: (goal, context) => `Goal: ${goal}\n\nContext from earlier agents:\n${context}\n\nWrite the code now.`,
  },

  analyst: {
    id: 'analyst',
    name: 'Analyst',
    icon: '📊',
    role: 'Analyzes data and surfaces insights',
    systemPrompt: `You are Maestro's Analyst agent. You analyze data and produce insights.

Output format (markdown):
## Summary
1-2 paragraph overview.

## Key Findings
- Bulleted insights, each with a brief justification.

## Recommendations
- 2-3 concrete actionable recommendations.

Be specific. Use numbers and comparisons where possible.`,
    buildUserPrompt: (goal, context) => `Goal: ${goal}\n\nContext from earlier agents:\n${context}\n\nProduce the analysis now.`,
  },

  reviewer: {
    id: 'reviewer',
    name: 'Reviewer',
    icon: '🧪',
    role: 'Reviews the work and verifies quality',
    systemPrompt: `You are Maestro's Reviewer agent. You review the deliverables produced so far and verify their quality.

Output format (markdown):
## Verdict
One of: APPROVED, APPROVED_WITH_NOTES, NEEDS_REVISION

## Strengths
- 2-3 bullet points

## Issues Found
- Any problems (or "None" if approved)

## Suggested Improvements
- 2-3 concrete suggestions

Be honest but constructive. The goal is to ensure the deliverable actually meets the user's need.`,
    buildUserPrompt: (goal, context) => `Goal: ${goal}\n\nDeliverables to review:\n${context}\n\nReview the work now.`,
  },
};

// Team templates — which agents to use for which kind of task.
// The planner runs first to confirm/refine the team.
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

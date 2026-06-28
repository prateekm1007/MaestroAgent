// conductor.js — Maestro's Conductor agent.
//
// The Conductor is the real cognition layer. It doesn't produce artifacts —
// it produces VISIBLE REASONING that streams to the user as narration.
//
// Responsibilities:
//   1. Examine the goal and explain what it sees (phase: "examine")
//   2. Pick the team and explain WHY each specialist is needed (phase: "assemble")
//   3. Before each specialist runs, hand off with context (phase: "handoff")
//   4. After all specialists complete, review disagreements and adjudicate (phase: "resolve")
//   5. Produce a final summary with overall confidence (phase: "summarize")
//
// Every call is a real LLM call via z-ai-web-dev-sdk. The output streams
// token-by-token to the user. This is NOT scripted narration — the model
// actually reads the goal/context and reasons about it.

import ZAI from 'z-ai-web-dev-sdk';
import { complete as llmComplete } from './llm/router.js';

// Shared ZAI instance (cheap to reuse).
let _zai = null;
async function getZAI() {
  if (!_zai) _zai = await ZAI.create();
  return _zai;
}

// Stream a conductor call. Returns the full text.
// Stream a conductor call via the multi-provider router.
async function streamConductor({ system, user, onToken }) {
  const response = await llmComplete({ system, user, stream: true, onToken });
  return response.text;
}

const CONDUCTOR_SYSTEM = `You are Maestro's Conductor — the orchestration intelligence visible to the user.

Your output is streamed directly to the user as it's generated. You are NOT producing an artifact. You are THINKING OUT LOUD about how to approach the work.

Rules:
- Be conversational and brief. 2-4 sentences per call unless asked for more.
- Reference the SPECIFIC goal and context — never generic.
- When explaining a decision, give the REASON, not just the conclusion.
- When picking specialists, explain what each one will contribute.
- When handing off to a specialist, say what they should focus on.
- When adjudicating a disagreement, explain the tradeoff and your call.
- Never say "as an AI" or "I cannot" — you ARE the conductor.
- Don't use markdown headings. Just plain conversational text.`;

// Phase 1: Examine the goal and narrate initial thinking.
// If past learning context is provided, the conductor references it —
// this is how past projects make the next project better.
export async function conductorExamine(goal, { onToken }, pastLearningContext = '') {
  const pastBlock = pastLearningContext
    ? `\n\n--- Past projects that are similar to this goal ---\n${pastLearningContext}\n---\n\nReference these past projects if they're relevant. If a past project succeeded, mention what worked. If one failed or was rejected, mention what to avoid. If none are truly relevant, ignore them. Be honest — don't force a connection that isn't there.`
    : '';
  return streamConductor({
    system: CONDUCTOR_SYSTEM + '\n\nRight now you are EXAMINING the user\'s goal for the first time. Read it carefully and think out loud about what kind of work this is, what the main challenges are, and what approach makes sense. 3-5 sentences.' + pastBlock,
    user: `User's goal: "${goal}"\n\nThink out loud about this goal.`,
    onToken,
  });
}

// Phase 2: Pick the team and explain why.
export async function conductorAssemble(goal, team, { onToken }) {
  const teamList = team.agents.map(id => {
    const a = AGENT_LOOKUP[id];
    return `- ${a.name} (${a.icon}) — ${a.role}`;
  }).join('\n');
  return streamConductor({
    system: CONDUCTOR_SYSTEM + '\n\nRight now you are ASSEMBLING the team. You\'ve decided on the specialists above. Explain to the user why this team is the right fit for their goal. 2-4 sentences.',
    user: `Goal: "${goal}"\n\nTeam I'm assembling:\n${teamList}\n\nExplain why this team.`,
    onToken,
  });
}

// Phase 3: Hand off to a specialist with context.
export async function conductorHandoff(goal, agent, context, step, totalSteps, { onToken }) {
  return streamConductor({
    system: CONDUCTOR_SYSTEM + '\n\nRight now you are HANDING OFF to the next specialist. Briefly say what they\'re going to do and why, in the context of the work so far. 1-2 sentences max.',
    user: `Goal: "${goal}"\n\nWork so far (summary):\n${context.slice(-2000)}\n\nNext specialist: ${agent.name} (${agent.role}).\nStep ${step} of ${totalSteps}.\n\nHand off to them.`,
    onToken,
  });
}

// Phase 4: Adjudicate disagreements.
// If there are no disagreements, returns null (don't call the LLM).
export async function conductorResolve(goal, disagreements, context, { onToken }) {
  if (!disagreements || disagreements.length === 0) return null;
  const disputeText = disagreements.map(d =>
    `**${d.agentName}** disagrees:\n${d.text}`
  ).join('\n\n---\n\n');
  return streamConductor({
    system: CONDUCTOR_SYSTEM + '\n\nRight now you are RESOLVING DISAGREEMENTS between your specialists. For each disagreement, explain the tradeoff and make a call. Be decisive but fair. Reference the specific goal.',
    user: `Goal: "${goal}"\n\nDisagreements raised:\n${disputeText}\n\nFull context:\n${context.slice(-3000)}\n\nResolve each disagreement. Explain your reasoning.`,
    onToken,
  });
}

// Phase 5: Final summary with overall confidence.
export async function conductorSummarize(goal, artifacts, avgConfidence, { onToken }) {
  const artifactList = artifacts.map(a => `- ${a.filename} (${a.bytes} bytes) by ${a.agent_name}`).join('\n');
  return streamConductor({
    system: CONDUCTOR_SYSTEM + '\n\nRight now you are WRAPPING UP. Summarize what was produced, call out the most important deliverable, and give an overall confidence assessment. 3-5 sentences.',
    user: `Goal: "${goal}"\n\nArtifacts produced:\n${artifactList}\n\nAverage specialist confidence: ${avgConfidence}%\n\nWrap up the run.`,
    onToken,
  });
}

// Phase 6: LEARN — extract lessons from the completed run.
//
// This is the most important conductor call. It runs AFTER the user-facing
// summarize phase, and its output is NOT shown to the user. Instead, it's
// stored as a Learning Object and used to improve future runs.
//
// The constitutional principle: "Every completed project must make Maestro
// measurably better." This function is what makes that true.
//
// Returns structured lessons: what worked, what to do differently next time,
// and any workflow-level patterns to remember.
export async function conductorLearn(goal, team, context, disagreements, avgConfidence, { onToken }) {
  const teamList = team.agents.map(id => {
    const a = AGENT_LOOKUP[id];
    return `- ${a.name}: ${a.role}`;
  }).join('\n');
  const disagreementSummary = disagreements.length > 0
    ? `\nDisagreements raised: ${disagreements.length}\n${disagreements.map(d => `- ${d.agentName}: ${d.text.slice(0, 200)}`).join('\n')}`
    : '\nNo disagreements were raised — team was aligned.';

  return streamConductor({
    system: `You are Maestro's learning system. A project just completed. Your job is to extract lessons that will make the NEXT similar project better.

Output format (be concise — this is for machine storage, not human reading):

WHAT WORKED:
- 1-3 bullet points on what went well in this workflow.

WHAT TO DO DIFFERENTLY NEXT TIME:
- 1-3 bullet points on what could be improved. If nothing, write "Nothing notable."

WORKFLOW PATTERN:
- One sentence summarizing the workflow template that emerged (e.g. "For [goal type X], use [team Y] with focus on [Z].")

CONFIDENCE CALIBRATION NOTE:
- One sentence on whether the predicted confidence (${avgConfidence ?? 'unknown'}%) felt right, too high, or too low based on the output quality.

Be honest. These lessons are stored and retrieved for future projects with similar goals. Vague lessons are useless; specific lessons compound.`,
    user: `Goal: ${goal}\n\nTeam:\n${teamList}${disagreementSummary}\n\nFull work output (compressed):\n${context.slice(-4000)}\n\nExtract lessons for future similar projects.`,
    onToken,
  });
}

// Lookup table for agent metadata (avoids circular import).
import { AGENTS as AGENT_LOOKUP } from './agents.js';

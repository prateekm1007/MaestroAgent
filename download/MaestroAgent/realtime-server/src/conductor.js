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

// Shared ZAI instance (cheap to reuse).
let _zai = null;
async function getZAI() {
  if (!_zai) _zai = await ZAI.create();
  return _zai;
}

// Stream a conductor call. Returns the full text.
// onToken(delta) is called for every token.
// Same SSE-parsing logic as the specialist streamLLM in engine.js.
// Retries on 429 (rate limit) with exponential backoff.
async function streamConductor({ system, user, onToken }) {
  const zai = await getZAI();
  const messages = [
    { role: 'assistant', content: system },
    { role: 'user', content: user },
  ];

  let lastErr = null;
  for (let attempt = 0; attempt < 4; attempt++) {
    try {
      const stream = await zai.chat.completions.create({
        messages,
        stream: true,
        thinking: { type: 'disabled' },
      });
      let full = '';
      let buffer = '';
      for await (const rawChunk of stream) {
        let text;
        if (rawChunk instanceof Uint8Array || ArrayBuffer.isView(rawChunk)) {
          text = Buffer.from(rawChunk).toString('utf8');
        } else if (typeof rawChunk === 'string') {
          text = rawChunk;
        } else if (rawChunk?.choices?.[0]?.delta?.content) {
          const delta = rawChunk.choices[0].delta.content;
          full += delta;
          if (onToken) onToken(delta);
          continue;
        } else {
          continue;
        }
        buffer += text;
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith('data:')) continue;
          const payload = trimmed.slice(5).trim();
          if (payload === '[DONE]') continue;
          try {
            const obj = JSON.parse(payload);
            const delta = obj?.choices?.[0]?.delta?.content || '';
            if (delta) {
              full += delta;
              if (onToken) onToken(delta);
            }
          } catch {}
        }
      }
      if (buffer.trim().startsWith('data:')) {
        const payload = buffer.trim().slice(5).trim();
        if (payload && payload !== '[DONE]') {
          try {
            const obj = JSON.parse(payload);
            const delta = obj?.choices?.[0]?.delta?.content || '';
            if (delta) {
              full += delta;
              if (onToken) onToken(delta);
            }
          } catch {}
        }
      }
      return full;
    } catch (err) {
      lastErr = err;
      // 429 = rate limited. Back off and retry.
      if (String(err.message || '').includes('429') && attempt < 3) {
        const wait = Math.pow(2, attempt + 2) * 1000; // 4s, 8s, 16s
        console.warn(`[conductor] 429 rate limited, retrying in ${wait/1000}s (attempt ${attempt+1}/3)`);
        await new Promise(r => setTimeout(r, wait));
        continue;
      }
      throw err;
    }
  }
  throw lastErr || new Error('conductor stream failed');
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
export async function conductorExamine(goal, { onToken }) {
  return streamConductor({
    system: CONDUCTOR_SYSTEM + '\n\nRight now you are EXAMINING the user\'s goal for the first time. Read it carefully and think out loud about what kind of work this is, what the main challenges are, and what approach makes sense. 3-5 sentences.',
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

// Lookup table for agent metadata (avoids circular import).
import { AGENTS as AGENT_LOOKUP } from './agents.js';

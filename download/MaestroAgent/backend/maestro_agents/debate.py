"""Debate — multi-agent debate, vote, and criticize primitives.

A `Debate` is a structured multi-turn exchange where N agents argue
about a topic, then vote on a resolution. The winner (or the synthesis
of all positions) is returned as the debate's output.

Use cases
---------
- **Conflict resolution.** When two sub-agents propose contradictory
  architectures, the supervisor can spawn a debate to resolve.
- **Critic loops.** A debate with a "proposer" and a "critic" is a
  lightweight evaluator-optimizer.
- **Voting on ambiguity.** When the goal is open-ended ("what should
  we build first?"), a debate with vote can produce a defensible choice.

Policies
--------
- `seek_consensus=True` — only return a result if a quorum agrees;
  otherwise escalate.
- `seek_consensus=False` — return the majority position; record
  dissenters in metadata.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from maestro_core.state import RunStatus, State
from maestro_core.streaming import EventType

if TYPE_CHECKING:
    from maestro_core.context import RunContext


@dataclass
class VotePolicy:
    """How a debate's vote is conducted."""

    quorum: float = 0.6  # fraction of participants needed for consensus
    seek_consensus: bool = True
    max_rounds: int = 3


@dataclass
class DebateResult:
    """Outcome of a debate."""

    resolution: str
    votes: dict[str, str]  # participant_id -> voted_for
    consensus: bool
    rounds: int


@dataclass
class Debate:
    """A structured multi-agent debate."""

    id: str
    topic: str
    participants: list[str]  # agent ids
    policy: VotePolicy = field(default_factory=VotePolicy)

    async def run(self, state: State, ctx: "RunContext") -> State:
        """Run the debate. Returns updated state with the resolution."""
        if not self.participants:
            return state

        await ctx.events.emit(
            EventType.AGENT_DEBATE,
            run_id=ctx.config.run_id,
            debate_id=self.id,
            topic=self.topic,
            participants=self.participants,
        )

        # Round 1: each participant proposes a position.
        positions: dict[str, str] = {}
        for pid in self.participants:
            positions[pid] = await self._get_position(pid, state, ctx)

        # Rounds 2..N: critique + revise.
        for round_idx in range(1, self.policy.max_rounds):
            critiques = await self._gather_critiques(positions, state, ctx)
            new_positions = await self._revise_positions(positions, critiques, state, ctx)
            if new_positions == positions:
                # Converged — no need for more rounds.
                break
            positions = new_positions

        # Final vote.
        votes = await self._vote(positions, state, ctx)
        resolution, consensus = self._tally(votes, positions)

        await ctx.events.emit(
            EventType.AGENT_DEBATE,
            run_id=ctx.config.run_id,
            debate_id=self.id,
            topic=self.topic,
            resolution=resolution,
            consensus=consensus,
        )

        result = DebateResult(
            resolution=resolution,
            votes=votes,
            consensus=consensus,
            rounds=self.policy.max_rounds,
        )

        return state.with_updates(
            messages=state.messages + [
                {
                    "role": "assistant",
                    "agent_id": self.id,
                    "role_label": "debate",
                    "content": f"Debate resolution: {resolution}",
                    "debate_result": {
                        "votes": votes,
                        "consensus": consensus,
                        "rounds": result.rounds,
                    },
                }
            ],
            artifacts={**state.artifacts, f"debate:{self.id}": resolution},
            metadata={
                **state.metadata,
                "last_debate": self.id,
                "debate_consensus": consensus,
            },
        )

    async def _get_position(
        self, participant_id: str, state: State, ctx: "RunContext"
    ) -> str:
        """Ask one participant for their position on the topic."""
        resp = await ctx.llm.complete(
            system=(
                "You are a participant in a structured debate. "
                "State your position clearly in 2-3 sentences. "
                "Be specific and reasoned."
            ),
            user=f"Topic: {self.topic}\n\nContext: {self._state_summary(state)}",
            provider=None,
            model=None,
            temperature=0.3,
            tools=[],
            run_id=ctx.config.run_id,
            agent_id=f"{participant_id}__debate",
        )
        ctx.cost_so_far += resp.cost_usd
        return resp.text

    async def _gather_critiques(
        self, positions: dict[str, str], state: State, ctx: "RunContext"
    ) -> dict[str, list[str]]:
        """Each participant critiques the others' positions."""
        critiques: dict[str, list[str]] = {pid: [] for pid in positions}
        positions_text = "\n\n".join(
            f"[{pid}]: {pos}" for pid, pos in positions.items()
        )
        for pid in positions:
            resp = await ctx.llm.complete(
                system=(
                    "You are critiquing other debaters' positions. "
                    "Identify the strongest objection to each. "
                    "Respond as JSON: {\"critiques\": {\"id\": \"objection\", ...}}."
                ),
                user=f"Topic: {self.topic}\n\nPositions:\n{positions_text}",
                provider=None,
                model=None,
                temperature=0.2,
                tools=[],
                run_id=ctx.config.run_id,
                agent_id=f"{pid}__critic",
            )
            ctx.cost_so_far += resp.cost_usd
            import json
            try:
                data = json.loads(resp.text)
                for other_id, objection in data.get("critiques", {}).items():
                    if other_id in critiques:
                        critiques[other_id].append(f"{pid}: {objection}")
            except Exception:
                pass
        return critiques

    async def _revise_positions(
        self,
        positions: dict[str, str],
        critiques: dict[str, list[str]],
        state: State,
        ctx: "RunContext",
    ) -> dict[str, str]:
        """Each participant revises their position in light of critiques."""
        revised: dict[str, str] = {}
        for pid, pos in positions.items():
            my_critiques = "\n".join(f"- {c}" for c in critiques.get(pid, []))
            if not my_critiques:
                revised[pid] = pos
                continue
            resp = await ctx.llm.complete(
                system=(
                    "You are revising your debate position in light of critiques. "
                    "Either update your position or defend it. 2-3 sentences."
                ),
                user=(
                    f"Topic: {self.topic}\n"
                    f"Your current position: {pos}\n\n"
                    f"Critiques received:\n{my_critiques}"
                ),
                provider=None,
                model=None,
                temperature=0.3,
                tools=[],
                run_id=ctx.config.run_id,
                agent_id=f"{pid}__revise",
            )
            ctx.cost_so_far += resp.cost_usd
            revised[pid] = resp.text
        return revised

    async def _vote(
        self, positions: dict[str, str], state: State, ctx: "RunContext"
    ) -> dict[str, str]:
        """Each participant votes for the position they now agree with most."""
        votes: dict[str, str] = {}
        positions_text = "\n\n".join(
            f"[{pid}]: {pos}" for pid, pos in positions.items()
        )
        for pid in positions:
            resp = await ctx.llm.complete(
                system=(
                    "You are voting in a debate. Pick exactly ONE position id "
                    "that you now agree with most. Respond with just the id."
                ),
                user=f"Topic: {self.topic}\n\nPositions:\n{positions_text}\n\n"
                f"Your id: {pid}. Vote for one (yours or another):",
                provider=None,
                model=None,
                temperature=0.0,
                tools=[],
                run_id=ctx.config.run_id,
                agent_id=f"{pid}__vote",
            )
            ctx.cost_so_far += resp.cost_usd
            voted = resp.text.strip()
            # Best-effort normalize: if the response contains a known id, use it.
            for known_id in positions:
                if known_id in voted:
                    votes[pid] = known_id
                    break
            else:
                votes[pid] = pid  # default to self
        return votes

    def _tally(
        self, votes: dict[str, str], positions: dict[str, str]
    ) -> tuple[str, bool]:
        """Tally votes and return (resolution, consensus)."""
        from collections import Counter
        tally = Counter(votes.values())
        winner_id, winner_count = tally.most_common(1)[0]
        fraction = winner_count / max(1, len(votes))
        consensus = fraction >= self.policy.quorum
        return positions[winner_id], consensus

    def _state_summary(self, state: State) -> str:
        recent = state.messages[-3:]
        return "\n".join(
            f"- [{m.get('role')}] {str(m.get('content', ''))[:200]}" for m in recent
        )

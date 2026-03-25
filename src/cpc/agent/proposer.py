"""Proposer: runs Phase 2 of the MHNG protocol.

Works with any CPCAgent implementation — the agent autonomously handles
the full generative + inference cycle:
  Generation: w -> z -> a -> o
  Inference:  o -> z' -> w'
"""

from __future__ import annotations

from cpc.agent.base import CPCAgent, ProposalOutput
from cpc.models import Proposal


async def run_propose(
    agent: CPCAgent,
    w_current: str,
    task_description: str,
    agent_id: str,
) -> tuple[Proposal, ProposalOutput]:
    """Execute one full propose cycle using any CPCAgent.

    The agent autonomously decides how to investigate and what to propose.
    We only receive the output: proposed_w, reasoning (z'), observations (o).
    """
    output = await agent.propose(w_current, task_description)

    proposal = Proposal(
        agent_id=agent_id,
        current_w=w_current,
        proposed_w=output.proposed_w,
        observation_summary=output.observation_summary,
        reasoning=output.reasoning,
    )

    return proposal, output

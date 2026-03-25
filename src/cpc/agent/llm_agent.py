"""LLM API agent: wraps a raw LLM API + Sandbox into the CPCAgent interface.

This is the "step-by-step" agent where the platform controls each
CPC step (interpret, design_experiment, execute, update, write).
"""

from __future__ import annotations

from cpc.agent.base import CPCAgent, ProposalOutput, ReviewScore
from cpc.agent.claude_api import ClaudeAPI
from cpc.sandbox.base import Sandbox


class LLMAgent(CPCAgent):
    """CPC agent backed by a raw LLM API with explicit sandbox."""

    def __init__(self, claude: ClaudeAPI, sandbox: Sandbox, specialization: str = "") -> None:
        self._claude = claude
        self._sandbox = sandbox
        self._specialization = specialization
        # Cached from last propose (used for review scoring)
        self._last_z: str = ""
        self._last_o: str = ""

    async def propose(self, w_current: str, task_description: str) -> ProposalOutput:
        await self._sandbox.setup()
        try:
            z = self._claude.interpret(w_current, task_description, self._specialization)
            a = self._claude.design_experiment(z, task_description)
            o = await self._sandbox.execute(a)
            z_prime = self._claude.update_hypothesis(z, o, w_current)
            w_prime = self._claude.write_proposal(w_current, z_prime, o)
        finally:
            await self._sandbox.teardown()

        self._last_z = z_prime
        self._last_o = o

        return ProposalOutput(
            proposed_w=w_prime,
            reasoning=z_prime,
            observation_summary=o[:2000],
        )

    async def score(self, w: str, task_description: str) -> ReviewScore:
        s = self._claude.score_consistency(w, self._last_z, self._last_o)
        return ReviewScore(score=s)

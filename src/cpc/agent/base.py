"""Abstract base for CPC agents.

From the CPC platform's perspective, an agent only needs to do two things:

1. **Propose**: Given current shared knowledge w, autonomously investigate
   and produce a proposal w' along with reasoning z and observations o.
   Internally, the agent may do anything — call LLM APIs, use tools,
   read/write files, run tests, browse the web, etc. The platform does
   not prescribe how. It only cares about the output.

2. **Score**: Given a document w, evaluate its consistency with the agent's
   own hypothesis z and observations o. Returns a score 0-100 for the
   MH acceptance ratio computation.

This abstraction allows any agent to participate in CPC:
  - Raw LLM API calls (ClaudeAPI, OpenAI, Gemini, Ollama)
  - Coding agents (Claude Code, Cursor, Aider, Devin)
  - Human researchers (via a UI that collects proposals and scores)
  - Hybrid systems (agent + human review)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ProposalOutput:
    """Output of an agent's propose step.

    CPC variables:
      proposed_w:           w' ~ q(w | z^k')
      reasoning:            z^k' (the agent's updated hypothesis)
      observation_summary:  o^k (what the agent observed)
    """

    proposed_w: str
    reasoning: str
    observation_summary: str


@dataclass
class ReviewScore:
    """Output of an agent's scoring step.

    Used to compute MH acceptance ratio:
      α = min(1, p(z^B | w') / p(z^B | w_current))
    approximated via:
      α ≈ min(1, exp(logit(score_proposed) - logit(score_current)))
    """

    score: float  # 0-100 consistency score
    reasoning: str = ""


class CPCAgent(ABC):
    """Abstract base class for any CPC-participating agent.

    Subclass this to plug in any agent system — from a simple LLM API
    wrapper to a full coding agent like Claude Code.
    """

    @abstractmethod
    async def propose(self, w_current: str, task_description: str) -> ProposalOutput:
        """Autonomously investigate and produce a proposal.

        The agent receives:
          - w_current: the current shared knowledge document
          - task_description: what to investigate

        The agent should:
          1. Interpret w_current (form hypothesis z)
          2. Design and run experiments (choose actions a, observe o)
          3. Update hypothesis with observations (z -> z')
          4. Write a proposed update to the shared document (w')

        How it does this internally is entirely up to the agent.
        It may call LLM APIs, execute shell commands, read files,
        run tests, use MCP tools, etc.

        Returns ProposalOutput with the proposed w', reasoning, and observations.
        """
        ...

    @abstractmethod
    async def score(self, w: str, task_description: str) -> ReviewScore:
        """Score how consistent a document is with this agent's findings.

        Used during the review phase to compute MH acceptance probability.
        The agent should evaluate how well the given document w aligns
        with its own hypothesis (z) and observations (o) from the
        most recent propose step.

        Returns a score from 0 (completely inconsistent) to 100 (perfect).
        """
        ...

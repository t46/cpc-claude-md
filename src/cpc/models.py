"""Core data models for the CPC platform.

CPC variable correspondence:
  w     -> Sample.content (shared external representation)
  z^k   -> Proposal.reasoning (agent's internal representation)
  o^k   -> Proposal.observation_summary (experiment results)
  θ^k   -> AgentRegistration.specialization + system_prompt
  a^k   -> Commands executed in sandbox (not stored explicitly)
  d     -> TaskDefinition
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _short_id() -> str:
    return uuid4().hex[:12]


class RoundPhase(str, Enum):
    PULL = "pull"
    PROPOSE = "propose"
    REVIEW = "review"
    UPDATE = "update"
    COMPLETED = "completed"


@dataclass
class TaskDefinition:
    """d — the research target."""

    task_id: str
    description: str
    initial_w: str = ""
    docker_image: str = "python:3.12-slim"
    max_rounds: int = 100
    convergence_threshold: float = 0.05
    agent_specializations: list[str] = field(default_factory=list)


@dataclass
class AgentRegistration:
    """θ^k — agent-specific parameters."""

    agent_id: str
    specialization: str = ""
    system_prompt_hash: str = ""
    registered_at: datetime = field(default_factory=_now)
    last_seen_at: datetime = field(default_factory=_now)


@dataclass
class Proposal:
    """w' — a proposed update to the shared document.

    Contains the agent's proposal (w'), observation summary (o^k),
    and reasoning (z^k') from one experiment-propose cycle.
    """

    proposal_id: str = field(default_factory=_short_id)
    agent_id: str = ""
    round_index: int = 0
    current_w: str = ""
    proposed_w: str = ""
    observation_summary: str = ""
    reasoning: str = ""
    created_at: datetime = field(default_factory=_now)


@dataclass
class ReviewResult:
    """Result of MHNG acceptance step.

    The reviewer scores consistency of their own z^B against both
    w_proposed and w_current, then computes the MH acceptance ratio.
    """

    review_id: str = field(default_factory=_short_id)
    proposal_id: str = ""
    reviewer_id: str = ""
    round_index: int = 0
    accepted: bool = False
    score_proposed: float = 0.0
    score_current: float = 0.0
    log_alpha: float = 0.0
    reasoning: str = ""
    created_at: datetime = field(default_factory=_now)


@dataclass
class Sample:
    """A single Monte Carlo sample of w.

    The collection {w^[1], ..., w^[I]} approximates the posterior
    q(w | o^1, ..., o^K) ≈ p(w | o^1, ..., o^K).
    """

    sample_id: str = field(default_factory=_short_id)
    content: str = ""
    round_index: int = 0
    proposer_id: str = ""
    reviewer_id: str = ""
    accepted: bool = False
    acceptance_score: float = 0.0
    created_at: datetime = field(default_factory=_now)


@dataclass
class Pairing:
    """A proposer-reviewer pair for one MHNG step."""

    proposer_id: str
    reviewer_id: str
    proposal_id: str = ""


@dataclass
class Round:
    """State for a single MHNG round."""

    round_index: int
    task_id: str = ""
    phase: RoundPhase = RoundPhase.PULL
    frozen_w: str = ""
    proposals: list[Proposal] = field(default_factory=list)
    pairings: list[Pairing] = field(default_factory=list)
    reviews: list[ReviewResult] = field(default_factory=list)
    started_at: datetime = field(default_factory=_now)
    completed_at: datetime | None = None


@dataclass
class ConvergenceDiagnostics:
    """Tracking statistics for MCMC convergence."""

    round_index: int
    acceptance_rate: float
    cumulative_acceptance_rate: float
    sample_count: int
    recent_sample_similarity: float = 0.0

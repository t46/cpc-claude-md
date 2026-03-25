"""Reviewer: runs Phase 4 of the MHNG protocol.

Computes the Metropolis-Hastings acceptance probability α using
scoring approximation (Method B):

  α = min(1, p(z^B | w') / p(z^B | w_current))

where p(z^B | w) is approximated by an agent's consistency score
transformed via logit function.

Works with any CPCAgent implementation.
"""

from __future__ import annotations

import math
import random

from cpc.agent.base import CPCAgent
from cpc.models import ReviewResult

# Small epsilon to prevent log(0) in logit transform
_EPSILON = 0.5


def _logit(score: float) -> float:
    """Logit transform: maps [0, 100] -> (-inf, +inf).

    logit(s) = log(s / (100 - s + ε))

    This transforms bounded consistency scores into log-probability-like
    quantities suitable for computing MH acceptance ratios.
    """
    s = max(_EPSILON, min(100 - _EPSILON, score))
    return math.log(s / (100.0 - s + _EPSILON))


async def compute_acceptance(
    agent: CPCAgent,
    w_proposed: str,
    w_current: str,
    task_description: str,
) -> tuple[bool, float, float, float]:
    """Compute MH acceptance decision using any CPCAgent.

    Returns (accepted, score_proposed, score_current, log_alpha).
    """
    # Score consistency of agent's findings with proposed w'
    result_proposed = await agent.score(w_proposed, task_description)
    score_proposed = result_proposed.score

    # Score consistency of agent's findings with current w
    result_current = await agent.score(w_current, task_description)
    score_current = result_current.score

    # Compute MH acceptance ratio via logit transform
    log_alpha = _logit(score_proposed) - _logit(score_current)
    alpha = min(1.0, math.exp(min(log_alpha, 700)))  # Clamp to prevent overflow

    # Accept with probability alpha
    u = random.random()
    accepted = u < alpha

    return accepted, score_proposed, score_current, log_alpha


async def run_review(
    agent: CPCAgent,
    proposal_id: str,
    w_proposed: str,
    w_current: str,
    reviewer_id: str,
    task_description: str,
    round_index: int = 0,
) -> ReviewResult:
    """Execute one review step of the MHNG protocol.

    The reviewing agent uses its own internal hypothesis (z^B) and
    observations (o^B) — retained from its most recent propose step —
    to evaluate the proposal w' against the current w.
    """
    accepted, score_proposed, score_current, log_alpha = await compute_acceptance(
        agent=agent,
        w_proposed=w_proposed,
        w_current=w_current,
        task_description=task_description,
    )

    return ReviewResult(
        proposal_id=proposal_id,
        reviewer_id=reviewer_id,
        round_index=round_index,
        accepted=accepted,
        score_proposed=score_proposed,
        score_current=score_current,
        log_alpha=log_alpha,
        reasoning=f"scores: proposed={score_proposed:.1f}, current={score_current:.1f}, "
        f"log_alpha={log_alpha:.3f}, accepted={accepted}",
    )

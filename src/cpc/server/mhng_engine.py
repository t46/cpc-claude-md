"""MHNG (Metropolis-Hastings Naming Game) engine.

Orchestrates the distributed Bayesian inference protocol:
  1. Freeze w^{[i-1]} for the round
  2. Collect proposals from agents
  3. Create random pairings (proposer, reviewer)
  4. Collect review results (accept/reject)
  5. Update sample store with results
"""

from __future__ import annotations

import random
from datetime import datetime, timezone

from cpc.models import (
    AgentRegistration,
    ConvergenceDiagnostics,
    Pairing,
    Proposal,
    ReviewResult,
    Round,
    RoundPhase,
    Sample,
    TaskDefinition,
)
from cpc.server.sample_store import SampleStore


class MHNGEngine:
    def __init__(self, sample_store: SampleStore) -> None:
        self._store = sample_store
        self._tasks: dict[str, TaskDefinition] = {}
        self._agents: dict[str, AgentRegistration] = {}
        self._rounds: dict[str, list[Round]] = {}  # task_id -> rounds

    # --- Task management ---

    def register_task(self, task: TaskDefinition) -> None:
        self._tasks[task.task_id] = task
        self._rounds[task.task_id] = []

    def get_task(self, task_id: str) -> TaskDefinition | None:
        return self._tasks.get(task_id)

    # --- Agent management ---

    def register_agent(self, agent: AgentRegistration) -> None:
        self._agents[agent.agent_id] = agent

    def get_agents(self) -> list[AgentRegistration]:
        return list(self._agents.values())

    # --- Round lifecycle ---

    def get_current_round(self, task_id: str) -> Round | None:
        rounds = self._rounds.get(task_id, [])
        return rounds[-1] if rounds else None

    def start_round(self, task_id: str) -> Round:
        """Phase 1: Freeze w^{[i-1]} and start a new round."""
        task = self._tasks[task_id]
        rounds = self._rounds.setdefault(task_id, [])
        round_index = len(rounds)

        # Determine w^{[i-1]}: latest accepted sample, or initial_w
        latest = self._store.get_latest_accepted(task_id)
        frozen_w = latest.content if latest else task.initial_w

        new_round = Round(
            round_index=round_index,
            task_id=task_id,
            phase=RoundPhase.PROPOSE,
            frozen_w=frozen_w,
        )
        rounds.append(new_round)
        return new_round

    def get_frozen_w(self, task_id: str) -> tuple[str, int]:
        """Return (frozen_w, round_index) for the current round."""
        current = self.get_current_round(task_id)
        if current is None:
            task = self._tasks[task_id]
            return task.initial_w, -1
        return current.frozen_w, current.round_index

    def submit_proposal(self, task_id: str, proposal: Proposal) -> None:
        """Phase 2: Collect a proposal from an agent."""
        current = self.get_current_round(task_id)
        if current is None:
            raise ValueError(f"No active round for task {task_id}")
        proposal.round_index = current.round_index
        current.proposals.append(proposal)

    def create_pairings(self, task_id: str) -> list[Pairing]:
        """Phase 3: Random pairing of proposers and reviewers.

        K agents -> K/2 pairs. Each pair produces one MHNG sample.
        If K is odd, one agent is left unpaired.
        """
        current = self.get_current_round(task_id)
        if current is None:
            raise ValueError(f"No active round for task {task_id}")

        proposals = current.proposals
        if len(proposals) < 2:
            return []

        # Shuffle and pair
        indices = list(range(len(proposals)))
        random.shuffle(indices)

        pairings: list[Pairing] = []
        for i in range(0, len(indices) - 1, 2):
            proposer = proposals[indices[i]]
            reviewer_proposal = proposals[indices[i + 1]]
            pairing = Pairing(
                proposer_id=proposer.agent_id,
                reviewer_id=reviewer_proposal.agent_id,
                proposal_id=proposer.proposal_id,
            )
            pairings.append(pairing)

        current.pairings = pairings
        current.phase = RoundPhase.REVIEW
        return pairings

    def get_review_assignment(self, task_id: str, agent_id: str) -> Proposal | None:
        """Get the proposal that this agent should review."""
        current = self.get_current_round(task_id)
        if current is None:
            return None

        for pairing in current.pairings:
            if pairing.reviewer_id == agent_id:
                for proposal in current.proposals:
                    if proposal.proposal_id == pairing.proposal_id:
                        return proposal
        return None

    def submit_review(self, task_id: str, review: ReviewResult) -> None:
        """Phase 4: Collect a review result."""
        current = self.get_current_round(task_id)
        if current is None:
            raise ValueError(f"No active round for task {task_id}")
        current.reviews.append(review)

    def complete_round(self, task_id: str) -> list[Sample]:
        """Phase 5: Finalize round and update sample store.

        For each pairing:
          - If accepted: store w' as a new sample
          - If rejected: store w_current again (standard MCMC)
        """
        current = self.get_current_round(task_id)
        if current is None:
            raise ValueError(f"No active round for task {task_id}")

        samples: list[Sample] = []

        for review in current.reviews:
            # Find the corresponding proposal
            proposal = None
            for p in current.proposals:
                if p.proposal_id == review.proposal_id:
                    proposal = p
                    break

            if review.accepted and proposal is not None:
                sample = Sample(
                    content=proposal.proposed_w,
                    round_index=current.round_index,
                    proposer_id=proposal.agent_id,
                    reviewer_id=review.reviewer_id,
                    accepted=True,
                    acceptance_score=review.score_proposed,
                )
            else:
                # Rejected: record current w as sample (standard MCMC behavior)
                sample = Sample(
                    content=current.frozen_w,
                    round_index=current.round_index,
                    proposer_id=review.proposal_id,
                    reviewer_id=review.reviewer_id,
                    accepted=False,
                    acceptance_score=0.0,
                )

            self._store.add_sample(sample)
            samples.append(sample)

        current.phase = RoundPhase.COMPLETED
        current.completed_at = datetime.now(timezone.utc)
        return samples

    # --- Diagnostics ---

    def get_diagnostics(self, task_id: str) -> ConvergenceDiagnostics:
        current = self.get_current_round(task_id)
        round_index = current.round_index if current else 0

        total = self._store.sample_count
        accepted = self._store.accepted_count
        cumulative_rate = accepted / total if total > 0 else 0.0

        # Per-round acceptance rate
        if current and current.reviews:
            round_accepted = sum(1 for r in current.reviews if r.accepted)
            round_rate = round_accepted / len(current.reviews)
        else:
            round_rate = 0.0

        return ConvergenceDiagnostics(
            round_index=round_index,
            acceptance_rate=round_rate,
            cumulative_acceptance_rate=cumulative_rate,
            sample_count=total,
        )

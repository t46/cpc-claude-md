"""Agent main loop: pull -> propose -> review cycle.

Each iteration of this loop produces one MHNG sample.
Multiple agents running this loop in parallel on separate PCs
collectively perform distributed Bayesian inference.

Works with any CPCAgent implementation.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from cpc.agent.base import CPCAgent
from cpc.agent.proposer import run_propose
from cpc.agent.reviewer import run_review
from cpc.config import AgentConfig

logger = logging.getLogger(__name__)


class AgentRunner:
    def __init__(self, config: AgentConfig, agent: CPCAgent) -> None:
        self.config = config
        self.agent = agent
        self._http = httpx.Client(base_url=config.server_url, timeout=300)

    def _api(self, method: str, path: str, **kwargs) -> dict:
        resp = getattr(self._http, method)(path, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def register(self) -> None:
        self._api("post", "/agents/register", json={
            "agent_id": self.config.agent_id,
            "specialization": self.config.specialization,
        })
        logger.info(f"Agent {self.config.agent_id} registered")

    async def run_one_cycle(self) -> None:
        """Execute one full MHNG cycle: propose + review."""
        task_id = self.config.task_id
        task_data = self._api("get", f"/tasks/{task_id}")
        task_description = task_data["description"]
        if self.config.specialization:
            task_description += f"\n\nYour specialization: {self.config.specialization}"

        # Phase 1: Pull w (sampled from W pool if available)
        w_data = self._api("get", f"/rounds/{task_id}/pull")
        w_current = w_data["frozen_w"]
        round_index = w_data["round_index"]
        w_pool_slot = w_data.get("w_pool_slot")
        logger.info(f"Round {round_index}: pulled w ({len(w_current)} chars, slot={w_pool_slot})")

        # Phase 2: Propose (agent runs autonomously)
        proposal, output = await run_propose(
            agent=self.agent,
            w_current=w_current,
            task_description=task_description,
            agent_id=self.config.agent_id,
        )

        # Submit proposal to server
        data = self._api("post", f"/rounds/{task_id}/propose", json={
            "agent_id": self.config.agent_id,
            "proposed_w": proposal.proposed_w,
            "observation_summary": proposal.observation_summary,
            "reasoning": proposal.reasoning,
            "current_w": w_current,
            "w_pool_slot": w_pool_slot,
        })
        logger.info(f"Submitted proposal {data['proposal_id']}")

        # Phase 4: Review — poll until pairing is done or round completes
        assignment = None
        for _ in range(60):  # Poll for up to 5 minutes
            resp = self._api("get", f"/rounds/{task_id}/review-assignment/{self.config.agent_id}")
            if resp.get("status") != "no_assignment":
                assignment = resp
                break
            # Check if round already completed (no review for us)
            rnd = self._api("get", f"/rounds/{task_id}/current")
            if rnd.get("phase") == "completed":
                break
            await asyncio.sleep(5)

        if assignment is not None:
            logger.info(f"Reviewing proposal {assignment['proposal_id']}")
            review_result = await run_review(
                agent=self.agent,
                proposal_id=assignment["proposal_id"],
                w_proposed=assignment["proposed_w"],
                w_current=assignment["current_w"],
                reviewer_id=self.config.agent_id,
                task_description=task_description,
                round_index=round_index,
            )
            self._api("post", f"/rounds/{task_id}/review", json={
                "proposal_id": assignment["proposal_id"],
                "reviewer_id": self.config.agent_id,
                "accepted": review_result.accepted,
                "score_proposed": review_result.score_proposed,
                "score_current": review_result.score_current,
                "log_alpha": review_result.log_alpha,
                "reasoning": review_result.reasoning,
            })
            logger.info(f"Review: accepted={review_result.accepted}, log_α={review_result.log_alpha:.3f}")
        else:
            logger.info("No review assignment this round")

    async def run_loop(self, max_rounds: int | None = None) -> None:
        """Run the agent loop, polling for new rounds."""
        self.register()
        rounds_completed = 0

        while max_rounds is None or rounds_completed < max_rounds:
            try:
                round_data = self._api("get", f"/rounds/{self.config.task_id}/current")
                if round_data.get("phase") == "propose":
                    await self.run_one_cycle()
                    rounds_completed += 1
                    logger.info(f"Completed {rounds_completed} rounds")
                else:
                    await asyncio.sleep(2)
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error: {e}")
                await asyncio.sleep(5)
            except Exception as e:
                logger.exception(f"Error in agent loop: {e}")
                await asyncio.sleep(5)

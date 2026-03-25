"""End-to-end demo: run 2 agents for a few MHNG rounds.

Demonstrates the full CPC protocol using Docker sandboxes.
Supports both LLM API agents and Claude Code agents.

Usage:
  # Start server first:
  CPC_SERVER_PORT=8111 uv run python scripts/run_server.py

  # Then run demo:
  uv run python scripts/demo.py                    # LLM API agents (default)
  uv run python scripts/demo.py --agent-type code  # Claude Code agents
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

import httpx

from cpc.agent.base import CPCAgent
from cpc.agent.proposer import run_propose
from cpc.agent.reviewer import run_review
from cpc.config import AgentConfig

logger = logging.getLogger(__name__)

SERVER_URL = "http://localhost:8111"


def create_agents(agent_type: str, api_key: str) -> list[tuple[str, CPCAgent]]:
    """Create agents based on type."""
    if agent_type == "code":
        from cpc.agent.claude_code_agent import ClaudeCodeAgent
        return [
            ("agent-arch", ClaudeCodeAgent(work_dir=".", model="claude-sonnet-4-20250514")),
            ("agent-quality", ClaudeCodeAgent(work_dir=".", model="claude-sonnet-4-20250514")),
        ]
    else:
        from cpc.agent.claude_api import ClaudeAPI
        from cpc.agent.llm_agent import LLMAgent
        from cpc.sandbox.docker_sandbox import DockerSandbox
        return [
            ("agent-arch", LLMAgent(
                claude=ClaudeAPI(api_key=api_key),
                sandbox=DockerSandbox(image="python:3.12-slim"),
                specialization="software architecture and design patterns",
            )),
            ("agent-quality", LLMAgent(
                claude=ClaudeAPI(api_key=api_key),
                sandbox=DockerSandbox(image="python:3.12-slim"),
                specialization="code quality, testing, and maintainability",
            )),
        ]


async def demo_round(
    client: httpx.Client,
    task_id: str,
    task_description: str,
    agents: list[tuple[str, CPCAgent]],
) -> None:
    """Run one full MHNG round."""
    # Start round
    round_info = client.post(f"/rounds/{task_id}/start").json()
    round_idx = round_info["round_index"]
    logger.info(f"=== Round {round_idx} started ===")

    # Pull w^{[i-1]}
    w_data = client.get(f"/rounds/{task_id}/pull").json()
    w_current = w_data["frozen_w"]
    logger.info(f"w^[{round_idx - 1 if round_idx > 0 else 'init'}] length: {len(w_current)}")

    # Phase 2: All agents propose
    agent_map: dict[str, CPCAgent] = {}
    for agent_id, agent in agents:
        logger.info(f"Agent {agent_id} proposing...")
        proposal, output = await run_propose(
            agent=agent,
            w_current=w_current,
            task_description=task_description,
            agent_id=agent_id,
        )
        agent_map[agent_id] = agent

        client.post(f"/rounds/{task_id}/propose", json={
            "agent_id": agent_id,
            "proposed_w": proposal.proposed_w,
            "observation_summary": proposal.observation_summary,
            "reasoning": proposal.reasoning,
        }).raise_for_status()
        logger.info(f"Agent {agent_id} submitted proposal")

    # Phase 3: Create pairings
    pair_info = client.post(f"/rounds/{task_id}/pair").json()
    logger.info(f"Created {pair_info['num_pairings']} pairings")

    # Phase 4: Reviews
    for pairing in pair_info["pairings"]:
        reviewer_id = pairing["reviewer_id"]
        proposal_id = pairing["proposal_id"]

        assignment = client.get(f"/rounds/{task_id}/review-assignment/{reviewer_id}").json()
        if assignment.get("status") == "no_assignment":
            continue

        reviewer_agent = agent_map.get(reviewer_id)
        if reviewer_agent is None:
            continue

        review = await run_review(
            agent=reviewer_agent,
            proposal_id=proposal_id,
            w_proposed=assignment["proposed_w"],
            w_current=assignment["current_w"],
            reviewer_id=reviewer_id,
            task_description=task_description,
            round_index=round_idx,
        )

        client.post(f"/rounds/{task_id}/review", json={
            "proposal_id": proposal_id,
            "reviewer_id": reviewer_id,
            "accepted": review.accepted,
            "score_proposed": review.score_proposed,
            "score_current": review.score_current,
            "log_alpha": review.log_alpha,
            "reasoning": review.reasoning,
        }).raise_for_status()
        logger.info(f"Agent {reviewer_id} reviewed: accepted={review.accepted}, "
                     f"scores=({review.score_proposed:.0f}/{review.score_current:.0f}), "
                     f"log_α={review.log_alpha:.3f}")

    # Phase 5: Complete round
    result = client.post(f"/rounds/{task_id}/complete").json()
    logger.info(f"Round completed: {result['num_accepted']}/{result['num_samples']} accepted")

    diag = client.get(f"/diagnostics/{task_id}").json()
    logger.info(f"Diagnostics: acceptance_rate={diag['acceptance_rate']:.2f}, "
                f"total_samples={diag['sample_count']}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="CPC Demo")
    parser.add_argument("--agent-type", choices=["llm", "code"], default="llm",
                        help="'llm' for API agents, 'code' for Claude Code agents")
    parser.add_argument("--rounds", type=int, default=3)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    api_key = AgentConfig().anthropic_api_key
    if not api_key and args.agent_type == "llm":
        logger.error("Set CPC_AGENT_ANTHROPIC_API_KEY or ANTHROPIC_API_KEY in .env")
        sys.exit(1)

    client = httpx.Client(base_url=SERVER_URL, timeout=300)
    try:
        client.get("/health").raise_for_status()
    except httpx.ConnectError:
        logger.error(f"Cannot connect to {SERVER_URL}. Start server: CPC_SERVER_PORT=8111 uv run python scripts/run_server.py")
        sys.exit(1)

    task_id = "demo-analysis"
    task_description = (
        "Analyze the structure and patterns of this Python project (the CPC platform itself). "
        "What are the main components, how do they interact, "
        "and what potential improvements could be made?"
    )

    client.post("/tasks", json={
        "task_id": task_id,
        "description": task_description,
        "initial_w": "",
        "max_rounds": 10,
    }).raise_for_status()
    logger.info(f"Created task: {task_id}")

    agents = create_agents(args.agent_type, api_key)

    for agent_id, _ in agents:
        client.post("/agents/register", json={
            "agent_id": agent_id,
            "specialization": agent_id,
        }).raise_for_status()

    for i in range(args.rounds):
        await demo_round(client, task_id, task_description, agents)
        print()

    # Show final w
    latest = client.get(f"/samples/{task_id}/latest").json()
    if latest.get("status") != "no_samples":
        print("\n" + "=" * 60)
        print("FINAL w (latest accepted sample):")
        print("=" * 60)
        print(latest["content"])


if __name__ == "__main__":
    asyncio.run(main())

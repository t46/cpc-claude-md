"""Local test: run 2 Claude Code agents for Task 1.

Each agent gets its own work directory with a copy of the task data.
Claude CLI runs locally (no Docker needed).

Usage:
  1. Start server: CPC_SERVER_PORT=8111 uv run python scripts/run_server.py
  2. Run test:     uv run python scripts/test_local.py
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import sys
import tempfile
from pathlib import Path

import httpx

from cpc.agent.claude_code_agent import ClaudeCodeAgent
from cpc.agent.proposer import run_propose
from cpc.agent.reviewer import run_review

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

SERVER = "http://localhost:8111"
TASK_ID = "cpc-camp-2026-summary"
DATA_DIR = "data/task-cpc-camp-2026-summary"


def setup_agent_dir(agent_name: str) -> str:
    """Create a work directory with task data for an agent."""
    dst = Path(tempfile.mkdtemp(prefix=f"cpc-{agent_name}-"))
    src = Path(DATA_DIR)
    for f in src.iterdir():
        if f.is_file() and not f.name.startswith("."):
            shutil.copy2(f, dst / f.name)
    logger.info(f"{agent_name} work dir: {dst}")
    return str(dst)


async def main():
    client = httpx.Client(base_url=SERVER, timeout=600)

    # Verify server
    try:
        client.get("/health").raise_for_status()
    except Exception:
        logger.error("Server not running. Start with: CPC_SERVER_PORT=8111 uv run python scripts/run_server.py")
        sys.exit(1)

    # Create task
    client.post("/tasks", json={
        "task_id": TASK_ID,
        "description": open("tasks/cpc-camp-2026-summary.yaml").read().split("description: |")[1].split("initial_w:")[0].strip(),
        "initial_w": "",
        "data_dir": DATA_DIR,
        "max_rounds": 20,
    })

    # Register agents
    client.post("/agents/register", json={"agent_id": "agent-1", "specialization": "research synthesis"})
    client.post("/agents/register", json={"agent_id": "agent-2", "specialization": "structural analysis"})

    # Get task description
    task_description = client.get(f"/tasks/{TASK_ID}").json()["description"]

    # Set up work directories
    agents = [
        ("agent-1", ClaudeCodeAgent(work_dir=setup_agent_dir("agent-1"))),
        ("agent-2", ClaudeCodeAgent(work_dir=setup_agent_dir("agent-2"))),
    ]

    # Start round
    round_resp = client.post(f"/rounds/{TASK_ID}/start").json()
    round_idx = round_resp["round_index"]
    logger.info(f"=== Round {round_idx} started ===")

    w_current = client.get(f"/rounds/{TASK_ID}/pull").json()["frozen_w"]
    logger.info(f"w_current: {len(w_current)} chars")

    # Phase 2: Both agents propose
    agent_map = {}
    for agent_id, agent in agents:
        logger.info(f"{agent_id} proposing...")
        proposal, output = await run_propose(
            agent=agent,
            w_current=w_current,
            task_description=task_description,
            agent_id=agent_id,
        )
        agent_map[agent_id] = agent

        client.post(f"/rounds/{TASK_ID}/propose", json={
            "agent_id": agent_id,
            "proposed_w": proposal.proposed_w,
            "observation_summary": proposal.observation_summary,
            "reasoning": proposal.reasoning,
        }).raise_for_status()
        logger.info(f"{agent_id} proposed ({len(proposal.proposed_w)} chars)")

    # Phase 3: Pair
    pair_info = client.post(f"/rounds/{TASK_ID}/pair").json()
    logger.info(f"Paired: {pair_info['num_pairings']} pairs")

    # Phase 4: Review
    for pairing in pair_info["pairings"]:
        reviewer_id = pairing["reviewer_id"]

        assignment = client.get(f"/rounds/{TASK_ID}/review-assignment/{reviewer_id}").json()
        if assignment.get("status") == "no_assignment":
            continue

        review = await run_review(
            agent=agent_map[reviewer_id],
            proposal_id=pairing["proposal_id"],
            w_proposed=assignment["proposed_w"],
            w_current=assignment["current_w"],
            reviewer_id=reviewer_id,
            task_description=task_description,
            round_index=round_idx,
        )

        client.post(f"/rounds/{TASK_ID}/review", json={
            "proposal_id": pairing["proposal_id"],
            "reviewer_id": reviewer_id,
            "accepted": review.accepted,
            "score_proposed": review.score_proposed,
            "score_current": review.score_current,
            "log_alpha": review.log_alpha,
            "reasoning": review.reasoning,
        }).raise_for_status()
        logger.info(f"{reviewer_id} reviewed: accepted={review.accepted}, "
                     f"scores=({review.score_proposed:.0f}/{review.score_current:.0f})")

    # Phase 5: Complete
    result = client.post(f"/rounds/{TASK_ID}/complete").json()
    logger.info(f"Round completed: {result}")

    # Show result
    latest = client.get(f"/samples/{TASK_ID}/latest").json()
    if latest.get("status") != "no_samples":
        print("\n" + "=" * 60)
        print("LATEST w (accepted sample):")
        print("=" * 60)
        print(latest["content"])
    else:
        print("\nNo samples accepted this round.")


if __name__ == "__main__":
    asyncio.run(main())

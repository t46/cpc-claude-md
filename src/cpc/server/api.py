"""FastAPI REST API for the CPC server.

All endpoints serve the MHNG protocol:
  Pull -> Propose -> Pair -> Review -> Update
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from cpc.models import AgentRegistration, Proposal, ReviewResult, TaskDefinition
from cpc.server.mhng_engine import MHNGEngine

router = APIRouter()

_engine: MHNGEngine | None = None


def set_engine(engine: MHNGEngine) -> None:
    global _engine
    _engine = engine


def get_engine() -> MHNGEngine:
    if _engine is None:
        raise RuntimeError("Engine not initialized")
    return _engine


# --- Request schemas ---

class CreateTaskRequest(BaseModel):
    task_id: str
    description: str
    initial_w: str = ""
    data_dir: str = ""
    docker_image: str = "python:3.12-slim"
    max_rounds: int = 100
    convergence_threshold: float = 0.05
    agent_specializations: list[str] = []


class RegisterAgentRequest(BaseModel):
    agent_id: str
    specialization: str = ""
    system_prompt_hash: str = ""


class SubmitProposalRequest(BaseModel):
    agent_id: str
    proposed_w: str
    observation_summary: str = ""
    reasoning: str = ""
    current_w: str = ""
    w_pool_slot: int | None = None


class SubmitReviewRequest(BaseModel):
    proposal_id: str
    reviewer_id: str
    accepted: bool
    score_proposed: float = 0.0
    score_current: float = 0.0
    log_alpha: float = 0.0
    reasoning: str = ""


# --- Endpoints ---

@router.post("/tasks")
def create_task(req: CreateTaskRequest) -> dict[str, Any]:
    engine = get_engine()
    task = TaskDefinition(
        task_id=req.task_id,
        description=req.description,
        initial_w=req.initial_w,
        data_dir=req.data_dir,
        docker_image=req.docker_image,
        max_rounds=req.max_rounds,
        convergence_threshold=req.convergence_threshold,
        agent_specializations=req.agent_specializations,
    )
    engine.register_task(task)
    return {"status": "created", "task_id": task.task_id}


@router.get("/tasks/{task_id}")
def get_task(task_id: str) -> dict[str, Any]:
    engine = get_engine()
    task = engine.get_task(task_id)
    if task is None:
        raise HTTPException(404, f"Task {task_id} not found")
    return task


@router.post("/agents/register")
def register_agent(req: RegisterAgentRequest) -> dict[str, Any]:
    engine = get_engine()
    agent = AgentRegistration(
        agent_id=req.agent_id,
        specialization=req.specialization,
        system_prompt_hash=req.system_prompt_hash,
    )
    engine.register_agent(agent)
    return {"status": "registered", "agent_id": agent.agent_id}


@router.get("/agents")
def list_agents() -> list[dict[str, Any]]:
    return get_engine().get_agents()


@router.post("/rounds/{task_id}/start")
def start_round(task_id: str) -> dict[str, Any]:
    engine = get_engine()
    if engine.get_task(task_id) is None:
        raise HTTPException(404, f"Task {task_id} not found")
    rnd = engine.start_round(task_id)
    return {
        "status": "started",
        "round_index": rnd["round_index"],
        "phase": rnd["phase"],
    }


@router.get("/rounds/{task_id}/pull")
def pull_w(task_id: str) -> dict[str, Any]:
    frozen_w, round_index = get_engine().get_frozen_w(task_id)
    return {"frozen_w": frozen_w, "round_index": round_index}


@router.get("/rounds/{task_id}/current")
def get_current_round(task_id: str) -> dict[str, Any]:
    rnd = get_engine().get_current_round(task_id)
    if rnd is None:
        return {"status": "no_active_round"}
    return {
        "round_index": rnd["round_index"],
        "phase": rnd["phase"],
    }


@router.post("/rounds/{task_id}/propose")
def submit_proposal(task_id: str, req: SubmitProposalRequest) -> dict[str, Any]:
    engine = get_engine()
    frozen_w, _ = engine.get_frozen_w(task_id)
    proposal = Proposal(
        agent_id=req.agent_id,
        current_w=frozen_w,
        proposed_w=req.proposed_w,
        observation_summary=req.observation_summary,
        reasoning=req.reasoning,
    )
    pid = engine.submit_proposal(task_id, proposal)
    return {"status": "submitted", "proposal_id": pid}


@router.post("/rounds/{task_id}/pair")
def create_pairings(task_id: str) -> dict[str, Any]:
    pairings = get_engine().create_pairings(task_id)
    return {
        "status": "paired",
        "num_pairings": len(pairings),
        "pairings": [
            {"proposer_id": p["proposer_id"], "reviewer_id": p["reviewer_id"], "proposal_id": p["proposal_id"]}
            for p in pairings
        ],
    }


@router.get("/rounds/{task_id}/review-assignment/{agent_id}")
def get_review_assignment(task_id: str, agent_id: str) -> dict[str, Any]:
    engine = get_engine()
    frozen_w, _ = engine.get_frozen_w(task_id)
    proposal = engine.get_review_assignment(task_id, agent_id)
    if proposal is None:
        return {"status": "no_assignment"}
    return {
        "status": "assigned",
        "proposal_id": proposal["id"],
        "proposer_id": proposal["agent_id"],
        "proposed_w": proposal["proposed_w"],
        "current_w": frozen_w,
        "observation_summary": proposal.get("observation_summary", ""),
        "reasoning": proposal.get("reasoning", ""),
    }


@router.post("/rounds/{task_id}/review")
def submit_review(task_id: str, req: SubmitReviewRequest) -> dict[str, Any]:
    engine = get_engine()
    review = ReviewResult(
        proposal_id=req.proposal_id,
        reviewer_id=req.reviewer_id,
        accepted=req.accepted,
        score_proposed=req.score_proposed,
        score_current=req.score_current,
        log_alpha=req.log_alpha,
        reasoning=req.reasoning,
    )
    engine.submit_review(task_id, review)
    return {"status": "reviewed", "accepted": review.accepted}


@router.post("/rounds/{task_id}/complete")
def complete_round(task_id: str) -> dict[str, Any]:
    samples = get_engine().complete_round(task_id)
    accepted_count = sum(1 for s in samples if s["accepted"])
    return {
        "status": "completed",
        "num_samples": len(samples),
        "num_accepted": accepted_count,
    }


@router.get("/samples/{task_id}")
def get_samples(task_id: str) -> list[dict[str, Any]]:
    return get_engine()._store.get_samples(task_id)


@router.get("/samples/{task_id}/latest")
def get_latest_sample(task_id: str) -> dict[str, Any]:
    sample = get_engine()._store.get_latest_accepted(task_id)
    if sample is None:
        return {"status": "no_samples"}
    return sample


@router.get("/proposals/{task_id}")
def get_proposals(task_id: str) -> list[dict[str, Any]]:
    return get_engine().get_proposals(task_id)


@router.get("/reviews/{task_id}")
def get_reviews(task_id: str) -> list[dict[str, Any]]:
    return get_engine().get_reviews(task_id)


class AgentActivityRequest(BaseModel):
    agent_id: str
    task_id: str
    activity_type: str  # "tool_use", "status", "review_start", "review_score"
    detail: str = ""


@router.post("/activity")
def post_activity(req: AgentActivityRequest) -> dict[str, Any]:
    engine = get_engine()
    engine.add_activity(req.agent_id, req.task_id, req.activity_type, req.detail)
    return {"status": "ok"}


@router.get("/activity/{task_id}")
def get_activity(task_id: str) -> list[dict[str, Any]]:
    return get_engine().get_activity(task_id)


@router.get("/diagnostics/{task_id}")
def get_diagnostics(task_id: str) -> dict[str, Any]:
    return get_engine().get_diagnostics(task_id)

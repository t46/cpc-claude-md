"""MHNG (Metropolis-Hastings Naming Game) engine backed by Supabase.

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

from supabase import Client as SupabaseClient

from cpc.models import (
    AgentRegistration,
    ConvergenceDiagnostics,
    Pairing,
    Proposal,
    ReviewResult,
    Sample,
    TaskDefinition,
)
from cpc.server.sample_store import SampleStore


class MHNGEngine:
    def __init__(self, sample_store: SampleStore, sb: SupabaseClient | None = None) -> None:
        self._store = sample_store
        self._sb = sb
        self._activities: list[dict] = []  # In-memory activity log

    # --- Task management ---

    def register_task(self, task: TaskDefinition) -> None:
        if self._sb:
            self._sb.table("tasks").upsert({
                "id": task.task_id,
                "description": task.description,
                "initial_w": task.initial_w,
                "data_dir": task.data_dir,
                "docker_image": task.docker_image,
                "max_rounds": task.max_rounds,
                "convergence_threshold": task.convergence_threshold,
            }).execute()
        else:
            if not hasattr(self, "_tasks"):
                self._tasks = {}
            self._tasks[task.task_id] = task

    def get_task(self, task_id: str) -> dict | None:
        if self._sb:
            res = self._sb.table("tasks").select("*").eq("id", task_id).execute()
            return res.data[0] if res.data else None
        return self._tasks.get(task_id).__dict__ if hasattr(self, "_tasks") and task_id in self._tasks else None

    # --- Agent management ---

    def register_agent(self, agent: AgentRegistration) -> None:
        now = datetime.now(timezone.utc).isoformat()
        if self._sb:
            self._sb.table("agents").upsert({
                "id": agent.agent_id,
                "specialization": agent.specialization,
                "system_prompt_hash": agent.system_prompt_hash,
                "last_seen": now,
            }).execute()
        else:
            if not hasattr(self, "_agents"):
                self._agents = {}
            self._agents[agent.agent_id] = agent

    def get_agents(self) -> list[dict]:
        if self._sb:
            res = self._sb.table("agents").select("*").order("registered_at").execute()
            return res.data or []
        return [{"id": a.agent_id, "specialization": a.specialization}
                for a in getattr(self, "_agents", {}).values()]

    # --- Round lifecycle ---

    def _get_current_round_data(self, task_id: str) -> dict | None:
        if self._sb:
            res = (self._sb.table("rounds").select("*")
                   .eq("task_id", task_id)
                   .order("round_index", desc=True)
                   .limit(1).execute())
            return res.data[0] if res.data else None
        rounds = getattr(self, "_rounds", {}).get(task_id, [])
        return rounds[-1] if rounds else None

    def get_current_round(self, task_id: str) -> dict | None:
        return self._get_current_round_data(task_id)

    def start_round(self, task_id: str) -> dict:
        """Phase 1: Freeze w^{[i-1]} and start a new round."""
        current = self._get_current_round_data(task_id)
        round_index = (current["round_index"] + 1) if current else 0

        # Determine w^{[i-1]}
        latest = self._store.get_latest_accepted(task_id)
        if latest:
            frozen_w = latest["content"]
        else:
            task = self.get_task(task_id)
            frozen_w = task["initial_w"] if task else ""

        round_data = {
            "task_id": task_id,
            "round_index": round_index,
            "phase": "propose",
            "frozen_w": frozen_w,
        }

        if self._sb:
            res = self._sb.table("rounds").insert(round_data).execute()
            return res.data[0]
        else:
            if not hasattr(self, "_rounds"):
                self._rounds = {}
            self._rounds.setdefault(task_id, []).append(round_data)
            return round_data

    def get_frozen_w(self, task_id: str) -> tuple[str, int]:
        current = self._get_current_round_data(task_id)
        if current:
            return current["frozen_w"], current["round_index"]
        task = self.get_task(task_id)
        return (task["initial_w"] if task else ""), -1

    def submit_proposal(self, task_id: str, proposal: Proposal) -> str:
        """Phase 2: Collect a proposal from an agent."""
        current = self._get_current_round_data(task_id)
        round_index = current["round_index"] if current else 0

        data = {
            "id": proposal.proposal_id,
            "agent_id": proposal.agent_id,
            "task_id": task_id,
            "round_index": round_index,
            "current_w": proposal.current_w,
            "proposed_w": proposal.proposed_w,
            "observation_summary": proposal.observation_summary,
            "reasoning": proposal.reasoning,
        }

        if self._sb:
            self._sb.table("proposals").insert(data).execute()
            # Update agent heartbeat
            self._sb.table("agents").update(
                {"last_seen": datetime.now(timezone.utc).isoformat()}
            ).eq("id", proposal.agent_id).execute()
        else:
            if not hasattr(self, "_proposals"):
                self._proposals = []
            self._proposals.append(data)

        return proposal.proposal_id

    def create_pairings(self, task_id: str) -> list[dict]:
        """Phase 3: Random pairing of proposers and reviewers."""
        current = self._get_current_round_data(task_id)
        if not current:
            return []
        round_index = current["round_index"]

        # Get proposals for this round
        if self._sb:
            res = (self._sb.table("proposals").select("*")
                   .eq("task_id", task_id).eq("round_index", round_index).execute())
            proposals = res.data or []
        else:
            proposals = [p for p in getattr(self, "_proposals", [])
                        if p["task_id"] == task_id and p["round_index"] == round_index]

        if len(proposals) < 2:
            return []

        indices = list(range(len(proposals)))
        random.shuffle(indices)

        pairings = []
        for i in range(0, len(indices) - 1, 2):
            p = {
                "task_id": task_id,
                "round_index": round_index,
                "proposer_id": proposals[indices[i]]["agent_id"],
                "reviewer_id": proposals[indices[i + 1]]["agent_id"],
                "proposal_id": proposals[indices[i]]["id"],
            }
            pairings.append(p)

        if self._sb:
            self._sb.table("pairings").insert(pairings).execute()
            self._sb.table("rounds").update({"phase": "review"}).eq(
                "task_id", task_id).eq("round_index", round_index).execute()
        else:
            if not hasattr(self, "_pairings"):
                self._pairings = []
            self._pairings.extend(pairings)

        return pairings

    def get_review_assignment(self, task_id: str, agent_id: str) -> dict | None:
        current = self._get_current_round_data(task_id)
        if not current:
            return None
        round_index = current["round_index"]

        if self._sb:
            res = (self._sb.table("pairings").select("*")
                   .eq("task_id", task_id).eq("round_index", round_index)
                   .eq("reviewer_id", agent_id).execute())
            pairing = res.data[0] if res.data else None
        else:
            pairing = next((p for p in getattr(self, "_pairings", [])
                           if p["task_id"] == task_id and p["round_index"] == round_index
                           and p["reviewer_id"] == agent_id), None)

        if not pairing:
            return None

        # Get the proposal
        if self._sb:
            res = self._sb.table("proposals").select("*").eq("id", pairing["proposal_id"]).execute()
            proposal = res.data[0] if res.data else None
        else:
            proposal = next((p for p in getattr(self, "_proposals", [])
                           if p["id"] == pairing["proposal_id"]), None)

        return proposal

    def submit_review(self, task_id: str, review: ReviewResult) -> None:
        """Phase 4: Collect a review result."""
        current = self._get_current_round_data(task_id)
        round_index = current["round_index"] if current else 0

        data = {
            "id": review.review_id,
            "proposal_id": review.proposal_id,
            "reviewer_id": review.reviewer_id,
            "task_id": task_id,
            "round_index": round_index,
            "accepted": review.accepted,
            "score_proposed": review.score_proposed,
            "score_current": review.score_current,
            "log_alpha": review.log_alpha,
            "reasoning": review.reasoning,
        }

        if self._sb:
            self._sb.table("reviews").insert(data).execute()
        else:
            if not hasattr(self, "_reviews"):
                self._reviews = []
            self._reviews.append(data)

    def complete_round(self, task_id: str) -> list[dict]:
        """Phase 5: Finalize round and update sample store."""
        current = self._get_current_round_data(task_id)
        if not current:
            return []
        round_index = current["round_index"]

        # Get reviews for this round
        if self._sb:
            res = (self._sb.table("reviews").select("*")
                   .eq("task_id", task_id).eq("round_index", round_index).execute())
            reviews = res.data or []
        else:
            reviews = [r for r in getattr(self, "_reviews", [])
                      if r["task_id"] == task_id and r["round_index"] == round_index]

        samples = []
        for review in reviews:
            if review["accepted"]:
                # Get proposal content
                if self._sb:
                    res = self._sb.table("proposals").select("proposed_w,agent_id").eq("id", review["proposal_id"]).execute()
                    proposal = res.data[0] if res.data else None
                else:
                    proposal = next((p for p in getattr(self, "_proposals", [])
                                   if p["id"] == review["proposal_id"]), None)

                content = proposal["proposed_w"] if proposal else ""
                proposer_id = proposal["agent_id"] if proposal else ""

                sample = Sample(
                    content=content,
                    round_index=round_index,
                    proposer_id=proposer_id,
                    reviewer_id=review["reviewer_id"],
                    accepted=True,
                    acceptance_score=review["score_proposed"],
                )
            else:
                sample = Sample(
                    content=current["frozen_w"],
                    round_index=round_index,
                    proposer_id=review.get("proposal_id", ""),
                    reviewer_id=review["reviewer_id"],
                    accepted=False,
                    acceptance_score=0.0,
                )

            self._store.add_sample(sample, task_id=task_id)
            samples.append({"accepted": sample.accepted, "content": sample.content[:100]})

        # Mark round as completed
        if self._sb:
            self._sb.table("rounds").update({
                "phase": "completed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("task_id", task_id).eq("round_index", round_index).execute()

        return samples

    # --- Activity log ---

    def add_activity(self, agent_id: str, task_id: str, activity_type: str, detail: str) -> None:
        entry = {
            "agent_id": agent_id,
            "task_id": task_id,
            "activity_type": activity_type,
            "detail": detail,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._activities.append(entry)
        # Keep last 200 entries
        if len(self._activities) > 200:
            self._activities = self._activities[-200:]

    def get_activity(self, task_id: str) -> list[dict]:
        return [a for a in self._activities if a["task_id"] == task_id]

    # --- Query helpers for frontend ---

    def get_proposals(self, task_id: str) -> list[dict]:
        if self._sb:
            res = (self._sb.table("proposals").select("*")
                   .eq("task_id", task_id).order("created_at").execute())
            return res.data or []
        return [p for p in getattr(self, "_proposals", []) if p.get("task_id") == task_id]

    def get_reviews(self, task_id: str) -> list[dict]:
        if self._sb:
            res = (self._sb.table("reviews").select("*")
                   .eq("task_id", task_id).order("created_at").execute())
            return res.data or []
        return [r for r in getattr(self, "_reviews", []) if r.get("task_id") == task_id]

    # --- Diagnostics ---

    def get_diagnostics(self, task_id: str) -> dict:
        current = self._get_current_round_data(task_id)
        round_index = current["round_index"] if current else 0

        total = self._store.get_sample_count(task_id)
        accepted = self._store.get_accepted_count(task_id)
        cumulative_rate = accepted / total if total > 0 else 0.0

        # Per-round rate
        if self._sb and current:
            res = (self._sb.table("reviews").select("accepted")
                   .eq("task_id", task_id).eq("round_index", round_index).execute())
            round_reviews = res.data or []
        else:
            round_reviews = [r for r in getattr(self, "_reviews", [])
                           if r.get("task_id") == task_id
                           and r.get("round_index") == round_index]

        if round_reviews:
            round_accepted = sum(1 for r in round_reviews if r["accepted"])
            round_rate = round_accepted / len(round_reviews)
        else:
            round_rate = 0.0

        return {
            "round_index": round_index,
            "acceptance_rate": round_rate,
            "cumulative_acceptance_rate": cumulative_rate,
            "sample_count": total,
            "recent_sample_similarity": 0.0,
        }

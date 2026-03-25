"""Supabase REST API client that mimics FastAPI server endpoints.

Agents and run_round.py can use this instead of the FastAPI server.
Provides the same HTTP-like interface so AgentRunner works unchanged.

Usage:
  client = SupabaseAPIClient(supabase_url, supabase_key)
  # Use like httpx.Client with our FastAPI paths:
  client.get("/tasks/my-task")
  client.post("/rounds/my-task/propose", json={...})
"""

from __future__ import annotations

import random
import re
from datetime import datetime, timezone
from uuid import uuid4

import httpx


class SupabaseAPIClient:
    """Drop-in replacement for httpx.Client talking to FastAPI server.

    Routes FastAPI-style paths to Supabase PostgREST queries.
    """

    def __init__(self, supabase_url: str, supabase_key: str) -> None:
        self._rest = f"{supabase_url}/rest/v1"
        self._headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        self._http = httpx.Client(timeout=30)

    def _sb(self, method: str, path: str, **kwargs) -> list:
        resp = self._http.request(method, f"{self._rest}{path}",
                                  headers=self._headers, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def _sb_patch(self, path: str, json: dict) -> None:
        self._http.request("PATCH", f"{self._rest}{path}",
                          headers=self._headers, json=json)

    # --- Route dispatcher (mimics httpx.Client.get/post) ---

    def get(self, path: str, **kwargs) -> "_FakeResponse":
        return _FakeResponse(self._dispatch("GET", path, **kwargs))

    def post(self, path: str, **kwargs) -> "_FakeResponse":
        return _FakeResponse(self._dispatch("POST", path, **kwargs))

    def _dispatch(self, method: str, path: str, json: dict | None = None, **kwargs) -> dict:
        # GET /health
        if path == "/health":
            return {"status": "ok", "backend": "supabase"}

        # GET /tasks/{task_id}
        m = re.match(r"/tasks/(.+)$", path)
        if m and method == "GET":
            return self._get_task(m.group(1))

        # POST /tasks
        if path == "/tasks" and method == "POST":
            return self._create_task(json)

        # POST /agents/register
        if path == "/agents/register" and method == "POST":
            return self._register_agent(json)

        # GET /agents
        if path == "/agents" and method == "GET":
            return self._get_agents()

        # POST /rounds/{task_id}/start
        m = re.match(r"/rounds/(.+)/start$", path)
        if m and method == "POST":
            return self._start_round(m.group(1))

        # GET /rounds/{task_id}/pull
        m = re.match(r"/rounds/(.+)/pull$", path)
        if m and method == "GET":
            return self._pull_w(m.group(1))

        # GET /rounds/{task_id}/current
        m = re.match(r"/rounds/(.+)/current$", path)
        if m and method == "GET":
            return self._get_current_round(m.group(1))

        # POST /rounds/{task_id}/propose
        m = re.match(r"/rounds/(.+)/propose$", path)
        if m and method == "POST":
            return self._submit_proposal(m.group(1), json)

        # POST /rounds/{task_id}/pair
        m = re.match(r"/rounds/(.+)/pair$", path)
        if m and method == "POST":
            return self._create_pairings(m.group(1))

        # GET /rounds/{task_id}/review-assignment/{agent_id}
        m = re.match(r"/rounds/(.+)/review-assignment/(.+)$", path)
        if m and method == "GET":
            return self._get_review_assignment(m.group(1), m.group(2))

        # POST /rounds/{task_id}/review
        m = re.match(r"/rounds/(.+)/review$", path)
        if m and method == "POST":
            return self._submit_review(m.group(1), json)

        # POST /rounds/{task_id}/complete
        m = re.match(r"/rounds/(.+)/complete$", path)
        if m and method == "POST":
            return self._complete_round(m.group(1))

        # GET /proposals/{task_id}
        m = re.match(r"/proposals/(.+)$", path)
        if m and method == "GET":
            return self._get_proposals(m.group(1))

        # GET /reviews/{task_id}
        m = re.match(r"/reviews/(.+)$", path)
        if m and method == "GET":
            return self._get_reviews(m.group(1))

        # GET /samples/{task_id}/latest
        m = re.match(r"/samples/(.+)/latest$", path)
        if m and method == "GET":
            return self._get_latest_sample(m.group(1))

        # GET /samples/{task_id}
        m = re.match(r"/samples/(.+)$", path)
        if m and method == "GET":
            return self._get_samples(m.group(1))

        # GET /diagnostics/{task_id}
        m = re.match(r"/diagnostics/(.+)$", path)
        if m and method == "GET":
            return self._get_diagnostics(m.group(1))

        # POST /activity
        if path == "/activity" and method == "POST":
            return {"status": "ok"}  # Activity not stored in Supabase for now

        # GET /activity/{task_id}
        m = re.match(r"/activity/(.+)$", path)
        if m and method == "GET":
            return []

        raise ValueError(f"Unknown route: {method} {path}")

    # --- Implementation ---

    def _get_task(self, task_id: str) -> dict:
        data = self._sb("GET", f"/tasks?id=eq.{task_id}&select=*")
        if not data:
            raise httpx.HTTPStatusError("Not found", request=None, response=None)
        return data[0]

    def _create_task(self, json: dict) -> dict:
        json["id"] = json.pop("task_id", json.get("id", ""))
        self._sb("POST", "/tasks", json=json)
        return {"status": "created", "task_id": json["id"]}

    def _register_agent(self, json: dict) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        agent_id = json["agent_id"]
        # Upsert
        headers = {**self._headers, "Prefer": "resolution=merge-duplicates,return=representation"}
        self._http.request("POST", f"{self._rest}/agents",
                          headers=headers,
                          json={"id": agent_id, "specialization": json.get("specialization", ""), "last_seen": now})
        return {"status": "registered", "agent_id": agent_id}

    def _get_agents(self) -> list:
        return self._sb("GET", "/agents?order=registered_at")

    def _get_current_round(self, task_id: str) -> dict:
        data = self._sb("GET", f"/rounds?task_id=eq.{task_id}&order=round_index.desc&limit=1")
        if not data:
            return {"status": "no_active_round"}
        return {"round_index": data[0]["round_index"], "phase": data[0]["phase"]}

    def _start_round(self, task_id: str) -> dict:
        current = self._sb("GET", f"/rounds?task_id=eq.{task_id}&order=round_index.desc&limit=1")
        round_index = (current[0]["round_index"] + 1) if current else 0

        accepted = self._sb("GET", f"/samples?task_id=eq.{task_id}&accepted=eq.true&order=created_at.desc&limit=1")
        if accepted:
            frozen_w = accepted[0]["content"]
        else:
            task = self._get_task(task_id)
            frozen_w = task.get("initial_w", "")

        self._sb("POST", "/rounds", json={
            "task_id": task_id, "round_index": round_index,
            "phase": "propose", "frozen_w": frozen_w,
        })
        return {"status": "started", "round_index": round_index, "phase": "propose"}

    def _pull_w(self, task_id: str) -> dict:
        data = self._sb("GET", f"/rounds?task_id=eq.{task_id}&order=round_index.desc&limit=1")
        if data:
            return {"frozen_w": data[0]["frozen_w"], "round_index": data[0]["round_index"]}
        task = self._get_task(task_id)
        return {"frozen_w": task.get("initial_w", ""), "round_index": -1}

    def _submit_proposal(self, task_id: str, json: dict) -> dict:
        current = self._sb("GET", f"/rounds?task_id=eq.{task_id}&order=round_index.desc&limit=1")
        ri = current[0]["round_index"] if current else 0
        frozen_w = current[0]["frozen_w"] if current else ""
        pid = uuid4().hex[:12]
        self._sb("POST", "/proposals", json={
            "id": pid, "agent_id": json["agent_id"], "task_id": task_id,
            "round_index": ri, "current_w": frozen_w,
            "proposed_w": json["proposed_w"],
            "observation_summary": json.get("observation_summary", ""),
            "reasoning": json.get("reasoning", ""),
        })
        now = datetime.now(timezone.utc).isoformat()
        self._sb_patch(f"/agents?id=eq.{json['agent_id']}", {"last_seen": now})
        return {"status": "submitted", "proposal_id": pid}

    def _create_pairings(self, task_id: str) -> dict:
        current = self._sb("GET", f"/rounds?task_id=eq.{task_id}&order=round_index.desc&limit=1")
        if not current:
            return {"status": "paired", "num_pairings": 0, "pairings": []}
        ri = current[0]["round_index"]

        proposals = self._sb("GET", f"/proposals?task_id=eq.{task_id}&round_index=eq.{ri}&order=created_at")
        if len(proposals) < 2:
            return {"status": "paired", "num_pairings": 0, "pairings": []}

        indices = list(range(len(proposals)))
        random.shuffle(indices)
        pairings = []
        for i in range(0, len(indices) - 1, 2):
            p = {
                "id": uuid4().hex[:12], "task_id": task_id, "round_index": ri,
                "proposer_id": proposals[indices[i]]["agent_id"],
                "reviewer_id": proposals[indices[i + 1]]["agent_id"],
                "proposal_id": proposals[indices[i]]["id"],
            }
            pairings.append(p)

        if pairings:
            self._sb("POST", "/pairings", json=pairings)
            self._sb_patch(f"/rounds?task_id=eq.{task_id}&round_index=eq.{ri}", {"phase": "review"})

        return {
            "status": "paired", "num_pairings": len(pairings),
            "pairings": [{"proposer_id": p["proposer_id"], "reviewer_id": p["reviewer_id"],
                          "proposal_id": p["proposal_id"]} for p in pairings],
        }

    def _get_review_assignment(self, task_id: str, agent_id: str) -> dict:
        current = self._sb("GET", f"/rounds?task_id=eq.{task_id}&order=round_index.desc&limit=1")
        if not current:
            return {"status": "no_assignment"}
        ri = current[0]["round_index"]

        pairings = self._sb("GET", f"/pairings?task_id=eq.{task_id}&round_index=eq.{ri}&reviewer_id=eq.{agent_id}")
        if not pairings:
            return {"status": "no_assignment"}

        proposals = self._sb("GET", f"/proposals?id=eq.{pairings[0]['proposal_id']}")
        if not proposals:
            return {"status": "no_assignment"}

        p = proposals[0]
        return {
            "status": "assigned", "proposal_id": p["id"], "proposer_id": p["agent_id"],
            "proposed_w": p["proposed_w"], "current_w": current[0]["frozen_w"],
            "observation_summary": p.get("observation_summary", ""),
            "reasoning": p.get("reasoning", ""),
        }

    def _submit_review(self, task_id: str, json: dict) -> dict:
        current = self._sb("GET", f"/rounds?task_id=eq.{task_id}&order=round_index.desc&limit=1")
        ri = current[0]["round_index"] if current else 0
        self._sb("POST", "/reviews", json={
            "id": uuid4().hex[:12], "proposal_id": json["proposal_id"],
            "reviewer_id": json["reviewer_id"], "task_id": task_id, "round_index": ri,
            "accepted": json["accepted"], "score_proposed": json.get("score_proposed", 0),
            "score_current": json.get("score_current", 0), "log_alpha": json.get("log_alpha", 0),
            "reasoning": json.get("reasoning", ""),
        })
        return {"status": "reviewed", "accepted": json["accepted"]}

    def _complete_round(self, task_id: str) -> dict:
        current = self._sb("GET", f"/rounds?task_id=eq.{task_id}&order=round_index.desc&limit=1")
        if not current:
            return {"status": "completed", "num_samples": 0, "num_accepted": 0}
        ri = current[0]["round_index"]

        reviews = self._sb("GET", f"/reviews?task_id=eq.{task_id}&round_index=eq.{ri}")
        accepted_count = 0
        for r in reviews:
            if r["accepted"]:
                proposals = self._sb("GET", f"/proposals?id=eq.{r['proposal_id']}")
                content = proposals[0]["proposed_w"] if proposals else ""
                proposer_id = proposals[0]["agent_id"] if proposals else ""
                accepted_count += 1
            else:
                content = current[0]["frozen_w"]
                proposer_id = ""

            self._sb("POST", "/samples", json={
                "id": uuid4().hex[:12], "task_id": task_id, "content": content,
                "round_index": ri, "proposer_id": proposer_id,
                "reviewer_id": r["reviewer_id"], "accepted": r["accepted"],
                "acceptance_score": r.get("score_proposed", 0),
            })

        now = datetime.now(timezone.utc).isoformat()
        self._sb_patch(f"/rounds?task_id=eq.{task_id}&round_index=eq.{ri}",
                      {"phase": "completed", "completed_at": now})

        return {"status": "completed", "num_samples": len(reviews), "num_accepted": accepted_count}

    def _get_proposals(self, task_id: str) -> list:
        return self._sb("GET", f"/proposals?task_id=eq.{task_id}&order=created_at")

    def _get_reviews(self, task_id: str) -> list:
        return self._sb("GET", f"/reviews?task_id=eq.{task_id}&order=created_at")

    def _get_samples(self, task_id: str) -> list:
        return self._sb("GET", f"/samples?task_id=eq.{task_id}&order=created_at")

    def _get_latest_sample(self, task_id: str) -> dict:
        data = self._sb("GET", f"/samples?task_id=eq.{task_id}&accepted=eq.true&order=created_at.desc&limit=1")
        if not data:
            return {"status": "no_samples"}
        return data[0]

    def _get_diagnostics(self, task_id: str) -> dict:
        samples = self._sb("GET", f"/samples?task_id=eq.{task_id}")
        total = len(samples)
        accepted = sum(1 for s in samples if s["accepted"])
        current = self._sb("GET", f"/rounds?task_id=eq.{task_id}&order=round_index.desc&limit=1")
        ri = current[0]["round_index"] if current else 0
        return {
            "round_index": ri,
            "acceptance_rate": accepted / total if total else 0,
            "cumulative_acceptance_rate": accepted / total if total else 0,
            "sample_count": total,
            "recent_sample_similarity": 0.0,
        }


class _FakeResponse:
    """Mimics httpx.Response so AgentRunner's _api() works unchanged."""

    def __init__(self, data):
        self._data = data
        self.status_code = 200

    def json(self):
        return self._data

    def raise_for_status(self):
        pass

"""Sample store backed by Supabase.

Maintains the Monte Carlo sample set {w^[1], ..., w^[I]} that
approximates the posterior q(w | o^1, ..., o^K).
"""

from __future__ import annotations

from dataclasses import asdict
from supabase import Client as SupabaseClient

from cpc.models import Sample


class SampleStore:
    def __init__(self, sb: SupabaseClient | None = None) -> None:
        self._sb = sb
        # Fallback in-memory store when Supabase is not configured
        self._memory: list[dict] = []

    def _to_dict(self, sample: Sample) -> dict:
        d = asdict(sample)
        d["created_at"] = d["created_at"].isoformat()
        return d

    def add_sample(self, sample: Sample, task_id: str = "") -> None:
        d = self._to_dict(sample)
        d["task_id"] = task_id
        if self._sb:
            self._sb.table("samples").insert(d).execute()
        else:
            self._memory.append(d)

    def get_samples(self, task_id: str) -> list[dict]:
        if self._sb:
            res = self._sb.table("samples").select("*").eq("task_id", task_id).order("created_at").execute()
            return res.data or []
        return [s for s in self._memory if s.get("task_id") == task_id]

    def get_accepted_samples(self, task_id: str) -> list[dict]:
        if self._sb:
            res = (self._sb.table("samples").select("*")
                   .eq("task_id", task_id).eq("accepted", True)
                   .order("created_at").execute())
            return res.data or []
        return [s for s in self._memory if s.get("task_id") == task_id and s.get("accepted")]

    def get_latest_accepted(self, task_id: str) -> dict | None:
        accepted = self.get_accepted_samples(task_id)
        return accepted[-1] if accepted else None

    def get_sample_count(self, task_id: str) -> int:
        return len(self.get_samples(task_id))

    def get_accepted_count(self, task_id: str) -> int:
        return len(self.get_accepted_samples(task_id))

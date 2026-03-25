"""Sample store for accumulating w samples.

Maintains the Monte Carlo sample set {w^[1], ..., w^[I]} that
approximates the posterior q(w | o^1, ..., o^K).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from cpc.models import Sample


class SampleStore:
    def __init__(self, data_dir: str = "data") -> None:
        self._samples: list[Sample] = []
        self._data_dir = Path(data_dir)

    def add_sample(self, sample: Sample) -> None:
        self._samples.append(sample)
        self._flush()

    def get_samples(self, task_id: str) -> list[Sample]:
        return [s for s in self._samples if True]  # TODO: filter by task_id when stored

    def get_accepted_samples(self, task_id: str) -> list[Sample]:
        return [s for s in self._samples if s.accepted]

    def get_latest_accepted(self, task_id: str) -> Sample | None:
        accepted = self.get_accepted_samples(task_id)
        return accepted[-1] if accepted else None

    @property
    def sample_count(self) -> int:
        return len(self._samples)

    @property
    def accepted_count(self) -> int:
        return sum(1 for s in self._samples if s.accepted)

    def _flush(self) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        path = self._data_dir / "samples.jsonl"
        with open(path, "w") as f:
            for s in self._samples:
                d = asdict(s)
                d["created_at"] = d["created_at"].isoformat()
                f.write(json.dumps(d, ensure_ascii=False) + "\n")

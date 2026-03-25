"""Docker sandbox for distributed execution mode.

Each agent runs experiments inside an isolated Docker container,
ensuring complete independence between agents on different PCs.
This is essential for i.i.d. sampling: o^k ⊥ o^{k'} for k ≠ k'.
"""

from __future__ import annotations

import asyncio

from cpc.sandbox.base import Sandbox


class DockerSandbox(Sandbox):
    def __init__(
        self,
        image: str = "python:3.12-slim",
        timeout: int = 300,
        memory_limit: str = "512m",
        cpu_count: int = 1,
    ) -> None:
        self._image = image
        self._timeout = timeout
        self._memory_limit = memory_limit
        self._cpu_count = cpu_count
        self._container_id: str | None = None

    async def setup(self) -> None:
        proc = await asyncio.create_subprocess_exec(
            "docker", "run", "-d",
            "--memory", self._memory_limit,
            "--cpus", str(self._cpu_count),
            "--network", "none",
            self._image,
            "sleep", "infinity",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"Failed to start container: {stderr.decode()}")
        self._container_id = stdout.decode().strip()

    async def execute(self, command: str) -> str:
        if self._container_id is None:
            raise RuntimeError("Sandbox not set up")

        proc = await asyncio.create_subprocess_exec(
            "docker", "exec", self._container_id,
            "sh", "-c", command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=self._timeout)
        output = stdout.decode("utf-8", errors="replace") if stdout else ""

        return f"[exit code: {proc.returncode}]\n{output}"

    async def teardown(self) -> None:
        if self._container_id is not None:
            proc = await asyncio.create_subprocess_exec(
                "docker", "rm", "-f", self._container_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            self._container_id = None

"""Git worktree sandbox for local demo mode.

Creates a temporary git worktree for each agent, providing filesystem
isolation without Docker. Suitable for running multiple agents on
a single machine.
"""

from __future__ import annotations

import asyncio
import tempfile
import uuid
from pathlib import Path

from cpc.sandbox.base import Sandbox


class WorktreeSandbox(Sandbox):
    def __init__(self, repo_path: str = ".") -> None:
        self._repo_path = Path(repo_path).resolve()
        self._worktree_path: Path | None = None
        self._branch_name: str = ""

    async def setup(self) -> None:
        self._branch_name = f"cpc-sandbox-{uuid.uuid4().hex[:8]}"
        self._worktree_path = Path(tempfile.mkdtemp(prefix="cpc-worktree-"))

        # Create an orphan branch and worktree
        proc = await asyncio.create_subprocess_exec(
            "git", "worktree", "add", "--detach",
            str(self._worktree_path),
            cwd=str(self._repo_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

    async def execute(self, command: str) -> str:
        if self._worktree_path is None:
            raise RuntimeError("Sandbox not set up")

        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=str(self._worktree_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=None,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=300)
        output = stdout.decode("utf-8", errors="replace") if stdout else ""

        return f"[exit code: {proc.returncode}]\n{output}"

    async def teardown(self) -> None:
        if self._worktree_path is not None:
            proc = await asyncio.create_subprocess_exec(
                "git", "worktree", "remove", "--force",
                str(self._worktree_path),
                cwd=str(self._repo_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            self._worktree_path = None

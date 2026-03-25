"""Claude Code agent: uses `claude` CLI as a fully autonomous CPC agent.

Instead of controlling each CPC step (interpret, experiment, update, write),
this agent delegates the entire propose/review process to a Claude Code
instance running as a subprocess. Claude Code autonomously decides what
tools to use, what files to read, what commands to run, etc.

This is the most natural mapping to CPC-MS:
  - z^k is Claude Code's entire reasoning trace (invisible to us)
  - o^k is whatever Claude Code observes through its tools
  - a^k is whatever actions Claude Code chooses
  - We only see the final output: w' (proposal) and score

Usage:
  agent = ClaudeCodeAgent(
      work_dir="/path/to/project",
      model="claude-sonnet-4-20250514",
  )
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from cpc.agent.base import CPCAgent, ProposalOutput, ReviewScore


class ClaudeCodeAgent(CPCAgent):
    """CPC agent that delegates to `claude` CLI (Claude Code).

    Each propose/score call spawns a `claude` subprocess with a
    carefully crafted prompt. Claude Code runs autonomously in the
    given work_dir, using whatever tools it needs.
    """

    def __init__(
        self,
        work_dir: str = ".",
        model: str = "claude-sonnet-4-20250514",
        max_turns: int = 20,
        timeout: int = 300,
    ) -> None:
        self._work_dir = Path(work_dir)
        self._model = model
        self._max_turns = max_turns
        self._timeout = timeout

    async def _run_claude(self, prompt: str) -> str:
        """Run `claude` CLI with a prompt and return its output."""
        proc = await asyncio.create_subprocess_exec(
            "claude",
            "--print",
            "--model", self._model,
            "--max-turns", str(self._max_turns),
            "--output-format", "text",
            "-p", prompt,
            cwd=str(self._work_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=self._timeout
        )
        output = stdout.decode("utf-8", errors="replace") if stdout else ""
        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace") if stderr else ""
            output += f"\n[claude exit code: {proc.returncode}]\n{err}"
        return output

    async def propose(self, w_current: str, task_description: str) -> ProposalOutput:
        prompt = f"""You are participating in a collaborative research process.

## Task
{task_description}

## Current shared document (proposed_w from previous round)
{w_current if w_current else "(None yet — you are the first to investigate.)"}

## Instructions
1. Read the current shared document above if it exists.
2. Follow the task instructions — read files, run commands, investigate, etc.
3. Produce your output in the exact format below.

## Output Format
You MUST end your response with EXACTLY this structure (including the markers):

===PROPOSED_W===
(Your proposed shared document. This will be evaluated against other agents' proposals.)
===END_PROPOSED_W===

===REASONING===
(Your hypothesis and reasoning — what you found and why you believe it.)
===END_REASONING===

===OBSERVATION_SUMMARY===
(Summary of key observations from your investigation.)
===END_OBSERVATION_SUMMARY===
"""
        output = await self._run_claude(prompt)
        return self._parse_proposal(output)

    async def score(self, w: str, task_description: str) -> ReviewScore:
        prompt = f"""You are reviewing a shared knowledge document as part of a Collective Predictive Coding (CPC) process.

## Research Problem
{task_description}

## Document to Evaluate
{w}

## Instructions
Based on your understanding of this codebase/problem, rate how accurate, complete, and well-supported
this document is. Consider:
- Are the findings supported by evidence?
- Are there any factual errors or unsupported claims?
- Does it address the key aspects of the research problem?

You MUST end your response with EXACTLY:
===SCORE===
(A single integer from 0 to 100)
===SCORE_END===
===SCORE_REASONING===
(Brief explanation of your score)
===SCORE_REASONING_END===
"""
        output = await self._run_claude(prompt)
        return self._parse_score(output)

    @staticmethod
    def _parse_proposal(output: str) -> ProposalOutput:
        def _extract(text: str, start_marker: str, end_marker: str) -> str:
            try:
                start = text.index(start_marker) + len(start_marker)
                end = text.index(end_marker)
                return text[start:end].strip()
            except ValueError:
                return ""

        proposed_w = _extract(output, "===PROPOSED_W===", "===END_PROPOSED_W===")
        reasoning = _extract(output, "===REASONING===", "===END_REASONING===")
        observations = _extract(output, "===OBSERVATION_SUMMARY===", "===END_OBSERVATION_SUMMARY===")

        # Fallback: if markers not found, use entire output as proposal
        if not proposed_w:
            proposed_w = output

        return ProposalOutput(
            proposed_w=proposed_w,
            reasoning=reasoning,
            observation_summary=observations[:2000],
        )

    @staticmethod
    def _parse_score(output: str) -> ReviewScore:
        try:
            start = output.index("===SCORE===") + len("===SCORE===")
            end = output.index("===SCORE_END===")
            score_str = output[start:end].strip()
            score = float(score_str)
        except (ValueError, IndexError):
            score = 50.0  # Neutral on parse failure

        try:
            start = output.index("===SCORE_REASONING===") + len("===SCORE_REASONING===")
            end = output.index("===SCORE_REASONING_END===")
            reasoning = output[start:end].strip()
        except (ValueError, IndexError):
            reasoning = ""

        return ReviewScore(score=min(100, max(0, score)), reasoning=reasoning)

"""Claude Code agent: uses `claude` CLI as a fully autonomous CPC agent.

Uses --output-format stream-json to capture tool usage events
and sends them to the CPC server for live activity display.

Usage:
  agent = ClaudeCodeAgent(work_dir="/path/to/task/data")
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

from cpc.agent.base import CPCAgent, ProposalOutput, ReviewScore


class ClaudeCodeAgent(CPCAgent):
    """CPC agent that delegates to `claude` CLI (Claude Code).

    Streams tool_use events to the server for live frontend display.
    """

    def __init__(
        self,
        work_dir: str = ".",
        model: str = "claude-sonnet-4-20250514",
        max_turns: int = 20,
        timeout: int = 600,
        agent_id: str = "",
        server_url: str = "",
        task_id: str = "",
        api_client=None,
    ) -> None:
        self._work_dir = Path(work_dir)
        self._model = model
        self._max_turns = max_turns
        self._timeout = timeout
        self._agent_id = agent_id
        self._server_url = server_url
        self._task_id = task_id
        self._api_client = api_client  # SupabaseAPIClient or None

    def _send_activity(self, activity_type: str, detail: str) -> None:
        """Send activity event (fire-and-forget)."""
        try:
            if self._api_client:
                self._api_client.post("/activity", json={
                    "agent_id": self._agent_id,
                    "task_id": self._task_id,
                    "activity_type": activity_type,
                    "detail": detail,
                })
            elif self._server_url:
                httpx.post(
                    f"{self._server_url}/activity",
                    json={
                        "agent_id": self._agent_id,
                        "task_id": self._task_id,
                        "activity_type": activity_type,
                        "detail": detail,
                    },
                    timeout=5,
                )
        except Exception:
            pass

    async def _run_claude(self, prompt: str, phase: str = "") -> str:
        """Run `claude` CLI with stream-json, send tool_use events in real-time."""
        if phase:
            self._send_activity("status", phase)

        proc = await asyncio.create_subprocess_exec(
            "claude",
            "--print",
            "--model", self._model,
            "--max-turns", str(self._max_turns),
            "--output-format", "stream-json",
            "--verbose",
            "-p", prompt,
            cwd=str(self._work_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        result_text = ""

        try:
            # Read stdout line-by-line as it streams
            while True:
                line = await asyncio.wait_for(
                    proc.stdout.readline(), timeout=self._timeout
                )
                if not line:
                    break  # EOF

                line_str = line.decode("utf-8", errors="replace").strip()
                if not line_str:
                    continue

                try:
                    event = json.loads(line_str)
                except json.JSONDecodeError:
                    continue

                event_type = event.get("type", "")

                # Send tool_use and text events immediately
                if event_type == "assistant":
                    msg = event.get("message", {})
                    content = msg.get("content", [])
                    for block in content:
                        if block.get("type") == "tool_use":
                            tool_name = block.get("name", "?")
                            tool_input = block.get("input", {})
                            detail = self._summarize_tool_use(tool_name, tool_input)
                            self._send_activity("tool_use", detail)
                        elif block.get("type") == "text":
                            text = block.get("text", "")
                            if text.strip():
                                snippet = text.strip().replace("\n", " ")[:120]
                                self._send_activity("thinking", snippet)

                # Capture final result
                if event_type == "result":
                    result_text = event.get("result", "")

        except asyncio.TimeoutError:
            proc.kill()
            return f"[timeout after {self._timeout}s]"

        await proc.wait()

        if proc.returncode != 0 and not result_text:
            result_text = f"[claude exit code: {proc.returncode}]"

        return result_text

    @staticmethod
    def _summarize_tool_use(tool_name: str, tool_input: dict) -> str:
        """Create a human-readable summary of a tool use."""
        if tool_name == "Read":
            path = tool_input.get("file_path", "?")
            return f"Read {path.split('/')[-1]}"
        elif tool_name == "Edit":
            path = tool_input.get("file_path", "?")
            return f"Edit {path.split('/')[-1]}"
        elif tool_name == "Write":
            path = tool_input.get("file_path", "?")
            return f"Write {path.split('/')[-1]}"
        elif tool_name == "Bash":
            cmd = tool_input.get("command", "?")
            return f"Bash: {cmd[:80]}"
        elif tool_name == "Grep":
            pattern = tool_input.get("pattern", "?")
            return f"Grep: {pattern[:60]}"
        elif tool_name == "Glob":
            pattern = tool_input.get("pattern", "?")
            return f"Glob: {pattern[:60]}"
        else:
            return f"{tool_name}"

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
        output = await self._run_claude(prompt, phase="proposing")
        self._send_activity("status", "proposed")
        return self._parse_proposal(output)

    async def score(self, w: str, task_description: str) -> ReviewScore:
        prompt = f"""You are reviewing a shared document as part of a collaborative research process.

## Task
{task_description}

## Document to Evaluate
{w}

## Instructions
You have already read the data files in the previous step. Do NOT read them again.
Based on your understanding from that investigation, rate how good this document is.

You MUST end your response with EXACTLY:
===SCORE===
(A single integer from 0 to 100)
===SCORE_END===
===SCORE_REASONING===
(Brief explanation of your score)
===SCORE_REASONING_END===
"""
        output = await self._run_claude(prompt, phase="scoring")
        result = self._parse_score(output)
        self._send_activity("review_score", f"score={result.score:.0f}")
        return result

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
            score = 50.0

        try:
            start = output.index("===SCORE_REASONING===") + len("===SCORE_REASONING===")
            end = output.index("===SCORE_REASONING_END===")
            reasoning = output[start:end].strip()
        except (ValueError, IndexError):
            reasoning = ""

        return ReviewScore(score=min(100, max(0, score)), reasoning=reasoning)

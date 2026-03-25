"""Anthropic API wrapper for CPC agent operations.

Each method corresponds to a specific step in the CPC generative/inference process:
  - interpret():          p(z^k | w)           generation: internalize shared knowledge
  - design_experiment():  p(a^k | z^k)         generation: design experiment
  - update_hypothesis():  q(z^k | w, o^k)      inference: update hypothesis with data
  - write_proposal():     q(w | z^k')          inference: externalize to proposal
  - score_consistency():  ≈ p(z^B | w)         review: score for MH acceptance
"""

from __future__ import annotations

import json
import re

import anthropic


class ClaudeAPI:
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514") -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def _call(self, system: str, user: str, max_tokens: int = 4096) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text

    def interpret(self, w_current: str, task_description: str, specialization: str = "") -> str:
        """p(z^k | w): Interpret current shared knowledge and form a hypothesis.

        Returns z^k — the agent's internal representation.
        """
        system = f"""You are a research agent specializing in: {specialization or 'general analysis'}.
Your role is to interpret the current shared knowledge and form hypotheses about the research problem."""

        user = f"""## Research Problem
{task_description}

## Current Shared Knowledge (w)
{w_current if w_current else "(No findings yet)"}

## Your Task
Based on the current shared knowledge, form your hypothesis about this problem.
What do you think is going on? What aspects need investigation?
Identify specific questions that need to be answered through experimentation.

Respond with your hypothesis and reasoning."""

        return self._call(system, user)

    def design_experiment(self, z: str, task_description: str) -> str:
        """p(a^k | z^k): Design an experiment based on hypothesis.

        Returns a^k — a shell command or sequence of commands to execute.
        """
        system = """You are a research agent designing experiments.
Output a concrete shell command (or sequence of commands) that will produce data to test the hypothesis.
The command should be executable in an isolated sandbox environment.
Output ONLY the command(s), no explanation. Use bash syntax."""

        user = f"""## Research Problem
{task_description}

## Your Hypothesis
{z}

## Design an Experiment
Write a shell command that will produce data to test your hypothesis.
Output ONLY the command, nothing else."""

        return self._call(system, user, max_tokens=1024)

    def update_hypothesis(self, z: str, o: str, w_current: str) -> str:
        """q(z^k | w, o^k): Update hypothesis with new observations.

        Combines top-down (w) and bottom-up (o) information.
        Returns z^k' — the updated internal representation.
        """
        system = """You are a research agent updating your hypothesis based on new experimental data.
Integrate both the existing shared knowledge (top-down) and your new observations (bottom-up)."""

        user = f"""## Current Shared Knowledge (w, top-down)
{w_current if w_current else "(No findings yet)"}

## Your Previous Hypothesis (z)
{z}

## Experimental Results (o, bottom-up)
{o}

## Update Your Hypothesis
Based on both the existing knowledge and your new data, update your hypothesis.
What do the results tell you? How does this change your understanding?
Be specific about what you now believe and why."""

        return self._call(system, user)

    def write_proposal(self, w_current: str, z_prime: str, o: str) -> str:
        """q(w | z^k'): Externalize updated hypothesis as a proposal document.

        Returns w' — the proposed shared document.
        """
        system = """You are a research agent writing a proposal to update the shared knowledge document.
Write a clear, structured document that incorporates your findings.
This document will be reviewed by other agents for acceptance."""

        user = f"""## Current Shared Knowledge (w)
{w_current if w_current else "(No findings yet)"}

## Your Updated Hypothesis (z')
{z_prime}

## Your Experimental Evidence (o)
{o}

## Write Proposal
Write an updated version of the shared knowledge document that incorporates your findings.
Structure it clearly with sections for: Findings, Evidence, and Remaining Questions.
Build on the existing document — don't discard previous findings unless your evidence contradicts them."""

        return self._call(system, user)

    def score_consistency(self, w: str, z: str, o: str) -> float:
        """Approximate p(z^B | w) via consistency scoring.

        Asks the LLM to rate how consistent the reviewer's hypothesis (z)
        and observations (o) are with a given document (w).
        Returns a score from 0 to 100.
        """
        system = """You are evaluating the consistency between a document and your own research findings.
You MUST respond with ONLY a JSON object: {"score": <number 0-100>, "reasoning": "<brief explanation>"}
Score 0 = completely inconsistent, 100 = perfectly consistent."""

        user = f"""## Document to Evaluate
{w}

## Your Hypothesis
{z}

## Your Experimental Observations
{o}

Rate the consistency between this document and your hypothesis/observations.
Respond with ONLY JSON: {{"score": <0-100>, "reasoning": "<brief>"}}"""

        response = self._call(system, user, max_tokens=256)

        # Parse score from response
        try:
            # Try to extract JSON from response
            match = re.search(r"\{[^}]*\"score\"\s*:\s*(\d+(?:\.\d+)?)[^}]*\}", response)
            if match:
                return float(match.group(1))
            # Fallback: try to parse as pure JSON
            data = json.loads(response)
            return float(data["score"])
        except (json.JSONDecodeError, KeyError, ValueError):
            return 50.0  # Neutral score on parse failure

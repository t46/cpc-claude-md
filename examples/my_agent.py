"""Example: custom CPC agent using OpenAI API.

This shows how to implement CPCAgent with any LLM or tool.
To use:
  uv run python scripts/run_agent.py \
    --task-id my-task \
    --agent-type custom \
    --agent-module examples/my_agent.py
"""

from __future__ import annotations

from cpc.agent.base import CPCAgent, ProposalOutput, ReviewScore


class MyCustomAgent(CPCAgent):
    """Example custom agent. Replace with your own logic."""

    async def propose(self, w_current: str, task_description: str) -> ProposalOutput:
        # Your agent's investigation logic here.
        # You can:
        #   - Call any LLM API (OpenAI, Gemini, Ollama, etc.)
        #   - Run shell commands
        #   - Read/write files
        #   - Use MCP tools
        #   - Do anything you want

        # Example: just echo back (replace with real logic)
        return ProposalOutput(
            proposed_w=f"(Findings from MyCustomAgent)\n{w_current}",
            reasoning="My hypothesis based on investigation",
            observation_summary="What I observed during investigation",
        )

    async def score(self, w: str, task_description: str) -> ReviewScore:
        # Score how consistent this document is with your findings.
        # Return 0-100.
        return ReviewScore(score=50.0, reasoning="Neutral score")


# Optional: factory function for more complex initialization
def create_agent(config) -> CPCAgent:
    """Called by run_agent.py if it exists."""
    return MyCustomAgent()

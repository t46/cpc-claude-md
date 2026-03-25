"""Start a CPC agent.

Usage:
  # Claude Code agent (autonomous, uses `claude` CLI):
  uv run python scripts/run_agent.py --task-id my-task --agent-type code

  # LLM API agent (step-by-step, uses Anthropic API + Docker sandbox):
  uv run python scripts/run_agent.py --task-id my-task --agent-type llm --sandbox docker

  # Custom agent (implement CPCAgent in your own module):
  uv run python scripts/run_agent.py --task-id my-task --agent-type custom --agent-module my_agent.py
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import logging
import sys
import uuid

from cpc.agent.base import CPCAgent
from cpc.agent.runner import AgentRunner
from cpc.config import AgentConfig


def create_agent(args: argparse.Namespace, config: AgentConfig) -> CPCAgent:
    if args.agent_type == "code":
        from cpc.agent.claude_code_agent import ClaudeCodeAgent
        return ClaudeCodeAgent(
            work_dir=args.work_dir,
            model=config.model_name,
        )

    elif args.agent_type == "llm":
        from cpc.agent.claude_api import ClaudeAPI
        from cpc.agent.llm_agent import LLMAgent

        if config.sandbox_type == "docker":
            from cpc.sandbox.docker_sandbox import DockerSandbox
            sandbox = DockerSandbox(image=config.docker_image)
        else:
            from cpc.sandbox.worktree_sandbox import WorktreeSandbox
            sandbox = WorktreeSandbox()

        return LLMAgent(
            claude=ClaudeAPI(api_key=config.anthropic_api_key, model=config.model_name),
            sandbox=sandbox,
            specialization=config.specialization,
        )

    elif args.agent_type == "custom":
        # Load a custom CPCAgent from a Python file
        if not args.agent_module:
            print("Error: --agent-module is required for --agent-type custom")
            sys.exit(1)

        spec = importlib.util.spec_from_file_location("custom_agent", args.agent_module)
        if spec is None or spec.loader is None:
            print(f"Error: cannot load {args.agent_module}")
            sys.exit(1)

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Look for a create_agent() factory or the first CPCAgent subclass
        if hasattr(module, "create_agent"):
            return module.create_agent(config)

        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (isinstance(attr, type)
                    and issubclass(attr, CPCAgent)
                    and attr is not CPCAgent):
                return attr()

        print(f"Error: no CPCAgent subclass or create_agent() found in {args.agent_module}")
        sys.exit(1)

    else:
        print(f"Unknown agent type: {args.agent_type}")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="CPC Agent Runner")
    parser.add_argument("--server-url", default="http://localhost:8000")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--agent-id", default="")
    parser.add_argument("--specialization", default="")
    parser.add_argument("--agent-type", choices=["llm", "code", "custom"], default="code")
    parser.add_argument("--agent-module", default="", help="Path to custom agent .py file")
    parser.add_argument("--work-dir", default=".", help="Working directory for Claude Code agents")
    parser.add_argument("--sandbox", choices=["worktree", "docker"], default="docker")
    parser.add_argument("--docker-image", default="python:3.12-slim")
    parser.add_argument("--max-rounds", type=int, default=None)
    parser.add_argument("--api-key", default="")
    parser.add_argument("--model", default="claude-sonnet-4-20250514")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

    config = AgentConfig(
        server_url=args.server_url,
        agent_id=args.agent_id or f"agent-{uuid.uuid4().hex[:8]}",
        task_id=args.task_id,
        specialization=args.specialization,
        sandbox_type=args.sandbox,
        docker_image=args.docker_image,
        anthropic_api_key=args.api_key or AgentConfig().anthropic_api_key,
        model_name=args.model,
    )

    # Fetch task's docker_image from server (overrides CLI default)
    if config.sandbox_type == "docker":
        try:
            import httpx
            resp = httpx.get(f"{config.server_url}/tasks/{config.task_id}", timeout=10)
            if resp.status_code == 200:
                task_image = resp.json().get("docker_image", "")
                if task_image:
                    config.docker_image = task_image
                    logging.info(f"Using task's Docker image: {task_image}")
        except Exception as e:
            logging.warning(f"Could not fetch task docker_image, using default: {e}")

    agent = create_agent(args, config)
    runner = AgentRunner(config=config, agent=agent)

    asyncio.run(runner.run_loop(max_rounds=args.max_rounds))


if __name__ == "__main__":
    main()

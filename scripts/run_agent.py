"""Start a CPC agent.

Usage:
  # Claude Code agent (recommended):
  uv run python scripts/run_agent.py --task-id cpc-camp-2026-summary --server-url http://SERVER:8111

  # Custom agent:
  uv run python scripts/run_agent.py --task-id my-task --agent-type custom --agent-module my_agent.py
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import logging
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

from cpc.agent.base import CPCAgent
from cpc.agent.runner import AgentRunner
from cpc.config import AgentConfig


def setup_work_dir(data_dir: str, work_dir: str | None) -> str:
    """Set up a work directory with task data files.

    If data_dir is specified in the task, copies its contents to work_dir.
    If work_dir is not specified, creates a temporary directory.
    """
    if work_dir:
        dst = Path(work_dir)
    else:
        dst = Path(tempfile.mkdtemp(prefix="cpc-agent-"))

    dst.mkdir(parents=True, exist_ok=True)

    if data_dir:
        src = Path(data_dir)
        if src.exists():
            for f in src.iterdir():
                if f.is_file() and not f.name.startswith("."):
                    shutil.copy2(f, dst / f.name)
            logging.info(f"Copied task data from {src} to {dst}")
        else:
            logging.warning(f"data_dir {src} not found")

    return str(dst)


def create_agent(args: argparse.Namespace, config: AgentConfig, work_dir: str) -> CPCAgent:
    if args.agent_type == "code":
        from cpc.agent.claude_code_agent import ClaudeCodeAgent
        return ClaudeCodeAgent(
            work_dir=work_dir,
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
        if not args.agent_module:
            print("Error: --agent-module is required for --agent-type custom")
            sys.exit(1)

        spec = importlib.util.spec_from_file_location("custom_agent", args.agent_module)
        if spec is None or spec.loader is None:
            print(f"Error: cannot load {args.agent_module}")
            sys.exit(1)

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

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
    parser.add_argument("--work-dir", default="", help="Working directory (auto-created if empty)")
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

    # Fetch task info from server to get data_dir
    data_dir = ""
    try:
        import httpx
        resp = httpx.get(f"{config.server_url}/tasks/{config.task_id}", timeout=10)
        if resp.status_code == 200:
            task_info = resp.json()
            data_dir = task_info.get("data_dir", "")
    except Exception as e:
        logging.warning(f"Could not fetch task info: {e}")

    # Set up work directory with task data
    work_dir = setup_work_dir(data_dir, args.work_dir or "")
    logging.info(f"Work directory: {work_dir}")

    agent = create_agent(args, config, work_dir)
    runner = AgentRunner(config=config, agent=agent)

    asyncio.run(runner.run_loop(max_rounds=args.max_rounds))


if __name__ == "__main__":
    main()

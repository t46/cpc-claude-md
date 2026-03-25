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


def setup_work_dir(data_dir: str, work_dir: str | None, specialization: str = "") -> str:
    """Set up a work directory with task data files.

    If specialization is set (e.g. "day1"), only copies the matching file
    (e.g. day1.md) — prevents the agent from seeing other agents' data.
    """
    if work_dir:
        dst = Path(work_dir)
    else:
        dst = Path(tempfile.mkdtemp(prefix="cpc-agent-"))

    dst.mkdir(parents=True, exist_ok=True)

    if data_dir:
        src = Path(data_dir)
        if src.exists():
            copied = []
            for f in src.iterdir():
                if f.is_file() and not f.name.startswith("."):
                    # If specialization is set, only copy matching file
                    if specialization and not f.stem == specialization:
                        continue
                    shutil.copy2(f, dst / f.name)
                    copied.append(f.name)
            logging.info(f"Copied {copied} from {src} to {dst}")
        else:
            logging.warning(f"data_dir {src} not found")

    return str(dst)


def create_agent(args: argparse.Namespace, config: AgentConfig, work_dir: str) -> CPCAgent:
    if args.agent_type == "code":
        from cpc.agent.claude_code_agent import ClaudeCodeAgent
        return ClaudeCodeAgent(
            work_dir=work_dir,
            model=config.model_name,
            agent_id=config.agent_id,
            server_url="" if args.supabase_url else config.server_url,
            task_id=config.task_id,
            api_client=getattr(args, '_api_client', None),
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
    parser.add_argument("--server-url", default="http://localhost:8000",
                        help="FastAPI server URL (ignored if --supabase-url is set)")
    parser.add_argument("--supabase-url", default="", help="Supabase project URL (no FastAPI needed)")
    parser.add_argument("--supabase-key", default="", help="Supabase anon key")
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

    # Create HTTP client — Supabase direct or FastAPI
    if args.supabase_url and args.supabase_key:
        from cpc.supabase_client import SupabaseAPIClient
        http_client = SupabaseAPIClient(args.supabase_url, args.supabase_key)
        args._api_client = http_client  # Pass to ClaudeCodeAgent for activity
        logging.info(f"Using Supabase direct mode: {args.supabase_url}")
    else:
        http_client = None
        args._api_client = None

    # Fetch task info to get data_dir and auto-assign specialization
    data_dir = ""
    try:
        if http_client:
            task_info = http_client.get(f"/tasks/{config.task_id}").json()
        else:
            import httpx
            resp = httpx.get(f"{config.server_url}/tasks/{config.task_id}", timeout=10)
            task_info = resp.json() if resp.status_code == 200 else {}
        data_dir = task_info.get("data_dir", "")

        # Auto-assign specialization if task has agent_specializations and none specified
        specs = task_info.get("agent_specializations", [])
        if specs and not config.specialization:
            # Get current agents to determine our index
            if http_client:
                agents = http_client.get("/agents").json()
            else:
                agents = httpx.get(f"{config.server_url}/agents", timeout=10).json()
            agent_count = len(agents)
            spec_index = agent_count % len(specs)  # Wrap around if more agents than specs
            config.specialization = specs[spec_index]
            logging.info(f"Auto-assigned specialization: {config.specialization}")
    except Exception as e:
        logging.warning(f"Could not fetch task info: {e}")

    # Set up work directory with task data
    work_dir = setup_work_dir(data_dir, args.work_dir or "", config.specialization)
    logging.info(f"Work directory: {work_dir}")

    agent = create_agent(args, config, work_dir)

    # Inject Supabase client into runner if available
    runner = AgentRunner(config=config, agent=agent)
    if http_client:
        runner._http = http_client

    asyncio.run(runner.run_loop(max_rounds=args.max_rounds))


if __name__ == "__main__":
    main()

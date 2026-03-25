"""Configuration for CPC server and agent."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class ServerConfig(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8000
    data_dir: str = "data"
    round_timeout_seconds: int = 600
    min_agents_for_round: int = 2
    max_agents_per_round: int = 100
    supabase_url: str = ""
    supabase_key: str = ""

    model_config = {"env_prefix": "CPC_SERVER_", "env_file": ".env", "extra": "ignore"}


class AgentConfig(BaseSettings):
    server_url: str = "http://localhost:8000"
    agent_id: str = ""
    anthropic_api_key: str = ""
    model_name: str = "claude-sonnet-4-20250514"
    specialization: str = ""
    task_id: str = ""
    sandbox_type: str = "worktree"  # "worktree" or "docker"
    docker_image: str = "python:3.12-slim"

    model_config = {"env_prefix": "CPC_AGENT_", "env_file": ".env", "extra": "ignore"}

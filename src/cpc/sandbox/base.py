"""Abstract sandbox interface for experiment execution.

The sandbox isolates each agent's experiments to ensure i.i.d. sampling:
  o^k ~ p(o | a^k)  independent across agents
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class Sandbox(ABC):
    @abstractmethod
    async def setup(self) -> None:
        """Initialize the isolated environment."""
        ...

    @abstractmethod
    async def execute(self, command: str) -> str:
        """Execute a command and return its output (o^k)."""
        ...

    @abstractmethod
    async def teardown(self) -> None:
        """Clean up the isolated environment."""
        ...

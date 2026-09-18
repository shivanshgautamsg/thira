"""Base Agent interface — the contract all execution agents implement."""

from __future__ import annotations

from abc import ABC, abstractmethod

from shared.enums import AgentState
from shared.models import AgentResult, Capability


class BaseAgent(ABC):
    """Base class for all THIRA execution agents.

    Every agent (Gmail, Browser, Terminal, ARTEMIS, etc.) implements this interface.
    The Agent Bus discovers and routes to agents through this contract.
    """

    def __init__(self):
        self._state = AgentState.REGISTERED

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for this agent (e.g., 'gmail', 'terminal', 'artemis')."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what this agent does."""
        ...

    @abstractmethod
    def capabilities(self) -> list[Capability]:
        """List of capabilities (tools) this agent exposes."""
        ...

    @abstractmethod
    async def execute(self, tool: str, arguments: dict) -> AgentResult:
        """Execute a specific tool with the given arguments.

        Args:
            tool: The tool name to execute.
            arguments: Tool-specific arguments.

        Returns:
            AgentResult with success status, output, and optional evidence.
        """
        ...

    async def initialize(self) -> None:
        """Initialize the agent (e.g., authenticate, connect). Override if needed."""
        self._state = AgentState.READY

    async def health_check(self) -> bool:
        """Check if the agent is operational. Override for custom checks."""
        return self._state == AgentState.READY

    @property
    def state(self) -> AgentState:
        return self._state

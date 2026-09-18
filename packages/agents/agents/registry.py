"""Agent Registry — Central registry and router for all agents."""

from __future__ import annotations

import time

import structlog

from agents.base import BaseAgent
from shared.models import (
    PlanStep,
    StepResult,
    ToolDescriptor,
)
from shared.security.audit import AuditTrail

logger = structlog.get_logger()


class AgentRegistry:
    """Central registry for all available agents.

    Handles registration, discovery, and health management.
    """

    def __init__(self):
        self._agents: dict[str, BaseAgent] = {}
        self._capability_index: dict[str, str] = {}  # tool_name → agent_name

    async def register(self, agent: BaseAgent) -> None:
        """Register an agent and index its capabilities."""
        await agent.initialize()
        self._agents[agent.name] = agent

        for cap in agent.capabilities():
            self._capability_index[cap.name] = agent.name
            # Also register with agent prefix for disambiguation
            self._capability_index[f"{agent.name}.{cap.name}"] = agent.name

        logger.info(
            "registry.agent_registered",
            agent=agent.name,
            capabilities=[c.name for c in agent.capabilities()],
            state=agent.state.value,
        )

    async def discover_tools(self) -> list[ToolDescriptor]:
        """Return all available tools across all agents."""
        tools = []
        for agent in self._agents.values():
            for cap in agent.capabilities():
                tools.append(
                    ToolDescriptor(
                        agent=agent.name,
                        tool=cap.name,
                        description=cap.description,
                        input_schema=cap.input_schema,
                        annotations=cap.annotations,
                    )
                )
        return tools

    async def route(self, tool_name: str) -> BaseAgent:
        """Find the agent responsible for a given tool."""
        agent_name = self._capability_index.get(tool_name)
        if not agent_name:
            raise ToolNotFoundError(f"No agent registered for tool: {tool_name}")
        agent = self._agents.get(agent_name)
        if not agent:
            raise ToolNotFoundError(f"Agent '{agent_name}' not found")
        return agent

    def list_agents(self) -> list[dict]:
        """List all registered agents and their status."""
        return [
            {
                "name": agent.name,
                "description": agent.description,
                "state": agent.state.value,
                "capabilities": [c.name for c in agent.capabilities()],
            }
            for agent in self._agents.values()
        ]


class AgentBus:
    """Routes plan steps to the correct agent and tool.

    This is the bridge between THIRA's thinking and the digital world's doing.
    """

    def __init__(self, registry: AgentRegistry, audit: AuditTrail | None = None):
        self.registry = registry
        self._audit = audit

    async def dispatch(self, step: PlanStep) -> StepResult:
        """Execute a single plan step by routing to the appropriate agent."""
        # Determine tool name — try agent.tool first, then just tool
        tool_name = f"{step.agent}.{step.tool}"
        try:
            agent = await self.registry.route(tool_name)
        except ToolNotFoundError:
            agent = await self.registry.route(step.tool)

        logger.info(
            "agent_bus.dispatching",
            agent=agent.name,
            tool=step.tool,
            step_index=step.index,
        )

        start = time.monotonic()
        try:
            result = await agent.execute(step.tool, step.arguments)
            duration_ms = int((time.monotonic() - start) * 1000)

            step_result = StepResult(
                step_index=step.index,
                success=result.success,
                output=result.output,
                error=result.error,
                duration_ms=duration_ms,
                evidence=result.evidence,
            )

            # Audit the action
            if self._audit:
                await self._audit.record(
                    action=f"{step.agent}.{step.tool}",
                    agent=agent.name,
                    tool=step.tool,
                    arguments=step.arguments,
                    result_summary="success" if result.success else f"failed: {result.error}",
                    policy_verdict="allowed",
                )

            logger.info(
                "agent_bus.dispatched",
                agent=agent.name,
                tool=step.tool,
                success=result.success,
                duration_ms=duration_ms,
            )

            return step_result

        except Exception as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.error(
                "agent_bus.dispatch_error",
                agent=agent.name,
                tool=step.tool,
                error=str(e),
                exc_info=True,
            )
            return StepResult(
                step_index=step.index,
                success=False,
                error=str(e),
                duration_ms=duration_ms,
            )


class ToolNotFoundError(Exception):
    """Raised when no agent is registered for the requested tool."""

    pass

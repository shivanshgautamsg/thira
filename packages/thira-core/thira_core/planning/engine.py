"""Planning Engine implementation.

Generates executable step-by-step plans from decisions.
Plans are DAGs of PlanSteps, each mapping to an agent + tool invocation.
"""

from __future__ import annotations

import json

import structlog

from shared.enums import PlanStatus
from shared.llm.provider import LLMMessage, LLMProvider
from shared.models import Decision, Plan, PlanStep, ToolDescriptor

logger = structlog.get_logger()


class PlanningEngine:
    """Generates executable plans from decisions.

    Given a decision to act, the Planning Engine:
    1. Considers available tools/agents
    2. Generates a step-by-step plan via LLM
    3. Structures it as a DAG of PlanSteps
    4. Validates tool references
    """

    def __init__(self, llm: LLMProvider, available_tools: list[ToolDescriptor] | None = None):
        self._llm = llm
        self._available_tools = available_tools or []

    def update_available_tools(self, tools: list[ToolDescriptor]) -> None:
        """Update the list of available tools (called after agent registration)."""
        self._available_tools = tools

    async def generate(self, decision: Decision, world_model: object) -> Plan:
        """Generate a plan for executing a decision.

        Uses LLM to decompose the decision's goal into concrete steps,
        each mapped to an available agent and tool.
        """
        tools_description = self._describe_tools()

        response = await self._llm.complete(
            messages=[
                LLMMessage(role="system", content=PLANNING_SYSTEM_PROMPT),
                LLMMessage(
                    role="user",
                    content=self._build_planning_prompt(decision, tools_description),
                ),
            ],
            json_mode=True,
            temperature=0.3,
            purpose="plan_generation",
        )

        try:
            result = json.loads(response.content)
            steps_data = result.get("steps", [])

            steps = [
                PlanStep(
                    index=i,
                    description=s.get("description", ""),
                    agent=s.get("agent", "terminal"),
                    tool=s.get("tool", "execute_command"),
                    arguments=s.get("arguments", {}),
                    depends_on=s.get("depends_on", []),
                )
                for i, s in enumerate(steps_data)
            ]

            plan = Plan(
                decision_id=decision.id,
                goal=result.get("goal", decision.reasoning),
                steps=steps,
                status=PlanStatus.PENDING,
                requires_approval=result.get("requires_approval", False),
            )

            logger.info(
                "planning.generated",
                plan_id=str(plan.id),
                goal=plan.goal[:100],
                steps=len(steps),
                requires_approval=plan.requires_approval,
            )

            return plan

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("planning.parse_failed", error=str(e))
            # Fallback: single-step plan
            return Plan(
                decision_id=decision.id,
                goal=decision.reasoning,
                steps=[
                    PlanStep(
                        index=0,
                        description="Execute the requested action",
                        agent="terminal",
                        tool="execute_command",
                        arguments={"reasoning": decision.reasoning},
                    )
                ],
                requires_approval=True,
            )

    async def replan(self, plan: Plan, failure_reason: str) -> Plan:
        """Generate an alternative plan after a failure.

        V1: Simple stub. Phase 2 will implement intelligent replanning.
        """
        logger.info(
            "planning.replanning",
            original_plan_id=str(plan.id),
            failure_reason=failure_reason[:100],
        )
        # For now, return the original plan marked as needing approval
        plan.requires_approval = True
        return plan

    def _describe_tools(self) -> str:
        """Generate a description of available tools for the LLM."""
        if not self._available_tools:
            return "Available tools: terminal (execute_command), filesystem (read_file, write_file, list_directory)"

        lines = []
        for tool in self._available_tools:
            lines.append(f"- {tool.agent}.{tool.tool}: {tool.description}")
        return "Available tools:\n" + "\n".join(lines)

    def _build_planning_prompt(self, decision: Decision, tools_description: str) -> str:
        """Build the planning prompt."""
        return f"""Generate a step-by-step execution plan for this decision.

DECISION:
Action: {decision.action.value}
Reasoning: {decision.reasoning}
Urgency: {decision.scores.urgency}
Importance: {decision.scores.importance}
Risk: {decision.scores.risk}

{tools_description}
"""


PLANNING_SYSTEM_PROMPT = """You are a planning engine for an autonomous agent platform called THIRA.

Given a decision to act and a list of available tools, generate a step-by-step execution plan.

Return a JSON object:
{
    "goal": "Brief description of what this plan achieves",
    "requires_approval": true/false,
    "steps": [
        {
            "description": "Human-readable description of this step",
            "agent": "agent_name",
            "tool": "tool_name",
            "arguments": { ... },
            "depends_on": [0, 1]  // indices of steps this depends on (empty for first steps)
        }
    ]
}

Rules:
- Each step must map to an available tool
- Steps should be ordered logically (dependencies first)
- Set requires_approval=true for plans that send external messages, modify important data, or have irreversible effects
- Keep plans concise — prefer fewer, well-defined steps
- If a tool doesn't exist for a step, use terminal.execute_command as fallback
- Always include a verification step at the end if the plan modifies external state"""

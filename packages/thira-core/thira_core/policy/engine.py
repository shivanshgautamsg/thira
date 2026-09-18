"""Policy Engine implementation.

Controls what THIRA is allowed to do based on autonomy levels,
tool annotations, user-defined policies, and risk assessment.
"""

from __future__ import annotations

import structlog

from shared.enums import AutonomyLevel, PolicyVerdict, RiskLevel
from shared.models import Action, AuthorizedPlan, Plan, PlanStep, PolicyCheckResult, ToolAnnotation

logger = structlog.get_logger()

# Default tool annotations when none are registered
_DEFAULT_ANNOTATIONS = ToolAnnotation(
    autonomy_level=AutonomyLevel.L3_EXECUTE_APPROVED,
    reversible=False,
    risk=RiskLevel.MEDIUM,
)


class PolicyEngine:
    """Controls what THIRA is allowed to do.

    Evaluates every planned action against:
    1. Tool annotations (autonomy_level, risk, reversibility)
    2. User-defined policies (per agent/tool overrides)
    3. Global safety rules (critical risk = always blocked)

    Autonomy levels (L0–L5):
    - L0: Observe only
    - L1: Recommend
    - L2: Prepare (draft)
    - L3: Execute with approval
    - L4: Execute autonomously (reversible)
    - L5: Fully autonomous
    """

    def __init__(
        self,
        default_autonomy: AutonomyLevel = AutonomyLevel.L3_EXECUTE_APPROVED,
        tool_annotations: dict[str, ToolAnnotation] | None = None,
    ):
        self._default_autonomy = default_autonomy
        self._tool_annotations = tool_annotations or {}
        self._user_policies: dict[str, AutonomyLevel] = {}

    def register_tool_annotations(self, agent: str, tool: str, annotations: ToolAnnotation) -> None:
        """Register annotations for a specific tool."""
        key = f"{agent}.{tool}"
        self._tool_annotations[key] = annotations

    def set_user_policy(self, agent: str, tool: str, level: AutonomyLevel) -> None:
        """Set user-defined autonomy level for a specific agent+tool."""
        key = f"{agent}.{tool}"
        self._user_policies[key] = level

    async def authorize(self, plan: Plan) -> AuthorizedPlan:
        """Evaluate every step in a plan against autonomy policies.

        Returns an AuthorizedPlan indicating which steps need approval
        and which can execute automatically.
        """
        approval_steps: list[PlanStep] = []
        auto_steps: list[PlanStep] = []

        for step in plan.steps:
            verdict = await self.check_action(
                Action(
                    agent=step.agent,
                    tool=step.tool,
                    arguments=step.arguments,
                )
            )

            if verdict.verdict == PolicyVerdict.ALLOWED:
                auto_steps.append(step)
            elif verdict.verdict == PolicyVerdict.REQUIRES_APPROVAL:
                approval_steps.append(step)
            elif verdict.verdict == PolicyVerdict.BLOCKED:
                logger.warning(
                    "policy.step_blocked",
                    agent=step.agent,
                    tool=step.tool,
                    reason=verdict.reason,
                )
                approval_steps.append(step)  # Blocked steps need explicit override

        requires_approval = len(approval_steps) > 0 or plan.requires_approval

        logger.info(
            "policy.authorized",
            plan_id=str(plan.id),
            total_steps=len(plan.steps),
            auto_approved=len(auto_steps),
            needs_approval=len(approval_steps),
        )

        return AuthorizedPlan(
            plan=plan,
            requires_approval=requires_approval,
            approval_steps=approval_steps,
            auto_approved_steps=auto_steps,
        )

    async def check_action(self, action: Action) -> PolicyCheckResult:
        """Check a single action against policy rules."""
        key = f"{action.agent}.{action.tool}"
        annotations = self._tool_annotations.get(key, _DEFAULT_ANNOTATIONS)

        # Rule 1: Critical risk = always blocked unless explicitly overridden
        if annotations.risk == RiskLevel.CRITICAL:
            return PolicyCheckResult(
                verdict=PolicyVerdict.BLOCKED,
                reason="Critical risk — requires explicit authorization",
                required_level=AutonomyLevel.L5_AUTONOMOUS,
                granted_level=self._default_autonomy,
            )

        # Rule 2: Check user-specific policy override
        user_level = self._user_policies.get(key)
        if user_level is None:
            # Check wildcard policy
            user_level = self._user_policies.get(f"{action.agent}.*")
        if user_level is None:
            user_level = self._user_policies.get("*.*")
        if user_level is None:
            user_level = self._default_autonomy

        required_level = annotations.autonomy_level

        # Rule 3: Compare levels
        if user_level.value >= required_level.value:
            return PolicyCheckResult(
                verdict=PolicyVerdict.ALLOWED,
                required_level=required_level,
                granted_level=user_level,
            )
        else:
            return PolicyCheckResult(
                verdict=PolicyVerdict.REQUIRES_APPROVAL,
                reason=f"Requires L{required_level.value}, granted L{user_level.value}",
                required_level=required_level,
                granted_level=user_level,
            )

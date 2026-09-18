"""THIRA Orchestrator — The THIRA loop controller.

Drives: PERCEIVE → UNDERSTAND → DECIDE → PLAN → AUTHORIZE → ACT → VERIFY → LEARN
"""

from __future__ import annotations

import time
import uuid

import structlog

from shared.enums import DecisionAction, ExecutionStatus, PlanStatus, RecoveryAction
from shared.events import EnrichedEvent, ThiraEvent
from shared.models import (
    AuthorizedPlan,
    Decision,
    Execution,
    LoopResult,
)

logger = structlog.get_logger()

# Type aliases for engine protocols — these will be replaced with actual
# Protocol classes when each engine is implemented in Phase 1.
# For now, we use `object` so the orchestrator skeleton compiles.
from datetime import UTC
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from thira_core.context.engine import ContextEngine
    from thira_core.decision.engine import DecisionEngine
    from thira_core.failure.engine import FailureEngine
    from thira_core.perception.engine import PerceptionEngine
    from thira_core.planning.engine import PlanningEngine
    from thira_core.policy.engine import PolicyEngine
    from thira_core.verification.engine import VerificationEngine
    from thira_core.world_model.model import WorldModel


class ThiraOrchestrator:
    """The central THIRA loop controller.

    This is the heart of the platform. It drives the complete agentic loop:
    PERCEIVE → UNDERSTAND → DECIDE → PLAN → AUTHORIZE → ACT → VERIFY → LEARN

    Each step delegates to a specialized engine.
    """

    def __init__(
        self,
        perception: PerceptionEngine,
        context: ContextEngine,
        world_model: WorldModel,
        decision: DecisionEngine,
        planning: PlanningEngine,
        policy: PolicyEngine,
        agent_bus: object,  # AgentBus — implemented in Phase 1
        verification: VerificationEngine,
        failure: FailureEngine,
        echo: object,  # EchoEngine — implemented in Phase 1
        jarvis: object,  # JarvisNotifier — implemented in Phase 1
    ):
        self.perception = perception
        self.context = context
        self.world_model = world_model
        self.decision = decision
        self.planning = planning
        self.policy = policy
        self.agent_bus = agent_bus
        self.verification = verification
        self.failure = failure
        self.echo = echo
        self.jarvis = jarvis

        self._pending_approvals: dict[uuid.UUID, dict] = {}
        self._running = False
        logger.info("orchestrator.initialized")

    async def run_loop(self) -> None:
        """Main event loop — continuously processes events from the perception engine."""
        self._running = True
        logger.info("orchestrator.loop_started")

        async for event in self.perception.stream():
            if not self._running:
                break
            try:
                result = await self.process_event(event)
                logger.info(
                    "orchestrator.loop_iteration",
                    event_id=str(event.id),
                    status=result.status,
                )
            except Exception as e:
                logger.error(
                    "orchestrator.loop_error",
                    event_id=str(event.id),
                    error=str(e),
                    exc_info=True,
                )

        logger.info("orchestrator.loop_stopped")

    async def process_event(self, event: ThiraEvent) -> LoopResult:
        """Single iteration of the THIRA loop.

        This is the core method — it takes one event through the complete
        agentic pipeline: perceive → understand → decide → plan → authorize → act → verify → learn.
        """
        trace_id = f"trace_{uuid.uuid4().hex[:12]}"
        start = time.monotonic()

        logger.info(
            "orchestrator.processing",
            trace_id=trace_id,
            event_id=str(event.id),
            source=event.source.value,
            type=event.type.value,
        )

        # ─── 1. UNDERSTAND — Enrich with context ─────────────────
        enriched = await self.context.enrich(event, self.world_model)

        logger.debug(
            "orchestrator.context_enriched",
            trace_id=trace_id,
            entities=len(enriched.resolved_entities),
            context_items=len(enriched.related_context),
            interpretation=enriched.interpretation[:100] if enriched.interpretation else "",
        )

        # ─── 2. DECIDE — Should we act? ──────────────────────────
        decision = await self.decision.evaluate(enriched, self.world_model)

        logger.info(
            "orchestrator.decision",
            trace_id=trace_id,
            action=decision.action.value,
            urgency=decision.scores.urgency,
            importance=decision.scores.importance,
            confidence=decision.scores.confidence,
        )

        if decision.action == DecisionAction.IGNORE:
            return LoopResult(
                status="ignored",
                trace_id=trace_id,
                response=f"Event noted but no action required: {decision.reasoning}",
            )

        if decision.action == DecisionAction.DEFER:
            return LoopResult(
                status="deferred",
                trace_id=trace_id,
                response=f"Deferring action: {decision.reasoning}",
            )

        # ─── 3. PLAN — How should we act? ────────────────────────
        plan = await self.planning.generate(decision, self.world_model)

        logger.info(
            "orchestrator.plan_generated",
            trace_id=trace_id,
            plan_id=str(plan.id),
            goal=plan.goal,
            steps=len(plan.steps),
        )

        # ─── 4. AUTHORIZE — Are we allowed? ──────────────────────
        authorized_plan = await self.policy.authorize(plan)

        if authorized_plan.requires_approval:
            logger.info(
                "orchestrator.approval_required",
                trace_id=trace_id,
                plan_id=str(plan.id),
                approval_steps=len(authorized_plan.approval_steps),
            )
            # Store pending approval context for resumption
            self._pending_approvals[plan.id] = {
                "authorized_plan": authorized_plan,
                "event": event,
                "enriched": enriched,
                "decision": decision,
                "trace_id": trace_id,
            }
            # Notify JARVIS to request user approval
            if self.jarvis and hasattr(self.jarvis, "request_approval"):
                await self.jarvis.request_approval(authorized_plan)
            return LoopResult(
                status="awaiting_approval",
                trace_id=trace_id,
                plan_id=plan.id,
                response=f"Plan requires your approval for {len(authorized_plan.approval_steps)} step(s).",
            )

        # ─── 5. ACT — Execute the plan ───────────────────────────
        execution = await self._execute_plan(authorized_plan, trace_id)

        # ─── 6. VERIFY — Did it work? ────────────────────────────
        verification = await self.verification.verify(execution)

        logger.info(
            "orchestrator.verified",
            trace_id=trace_id,
            passed=verification.passed,
            summary=verification.summary,
        )

        # ─── 7. LEARN — Record experience ────────────────────────
        experience = await self.echo.record(
            event=event,
            enriched=enriched,
            decision=decision,
            plan=plan,
            execution=execution,
            verification=verification,
        )

        # Update world model with execution outcomes
        await self.world_model.apply_execution(execution, verification)

        duration_ms = int((time.monotonic() - start) * 1000)

        logger.info(
            "orchestrator.completed",
            trace_id=trace_id,
            duration_ms=duration_ms,
            success=verification.passed,
        )

        return LoopResult(
            status="completed",
            trace_id=trace_id,
            plan_id=plan.id,
            execution_id=execution.id,
            experience_id=experience.id,
            response=verification.summary,
        )

    async def _execute_plan(self, plan: AuthorizedPlan, trace_id: str) -> Execution:
        """Execute a plan step-by-step via the agent bus."""
        execution = Execution(
            plan_id=plan.plan.id,
            status=ExecutionStatus.RUNNING,
        )

        for step in plan.plan.steps:
            logger.info(
                "orchestrator.executing_step",
                trace_id=trace_id,
                step_index=step.index,
                agent=step.agent,
                tool=step.tool,
            )

            try:
                result = await self.agent_bus.dispatch(step)
                execution.record_step(step, result)

                if not result.success:
                    recovery = await self.failure.handle(step, result=result)
                    execution.record_recovery(recovery)
                    if recovery.action == RecoveryAction.ABORT:
                        execution.status = ExecutionStatus.ABORTED
                        execution.error = f"Aborted at step {step.index}: {result.error}"
                        break
                    elif recovery.action == RecoveryAction.SKIP:
                        continue
                    elif recovery.action == RecoveryAction.RETRY:
                        # Simple retry — re-dispatch the same step
                        retry_result = await self.agent_bus.dispatch(step)
                        execution.record_step(step, retry_result)
                        if not retry_result.success:
                            execution.status = ExecutionStatus.FAILED
                            execution.error = f"Step {step.index} failed after retry"
                            break

            except Exception as e:
                logger.error(
                    "orchestrator.step_error",
                    trace_id=trace_id,
                    step_index=step.index,
                    error=str(e),
                    exc_info=True,
                )
                recovery = await self.failure.handle(step, error=e)
                execution.record_recovery(recovery)
                if recovery.action == RecoveryAction.ABORT:
                    execution.status = ExecutionStatus.ABORTED
                    execution.error = str(e)
                    break

        if execution.status == ExecutionStatus.RUNNING:
            execution.status = ExecutionStatus.COMPLETED

        from datetime import datetime

        execution.completed_at = datetime.now(UTC)
        return execution

    async def process_user_message(self, message: str) -> LoopResult:
        """Process a direct user message (from JARVIS).

        Convenience method that wraps a user message into a ThiraEvent
        and feeds it through the full loop.
        """
        from datetime import datetime

        from shared.enums import EventSource, EventType

        event = ThiraEvent(
            source=EventSource.USER_COMMAND,
            type=EventType.USER_REQUEST,
            timestamp=datetime.now(UTC),
            actor="user",
            content=message,
        )

        return await self.process_event(event)

    async def handle_approval(self, plan_id: uuid.UUID, approved: bool) -> LoopResult:
        """Handle user approval/rejection of a plan.

        Called by JARVIS when the user responds to an approval request.
        """
        pending = self._pending_approvals.pop(plan_id, None)
        if not pending:
            logger.warning("orchestrator.plan_not_found_for_approval", plan_id=str(plan_id))
            return LoopResult(
                status="not_found",
                plan_id=plan_id,
                response="Plan not found or already processed.",
            )

        authorized_plan: AuthorizedPlan = pending["authorized_plan"]
        event: ThiraEvent = pending["event"]
        enriched: EnrichedEvent = pending["enriched"]
        decision: Decision = pending["decision"]
        trace_id: str = pending["trace_id"]

        if not approved:
            logger.info("orchestrator.plan_rejected", plan_id=str(plan_id))
            authorized_plan.plan.status = PlanStatus.FAILED
            if self.jarvis and hasattr(self.jarvis, "notify"):
                await self.jarvis.notify(f"Plan {plan_id} was rejected by user.", level="warning")
            return LoopResult(
                status="rejected",
                plan_id=plan_id,
                trace_id=trace_id,
                response="Plan execution was rejected by user.",
            )

        logger.info("orchestrator.plan_approved", plan_id=str(plan_id))
        authorized_plan.plan.status = PlanStatus.APPROVED
        authorized_plan.requires_approval = False

        # Execute the approved plan
        execution = await self._execute_plan(authorized_plan, trace_id)

        # Verify
        verification = await self.verification.verify(execution)

        # Learn
        experience = await self.echo.record(
            event=event,
            enriched=enriched,
            decision=decision,
            plan=authorized_plan.plan,
            execution=execution,
            verification=verification,
        )

        # Update world model
        await self.world_model.apply_execution(execution, verification)

        if self.jarvis and hasattr(self.jarvis, "notify"):
            await self.jarvis.notify(
                f"Approved plan completed: {verification.summary}", level="info"
            )

        return LoopResult(
            status="completed",
            trace_id=trace_id,
            plan_id=plan_id,
            execution_id=execution.id,
            experience_id=experience.id,
            response=verification.summary,
        )

    def stop(self) -> None:
        """Stop the orchestrator loop."""
        self._running = False
        logger.info("orchestrator.stopping")

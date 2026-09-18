"""Unit tests for the Failure Engine."""

from __future__ import annotations

import pytest

from shared.enums import RecoveryAction
from shared.models import PlanStep, StepResult
from thira_core.failure.engine import FailureEngine


class TestFailureEngine:
    @pytest.fixture
    def engine(self) -> FailureEngine:
        return FailureEngine(max_retries=3)

    @pytest.fixture
    def step(self) -> PlanStep:
        return PlanStep(index=0, description="Test step", agent="test", tool="test_tool")

    @pytest.mark.asyncio
    async def test_transient_error_retries(self, engine: FailureEngine, step: PlanStep):
        result = StepResult(step_index=0, success=False, error="Connection timeout")
        recovery = await engine.handle(step, result=result)
        assert recovery.action == RecoveryAction.RETRY
        assert recovery.retries_attempted == 1

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self, engine: FailureEngine, step: PlanStep):
        result = StepResult(step_index=0, success=False, error="Connection timeout")

        for _ in range(3):
            await engine.handle(step, result=result)

        recovery = await engine.handle(step, result=result)
        assert recovery.action == RecoveryAction.ABORT

    @pytest.mark.asyncio
    async def test_non_transient_error_aborts(self, engine: FailureEngine, step: PlanStep):
        result = StepResult(
            step_index=0, success=False, error="Permission denied: access forbidden"
        )
        recovery = await engine.handle(step, result=result)
        assert recovery.action == RecoveryAction.ABORT

    @pytest.mark.asyncio
    async def test_exception_handling(self, engine: FailureEngine, step: PlanStep):
        recovery = await engine.handle(step, error=ValueError("Invalid argument"))
        assert recovery.action == RecoveryAction.ABORT

    @pytest.mark.asyncio
    async def test_rate_limit_is_transient(self, engine: FailureEngine, step: PlanStep):
        result = StepResult(step_index=0, success=False, error="Rate limit exceeded (429)")
        recovery = await engine.handle(step, result=result)
        assert recovery.action == RecoveryAction.RETRY

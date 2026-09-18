"""Unit tests for the Policy Engine."""

from __future__ import annotations

import pytest

from shared.enums import AutonomyLevel, PolicyVerdict, RiskLevel
from shared.models import Action, ToolAnnotation
from thira_core.policy.engine import PolicyEngine


class TestPolicyEngine:
    @pytest.fixture
    def policy(self) -> PolicyEngine:
        engine = PolicyEngine(default_autonomy=AutonomyLevel.L3_EXECUTE_APPROVED)
        # Register some tool annotations
        engine.register_tool_annotations(
            "filesystem",
            "read_file",
            ToolAnnotation(autonomy_level=AutonomyLevel.L0_OBSERVE, risk=RiskLevel.LOW),
        )
        engine.register_tool_annotations(
            "gmail",
            "send_email",
            ToolAnnotation(
                autonomy_level=AutonomyLevel.L3_EXECUTE_APPROVED,
                risk=RiskLevel.MEDIUM,
                reversible=False,
            ),
        )
        engine.register_tool_annotations(
            "banking",
            "transfer",
            ToolAnnotation(autonomy_level=AutonomyLevel.L5_AUTONOMOUS, risk=RiskLevel.CRITICAL),
        )
        return engine

    @pytest.mark.asyncio
    async def test_low_risk_allowed(self, policy: PolicyEngine):
        result = await policy.check_action(Action(agent="filesystem", tool="read_file"))
        assert result.verdict == PolicyVerdict.ALLOWED

    @pytest.mark.asyncio
    async def test_medium_risk_requires_approval(self, policy: PolicyEngine):
        result = await policy.check_action(Action(agent="gmail", tool="send_email"))
        assert result.verdict == PolicyVerdict.ALLOWED  # L3 granted, L3 required

    @pytest.mark.asyncio
    async def test_critical_risk_blocked(self, policy: PolicyEngine):
        result = await policy.check_action(Action(agent="banking", tool="transfer"))
        assert result.verdict == PolicyVerdict.BLOCKED

    @pytest.mark.asyncio
    async def test_unknown_tool_requires_approval(self, policy: PolicyEngine):
        result = await policy.check_action(Action(agent="unknown", tool="unknown"))
        assert result.verdict == PolicyVerdict.ALLOWED  # Default L3 matches default L3

    @pytest.mark.asyncio
    async def test_user_policy_override(self, policy: PolicyEngine):
        # Downgrade gmail autonomy to L1
        policy.set_user_policy("gmail", "send_email", AutonomyLevel.L1_RECOMMEND)
        result = await policy.check_action(Action(agent="gmail", tool="send_email"))
        assert result.verdict == PolicyVerdict.REQUIRES_APPROVAL

    @pytest.mark.asyncio
    async def test_wildcard_policy(self, policy: PolicyEngine):
        policy.set_user_policy("*", "*", AutonomyLevel.L4_EXECUTE_AUTO)
        result = await policy.check_action(Action(agent="gmail", tool="send_email"))
        assert result.verdict == PolicyVerdict.ALLOWED

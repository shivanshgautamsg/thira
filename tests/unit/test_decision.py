"""Unit tests for the Decision Engine."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from shared.enums import DecisionAction, EventSource, EventType
from shared.events import EnrichedEvent, ThiraEvent
from tests.conftest import MockLLMProvider
from thira_core.decision.engine import DecisionEngine


class TestDecisionEngine:
    @pytest.mark.asyncio
    async def test_decision_act(self):
        llm = MockLLMProvider(
            response_content=json.dumps(
                {
                    "action": "act",
                    "urgency": 0.8,
                    "importance": 0.9,
                    "opportunity": 0.7,
                    "effort": 0.3,
                    "confidence": 0.85,
                    "risk": 0.2,
                    "reversibility": 0.9,
                    "dependency": 0.1,
                    "reasoning": "User explicitly requested action",
                }
            )
        )

        engine = DecisionEngine(llm=llm)
        event = ThiraEvent(
            source=EventSource.USER_COMMAND,
            type=EventType.USER_REQUEST,
            timestamp=datetime.utcnow(),
            content="List files in the directory",
        )
        enriched = EnrichedEvent(event=event, interpretation="User wants to see directory listing")

        decision = await engine.evaluate(enriched, world_model=None)

        assert decision.action == DecisionAction.ACT
        assert decision.scores.urgency == 0.8
        assert decision.scores.importance == 0.9
        assert len(llm.calls) == 1
        assert llm.calls[0]["purpose"] == "decision_scoring"

    @pytest.mark.asyncio
    async def test_decision_ignore(self):
        llm = MockLLMProvider(
            response_content=json.dumps(
                {
                    "action": "ignore",
                    "urgency": 0.1,
                    "importance": 0.1,
                    "reasoning": "Informational only, no action needed",
                }
            )
        )

        engine = DecisionEngine(llm=llm)
        event = ThiraEvent(
            source=EventSource.SYSTEM,
            type=EventType.NOTIFICATION,
            timestamp=datetime.utcnow(),
            content="System update available",
        )
        enriched = EnrichedEvent(event=event)

        decision = await engine.evaluate(enriched, world_model=None)
        assert decision.action == DecisionAction.IGNORE

    @pytest.mark.asyncio
    async def test_decision_fallback_on_parse_error(self):
        llm = MockLLMProvider(response_content="not valid json")
        engine = DecisionEngine(llm=llm)
        event = ThiraEvent(
            source=EventSource.USER_COMMAND,
            type=EventType.USER_REQUEST,
            timestamp=datetime.utcnow(),
            content="Do something",
        )
        enriched = EnrichedEvent(event=event)

        decision = await engine.evaluate(enriched, world_model=None)
        # Should default to ACT on parse failure
        assert decision.action == DecisionAction.ACT

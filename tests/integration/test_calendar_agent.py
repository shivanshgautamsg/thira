"""Integration tests for Calendar Agent and its tool execution."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from agents.calendar import CalendarAgent
from shared.enums import PolicyVerdict
from thira_core.policy.engine import PolicyEngine


@pytest.mark.asyncio
async def test_calendar_agent_tools():
    """Test listing, reading, creating, and updating events via CalendarAgent."""
    agent = CalendarAgent()
    await agent.initialize()

    # 1. List events
    list_res = await agent.execute("list_events", {"max_results": 5})
    assert list_res.success is True
    assert list_res.output["count"] >= 1
    event_id = list_res.output["events"][0]["id"]

    # 2. Get event
    get_res = await agent.execute("get_event", {"event_id": event_id})
    assert get_res.success is True
    assert get_res.output["event"]["id"] == event_id

    # 3. Create event
    now = datetime.now(UTC)
    start_time = (now + timedelta(days=2, hours=10)).isoformat()
    end_time = (now + timedelta(days=2, hours=11)).isoformat()

    create_res = await agent.execute(
        "create_event",
        {
            "summary": "Phase 2 Architecture Review",
            "start_time": start_time,
            "end_time": end_time,
            "attendees": ["team@enterprise.com", "user@thira.local"],
            "description": "Deep-dive into proactive event bus processing",
        },
    )
    assert create_res.success is True
    created_id = create_res.output["event"]["id"]
    assert created_id.startswith("cal_")
    assert create_res.output["event"]["summary"] == "Phase 2 Architecture Review"

    # 4. Update event
    update_res = await agent.execute(
        "update_event",
        {
            "event_id": created_id,
            "summary": "Phase 2 Architecture & Security Review",
            "description": "Updated agenda with safety policies",
        },
    )
    assert update_res.success is True
    assert update_res.output["event"]["summary"] == "Phase 2 Architecture & Security Review"

    # Verify event reflects updates
    get_updated = await agent.execute("get_event", {"event_id": created_id})
    assert get_updated.output["event"]["summary"] == "Phase 2 Architecture & Security Review"


@pytest.mark.asyncio
async def test_calendar_agent_policy_enforcement():
    """Verify that read actions are allowed while event mutations require authorization."""
    agent = CalendarAgent()
    policy = PolicyEngine()

    for cap in agent.capabilities():
        policy.register_tool_annotations("calendar", cap.name, cap.annotations)

    # list_events and get_event are low risk (L0)
    list_check = policy.check_tool_authorization("calendar", "list_events")
    assert list_check.verdict == PolicyVerdict.ALLOWED

    get_check = policy.check_tool_authorization("calendar", "get_event")
    assert get_check.verdict == PolicyVerdict.ALLOWED

    # create_event and update_event are L4 mutations requiring explicit approval under default L3
    create_check = policy.check_tool_authorization("calendar", "create_event")
    assert create_check.verdict == PolicyVerdict.REQUIRES_APPROVAL

    update_check = policy.check_tool_authorization("calendar", "update_event")
    assert update_check.verdict == PolicyVerdict.REQUIRES_APPROVAL

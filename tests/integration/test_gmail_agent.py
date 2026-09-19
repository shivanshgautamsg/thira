"""Integration tests for Gmail Agent and its tool execution."""

from __future__ import annotations

import pytest

from agents.gmail import GmailAgent
from shared.enums import PolicyVerdict
from thira_core.policy.engine import PolicyEngine


@pytest.mark.asyncio
async def test_gmail_agent_tools():
    """Test searching, reading, drafting, and sending emails via GmailAgent."""
    agent = GmailAgent()
    await agent.initialize()

    # 1. List emails
    list_res = await agent.execute("list_emails", {"query": "Proposal", "max_results": 5})
    assert list_res.success is True
    assert list_res.output["count"] >= 1
    msg_id = list_res.output["messages"][0]["id"]

    # 2. Read email
    read_res = await agent.execute("read_email", {"message_id": msg_id})
    assert read_res.success is True
    assert read_res.output["message"]["id"] == msg_id
    assert "RFP" in read_res.output["message"]["body"]

    # 3. Draft email
    draft_res = await agent.execute(
        "draft_email",
        {
            "to": "client@enterprise.com",
            "subject": "Re: Q3 Proposal Review",
            "body": "Thank you for the update. The revised proposal will be submitted by 3 PM.",
        },
    )
    assert draft_res.success is True
    assert "draft_id" in draft_res.output["draft"]
    draft_id = draft_res.output["draft"]["draft_id"]
    assert draft_id.startswith("draft_")

    # 4. Send email
    send_res = await agent.execute(
        "send_email",
        {
            "to": "client@enterprise.com",
            "subject": "Final Q3 Proposal Submission",
            "body": "Please find attached our approved proposal. Thank you.",
        },
    )
    assert send_res.success is True
    assert "message_id" in send_res.output["sent"]
    assert send_res.output["sent"]["status"] == "delivered"


@pytest.mark.asyncio
async def test_gmail_agent_policy_enforcement():
    """Verify that send_email requires approval while draft_email is allowed."""
    agent = GmailAgent()
    policy = PolicyEngine()

    for cap in agent.capabilities():
        policy.register_tool_annotations("gmail", cap.name, cap.annotations)

    # draft_email is low risk
    draft_check = policy.check_tool_authorization("gmail", "draft_email")
    assert draft_check.verdict == PolicyVerdict.ALLOWED

    # send_email is high risk and requires explicit approval
    send_check = policy.check_tool_authorization("gmail", "send_email")
    assert send_check.verdict == PolicyVerdict.REQUIRES_APPROVAL

"""Gmail Execution Agent for THIRA."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Protocol

import structlog

from agents.base import BaseAgent
from agents.gmail.tools import GMAIL_CAPABILITIES
from shared.enums import AgentState
from shared.models import AgentResult, Capability

logger = structlog.get_logger()


class GmailClientAdapter(Protocol):
    """Abstract interface for Gmail client implementations."""

    async def list_messages(self, query: str, max_results: int) -> list[dict[str, Any]]: ...
    async def get_message(self, message_id: str) -> dict[str, Any] | None: ...
    async def create_draft(
        self, to: str, subject: str, body: str, thread_id: str | None
    ) -> dict[str, Any]: ...
    async def send_message(
        self, to: str, subject: str, body: str, thread_id: str | None
    ) -> dict[str, Any]: ...


class MockGmailClient:
    """In-memory mock Gmail client for testing and local operation."""

    def __init__(self):
        self.messages: dict[str, dict[str, Any]] = {
            "msg_sample_001": {
                "id": "msg_sample_001",
                "thread_id": "th_001",
                "from": "client@enterprise.com",
                "to": "user@thira.local",
                "subject": "Q3 Proposal Review and Deadline",
                "body": "Hi, Please find the updated RFP details. We need the final proposal signed by 5 PM tomorrow.",
                "snippet": "We need the final proposal signed by 5 PM tomorrow.",
                "timestamp": datetime.now(UTC).isoformat(),
                "labels": ["INBOX", "UNREAD", "IMPORTANT"],
            },
            "msg_sample_002": {
                "id": "msg_sample_002",
                "thread_id": "th_002",
                "from": "newsletter@techinsights.com",
                "to": "user@thira.local",
                "subject": "Weekly AI Digest",
                "body": "Here are the top AI breakthroughs this week...",
                "snippet": "Here are the top AI breakthroughs this week...",
                "timestamp": datetime.now(UTC).isoformat(),
                "labels": ["INBOX"],
            },
        }
        self.drafts: dict[str, dict[str, Any]] = {}
        self.sent: list[dict[str, Any]] = []

    async def list_messages(self, query: str = "", max_results: int = 10) -> list[dict[str, Any]]:
        results = []
        for msg in self.messages.values():
            if query:
                q_lower = query.lower()
                content = f"{msg['subject']} {msg['body']} {msg['from']} {' '.join(msg['labels'])}".lower()
                if q_lower not in content:
                    continue
            results.append(
                {
                    "id": msg["id"],
                    "thread_id": msg["thread_id"],
                    "from": msg["from"],
                    "to": msg["to"],
                    "subject": msg["subject"],
                    "snippet": msg["snippet"],
                    "timestamp": msg["timestamp"],
                }
            )
            if len(results) >= max_results:
                break
        return results

    async def get_message(self, message_id: str) -> dict[str, Any] | None:
        return self.messages.get(message_id)

    async def create_draft(
        self, to: str, subject: str, body: str, thread_id: str | None = None
    ) -> dict[str, Any]:
        draft_id = f"draft_{uuid.uuid4().hex[:8]}"
        draft = {
            "draft_id": draft_id,
            "to": to,
            "subject": subject,
            "body": body,
            "thread_id": thread_id or f"th_{uuid.uuid4().hex[:6]}",
            "created_at": datetime.now(UTC).isoformat(),
        }
        self.drafts[draft_id] = draft
        return draft

    async def send_message(
        self, to: str, subject: str, body: str, thread_id: str | None = None
    ) -> dict[str, Any]:
        msg_id = f"msg_{uuid.uuid4().hex[:8]}"
        sent_record = {
            "message_id": msg_id,
            "to": to,
            "subject": subject,
            "body": body,
            "thread_id": thread_id or f"th_{uuid.uuid4().hex[:6]}",
            "sent_at": datetime.now(UTC).isoformat(),
            "status": "delivered",
        }
        self.sent.append(sent_record)
        # Also store in messages store
        self.messages[msg_id] = {
            "id": msg_id,
            "thread_id": sent_record["thread_id"],
            "from": "user@thira.local",
            "to": to,
            "subject": subject,
            "body": body,
            "snippet": body[:100],
            "timestamp": sent_record["sent_at"],
            "labels": ["SENT"],
        }
        return sent_record


class GmailAgent(BaseAgent):
    """Executes Gmail operations: search, read, draft, and send emails."""

    def __init__(self, client: GmailClientAdapter | None = None):
        super().__init__()
        self._client = client or MockGmailClient()

    @property
    def name(self) -> str:
        return "gmail"

    @property
    def description(self) -> str:
        return "Gmail integration for searching, reading, drafting, and sending emails"

    def capabilities(self) -> list[Capability]:
        return GMAIL_CAPABILITIES

    async def initialize(self) -> None:
        self._state = AgentState.READY
        logger.info("gmail.agent_initialized")

    async def execute(self, tool: str, arguments: dict) -> AgentResult:
        logger.info("gmail.executing", tool=tool, arguments=arguments)

        try:
            if tool == "list_emails":
                query = arguments.get("query", "")
                max_results = arguments.get("max_results", 10)
                messages = await self._client.list_messages(query, max_results)
                return AgentResult(
                    success=True,
                    output={"messages": messages, "count": len(messages)},
                )

            elif tool == "read_email":
                message_id = arguments.get("message_id")
                if not message_id:
                    return AgentResult(success=False, error="Missing required argument: message_id")
                msg = await self._client.get_message(message_id)
                if not msg:
                    return AgentResult(
                        success=False, error=f"Message with ID {message_id} not found"
                    )
                return AgentResult(
                    success=True,
                    output={"message": msg},
                )

            elif tool == "draft_email":
                to = arguments.get("to")
                subject = arguments.get("subject")
                body = arguments.get("body")
                thread_id = arguments.get("thread_id")

                if not to or not subject or not body:
                    return AgentResult(
                        success=False, error="Arguments 'to', 'subject', and 'body' are required"
                    )

                draft = await self._client.create_draft(to, subject, body, thread_id)
                return AgentResult(
                    success=True,
                    output={"draft": draft, "message": f"Draft created for {to}"},
                )

            elif tool == "send_email":
                to = arguments.get("to")
                subject = arguments.get("subject")
                body = arguments.get("body")
                thread_id = arguments.get("thread_id")

                if not to or not subject or not body:
                    return AgentResult(
                        success=False, error="Arguments 'to', 'subject', and 'body' are required"
                    )

                sent = await self._client.send_message(to, subject, body, thread_id)
                return AgentResult(
                    success=True,
                    output={"sent": sent, "message": f"Email successfully sent to {to}"},
                )

            else:
                return AgentResult(success=False, error=f"Unknown Gmail tool: {tool}")

        except Exception as e:
            logger.error("gmail.execution_error", tool=tool, error=str(e), exc_info=True)
            return AgentResult(success=False, error=str(e))

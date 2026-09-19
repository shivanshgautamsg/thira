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


class LiveGoogleGmailClient:
    """Production client integrating directly with Google Gmail REST API v1."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        access_token: str | None = None,
    ):
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._access_token = access_token
        self._token_expiry: datetime | None = None

    async def _get_valid_token(self) -> str:
        """Obtain a fresh OAuth2 access token using the refresh token."""
        import httpx

        if self._access_token and self._token_expiry and datetime.now(UTC) < self._token_expiry:
            return self._access_token

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "refresh_token": self._refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            if resp.status_code != 200:
                logger.error("gmail.token_refresh_failed", status=resp.status_code, body=resp.text)
                raise RuntimeError(f"Failed to refresh Google OAuth token: {resp.text}")

            data = resp.json()
            self._access_token = data["access_token"]
            expires_in = data.get("expires_in", 3600)
            from datetime import timedelta

            self._token_expiry = datetime.now(UTC) + timedelta(seconds=expires_in - 60)
            return self._access_token

    async def list_messages(self, query: str = "", max_results: int = 10) -> list[dict[str, Any]]:
        import httpx

        token = await self._get_valid_token()
        headers = {"Authorization": f"Bearer {token}"}
        params: dict[str, Any] = {"maxResults": max_results}
        if query:
            params["q"] = query

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages",
                headers=headers,
                params=params,
            )
            if resp.status_code != 200:
                logger.warning("gmail.list_messages_failed", status=resp.status_code)
                return []

            items = resp.json().get("messages", [])
            results = []
            for item in items[:max_results]:
                detail = await self.get_message(item["id"])
                if detail:
                    results.append(detail)
            return results

    async def get_message(self, message_id: str) -> dict[str, Any] | None:
        import base64

        import httpx

        token = await self._get_valid_token()
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}",
                headers=headers,
                params={"format": "full"},
            )
            if resp.status_code != 200:
                return None

            data = resp.json()
            payload = data.get("payload", {})
            headers_list = payload.get("headers", [])
            headers_dict = {h["name"].lower(): h["value"] for h in headers_list}

            body_content = ""
            if "body" in payload and payload["body"].get("data"):
                body_content = base64.urlsafe_b64decode(payload["body"]["data"]).decode(
                    "utf-8", errors="ignore"
                )
            elif "parts" in payload:
                for part in payload["parts"]:
                    if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                        body_content = base64.urlsafe_b64decode(part["body"]["data"]).decode(
                            "utf-8", errors="ignore"
                        )
                        break

            return {
                "id": data["id"],
                "thread_id": data.get("threadId"),
                "from": headers_dict.get("from", "unknown"),
                "to": headers_dict.get("to", ""),
                "subject": headers_dict.get("subject", "(No Subject)"),
                "snippet": data.get("snippet", ""),
                "body": body_content,
                "timestamp": headers_dict.get("date", datetime.now(UTC).isoformat()),
                "labels": data.get("labelIds", []),
            }

    async def create_draft(
        self, to: str, subject: str, body: str, thread_id: str | None = None
    ) -> dict[str, Any]:
        import base64
        from email.message import EmailMessage

        import httpx

        token = await self._get_valid_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        msg = EmailMessage()
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        raw_msg = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

        payload: dict[str, Any] = {"message": {"raw": raw_msg}}
        if thread_id:
            payload["message"]["threadId"] = thread_id

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/drafts",
                headers=headers,
                json=payload,
            )
            if resp.status_code not in (200, 201):
                raise RuntimeError(f"Gmail create_draft failed: {resp.text}")

            data = resp.json()
            return {
                "draft_id": data.get("id"),
                "to": to,
                "subject": subject,
                "body": body,
                "thread_id": thread_id,
                "created_at": datetime.now(UTC).isoformat(),
            }

    async def send_message(
        self, to: str, subject: str, body: str, thread_id: str | None = None
    ) -> dict[str, Any]:
        import base64
        from email.message import EmailMessage

        import httpx

        token = await self._get_valid_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        msg = EmailMessage()
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        raw_msg = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

        payload: dict[str, Any] = {"raw": raw_msg}
        if thread_id:
            payload["threadId"] = thread_id

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                headers=headers,
                json=payload,
            )
            if resp.status_code not in (200, 201):
                raise RuntimeError(f"Gmail send_message failed: {resp.text}")

            data = resp.json()
            return {
                "message_id": data.get("id"),
                "to": to,
                "subject": subject,
                "body": body,
                "thread_id": thread_id,
                "sent_at": datetime.now(UTC).isoformat(),
                "status": "delivered",
            }


def create_gmail_client(config: Any = None) -> GmailClientAdapter:
    """Factory creating LiveGoogleGmailClient if credentials exist, otherwise MockGmailClient."""
    if config:
        client_id = getattr(config, "google_client_id", "") or getattr(
            config, "gmail_client_id", ""
        )
        client_secret = getattr(config, "google_client_secret", "") or getattr(
            config, "gmail_client_secret", ""
        )
        refresh_token = getattr(config, "google_refresh_token", "") or getattr(
            config, "gmail_refresh_token", ""
        )

        if client_id and client_secret and refresh_token:
            logger.info("gmail.live_client_selected")
            return LiveGoogleGmailClient(
                client_id=client_id,
                client_secret=client_secret,
                refresh_token=refresh_token,
            )

    logger.info(
        "gmail.mock_client_selected", reason="Credentials not configured; using in-memory mock"
    )
    return MockGmailClient()


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

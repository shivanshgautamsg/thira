"""Calendar Execution Agent for THIRA."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import structlog

from agents.base import BaseAgent
from agents.calendar.tools import CALENDAR_CAPABILITIES
from shared.enums import AgentState
from shared.models import AgentResult, Capability

logger = structlog.get_logger()


class CalendarClientAdapter(Protocol):
    """Abstract interface for Calendar client implementations."""

    async def list_events(
        self, time_min: str | None, time_max: str | None, max_results: int
    ) -> list[dict[str, Any]]: ...
    async def get_event(self, event_id: str) -> dict[str, Any] | None: ...
    async def create_event(
        self, summary: str, start_time: str, end_time: str, attendees: list[str], description: str
    ) -> dict[str, Any]: ...
    async def update_event(self, event_id: str, **updates: Any) -> dict[str, Any] | None: ...


class MockCalendarClient:
    """In-memory mock Calendar client for testing and local operation."""

    def __init__(self):
        now = datetime.now(UTC)
        self.events: dict[str, dict[str, Any]] = {
            "cal_sample_001": {
                "id": "cal_sample_001",
                "summary": "Engineering Sync",
                "start_time": (now + timedelta(hours=2)).isoformat(),
                "end_time": (now + timedelta(hours=3)).isoformat(),
                "attendees": ["alice@enterprise.com", "bob@enterprise.com", "user@thira.local"],
                "description": "Weekly engineering architecture alignment",
                "status": "confirmed",
            },
            "cal_sample_002": {
                "id": "cal_sample_002",
                "summary": "Q3 Proposal Review Session",
                "start_time": (now + timedelta(days=1, hours=4)).isoformat(),
                "end_time": (now + timedelta(days=1, hours=5)).isoformat(),
                "attendees": ["client@enterprise.com", "user@thira.local"],
                "description": "Review proposal with client lead before final sign-off",
                "status": "confirmed",
            },
        }

    async def list_events(
        self, time_min: str | None = None, time_max: str | None = None, max_results: int = 10
    ) -> list[dict[str, Any]]:
        results = list(self.events.values())
        return results[:max_results]

    async def get_event(self, event_id: str) -> dict[str, Any] | None:
        return self.events.get(event_id)

    async def create_event(
        self,
        summary: str,
        start_time: str,
        end_time: str,
        attendees: list[str] | None = None,
        description: str = "",
    ) -> dict[str, Any]:
        event_id = f"cal_{uuid.uuid4().hex[:8]}"
        event_record = {
            "id": event_id,
            "summary": summary,
            "start_time": start_time,
            "end_time": end_time,
            "attendees": attendees or [],
            "description": description,
            "status": "confirmed",
            "created_at": datetime.now(UTC).isoformat(),
        }
        self.events[event_id] = event_record
        return event_record

    async def update_event(self, event_id: str, **updates: Any) -> dict[str, Any] | None:
        event = self.events.get(event_id)
        if not event:
            return None
        for k, v in updates.items():
            if v is not None:
                event[k] = v
        event["updated_at"] = datetime.now(UTC).isoformat()
        return event


class LiveGoogleCalendarClient:
    """Production client integrating directly with Google Calendar REST API v3."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        calendar_id: str = "primary",
        access_token: str | None = None,
    ):
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._calendar_id = calendar_id
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
                logger.error(
                    "calendar.token_refresh_failed", status=resp.status_code, body=resp.text
                )
                raise RuntimeError(f"Failed to refresh Google OAuth token: {resp.text}")

            data = resp.json()
            self._access_token = data["access_token"]
            expires_in = data.get("expires_in", 3600)
            from datetime import timedelta

            self._token_expiry = datetime.now(UTC) + timedelta(seconds=expires_in - 60)
            return self._access_token

    async def list_events(
        self,
        time_min: str | None = None,
        time_max: str | None = None,
        max_results: int = 10,
    ) -> list[dict[str, Any]]:
        import httpx

        token = await self._get_valid_token()
        headers = {"Authorization": f"Bearer {token}"}
        params: dict[str, Any] = {
            "maxResults": max_results,
            "singleEvents": "true",
            "orderBy": "startTime",
        }
        if time_min:
            params["timeMin"] = time_min
        if time_max:
            params["timeMax"] = time_max

        url = f"https://www.googleapis.com/calendar/v3/calendars/{self._calendar_id}/events"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code != 200:
                logger.warning("calendar.list_events_failed", status=resp.status_code)
                return []

            items = resp.json().get("items", [])
            events = []
            for item in items:
                start = item.get("start", {}).get("dateTime") or item.get("start", {}).get("date")
                end = item.get("end", {}).get("dateTime") or item.get("end", {}).get("date")
                attendees = [a.get("email") for a in item.get("attendees", []) if a.get("email")]
                events.append(
                    {
                        "id": item.get("id"),
                        "summary": item.get("summary", "(No title)"),
                        "start_time": start,
                        "end_time": end,
                        "attendees": attendees,
                        "description": item.get("description", ""),
                        "status": item.get("status", "confirmed"),
                    }
                )
            return events

    async def get_event(self, event_id: str) -> dict[str, Any] | None:
        import httpx

        token = await self._get_valid_token()
        headers = {"Authorization": f"Bearer {token}"}
        url = f"https://www.googleapis.com/calendar/v3/calendars/{self._calendar_id}/events/{event_id}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                return None

            item = resp.json()
            start = item.get("start", {}).get("dateTime") or item.get("start", {}).get("date")
            end = item.get("end", {}).get("dateTime") or item.get("end", {}).get("date")
            attendees = [a.get("email") for a in item.get("attendees", []) if a.get("email")]
            return {
                "id": item.get("id"),
                "summary": item.get("summary", "(No title)"),
                "start_time": start,
                "end_time": end,
                "attendees": attendees,
                "description": item.get("description", ""),
                "status": item.get("status", "confirmed"),
            }

    async def create_event(
        self,
        summary: str,
        start_time: str,
        end_time: str,
        attendees: list[str] | None = None,
        description: str = "",
    ) -> dict[str, Any]:
        import httpx

        token = await self._get_valid_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        url = f"https://www.googleapis.com/calendar/v3/calendars/{self._calendar_id}/events"

        body: dict[str, Any] = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": start_time},
            "end": {"dateTime": end_time},
        }
        if attendees:
            body["attendees"] = [{"email": a} for a in attendees]

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, headers=headers, json=body)
            if resp.status_code not in (200, 201):
                raise RuntimeError(f"Google Calendar create_event failed: {resp.text}")

            item = resp.json()
            return {
                "id": item.get("id"),
                "summary": summary,
                "start_time": start_time,
                "end_time": end_time,
                "attendees": attendees or [],
                "description": description,
                "status": item.get("status", "confirmed"),
                "html_link": item.get("htmlLink"),
            }

    async def update_event(self, event_id: str, **updates: Any) -> dict[str, Any] | None:
        import httpx

        token = await self._get_valid_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        url = f"https://www.googleapis.com/calendar/v3/calendars/{self._calendar_id}/events/{event_id}"

        patch_body: dict[str, Any] = {}
        if "summary" in updates:
            patch_body["summary"] = updates["summary"]
        if "description" in updates:
            patch_body["description"] = updates["description"]
        if "start_time" in updates:
            patch_body["start"] = {"dateTime": updates["start_time"]}
        if "end_time" in updates:
            patch_body["end"] = {"dateTime": updates["end_time"]}

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.patch(url, headers=headers, json=patch_body)
            if resp.status_code != 200:
                return None
            item = resp.json()
            start = item.get("start", {}).get("dateTime") or item.get("start", {}).get("date")
            end = item.get("end", {}).get("dateTime") or item.get("end", {}).get("date")
            return {
                "id": item.get("id"),
                "summary": item.get("summary"),
                "start_time": start,
                "end_time": end,
                "description": item.get("description", ""),
            }


def create_calendar_client(config: Any = None) -> CalendarClientAdapter:
    """Factory creating LiveGoogleCalendarClient if credentials exist, otherwise MockCalendarClient."""
    if config:
        client_id = getattr(config, "google_client_id", "")
        client_secret = getattr(config, "google_client_secret", "")
        refresh_token = getattr(config, "google_refresh_token", "")
        cal_id = getattr(config, "calendar_id", "primary")

        if client_id and client_secret and refresh_token:
            logger.info("calendar.live_client_selected", calendar_id=cal_id)
            return LiveGoogleCalendarClient(
                client_id=client_id,
                client_secret=client_secret,
                refresh_token=refresh_token,
                calendar_id=cal_id,
            )

    logger.info(
        "calendar.mock_client_selected", reason="Credentials not configured; using in-memory mock"
    )
    return MockCalendarClient()


class CalendarAgent(BaseAgent):
    """Executes Calendar operations: list, get, schedule, and update events."""

    def __init__(self, client: CalendarClientAdapter | None = None):
        super().__init__()
        self._client = client or MockCalendarClient()

    @property
    def name(self) -> str:
        return "calendar"

    @property
    def description(self) -> str:
        return (
            "Calendar integration for schedule inspection, event creation, and meeting management"
        )

    def capabilities(self) -> list[Capability]:
        return CALENDAR_CAPABILITIES

    async def initialize(self) -> None:
        self._state = AgentState.READY
        logger.info("calendar.agent_initialized")

    async def execute(self, tool: str, arguments: dict) -> AgentResult:
        logger.info("calendar.executing", tool=tool, arguments=arguments)

        try:
            if tool == "list_events":
                time_min = arguments.get("time_min")
                time_max = arguments.get("time_max")
                max_results = arguments.get("max_results", 10)
                events = await self._client.list_events(time_min, time_max, max_results)
                return AgentResult(
                    success=True,
                    output={"events": events, "count": len(events)},
                )

            elif tool == "get_event":
                event_id = arguments.get("event_id")
                if not event_id:
                    return AgentResult(success=False, error="Missing required argument: event_id")
                event = await self._client.get_event(event_id)
                if not event:
                    return AgentResult(success=False, error=f"Calendar event {event_id} not found")
                return AgentResult(
                    success=True,
                    output={"event": event},
                )

            elif tool == "create_event":
                summary = arguments.get("summary")
                start_time = arguments.get("start_time")
                end_time = arguments.get("end_time")
                attendees = arguments.get("attendees", [])
                description = arguments.get("description", "")

                if not summary or not start_time or not end_time:
                    return AgentResult(
                        success=False,
                        error="Arguments 'summary', 'start_time', and 'end_time' are required",
                    )

                created = await self._client.create_event(
                    summary=summary,
                    start_time=start_time,
                    end_time=end_time,
                    attendees=attendees,
                    description=description,
                )
                return AgentResult(
                    success=True,
                    output={
                        "event": created,
                        "message": f"Event '{summary}' scheduled successfully",
                    },
                )

            elif tool == "update_event":
                event_id = arguments.get("event_id")
                if not event_id:
                    return AgentResult(success=False, error="Missing required argument: event_id")

                updates = {
                    k: v
                    for k, v in arguments.items()
                    if k in ("summary", "start_time", "end_time", "description")
                }
                updated = await self._client.update_event(event_id, **updates)
                if not updated:
                    return AgentResult(success=False, error=f"Calendar event {event_id} not found")

                return AgentResult(
                    success=True,
                    output={"event": updated, "message": f"Event {event_id} updated successfully"},
                )

            else:
                return AgentResult(success=False, error=f"Unknown Calendar tool: {tool}")

        except Exception as e:
            logger.error("calendar.execution_error", tool=tool, error=str(e), exc_info=True)
            return AgentResult(success=False, error=str(e))

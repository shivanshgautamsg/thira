"""Calendar Agent MCP Tool definitions and capabilities."""

from __future__ import annotations

from shared.enums import AutonomyLevel, RiskLevel
from shared.models import Capability, ToolAnnotation

CALENDAR_CAPABILITIES = [
    Capability(
        name="list_events",
        description="List upcoming calendar events within a time range",
        input_schema={
            "type": "object",
            "properties": {
                "time_min": {
                    "type": "string",
                    "description": "Start of time range (ISO 8601 string, defaults to now)",
                },
                "time_max": {
                    "type": "string",
                    "description": "End of time range (ISO 8601 string)",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of events to return",
                    "default": 10,
                },
            },
        },
        annotations=ToolAnnotation(
            autonomy_level=AutonomyLevel.L0_OBSERVE,
            reversible=True,
            risk=RiskLevel.LOW,
            side_effects=[],
        ),
    ),
    Capability(
        name="get_event",
        description="Get full details for a calendar event by ID",
        input_schema={
            "type": "object",
            "properties": {
                "event_id": {
                    "type": "string",
                    "description": "Unique identifier of the calendar event",
                },
            },
            "required": ["event_id"],
        },
        annotations=ToolAnnotation(
            autonomy_level=AutonomyLevel.L0_OBSERVE,
            reversible=True,
            risk=RiskLevel.LOW,
            side_effects=[],
        ),
    ),
    Capability(
        name="create_event",
        description="Schedule a new calendar event (Requires approval if inviting attendees)",
        input_schema={
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Title/summary of the event"},
                "start_time": {"type": "string", "description": "Start time in ISO 8601 format"},
                "end_time": {"type": "string", "description": "End time in ISO 8601 format"},
                "attendees": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of attendee email addresses",
                    "default": [],
                },
                "description": {
                    "type": "string",
                    "description": "Meeting description or agenda",
                    "default": "",
                },
            },
            "required": ["summary", "start_time", "end_time"],
        },
        annotations=ToolAnnotation(
            autonomy_level=AutonomyLevel.L4_EXECUTE_AUTO,
            reversible=True,
            risk=RiskLevel.MEDIUM,
            side_effects=["calendar_modification", "invitation_sent"],
        ),
    ),
    Capability(
        name="update_event",
        description="Update an existing calendar event",
        input_schema={
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "ID of event to update"},
                "summary": {"type": "string", "description": "Updated event summary"},
                "start_time": {"type": "string", "description": "Updated start time (ISO 8601)"},
                "end_time": {"type": "string", "description": "Updated end time (ISO 8601)"},
                "description": {"type": "string", "description": "Updated description"},
            },
            "required": ["event_id"],
        },
        annotations=ToolAnnotation(
            autonomy_level=AutonomyLevel.L4_EXECUTE_AUTO,
            reversible=True,
            risk=RiskLevel.MEDIUM,
            side_effects=["calendar_modification"],
        ),
    ),
]

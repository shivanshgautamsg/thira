"""Gmail Agent MCP Tool definitions and capabilities."""

from __future__ import annotations

from shared.enums import AutonomyLevel, RiskLevel
from shared.models import Capability, ToolAnnotation

GMAIL_CAPABILITIES = [
    Capability(
        name="list_emails",
        description="List emails matching an optional search query",
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Gmail search query (e.g. 'is:unread', 'from:client@example.com')",
                    "default": "",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of messages to return",
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
        name="read_email",
        description="Read the full body and metadata of an email by message ID",
        input_schema={
            "type": "object",
            "properties": {
                "message_id": {
                    "type": "string",
                    "description": "The unique message ID of the email to retrieve",
                },
            },
            "required": ["message_id"],
        },
        annotations=ToolAnnotation(
            autonomy_level=AutonomyLevel.L0_OBSERVE,
            reversible=True,
            risk=RiskLevel.LOW,
            side_effects=[],
        ),
    ),
    Capability(
        name="draft_email",
        description="Create an email draft without sending it",
        input_schema={
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string", "description": "Email subject line"},
                "body": {"type": "string", "description": "Email body content (text/plain)"},
                "thread_id": {
                    "type": "string",
                    "description": "Thread ID if this is a reply (optional)",
                },
            },
            "required": ["to", "subject", "body"],
        },
        annotations=ToolAnnotation(
            autonomy_level=AutonomyLevel.L2_PREPARE,
            reversible=True,
            risk=RiskLevel.LOW,
            side_effects=["draft_creation"],
        ),
    ),
    Capability(
        name="send_email",
        description="Send an email to an external recipient (Requires User Authorization)",
        input_schema={
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string", "description": "Email subject line"},
                "body": {"type": "string", "description": "Email body content"},
                "thread_id": {
                    "type": "string",
                    "description": "Thread ID if replying to an existing thread (optional)",
                },
            },
            "required": ["to", "subject", "body"],
        },
        annotations=ToolAnnotation(
            autonomy_level=AutonomyLevel.L4_EXECUTE_AUTO,
            reversible=False,
            risk=RiskLevel.HIGH,
            side_effects=["external_communication"],
        ),
    ),
]

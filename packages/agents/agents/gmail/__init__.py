"""Gmail Agent package."""

from agents.gmail.agent import (
    GmailAgent,
    LiveGoogleGmailClient,
    MockGmailClient,
    create_gmail_client,
)
from agents.gmail.tools import GMAIL_CAPABILITIES

__all__ = [
    "GMAIL_CAPABILITIES",
    "GmailAgent",
    "LiveGoogleGmailClient",
    "MockGmailClient",
    "create_gmail_client",
]

"""Unit tests verifying Google Workspace client selection and fallback logic."""

from __future__ import annotations

import pytest

from agents.calendar import (
    CalendarAgent,
    LiveGoogleCalendarClient,
    MockCalendarClient,
    create_calendar_client,
)
from agents.gmail import (
    GmailAgent,
    LiveGoogleGmailClient,
    MockGmailClient,
    create_gmail_client,
)
from shared.config import ThiraConfig


def test_google_clients_fallback_to_mock_when_no_credentials():
    """Verify that absent credentials cleanly return in-memory Mock clients."""
    config = ThiraConfig(
        google_client_id="",
        google_client_secret="",
        google_refresh_token="",
        gmail_client_id="",
        gmail_client_secret="",
        gmail_refresh_token="",
    )

    gmail_client = create_gmail_client(config)
    assert isinstance(gmail_client, MockGmailClient)

    cal_client = create_calendar_client(config)
    assert isinstance(cal_client, MockCalendarClient)


def test_google_clients_instantiate_live_when_credentials_present():
    """Verify that present credentials instantiate LiveGoogle clients."""
    config = ThiraConfig(
        google_client_id="dummy_client_id_123.apps.googleusercontent.com",
        google_client_secret="GOCSPX-dummy_secret_abc",
        google_refresh_token="1//dummy_refresh_token_xyz",
        calendar_id="primary",
    )

    gmail_client = create_gmail_client(config)
    assert isinstance(gmail_client, LiveGoogleGmailClient)
    assert gmail_client._client_id == "dummy_client_id_123.apps.googleusercontent.com"
    assert gmail_client._refresh_token == "1//dummy_refresh_token_xyz"

    cal_client = create_calendar_client(config)
    assert isinstance(cal_client, LiveGoogleCalendarClient)
    assert cal_client._client_id == "dummy_client_id_123.apps.googleusercontent.com"
    assert cal_client._calendar_id == "primary"


@pytest.mark.asyncio
async def test_agent_initialization_with_factory_clients():
    """Verify GmailAgent and CalendarAgent initialize seamlessly with factory clients."""
    config = ThiraConfig()
    gmail_agent = GmailAgent(client=create_gmail_client(config))
    cal_agent = CalendarAgent(client=create_calendar_client(config))

    await gmail_agent.initialize()
    await cal_agent.initialize()

    assert gmail_agent.state.value == "ready"
    assert cal_agent.state.value == "ready"

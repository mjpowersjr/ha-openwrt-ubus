"""Tests for the config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.openwrt_ubus.const import DOMAIN

from .conftest import (
    MOCK_CONFIG_DATA,
    MOCK_HOST,
    create_mock_client,
)


@pytest.fixture
def mock_setup_entry():
    """Mock setting up the config entry."""
    with patch(
        "custom_components.openwrt_ubus.async_setup_entry",
        return_value=True,
    ) as mock:
        yield mock


def _patch_client(client_mock):
    """Patch UbusClient construction to return the given mock."""
    return patch(
        "custom_components.openwrt_ubus.config_flow.UbusClient",
        return_value=client_mock,
    )


class TestUserStep:
    """Tests for the user setup step."""

    async def test_user_flow_success(
        self, hass: HomeAssistant, mock_setup_entry
    ):
        """Test successful user setup."""
        client = create_mock_client()

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"
        assert result["errors"] == {}

        with _patch_client(client):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], MOCK_CONFIG_DATA
            )

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["title"] == "OpenWrt (Linksys E8450 (UBI))"
        assert result["data"] == MOCK_CONFIG_DATA

    async def test_user_flow_cannot_connect(
        self, hass: HomeAssistant, mock_setup_entry
    ):
        """Test connection failure during setup."""
        from custom_components.openwrt_ubus.ubus_client import (
            UbusConnectionError,
        )

        client = create_mock_client()
        client.connect = AsyncMock(
            side_effect=UbusConnectionError("Connection refused")
        )

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        with _patch_client(client):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], MOCK_CONFIG_DATA
            )

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "cannot_connect"}

    async def test_user_flow_invalid_auth(
        self, hass: HomeAssistant, mock_setup_entry
    ):
        """Test invalid authentication during setup."""
        from custom_components.openwrt_ubus.ubus_client import (
            UbusAuthenticationError,
        )

        client = create_mock_client()
        client.connect = AsyncMock(
            side_effect=UbusAuthenticationError("Bad credentials")
        )

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        with _patch_client(client):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], MOCK_CONFIG_DATA
            )

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "invalid_auth"}

    async def test_user_flow_unknown_error(
        self, hass: HomeAssistant, mock_setup_entry
    ):
        """Test unexpected error during setup."""
        client = create_mock_client()
        client.connect = AsyncMock(side_effect=RuntimeError("boom"))

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        with _patch_client(client):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], MOCK_CONFIG_DATA
            )

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "unknown"}


class TestReauthFlow:
    """Tests for the reauth flow."""

    async def test_reauth_success(
        self, hass: HomeAssistant, mock_setup_entry
    ):
        """Test successful reauthentication."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="OpenWrt",
            data=MOCK_CONFIG_DATA,
            unique_id=MOCK_HOST,
        )
        entry.add_to_hass(hass)

        client = create_mock_client()

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_REAUTH,
                "entry_id": entry.entry_id,
            },
            data=entry.data,
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "reauth_confirm"

        with _patch_client(client):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {"username": "root", "password": "newpass"},
            )

        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "reauth_successful"

    async def test_reauth_invalid_auth(
        self, hass: HomeAssistant, mock_setup_entry
    ):
        """Test reauth with invalid credentials."""
        from custom_components.openwrt_ubus.ubus_client import (
            UbusAuthenticationError,
        )

        entry = MockConfigEntry(
            domain=DOMAIN,
            title="OpenWrt",
            data=MOCK_CONFIG_DATA,
            unique_id=MOCK_HOST,
        )
        entry.add_to_hass(hass)

        client = create_mock_client()
        client.connect = AsyncMock(
            side_effect=UbusAuthenticationError("Bad credentials")
        )

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_REAUTH,
                "entry_id": entry.entry_id,
            },
            data=entry.data,
        )

        with _patch_client(client):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {"username": "root", "password": "wrongpass"},
            )

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "invalid_auth"}


class TestOptionsFlow:
    """Tests for the options flow."""

    async def test_options_flow(
        self, hass: HomeAssistant, mock_setup_entry
    ):
        """Test the options flow."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="OpenWrt",
            data=MOCK_CONFIG_DATA,
            unique_id=MOCK_HOST,
        )
        entry.add_to_hass(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "init"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                "track_devices": False,
                "consider_home": 300,
                "device_tracker_scan_interval": 60,
                "stats_scan_interval": 120,
            },
        )

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"]["track_devices"] is False
        assert result["data"]["consider_home"] == 300
        assert result["data"]["device_tracker_scan_interval"] == 60
        assert result["data"]["stats_scan_interval"] == 120

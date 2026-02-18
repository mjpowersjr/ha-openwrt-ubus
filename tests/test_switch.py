"""Tests for the switch platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.core import HomeAssistant

from custom_components.openwrt_ubus.coordinator import StatsCoordinator
from custom_components.openwrt_ubus.switch import (
    OpenWrtWifiRadioSwitch,
    _band_label,
    _discover_wifi_radios,
)
from custom_components.openwrt_ubus.ubus_client import UbusError

from .conftest import create_mock_client


class TestDiscoverRadios:
    """Tests for WiFi radio discovery."""

    async def test_discover_radios(self):
        """Test discovering radios from UCI."""
        client = create_mock_client()
        radios = await _discover_wifi_radios(client)
        assert "radio0" in radios
        assert "radio1" in radios
        assert radios["radio0"]["band"] == "2g"
        assert radios["radio1"]["band"] == "5g"

    async def test_discover_radios_uci_error(self):
        """Test radio discovery when UCI fails."""
        client = create_mock_client()
        client.get_uci_config = AsyncMock(
            side_effect=UbusError("No access")
        )
        radios = await _discover_wifi_radios(client)
        assert radios == {}


class TestWifiRadioSwitch:
    """Tests for the WiFi radio switch."""

    async def test_initial_state_enabled(self, hass: HomeAssistant):
        """Test that radio starts as enabled."""
        client = create_mock_client()
        coordinator = StatsCoordinator(hass, client, scan_interval=60)
        await coordinator.async_refresh()

        switch = OpenWrtWifiRadioSwitch(
            coordinator=coordinator,
            entry_id="test",
            client=client,
            radio_name="radio0",
            radio_info={"band": "2g", "disabled": "0"},
        )
        assert switch.is_on is True

    async def test_initial_state_disabled(self, hass: HomeAssistant):
        """Test that a disabled radio reports off."""
        client = create_mock_client()
        coordinator = StatsCoordinator(hass, client, scan_interval=60)
        await coordinator.async_refresh()

        switch = OpenWrtWifiRadioSwitch(
            coordinator=coordinator,
            entry_id="test",
            client=client,
            radio_name="radio0",
            radio_info={"band": "2g", "disabled": "1"},
        )
        assert switch.is_on is False

    async def test_turn_off(self, hass: HomeAssistant):
        """Test disabling a radio."""
        client = create_mock_client()
        coordinator = StatsCoordinator(hass, client, scan_interval=60)
        await coordinator.async_refresh()

        switch = OpenWrtWifiRadioSwitch(
            coordinator=coordinator,
            entry_id="test",
            client=client,
            radio_name="radio0",
            radio_info={"band": "2g", "disabled": "0"},
        )
        # Patch async_write_ha_state since entity isn't registered with hass
        with patch.object(switch, "async_write_ha_state"):
            await switch.async_turn_off()

        client.uci_set.assert_called_once_with(
            "wireless", "radio0", {"disabled": "1"}
        )
        client.uci_commit.assert_called_once_with("wireless")
        assert switch.is_on is False

    async def test_turn_on(self, hass: HomeAssistant):
        """Test enabling a radio."""
        client = create_mock_client()
        coordinator = StatsCoordinator(hass, client, scan_interval=60)
        await coordinator.async_refresh()

        switch = OpenWrtWifiRadioSwitch(
            coordinator=coordinator,
            entry_id="test",
            client=client,
            radio_name="radio0",
            radio_info={"band": "2g", "disabled": "1"},
        )
        with patch.object(switch, "async_write_ha_state"):
            await switch.async_turn_on()

        client.uci_set.assert_called_once_with(
            "wireless", "radio0", {"disabled": "0"}
        )
        client.uci_commit.assert_called_once_with("wireless")
        assert switch.is_on is True

    async def test_turn_off_error(self, hass: HomeAssistant):
        """Test handling UCI error during toggle."""
        client = create_mock_client()
        client.uci_set = AsyncMock(side_effect=UbusError("UCI error"))
        coordinator = StatsCoordinator(hass, client, scan_interval=60)
        await coordinator.async_refresh()

        switch = OpenWrtWifiRadioSwitch(
            coordinator=coordinator,
            entry_id="test",
            client=client,
            radio_name="radio0",
            radio_info={"band": "2g", "disabled": "0"},
        )

        await switch.async_turn_off()
        # State should remain on because the set failed
        assert switch.is_on is True


class TestBandLabel:
    """Tests for band label conversion."""

    def test_2g(self):
        assert _band_label("2g") == "2.4 GHz"

    def test_5g(self):
        assert _band_label("5g") == "5 GHz"

    def test_6g(self):
        assert _band_label("6g") == "6 GHz"

    def test_unknown(self):
        assert _band_label("") == "Unknown"

    def test_custom(self):
        assert _band_label("60g") == "60g"

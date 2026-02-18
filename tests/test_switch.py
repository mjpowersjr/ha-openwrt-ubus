"""Tests for the switch platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.core import HomeAssistant

from custom_components.openwrt_ubus.coordinator import StatsCoordinator
from custom_components.openwrt_ubus.switch import (
    OpenWrtWifiApSwitch,
    OpenWrtWifiRadioSwitch,
    _band_label,
    _discover_wireless,
)
from custom_components.openwrt_ubus.ubus_client import UbusError

from .conftest import create_mock_client


class TestDiscoverWireless:
    """Tests for wireless discovery."""

    async def test_discover_radios(self):
        """Test discovering radios from UCI."""
        client = create_mock_client()
        wireless = await _discover_wireless(client)
        assert "radio0" in wireless["radios"]
        assert "radio1" in wireless["radios"]
        assert wireless["radios"]["radio0"]["band"] == "2g"
        assert wireless["radios"]["radio1"]["band"] == "5g"

    async def test_discover_ifaces(self):
        """Test discovering wifi-ifaces from UCI."""
        client = create_mock_client()
        wireless = await _discover_wireless(client)
        assert "default_radio0" in wireless["ifaces"]
        assert "default_radio1" in wireless["ifaces"]
        assert wireless["ifaces"]["default_radio0"]["ssid"] == "OpenWrt"
        assert wireless["ifaces"]["default_radio0"]["band"] == "2g"

    async def test_discover_uci_error(self):
        """Test discovery when UCI fails."""
        client = create_mock_client()
        client.get_uci_config = AsyncMock(
            side_effect=UbusError("No access")
        )
        wireless = await _discover_wireless(client)
        assert wireless["radios"] == {}
        assert wireless["ifaces"] == {}


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


class TestWifiApSwitch:
    """Tests for the WiFi AP switch."""

    async def test_initial_state_enabled(self, hass: HomeAssistant):
        """Test that AP starts as enabled."""
        client = create_mock_client()
        coordinator = StatsCoordinator(hass, client, scan_interval=60)
        await coordinator.async_refresh()

        switch = OpenWrtWifiApSwitch(
            coordinator=coordinator,
            entry_id="test",
            client=client,
            iface_name="default_radio0",
            iface_info={"ssid": "MyWiFi", "band": "2g", "disabled": "0"},
        )
        assert switch.is_on is True
        assert switch.name == "AP MyWiFi 2.4 GHz"

    async def test_turn_off_ap(self, hass: HomeAssistant):
        """Test disabling an AP."""
        client = create_mock_client()
        coordinator = StatsCoordinator(hass, client, scan_interval=60)
        await coordinator.async_refresh()

        switch = OpenWrtWifiApSwitch(
            coordinator=coordinator,
            entry_id="test",
            client=client,
            iface_name="guest2g",
            iface_info={"ssid": "Guest", "band": "2g", "disabled": "0"},
        )
        with patch.object(switch, "async_write_ha_state"):
            await switch.async_turn_off()

        client.uci_set.assert_called_once_with(
            "wireless", "guest2g", {"disabled": "1"}
        )
        client.uci_commit.assert_called_once_with("wireless")
        assert switch.is_on is False

    async def test_turn_on_ap(self, hass: HomeAssistant):
        """Test enabling an AP."""
        client = create_mock_client()
        coordinator = StatsCoordinator(hass, client, scan_interval=60)
        await coordinator.async_refresh()

        switch = OpenWrtWifiApSwitch(
            coordinator=coordinator,
            entry_id="test",
            client=client,
            iface_name="guest2g",
            iface_info={"ssid": "Guest", "band": "2g", "disabled": "1"},
        )
        with patch.object(switch, "async_write_ha_state"):
            await switch.async_turn_on()

        client.uci_set.assert_called_once_with(
            "wireless", "guest2g", {"disabled": "0"}
        )
        assert switch.is_on is True

    async def test_turn_off_error(self, hass: HomeAssistant):
        """Test handling UCI error during AP toggle."""
        client = create_mock_client()
        client.uci_set = AsyncMock(side_effect=UbusError("UCI error"))
        coordinator = StatsCoordinator(hass, client, scan_interval=60)
        await coordinator.async_refresh()

        switch = OpenWrtWifiApSwitch(
            coordinator=coordinator,
            entry_id="test",
            client=client,
            iface_name="guest2g",
            iface_info={"ssid": "Guest", "band": "2g", "disabled": "0"},
        )

        await switch.async_turn_off()
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

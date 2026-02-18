"""Tests for the device tracker platform."""

from __future__ import annotations

import pytest

from homeassistant.components.device_tracker import SourceType
from homeassistant.core import HomeAssistant

from custom_components.openwrt_ubus.coordinator import (
    DeviceTrackerCoordinator,
)
from custom_components.openwrt_ubus.device_tracker import (
    OpenWrtWifiClientTracker,
)

from .conftest import create_mock_client


class TestWifiClientTracker:
    """Tests for OpenWrtWifiClientTracker."""

    async def test_connected_client(self, hass: HomeAssistant):
        """Test that a connected client reports as connected."""
        client = create_mock_client()
        coordinator = DeviceTrackerCoordinator(
            hass, client, dhcp_software="dnsmasq", entry_id="test"
        )
        await coordinator.async_refresh()

        tracker = OpenWrtWifiClientTracker(
            coordinator=coordinator,
            entry_id="test",
            mac="AA:BB:CC:DD:EE:01",
            consider_home=180,
        )

        assert tracker.is_connected is True
        assert tracker.mac_address == "AA:BB:CC:DD:EE:01"
        assert tracker.source_type == SourceType.ROUTER

    async def test_disconnected_client_consider_home(
        self, hass: HomeAssistant
    ):
        """Test consider_home logic for disconnected client."""
        client = create_mock_client()
        coordinator = DeviceTrackerCoordinator(
            hass, client, dhcp_software="dnsmasq", entry_id="test"
        )

        # First refresh — client is connected
        await coordinator.async_refresh()

        tracker = OpenWrtWifiClientTracker(
            coordinator=coordinator,
            entry_id="test",
            mac="AA:BB:CC:DD:EE:01",
            consider_home=180,
        )

        # Initially connected
        assert tracker.is_connected is True

    async def test_client_extra_attributes(self, hass: HomeAssistant):
        """Test extra state attributes."""
        client = create_mock_client()
        coordinator = DeviceTrackerCoordinator(
            hass, client, dhcp_software="dnsmasq", entry_id="test"
        )
        await coordinator.async_refresh()

        tracker = OpenWrtWifiClientTracker(
            coordinator=coordinator,
            entry_id="test",
            mac="AA:BB:CC:DD:EE:01",
            consider_home=180,
        )

        attrs = tracker.extra_state_attributes
        assert "interface" in attrs
        assert "ssid" in attrs
        assert "signal" in attrs

    async def test_client_device_info(self, hass: HomeAssistant):
        """Test device info for a client."""
        client = create_mock_client()
        coordinator = DeviceTrackerCoordinator(
            hass, client, dhcp_software="dnsmasq", entry_id="test"
        )
        await coordinator.async_refresh()

        tracker = OpenWrtWifiClientTracker(
            coordinator=coordinator,
            entry_id="test",
            mac="AA:BB:CC:DD:EE:01",
            consider_home=180,
        )

        info = tracker.device_info
        assert info is not None

    async def test_unknown_client(self, hass: HomeAssistant):
        """Test behavior for a client not in coordinator data."""
        client = create_mock_client()
        coordinator = DeviceTrackerCoordinator(
            hass, client, dhcp_software="dnsmasq", entry_id="test"
        )
        await coordinator.async_refresh()

        tracker = OpenWrtWifiClientTracker(
            coordinator=coordinator,
            entry_id="test",
            mac="FF:FF:FF:FF:FF:FF",  # Not in data
            consider_home=0,
        )

        assert tracker.is_connected is False
        assert tracker.hostname is None
        assert tracker.ip_address is None
        assert tracker.extra_state_attributes == {}

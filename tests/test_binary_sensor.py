"""Tests for the binary sensor platform."""

from __future__ import annotations

import pytest

from homeassistant.core import HomeAssistant

from custom_components.openwrt_ubus.binary_sensor import (
    OpenWrtWanConnectivity,
)
from custom_components.openwrt_ubus.coordinator import StatsCoordinator

from .conftest import create_mock_client


class TestWanConnectivity:
    """Tests for WAN connectivity binary sensor."""

    async def test_wan_up(self, hass: HomeAssistant):
        """Test WAN connected state."""
        client = create_mock_client()
        coordinator = StatsCoordinator(hass, client, scan_interval=60)
        await coordinator.async_refresh()

        sensor = OpenWrtWanConnectivity(coordinator, "test")
        assert sensor.is_on is True

    async def test_wan_down(self, hass: HomeAssistant):
        """Test WAN disconnected state when no wan interface is up."""
        client = create_mock_client()
        # Override network dump to have wan down
        client.get_network_interface_dump.return_value = {
            "interface": [
                {
                    "interface": "wan",
                    "up": False,
                    "proto": "dhcp",
                    "l3_device": "eth1",
                    "device": "eth1",
                },
            ]
        }
        coordinator = StatsCoordinator(hass, client, scan_interval=60)
        await coordinator.async_refresh()

        sensor = OpenWrtWanConnectivity(coordinator, "test")
        assert sensor.is_on is False

    async def test_no_data(self, hass: HomeAssistant):
        """Test when coordinator has no data."""
        client = create_mock_client()
        coordinator = StatsCoordinator(hass, client, scan_interval=60)
        # Don't refresh — data is None

        sensor = OpenWrtWanConnectivity(coordinator, "test")
        assert sensor.is_on is None

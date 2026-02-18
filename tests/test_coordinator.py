"""Tests for the coordinators."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.core import HomeAssistant

from custom_components.openwrt_ubus.coordinator import (
    DeviceTrackerCoordinator,
    StatsCoordinator,
)
from custom_components.openwrt_ubus.ubus_client import UbusError

from .conftest import (
    MOCK_HOSTAPD_WLAN0,
    MOCK_SYSTEM_BOARD,
    MOCK_SYSTEM_INFO,
    create_mock_client,
)


class TestStatsCoordinator:
    """Tests for StatsCoordinator."""

    async def test_fetch_system_info(self, hass: HomeAssistant):
        """Test fetching system board and info data."""
        client = create_mock_client()
        coordinator = StatsCoordinator(hass, client, scan_interval=60)
        await coordinator.async_refresh()

        assert coordinator.data is not None
        assert coordinator.data.hostname == "OpenWrt"
        assert coordinator.data.model == "Linksys E8450 (UBI)"
        assert coordinator.data.firmware_version == "OpenWrt 23.05.3 r23809-234f1a2efa"
        assert coordinator.data.uptime == 123456

    async def test_fetch_memory_info(self, hass: HomeAssistant):
        """Test memory info parsing."""
        client = create_mock_client()
        coordinator = StatsCoordinator(hass, client, scan_interval=60)
        await coordinator.async_refresh()

        assert coordinator.data.memory_total == 262144000
        assert coordinator.data.memory_free == 131072000
        assert coordinator.data.memory_buffered == 16384000

    async def test_load_average_conversion(self, hass: HomeAssistant):
        """Test that load averages are converted from fixed-point."""
        client = create_mock_client()
        coordinator = StatsCoordinator(hass, client, scan_interval=60)
        await coordinator.async_refresh()

        # 19660 / 65536 ≈ 0.30
        assert coordinator.data.load_1m == 0.30
        # 22937 / 65536 ≈ 0.35
        assert coordinator.data.load_5m == 0.35
        # 24576 / 65536 = 0.375 → 0.38
        assert coordinator.data.load_15m == 0.38

    async def test_wan_status(self, hass: HomeAssistant):
        """Test WAN up/down detection."""
        client = create_mock_client()
        coordinator = StatsCoordinator(hass, client, scan_interval=60)
        await coordinator.async_refresh()

        assert coordinator.data.wan_up is True
        assert "wan" in coordinator.data.interfaces
        assert coordinator.data.interfaces["wan"].ipv4_address == "100.64.1.50"

    async def test_network_device_stats(self, hass: HomeAssistant):
        """Test per-device TX/RX byte counters."""
        client = create_mock_client()
        coordinator = StatsCoordinator(hass, client, scan_interval=60)
        await coordinator.async_refresh()

        assert "eth1" in coordinator.data.devices
        assert coordinator.data.devices["eth1"].tx_bytes == 5000000
        assert coordinator.data.devices["eth1"].rx_bytes == 15000000

    async def test_board_info_cached(self, hass: HomeAssistant):
        """Test that system board info is cached after first fetch."""
        client = create_mock_client()
        coordinator = StatsCoordinator(hass, client, scan_interval=60)

        await coordinator.async_refresh()
        await coordinator.async_refresh()

        # get_system_board should only be called once (cached)
        assert client.get_system_board.call_count == 1
        # get_system_info should be called every time
        assert client.get_system_info.call_count == 2

    async def test_wireless_radio_discovery(self, hass: HomeAssistant):
        """Test wireless radio discovery."""
        client = create_mock_client()
        coordinator = StatsCoordinator(hass, client, scan_interval=60)
        await coordinator.async_refresh()

        assert len(coordinator.data.radios) >= 1


class TestDeviceTrackerCoordinator:
    """Tests for DeviceTrackerCoordinator."""

    async def test_fetch_wifi_clients(self, hass: HomeAssistant):
        """Test fetching WiFi clients from hostapd."""
        client = create_mock_client()
        coordinator = DeviceTrackerCoordinator(
            hass, client, dhcp_software="dnsmasq", entry_id="test"
        )
        await coordinator.async_refresh()

        assert coordinator.data is not None
        clients = coordinator.data.clients
        assert len(clients) >= 2  # At least from wlan0

    async def test_hostname_resolution_dnsmasq(self, hass: HomeAssistant):
        """Test hostname resolution from dnsmasq leases."""
        client = create_mock_client()
        coordinator = DeviceTrackerCoordinator(
            hass, client, dhcp_software="dnsmasq", entry_id="test"
        )
        await coordinator.async_refresh()

        clients = coordinator.data.clients
        # AA:BB:CC:DD:EE:01 should resolve to "phone"
        mac01 = "AA:BB:CC:DD:EE:01"
        if mac01 in clients:
            assert clients[mac01].hostname == "phone"
            assert clients[mac01].ip_address == "192.168.1.100"

    async def test_no_dhcp_resolution(self, hass: HomeAssistant):
        """Test that DHCP none skips resolution."""
        client = create_mock_client()
        coordinator = DeviceTrackerCoordinator(
            hass, client, dhcp_software="none", entry_id="test"
        )
        await coordinator.async_refresh()

        # file_read should not be called
        client.file_read.assert_not_called()

    async def test_client_signal_info(self, hass: HomeAssistant):
        """Test that signal info is captured."""
        client = create_mock_client()
        coordinator = DeviceTrackerCoordinator(
            hass, client, dhcp_software="dnsmasq", entry_id="test"
        )
        await coordinator.async_refresh()

        clients = coordinator.data.clients
        for mac, c in clients.items():
            assert c.connected is True
            # Signal should be a negative number
            if c.signal is not None:
                assert c.signal < 0

    async def test_hostapd_interface_discovery_fallback(
        self, hass: HomeAssistant
    ):
        """Test fallback interface discovery when UCI fails."""
        client = create_mock_client()
        client.get_uci_config = AsyncMock(
            side_effect=UbusError("No access")
        )
        coordinator = DeviceTrackerCoordinator(
            hass, client, dhcp_software="dnsmasq", entry_id="test"
        )
        await coordinator.async_refresh()

        # Should still discover interfaces via fallback
        assert coordinator._hostapd_interfaces is not None

"""Tests for the sensor platform."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from homeassistant.core import HomeAssistant

from custom_components.openwrt_ubus.coordinator import (
    NetworkDeviceData,
    NetworkInterfaceData,
    StatsCoordinator,
    StatsData,
    WirelessRadioData,
)
from custom_components.openwrt_ubus.sensor import SYSTEM_SENSORS

from .conftest import create_mock_client


class TestSystemSensors:
    """Tests for system sensor descriptions."""

    def _make_stats_data(self) -> StatsData:
        """Create test StatsData."""
        return StatsData(
            hostname="OpenWrt",
            model="Test Router",
            firmware_version="23.05.3",
            kernel_version="5.15.150",
            uptime=3600,
            memory_total=262144000,
            memory_free=131072000,
            memory_buffered=16384000,
            load_1m=0.30,
            load_5m=0.35,
            load_15m=0.38,
            interfaces={
                "wan": NetworkInterfaceData(
                    name="wan",
                    up=True,
                    proto="dhcp",
                    ipv4_address="100.64.1.50",
                    device="eth1",
                ),
            },
            devices={
                "eth1": NetworkDeviceData(
                    name="eth1", tx_bytes=5000000, rx_bytes=15000000
                ),
            },
            wan_up=True,
            radios={
                "wlan0": WirelessRadioData(
                    device="wlan0",
                    ssid="OpenWrt",
                    channel=6,
                    frequency=2437,
                    client_count=2,
                ),
            },
        )

    def test_uptime_sensor(self):
        """Test uptime sensor returns a timestamp."""
        data = self._make_stats_data()
        uptime_desc = next(s for s in SYSTEM_SENSORS if s.key == "uptime")
        value = uptime_desc.value_fn(data)
        assert isinstance(value, datetime)

    def test_load_sensors(self):
        """Test load average sensors."""
        data = self._make_stats_data()
        for key, expected in [
            ("load_1m", 0.30),
            ("load_5m", 0.35),
            ("load_15m", 0.38),
        ]:
            desc = next(s for s in SYSTEM_SENSORS if s.key == key)
            assert desc.value_fn(data) == expected

    def test_memory_usage_sensor(self):
        """Test memory usage percentage calculation."""
        data = self._make_stats_data()
        desc = next(s for s in SYSTEM_SENSORS if s.key == "memory_usage")
        value = desc.value_fn(data)
        # (262144000 - 131072000 - 16384000) / 262144000 * 100 ≈ 43.75
        assert value == pytest.approx(43.8, abs=0.1)

    def test_memory_free_sensor(self):
        """Test memory free in MB."""
        data = self._make_stats_data()
        desc = next(s for s in SYSTEM_SENSORS if s.key == "memory_free")
        value = desc.value_fn(data)
        # 131072000 / 1048576 = 125.0 MB
        assert value == 125.0

    def test_firmware_version_sensor(self):
        """Test firmware version string."""
        data = self._make_stats_data()
        desc = next(
            s for s in SYSTEM_SENSORS if s.key == "firmware_version"
        )
        assert desc.value_fn(data) == "23.05.3"

    def test_connected_clients_sensor(self):
        """Test connected clients count."""
        data = self._make_stats_data()
        desc = next(
            s for s in SYSTEM_SENSORS if s.key == "connected_clients"
        )
        assert desc.value_fn(data) == 2

    def test_memory_usage_zero_total(self):
        """Test memory usage when total is zero."""
        data = StatsData(memory_total=0)
        desc = next(s for s in SYSTEM_SENSORS if s.key == "memory_usage")
        assert desc.value_fn(data) is None

    def test_memory_free_zero(self):
        """Test memory free when value is zero."""
        data = StatsData(memory_free=0)
        desc = next(s for s in SYSTEM_SENSORS if s.key == "memory_free")
        assert desc.value_fn(data) is None

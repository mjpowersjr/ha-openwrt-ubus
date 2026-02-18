"""Test fixtures for the OpenWrt ubus integration."""

from __future__ import annotations

import pathlib
from unittest.mock import AsyncMock

import pytest

from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SSL,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant
from homeassistant.loader import DATA_CUSTOM_COMPONENTS, Integration

from custom_components.openwrt_ubus.const import (
    CONF_DHCP_SOFTWARE,
    CONF_VERIFY_SSL,
    DHCP_DNSMASQ,
    DOMAIN,
)

MOCK_HOST = "192.168.1.1"
MOCK_PORT = 80
MOCK_USERNAME = "root"
MOCK_PASSWORD = "testpass"

MOCK_CONFIG_DATA = {
    CONF_HOST: MOCK_HOST,
    CONF_PORT: MOCK_PORT,
    CONF_USERNAME: MOCK_USERNAME,
    CONF_PASSWORD: MOCK_PASSWORD,
    CONF_SSL: False,
    CONF_VERIFY_SSL: True,
    CONF_DHCP_SOFTWARE: DHCP_DNSMASQ,
}

MOCK_SYSTEM_BOARD = {
    "hostname": "OpenWrt",
    "model": "Linksys E8450 (UBI)",
    "board_name": "linksys,e8450-ubi",
    "rootfs_type": "squashfs",
    "release": {
        "distribution": "OpenWrt",
        "version": "23.05.3",
        "revision": "r23809-234f1a2efa",
        "target": "mediatek/mt7622",
        "description": "OpenWrt 23.05.3 r23809-234f1a2efa",
    },
    "kernel": "5.15.150",
    "system": "MediaTek MT7622BV",
}

MOCK_SYSTEM_INFO = {
    "uptime": 123456,
    "localtime": 1700000000,
    "load": [19660, 22937, 24576],  # Fixed-point: /65536 → 0.30, 0.35, 0.375
    "memory": {
        "total": 262144000,
        "free": 131072000,
        "shared": 1024000,
        "buffered": 16384000,
    },
    "swap": {"total": 0, "free": 0},
}

MOCK_NETWORK_INTERFACE_DUMP = {
    "interface": [
        {
            "interface": "loopback",
            "up": True,
            "proto": "static",
            "device": "lo",
            "ipv4-address": [{"address": "127.0.0.1", "mask": 8}],
        },
        {
            "interface": "lan",
            "up": True,
            "proto": "static",
            "l3_device": "br-lan",
            "device": "br-lan",
            "uptime": 123000,
            "ipv4-address": [{"address": "192.168.1.1", "mask": 24}],
        },
        {
            "interface": "wan",
            "up": True,
            "proto": "dhcp",
            "l3_device": "eth1",
            "device": "eth1",
            "uptime": 120000,
            "ipv4-address": [{"address": "100.64.1.50", "mask": 24}],
        },
    ]
}

MOCK_DEVICE_STATUS_ETH1 = {
    "up": True,
    "statistics": {
        "tx_bytes": 5000000,
        "rx_bytes": 15000000,
        "tx_packets": 50000,
        "rx_packets": 100000,
    },
}

MOCK_DEVICE_STATUS_BR_LAN = {
    "up": True,
    "statistics": {
        "tx_bytes": 10000000,
        "rx_bytes": 20000000,
        "tx_packets": 80000,
        "rx_packets": 150000,
    },
}

MOCK_UCI_WIRELESS = {
    "values": {
        "radio0": {
            ".anonymous": False,
            ".type": "wifi-device",
            ".name": "radio0",
            "type": "mac80211",
            "band": "2g",
            "htmode": "HE20",
            "disabled": "0",
            "channel": "auto",
        },
        "radio1": {
            ".anonymous": False,
            ".type": "wifi-device",
            ".name": "radio1",
            "type": "mac80211",
            "band": "5g",
            "htmode": "HE80",
            "disabled": "0",
            "channel": "auto",
        },
        "default_radio0": {
            ".anonymous": False,
            ".type": "wifi-iface",
            ".name": "default_radio0",
            "device": "radio0",
            "network": "lan",
            "mode": "ap",
            "ssid": "OpenWrt",
            "encryption": "sae-mixed",
            "ifname": "wlan0",
        },
        "default_radio1": {
            ".anonymous": False,
            ".type": "wifi-iface",
            ".name": "default_radio1",
            "device": "radio1",
            "network": "lan",
            "mode": "ap",
            "ssid": "OpenWrt-5G",
            "encryption": "sae-mixed",
            "ifname": "wlan1",
        },
    }
}

MOCK_IWINFO_WLAN0 = {
    "ssid": "OpenWrt",
    "channel": 6,
    "frequency": 2437,
    "signal": -50,
    "noise": -95,
}

MOCK_IWINFO_WLAN1 = {
    "ssid": "OpenWrt-5G",
    "channel": 36,
    "frequency": 5180,
    "signal": -45,
    "noise": -90,
}

MOCK_HOSTAPD_WLAN0 = {
    "freq": 2437,
    "clients": {
        "AA:BB:CC:DD:EE:01": {
            "authorized": True,
            "signal": -55,
            "bytes": {"rx": 1000000, "tx": 500000},
            "rx_rate": 72000,
            "tx_rate": 54000,
        },
        "AA:BB:CC:DD:EE:02": {
            "authorized": True,
            "signal": -70,
            "bytes": {"rx": 200000, "tx": 100000},
            "rx_rate": 24000,
            "tx_rate": 18000,
        },
    },
}

MOCK_HOSTAPD_WLAN1 = {
    "freq": 5180,
    "clients": {
        "AA:BB:CC:DD:EE:03": {
            "authorized": True,
            "signal": -40,
            "bytes": {"rx": 5000000, "tx": 3000000},
            "rx_rate": 866000,
            "tx_rate": 600000,
        },
    },
}

MOCK_DNSMASQ_LEASES = {
    "data": (
        "1700000000 AA:BB:CC:DD:EE:01 192.168.1.100 phone *\n"
        "1700000000 AA:BB:CC:DD:EE:02 192.168.1.101 laptop *\n"
        "1700000000 AA:BB:CC:DD:EE:03 192.168.1.102 tablet *\n"
    )
}


def create_mock_client() -> AsyncMock:
    """Create a mock UbusClient."""
    client = AsyncMock()
    client.host = MOCK_HOST
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.get_system_board = AsyncMock(return_value=MOCK_SYSTEM_BOARD)
    client.get_system_info = AsyncMock(return_value=MOCK_SYSTEM_INFO)
    client.get_network_interface_dump = AsyncMock(
        return_value=MOCK_NETWORK_INTERFACE_DUMP
    )
    client.get_network_device_status = AsyncMock(
        side_effect=_mock_device_status
    )
    client.get_uci_config = AsyncMock(side_effect=_mock_uci_config)
    client.get_iwinfo = AsyncMock(side_effect=_mock_iwinfo)
    client.get_hostapd_clients = AsyncMock(side_effect=_mock_hostapd)
    client.file_read = AsyncMock(return_value=MOCK_DNSMASQ_LEASES)
    client.get_dhcp_ipv4_leases = AsyncMock(return_value={})
    client.uci_set = AsyncMock(return_value={})
    client.uci_commit = AsyncMock(return_value={})
    client.system_reboot = AsyncMock(return_value={})
    return client


async def _mock_device_status(device: str) -> dict:
    """Return mock device status based on device name."""
    if device == "eth1":
        return MOCK_DEVICE_STATUS_ETH1
    if device == "br-lan":
        return MOCK_DEVICE_STATUS_BR_LAN
    return {"statistics": {"tx_bytes": 0, "rx_bytes": 0}}


async def _mock_uci_config(config: str, section: str | None = None) -> dict:
    """Return mock UCI config."""
    if config == "wireless":
        if section and section in MOCK_UCI_WIRELESS["values"]:
            return {"values": MOCK_UCI_WIRELESS["values"][section]}
        return MOCK_UCI_WIRELESS
    return {"values": {}}


async def _mock_iwinfo(device: str) -> dict:
    """Return mock iwinfo."""
    if device == "wlan0":
        return MOCK_IWINFO_WLAN0
    if device == "wlan1":
        return MOCK_IWINFO_WLAN1
    return {}


async def _mock_hostapd(interface: str) -> dict:
    """Return mock hostapd data."""
    if interface == "wlan0":
        return MOCK_HOSTAPD_WLAN0
    if interface == "wlan1":
        return MOCK_HOSTAPD_WLAN1
    from custom_components.openwrt_ubus.ubus_client import UbusError

    raise UbusError(f"No such interface: {interface}")


@pytest.fixture
def mock_client() -> AsyncMock:
    """Provide a mock UbusClient."""
    return create_mock_client()


@pytest.fixture(autouse=True)
def _register_custom_integration(hass: HomeAssistant) -> None:
    """Register the openwrt_ubus integration with the test HA instance."""
    import json
    import custom_components.openwrt_ubus as comp_module

    comp_path = pathlib.Path(comp_module.__file__).parent
    manifest_path = comp_path / "manifest.json"
    with open(manifest_path) as f:
        manifest = json.load(f)

    integration = Integration(
        hass,
        f"custom_components.{DOMAIN}",
        comp_path,
        manifest,
    )

    # Register in the integration cache so the loader can find it
    from homeassistant.loader import DATA_INTEGRATIONS

    hass.data.setdefault(DATA_INTEGRATIONS, {})
    hass.data[DATA_INTEGRATIONS][DOMAIN] = integration

    # Also register in custom components cache
    hass.data.setdefault(DATA_CUSTOM_COMPONENTS, {})
    hass.data[DATA_CUSTOM_COMPONENTS][DOMAIN] = integration

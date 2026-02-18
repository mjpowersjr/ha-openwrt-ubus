"""Constants for the OpenWrt ubus integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "openwrt_ubus"

PLATFORMS: Final = [
    "binary_sensor",
    "button",
    "device_tracker",
    "sensor",
    "switch",
]

# Config keys
CONF_DHCP_SOFTWARE: Final = "dhcp_software"
CONF_VERIFY_SSL: Final = "verify_ssl"

# Options keys
CONF_TRACK_DEVICES: Final = "track_devices"
CONF_CONSIDER_HOME: Final = "consider_home"
CONF_DEVICE_TRACKER_SCAN_INTERVAL: Final = "device_tracker_scan_interval"
CONF_STATS_SCAN_INTERVAL: Final = "stats_scan_interval"

# Defaults
DEFAULT_PORT: Final = 80
DEFAULT_HTTPS: Final = False
DEFAULT_VERIFY_SSL: Final = True
DEFAULT_DHCP_SOFTWARE: Final = "dnsmasq"
DEFAULT_TRACK_DEVICES: Final = True
DEFAULT_CONSIDER_HOME: Final = 180
DEFAULT_DEVICE_TRACKER_SCAN_INTERVAL: Final = 30
DEFAULT_STATS_SCAN_INTERVAL: Final = 60

# DHCP software options
DHCP_DNSMASQ: Final = "dnsmasq"
DHCP_ODHCPD: Final = "odhcpd"
DHCP_NONE: Final = "none"

# Ubus JSON-RPC
UBUS_URL_PATH: Final = "/ubus"
UBUS_SESSION_ANONYMOUS: Final = "00000000000000000000000000000000"
UBUS_ERROR_ACCESS_DENIED: Final = -32002

# Dispatcher signals
SIGNAL_NEW_DEVICE: Final = f"{DOMAIN}_new_device"

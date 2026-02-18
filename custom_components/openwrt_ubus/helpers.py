"""Helper utilities for the OpenWrt ubus integration."""

from __future__ import annotations


def format_mac(mac: str) -> str:
    """Format a MAC address to uppercase colon-separated form."""
    mac = mac.upper().replace("-", ":").replace(".", ":")
    # Handle cases like AABB.CCDD.EEFF (Cisco format)
    if len(mac) == 14 and mac.count(":") == 2:
        mac = mac.replace(":", "")
        mac = ":".join(mac[i : i + 2] for i in range(0, 12, 2))
    return mac

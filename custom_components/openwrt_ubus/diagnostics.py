"""Diagnostics support for the OpenWrt ubus integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from . import get_entry_data

TO_REDACT_CONFIG = {CONF_PASSWORD, CONF_USERNAME}
TO_REDACT_DATA = {"ipv4_address", "ip_address", "hostname"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = get_entry_data(hass, entry)

    # System info from stats coordinator
    stats = data.stats_coordinator.data
    stats_dict: dict[str, Any] = {}
    if stats:
        stats_dict = {
            "hostname": stats.hostname,
            "model": stats.model,
            "firmware_version": stats.firmware_version,
            "kernel_version": stats.kernel_version,
            "uptime": stats.uptime,
            "memory_total": stats.memory_total,
            "memory_free": stats.memory_free,
            "memory_buffered": stats.memory_buffered,
            "load_1m": stats.load_1m,
            "load_5m": stats.load_5m,
            "load_15m": stats.load_15m,
            "wan_up": stats.wan_up,
            "interfaces": {
                name: {
                    "up": iface.up,
                    "proto": iface.proto,
                    "ipv4_address": iface.ipv4_address,
                    "uptime": iface.uptime,
                    "device": iface.device,
                }
                for name, iface in stats.interfaces.items()
            },
            "devices": {
                name: {
                    "tx_bytes": dev.tx_bytes,
                    "rx_bytes": dev.rx_bytes,
                }
                for name, dev in stats.devices.items()
            },
            "radios": {
                name: {
                    "ssid": radio.ssid,
                    "channel": radio.channel,
                    "frequency": radio.frequency,
                    "signal": radio.signal,
                    "noise": radio.noise,
                    "client_count": radio.client_count,
                }
                for name, radio in stats.radios.items()
            },
        }

    # Device tracker info
    dt_data = data.device_tracker_coordinator.data
    clients_dict: dict[str, Any] = {}
    if dt_data:
        for mac, client in dt_data.clients.items():
            # Partially redact MAC: keep first 3 octets
            redacted_mac = mac[:8] + ":XX:XX:XX"
            clients_dict[redacted_mac] = {
                "hostname": client.hostname,
                "ip_address": client.ip_address,
                "interface": client.interface,
                "ssid": client.ssid,
                "signal": client.signal,
                "connected": client.connected,
            }

    return {
        "config": async_redact_data(dict(entry.data), TO_REDACT_CONFIG),
        "options": dict(entry.options),
        "stats": async_redact_data(stats_dict, TO_REDACT_DATA),
        "tracked_clients": async_redact_data(clients_dict, TO_REDACT_DATA),
    }

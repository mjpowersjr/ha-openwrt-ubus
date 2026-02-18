"""Device tracker platform for OpenWrt ubus integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.components.device_tracker import ScannerEntity, SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
)
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import get_entry_data
from .const import (
    CONF_CONSIDER_HOME,
    CONF_TRACK_DEVICES,
    DEFAULT_CONSIDER_HOME,
    DEFAULT_TRACK_DEVICES,
    DOMAIN,
    SIGNAL_NEW_DEVICE,
)
from .coordinator import DeviceTrackerCoordinator, TrackedClient
from .entity import OpenWrtDeviceTrackerEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up device tracker entities."""
    if not entry.options.get(CONF_TRACK_DEVICES, DEFAULT_TRACK_DEVICES):
        return

    data = get_entry_data(hass, entry)
    coordinator = data.device_tracker_coordinator
    consider_home = entry.options.get(CONF_CONSIDER_HOME, DEFAULT_CONSIDER_HOME)
    tracked_macs: set[str] = set()

    @callback
    def _add_new_entities() -> None:
        """Add entities for any newly discovered clients."""
        if coordinator.data is None:
            return

        new_entities: list[OpenWrtWifiClientTracker] = []
        for mac, client_data in coordinator.data.clients.items():
            if mac not in tracked_macs:
                tracked_macs.add(mac)
                new_entities.append(
                    OpenWrtWifiClientTracker(
                        coordinator=coordinator,
                        entry_id=entry.entry_id,
                        mac=mac,
                        consider_home=consider_home,
                    )
                )

        if new_entities:
            async_add_entities(new_entities)

    # Add entities for initially known clients
    _add_new_entities()

    # Subscribe to new device discovery
    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            f"{SIGNAL_NEW_DEVICE}_{entry.entry_id}",
            _add_new_entities,
        )
    )


class OpenWrtWifiClientTracker(OpenWrtDeviceTrackerEntity, ScannerEntity):
    """Represents a WiFi client connected to the OpenWrt router."""

    def __init__(
        self,
        coordinator: DeviceTrackerCoordinator,
        entry_id: str,
        mac: str,
        consider_home: int,
    ) -> None:
        """Initialize the WiFi client tracker."""
        super().__init__(coordinator, entry_id, mac)
        self._consider_home = timedelta(seconds=consider_home)
        self._last_seen = None
        self._attr_unique_id = f"{entry_id}_{mac}"

        # Set initial name from client data if available
        client = self._get_client()
        if client and client.hostname:
            self._attr_name = client.hostname
        else:
            self._attr_name = mac

    def _get_client(self) -> TrackedClient | None:
        """Get the client data from the coordinator."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.clients.get(self._mac)

    @property
    def source_type(self) -> SourceType:
        """Return the source type."""
        return SourceType.ROUTER

    @property
    def is_connected(self) -> bool:
        """Return true if the client is connected."""
        client = self._get_client()
        now = dt_util.utcnow()

        if client and client.connected:
            self._last_seen = now
            return True

        # Consider home logic
        if self._last_seen and (now - self._last_seen) < self._consider_home:
            return True

        return False

    @property
    def mac_address(self) -> str:
        """Return the MAC address."""
        return self._mac

    @property
    def hostname(self) -> str | None:
        """Return the hostname."""
        client = self._get_client()
        return client.hostname if client else None

    @property
    def ip_address(self) -> str | None:
        """Return the IP address."""
        client = self._get_client()
        return client.ip_address if client else None

    @property
    def extra_state_attributes(self) -> dict[str, str | int | None]:
        """Return extra state attributes."""
        client = self._get_client()
        if not client:
            return {}
        return {
            "interface": client.interface,
            "ssid": client.ssid,
            "signal": client.signal,
            "rx_rate": client.rx_rate,
            "tx_rate": client.tx_rate,
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for this WiFi client."""
        client = self._get_client()
        name = (client.hostname if client and client.hostname else self._mac)
        return DeviceInfo(
            connections={(CONNECTION_NETWORK_MAC, self._mac)},
            name=name,
            via_device=(DOMAIN, self._entry_id),
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Update name if hostname was resolved later
        client = self._get_client()
        if client and client.hostname and self._attr_name == self._mac:
            self._attr_name = client.hostname
        super()._handle_coordinator_update()

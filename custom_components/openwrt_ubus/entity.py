"""Base entity classes for the OpenWrt ubus integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DeviceTrackerCoordinator, StatsCoordinator, StatsData


class OpenWrtStatsEntity(CoordinatorEntity[StatsCoordinator]):
    """Base entity for router-level stats entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: StatsCoordinator,
        entry_id: str,
    ) -> None:
        """Initialize the stats entity."""
        super().__init__(coordinator)
        self._entry_id = entry_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the router."""
        data: StatsData = self.coordinator.data
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name=data.hostname or "OpenWrt Router",
            manufacturer="OpenWrt",
            model=data.model,
            sw_version=data.firmware_version,
            configuration_url=(
                f"http://{self.coordinator.client.host}"
            ),
        )


class OpenWrtDeviceTrackerEntity(
    CoordinatorEntity[DeviceTrackerCoordinator]
):
    """Base entity for tracked WiFi client entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DeviceTrackerCoordinator,
        entry_id: str,
        mac: str,
    ) -> None:
        """Initialize the device tracker entity."""
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._mac = mac

"""Binary sensor platform for the OpenWrt ubus integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import get_entry_data
from .coordinator import StatsCoordinator
from .entity import OpenWrtStatsEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensor entities."""
    entry_data = get_entry_data(hass, entry)
    coordinator = entry_data.stats_coordinator
    async_add_entities([OpenWrtWanConnectivity(coordinator, entry.entry_id)])


class OpenWrtWanConnectivity(OpenWrtStatsEntity, BinarySensorEntity):
    """Binary sensor indicating WAN connectivity."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_name = "WAN connected"

    def __init__(
        self,
        coordinator: StatsCoordinator,
        entry_id: str,
    ) -> None:
        """Initialize the WAN connectivity sensor."""
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_wan_connected"

    @property
    def is_on(self) -> bool | None:
        """Return true if WAN is connected."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.wan_up

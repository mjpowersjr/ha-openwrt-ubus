"""Button platform for the OpenWrt ubus integration."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import get_entry_data
from .coordinator import StatsCoordinator
from .entity import OpenWrtStatsEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up button entities."""
    entry_data = get_entry_data(hass, entry)
    coordinator = entry_data.stats_coordinator
    client = entry_data.client
    async_add_entities(
        [OpenWrtRebootButton(coordinator, entry.entry_id, client)]
    )


class OpenWrtRebootButton(OpenWrtStatsEntity, ButtonEntity):
    """Button to reboot the OpenWrt router."""

    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG
    _attr_name = "Reboot"

    def __init__(
        self,
        coordinator: StatsCoordinator,
        entry_id: str,
        client,
    ) -> None:
        """Initialize the reboot button."""
        super().__init__(coordinator, entry_id)
        self._client = client
        self._attr_unique_id = f"{entry_id}_reboot"

    async def async_press(self) -> None:
        """Reboot the router."""
        _LOGGER.info("Rebooting OpenWrt router")
        await self._client.system_reboot()

"""Switch platform for the OpenWrt ubus integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import get_entry_data
from .coordinator import StatsCoordinator
from .entity import OpenWrtStatsEntity
from .ubus_client import UbusClient, UbusError

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switch entities for WiFi radios."""
    entry_data = get_entry_data(hass, entry)
    coordinator = entry_data.stats_coordinator
    client = entry_data.client

    # Discover WiFi radios from UCI wireless config
    radios = await _discover_wifi_radios(client)

    entities: list[OpenWrtWifiRadioSwitch] = []
    for radio_name, radio_info in radios.items():
        entities.append(
            OpenWrtWifiRadioSwitch(
                coordinator=coordinator,
                entry_id=entry.entry_id,
                client=client,
                radio_name=radio_name,
                radio_info=radio_info,
            )
        )

    async_add_entities(entities)


async def _discover_wifi_radios(
    client: UbusClient,
) -> dict[str, dict[str, Any]]:
    """Discover WiFi radio sections from UCI wireless config."""
    radios: dict[str, dict[str, Any]] = {}
    try:
        uci_result = await client.get_uci_config("wireless")
        values = uci_result.get("values", {})
        for section_name, section_data in values.items():
            if section_data.get(".type") == "wifi-device":
                band = section_data.get("band", "")
                htmode = section_data.get("htmode", "")
                radios[section_name] = {
                    "band": band,
                    "htmode": htmode,
                    "disabled": section_data.get("disabled", "0"),
                }
    except UbusError:
        _LOGGER.debug("Could not discover WiFi radios from UCI")
    return radios


class OpenWrtWifiRadioSwitch(OpenWrtStatsEntity, SwitchEntity):
    """Switch to enable/disable a WiFi radio."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:wifi"

    def __init__(
        self,
        coordinator: StatsCoordinator,
        entry_id: str,
        client: UbusClient,
        radio_name: str,
        radio_info: dict[str, Any],
    ) -> None:
        """Initialize the WiFi radio switch."""
        super().__init__(coordinator, entry_id)
        self._client = client
        self._radio_name = radio_name
        self._radio_info = radio_info
        self._attr_unique_id = f"{entry_id}_{radio_name}_enabled"

        band = radio_info.get("band", "")
        band_label = _band_label(band)
        self._attr_name = f"WiFi {band_label} ({radio_name})"

        self._is_on: bool = radio_info.get("disabled", "0") != "1"

    @property
    def is_on(self) -> bool:
        """Return true if the radio is enabled."""
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the WiFi radio."""
        await self._set_radio_state(disabled=False)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the WiFi radio."""
        await self._set_radio_state(disabled=True)

    async def _set_radio_state(self, *, disabled: bool) -> None:
        """Set the radio disabled state via UCI."""
        try:
            await self._client.uci_set(
                "wireless",
                self._radio_name,
                {"disabled": "1" if disabled else "0"},
            )
            await self._client.uci_commit("wireless")
            self._is_on = not disabled
            self.async_write_ha_state()
        except UbusError as err:
            _LOGGER.error(
                "Failed to %s radio %s: %s",
                "disable" if disabled else "enable",
                self._radio_name,
                err,
            )

    async def async_update(self) -> None:
        """Fetch the current radio state from UCI."""
        try:
            result = await self._client.get_uci_config(
                "wireless", self._radio_name
            )
            values = result.get("values", {})
            self._is_on = values.get("disabled", "0") != "1"
        except UbusError:
            _LOGGER.debug(
                "Could not refresh state for radio %s", self._radio_name
            )


def _band_label(band: str) -> str:
    """Convert a band identifier to a friendly label."""
    band_map = {
        "2g": "2.4 GHz",
        "5g": "5 GHz",
        "6g": "6 GHz",
    }
    return band_map.get(band, band or "Unknown")

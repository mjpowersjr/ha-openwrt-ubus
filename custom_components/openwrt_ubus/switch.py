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
    """Set up switch entities for WiFi radios and APs."""
    entry_data = get_entry_data(hass, entry)
    coordinator = entry_data.stats_coordinator
    client = entry_data.client

    wireless = await _discover_wireless(client)
    entities: list[SwitchEntity] = []

    # Per-radio switches
    for radio_name, radio_info in wireless["radios"].items():
        entities.append(
            OpenWrtWifiRadioSwitch(
                coordinator=coordinator,
                entry_id=entry.entry_id,
                client=client,
                radio_name=radio_name,
                radio_info=radio_info,
            )
        )

    # Per-AP switches
    for iface_name, iface_info in wireless["ifaces"].items():
        entities.append(
            OpenWrtWifiApSwitch(
                coordinator=coordinator,
                entry_id=entry.entry_id,
                client=client,
                iface_name=iface_name,
                iface_info=iface_info,
            )
        )

    async_add_entities(entities)


async def _discover_wireless(
    client: UbusClient,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Discover WiFi radios and interfaces from UCI wireless config."""
    radios: dict[str, dict[str, Any]] = {}
    ifaces: dict[str, dict[str, Any]] = {}
    try:
        uci_result = await client.get_uci_config("wireless")
        values = uci_result.get("values", {})

        # First pass: collect radios
        for section_name, section_data in values.items():
            if section_data.get(".type") == "wifi-device":
                radios[section_name] = {
                    "band": section_data.get("band", ""),
                    "htmode": section_data.get("htmode", ""),
                    "disabled": section_data.get("disabled", "0"),
                }

        # Second pass: collect wifi-ifaces
        for section_name, section_data in values.items():
            if section_data.get(".type") == "wifi-iface":
                device = section_data.get("device", "")
                band = radios.get(device, {}).get("band", "")
                ifaces[section_name] = {
                    "ssid": section_data.get("ssid", ""),
                    "device": device,
                    "band": band,
                    "ifname": section_data.get("ifname", ""),
                    "network": section_data.get("network", ""),
                    "disabled": section_data.get("disabled", "0"),
                }
    except UbusError:
        _LOGGER.debug("Could not discover wireless config from UCI")

    return {"radios": radios, "ifaces": ifaces}


class OpenWrtWifiRadioSwitch(OpenWrtStatsEntity, SwitchEntity):
    """Switch to enable/disable a WiFi radio."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:access-point"

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
        self._attr_name = f"Radio {band_label} ({radio_name})"

        self._is_on: bool = radio_info.get("disabled", "0") != "1"

    @property
    def is_on(self) -> bool:
        """Return true if the radio is enabled."""
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the WiFi radio."""
        await self._set_state(disabled=False)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the WiFi radio."""
        await self._set_state(disabled=True)

    async def _set_state(self, *, disabled: bool) -> None:
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


class OpenWrtWifiApSwitch(OpenWrtStatsEntity, SwitchEntity):
    """Switch to enable/disable an individual WiFi AP (SSID)."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:wifi"

    def __init__(
        self,
        coordinator: StatsCoordinator,
        entry_id: str,
        client: UbusClient,
        iface_name: str,
        iface_info: dict[str, Any],
    ) -> None:
        """Initialize the WiFi AP switch."""
        super().__init__(coordinator, entry_id)
        self._client = client
        self._iface_name = iface_name
        self._iface_info = iface_info
        self._attr_unique_id = f"{entry_id}_{iface_name}_enabled"

        ssid = iface_info.get("ssid", iface_name)
        band = iface_info.get("band", "")
        band_label = _band_label(band)
        self._attr_name = f"AP {ssid} {band_label}"

        self._is_on: bool = iface_info.get("disabled", "0") != "1"

    @property
    def is_on(self) -> bool:
        """Return true if the AP is enabled."""
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the WiFi AP."""
        await self._set_state(disabled=False)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the WiFi AP."""
        await self._set_state(disabled=True)

    async def _set_state(self, *, disabled: bool) -> None:
        """Set the AP disabled state via UCI."""
        try:
            await self._client.uci_set(
                "wireless",
                self._iface_name,
                {"disabled": "1" if disabled else "0"},
            )
            await self._client.uci_commit("wireless")
            self._is_on = not disabled
            self.async_write_ha_state()
        except UbusError as err:
            _LOGGER.error(
                "Failed to %s AP %s: %s",
                "disable" if disabled else "enable",
                self._iface_name,
                err,
            )

    async def async_update(self) -> None:
        """Fetch the current AP state from UCI."""
        try:
            result = await self._client.get_uci_config(
                "wireless", self._iface_name
            )
            values = result.get("values", {})
            self._is_on = values.get("disabled", "0") != "1"
        except UbusError:
            _LOGGER.debug(
                "Could not refresh state for AP %s", self._iface_name
            )


def _band_label(band: str) -> str:
    """Convert a band identifier to a friendly label."""
    band_map = {
        "2g": "2.4 GHz",
        "5g": "5 GHz",
        "6g": "6 GHz",
    }
    return band_map.get(band, band or "Unknown")

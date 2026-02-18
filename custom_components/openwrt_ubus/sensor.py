"""Sensor platform for the OpenWrt ubus integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfInformation,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import get_entry_data
from .coordinator import StatsCoordinator, StatsData
from .entity import OpenWrtStatsEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class OpenWrtSensorDescription(SensorEntityDescription):
    """Describe an OpenWrt sensor."""

    value_fn: Callable[[StatsData], float | int | str | datetime | None]
    available_fn: Callable[[StatsData], bool] = lambda _: True


# System-level sensors (always created)
SYSTEM_SENSORS: tuple[OpenWrtSensorDescription, ...] = (
    OpenWrtSensorDescription(
        key="uptime",
        translation_key="uptime",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: (
            dt_util.utcnow() - timedelta(seconds=d.uptime) if d.uptime else None
        ),
    ),
    OpenWrtSensorDescription(
        key="load_1m",
        translation_key="load_1m",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=2,
        value_fn=lambda d: d.load_1m,
    ),
    OpenWrtSensorDescription(
        key="load_5m",
        translation_key="load_5m",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=2,
        value_fn=lambda d: d.load_5m,
    ),
    OpenWrtSensorDescription(
        key="load_15m",
        translation_key="load_15m",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=2,
        value_fn=lambda d: d.load_15m,
    ),
    OpenWrtSensorDescription(
        key="memory_usage",
        translation_key="memory_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
        value_fn=lambda d: (
            round(
                (d.memory_total - d.memory_free - d.memory_buffered)
                / d.memory_total
                * 100,
                1,
            )
            if d.memory_total
            else None
        ),
    ),
    OpenWrtSensorDescription(
        key="memory_free",
        translation_key="memory_free",
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
        value_fn=lambda d: round(d.memory_free / 1048576, 1) if d.memory_free else None,
    ),
    OpenWrtSensorDescription(
        key="firmware_version",
        translation_key="firmware_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.firmware_version,
    ),
    OpenWrtSensorDescription(
        key="connected_clients",
        translation_key="connected_clients",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:devices",
        value_fn=lambda d: sum(r.client_count for r in d.radios.values()),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities."""
    entry_data = get_entry_data(hass, entry)
    coordinator = entry_data.stats_coordinator
    entities: list[OpenWrtSensor] = []

    # System sensors
    for desc in SYSTEM_SENSORS:
        entities.append(
            OpenWrtSensor(
                coordinator=coordinator,
                entry_id=entry.entry_id,
                description=desc,
            )
        )

    # Dynamic per-interface sensors (WAN IPv4, TX/RX bytes)
    if coordinator.data:
        for iface_name, iface_data in coordinator.data.interfaces.items():
            if iface_name.startswith("wan"):
                entities.append(
                    OpenWrtSensor(
                        coordinator=coordinator,
                        entry_id=entry.entry_id,
                        description=OpenWrtSensorDescription(
                            key=f"{iface_name}_ipv4",
                            translation_key="wan_ipv4",
                            entity_category=EntityCategory.DIAGNOSTIC,
                            icon="mdi:ip-network",
                            value_fn=lambda d, n=iface_name: (
                                d.interfaces[n].ipv4_address
                                if n in d.interfaces
                                else None
                            ),
                        ),
                    )
                )

            device = iface_data.device
            if device:
                entities.extend(
                    [
                        OpenWrtSensor(
                            coordinator=coordinator,
                            entry_id=entry.entry_id,
                            description=OpenWrtSensorDescription(
                                key=f"{device}_tx_bytes",
                                translation_key="tx_bytes",
                                native_unit_of_measurement=UnitOfInformation.BYTES,
                                device_class=SensorDeviceClass.DATA_SIZE,
                                state_class=SensorStateClass.TOTAL_INCREASING,
                                entity_category=EntityCategory.DIAGNOSTIC,
                                value_fn=lambda d, dev=device: (
                                    d.devices[dev].tx_bytes
                                    if dev in d.devices
                                    else None
                                ),
                            ),
                            name_suffix=f" {device}",
                        ),
                        OpenWrtSensor(
                            coordinator=coordinator,
                            entry_id=entry.entry_id,
                            description=OpenWrtSensorDescription(
                                key=f"{device}_rx_bytes",
                                translation_key="rx_bytes",
                                native_unit_of_measurement=UnitOfInformation.BYTES,
                                device_class=SensorDeviceClass.DATA_SIZE,
                                state_class=SensorStateClass.TOTAL_INCREASING,
                                entity_category=EntityCategory.DIAGNOSTIC,
                                value_fn=lambda d, dev=device: (
                                    d.devices[dev].rx_bytes
                                    if dev in d.devices
                                    else None
                                ),
                            ),
                            name_suffix=f" {device}",
                        ),
                    ]
                )

        # Per-radio WiFi client count
        for radio_dev, radio_data in coordinator.data.radios.items():
            entities.append(
                OpenWrtSensor(
                    coordinator=coordinator,
                    entry_id=entry.entry_id,
                    description=OpenWrtSensorDescription(
                        key=f"{radio_dev}_wifi_clients",
                        translation_key="wifi_clients",
                        state_class=SensorStateClass.MEASUREMENT,
                        icon="mdi:wifi",
                        value_fn=lambda d, dev=radio_dev: (
                            d.radios[dev].client_count
                            if dev in d.radios
                            else None
                        ),
                    ),
                    name_suffix=f" {radio_dev}",
                )
            )

    async_add_entities(entities)


class OpenWrtSensor(OpenWrtStatsEntity, SensorEntity):
    """Representation of an OpenWrt sensor."""

    entity_description: OpenWrtSensorDescription

    def __init__(
        self,
        coordinator: StatsCoordinator,
        entry_id: str,
        description: OpenWrtSensorDescription,
        name_suffix: str = "",
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry_id)
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_{description.key}"
        self._name_suffix = name_suffix

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        base = self.entity_description.translation_key or self.entity_description.key
        # Replace underscores with spaces and title-case
        friendly = base.replace("_", " ").title()
        return f"{friendly}{self._name_suffix}"

    @property
    def native_value(self) -> float | int | str | datetime | None:
        """Return the sensor value."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not super().available:
            return False
        if self.coordinator.data is None:
            return False
        return self.entity_description.available_fn(self.coordinator.data)

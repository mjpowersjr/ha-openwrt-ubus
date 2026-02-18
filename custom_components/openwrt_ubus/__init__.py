"""The OpenWrt ubus integration."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SSL,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_DEVICE_TRACKER_SCAN_INTERVAL,
    CONF_DHCP_SOFTWARE,
    CONF_STATS_SCAN_INTERVAL,
    CONF_VERIFY_SSL,
    DEFAULT_DEVICE_TRACKER_SCAN_INTERVAL,
    DEFAULT_DHCP_SOFTWARE,
    DEFAULT_HTTPS,
    DEFAULT_STATS_SCAN_INTERVAL,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import DeviceTrackerCoordinator, StatsCoordinator
from .ubus_client import (
    UbusAuthenticationError,
    UbusClient,
    UbusConnectionError,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class OpenWrtUbusData:
    """Runtime data for an OpenWrt ubus config entry."""

    client: UbusClient
    device_tracker_coordinator: DeviceTrackerCoordinator
    stats_coordinator: StatsCoordinator


def get_entry_data(hass: HomeAssistant, entry: ConfigEntry) -> OpenWrtUbusData:
    """Get the runtime data for a config entry."""
    return hass.data[DOMAIN][entry.entry_id]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> bool:
    """Set up OpenWrt ubus from a config entry."""
    session = async_get_clientsession(
        hass, verify_ssl=entry.data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
    )
    client = UbusClient(
        session=session,
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        https=entry.data.get(CONF_SSL, DEFAULT_HTTPS),
        verify_ssl=entry.data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
    )

    try:
        await client.connect()
    except UbusAuthenticationError as err:
        raise ConfigEntryAuthFailed(
            f"Authentication failed: {err}"
        ) from err
    except UbusConnectionError as err:
        raise ConfigEntryNotReady(
            f"Cannot connect to {entry.data[CONF_HOST]}: {err}"
        ) from err

    dt_interval = entry.options.get(
        CONF_DEVICE_TRACKER_SCAN_INTERVAL,
        DEFAULT_DEVICE_TRACKER_SCAN_INTERVAL,
    )
    stats_interval = entry.options.get(
        CONF_STATS_SCAN_INTERVAL, DEFAULT_STATS_SCAN_INTERVAL
    )

    device_tracker_coordinator = DeviceTrackerCoordinator(
        hass,
        client,
        dhcp_software=entry.data.get(CONF_DHCP_SOFTWARE, DEFAULT_DHCP_SOFTWARE),
        scan_interval=dt_interval,
        entry_id=entry.entry_id,
    )
    stats_coordinator = StatsCoordinator(
        hass, client, scan_interval=stats_interval
    )

    # Fetch initial data — raises UpdateFailed → ConfigEntryNotReady
    await stats_coordinator.async_config_entry_first_refresh()
    await device_tracker_coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = OpenWrtUbusData(
        client=client,
        device_tracker_coordinator=device_tracker_coordinator,
        stats_coordinator=stats_coordinator,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> bool:
    """Unload an OpenWrt ubus config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )
    if unload_ok:
        data: OpenWrtUbusData = hass.data[DOMAIN].pop(entry.entry_id)
        await data.client.disconnect()
    return unload_ok


async def _async_options_updated(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Handle options update by reloading the entry."""
    await hass.config_entries.async_reload(entry.entry_id)

"""DataUpdateCoordinators for the OpenWrt ubus integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    DEFAULT_DEVICE_TRACKER_SCAN_INTERVAL,
    DEFAULT_STATS_SCAN_INTERVAL,
    DHCP_DNSMASQ,
    DHCP_NONE,
    DHCP_ODHCPD,
    DOMAIN,
    SIGNAL_NEW_DEVICE,
)
from .helpers import format_mac
from .ubus_client import UbusAuthenticationError, UbusClient, UbusError

_LOGGER = logging.getLogger(__name__)

# OpenWrt load averages are fixed-point with a divisor of 65536
_LOAD_DIVISOR = 65536


@dataclass
class TrackedClient:
    """Represents a tracked WiFi client."""

    mac: str
    hostname: str | None = None
    ip_address: str | None = None
    interface: str | None = None
    ssid: str | None = None
    signal: int | None = None
    rx_bytes: int = 0
    tx_bytes: int = 0
    rx_rate: int = 0
    tx_rate: int = 0
    connected: bool = False


@dataclass
class DeviceTrackerData:
    """Data from the device tracker coordinator."""

    clients: dict[str, TrackedClient] = field(default_factory=dict)


@dataclass
class NetworkInterfaceData:
    """Data for a network interface."""

    name: str
    up: bool = False
    proto: str = ""
    ipv4_address: str | None = None
    uptime: int = 0
    device: str | None = None


@dataclass
class NetworkDeviceData:
    """Data for a network device (tx/rx counters)."""

    name: str
    tx_bytes: int = 0
    rx_bytes: int = 0


@dataclass
class WirelessRadioData:
    """Data for a wireless radio."""

    device: str
    ssid: str | None = None
    channel: int | None = None
    frequency: int | None = None
    signal: int | None = None
    noise: int | None = None
    client_count: int = 0


@dataclass
class StatsData:
    """Data from the stats coordinator."""

    # System board (cached)
    hostname: str | None = None
    model: str | None = None
    firmware_version: str | None = None
    kernel_version: str | None = None

    # System info
    uptime: int = 0
    memory_total: int = 0
    memory_free: int = 0
    memory_buffered: int = 0
    load_1m: float = 0.0
    load_5m: float = 0.0
    load_15m: float = 0.0

    # Network
    interfaces: dict[str, NetworkInterfaceData] = field(default_factory=dict)
    devices: dict[str, NetworkDeviceData] = field(default_factory=dict)
    wan_up: bool = False

    # Wireless
    radios: dict[str, WirelessRadioData] = field(default_factory=dict)


class DeviceTrackerCoordinator(DataUpdateCoordinator[DeviceTrackerData]):
    """Coordinator for WiFi client tracking (fast polling)."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: UbusClient,
        dhcp_software: str,
        scan_interval: int = DEFAULT_DEVICE_TRACKER_SCAN_INTERVAL,
        entry_id: str = "",
    ) -> None:
        """Initialize the device tracker coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_device_tracker",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.dhcp_software = dhcp_software
        self._entry_id = entry_id
        self._known_macs: set[str] = set()
        self._hostapd_interfaces: list[str] | None = None
        self._dhcp_cache: dict[str, tuple[str | None, str | None]] = {}

    async def _async_update_data(self) -> DeviceTrackerData:
        """Fetch WiFi client data from all hostapd interfaces."""
        try:
            return await self._fetch_data()
        except UbusAuthenticationError as err:
            raise UpdateFailed(f"Authentication failed: {err}") from err
        except UbusError as err:
            raise UpdateFailed(f"Error communicating with router: {err}") from err

    async def _fetch_data(self) -> DeviceTrackerData:
        """Fetch and process WiFi client data."""
        # Discover hostapd interfaces if not yet known
        if self._hostapd_interfaces is None:
            self._hostapd_interfaces = await self._discover_hostapd_interfaces()
            _LOGGER.debug(
                "Discovered hostapd interfaces: %s", self._hostapd_interfaces
            )

        # Refresh DHCP leases for hostname/IP resolution
        await self._refresh_dhcp_cache()

        clients: dict[str, TrackedClient] = {}

        for iface in self._hostapd_interfaces:
            try:
                result = await self.client.get_hostapd_clients(iface)
            except UbusError:
                _LOGGER.debug("Failed to query hostapd.%s, skipping", iface)
                continue

            freq = result.get("freq", 0)
            ssid_info = await self._get_ssid_for_interface(iface)

            for mac_raw, info in result.get("clients", {}).items():
                if not info.get("authorized", False):
                    continue

                mac = format_mac(mac_raw)
                hostname, ip_address = self._dhcp_cache.get(
                    mac, (None, None)
                )

                clients[mac] = TrackedClient(
                    mac=mac,
                    hostname=hostname,
                    ip_address=ip_address,
                    interface=iface,
                    ssid=ssid_info,
                    signal=info.get("signal"),
                    rx_bytes=info.get("bytes", {}).get("rx", 0),
                    tx_bytes=info.get("bytes", {}).get("tx", 0),
                    rx_rate=info.get("rx_rate", 0),
                    tx_rate=info.get("tx_rate", 0),
                    connected=True,
                )

        # Check for new devices
        new_macs = set(clients.keys()) - self._known_macs
        if new_macs:
            self._known_macs |= new_macs
            for mac in new_macs:
                _LOGGER.debug("New WiFi client discovered: %s", mac)
            async_dispatcher_send(
                self.hass, f"{SIGNAL_NEW_DEVICE}_{self._entry_id}"
            )

        return DeviceTrackerData(clients=clients)

    async def _discover_hostapd_interfaces(self) -> list[str]:
        """Discover available hostapd interfaces via ubus list."""
        # We query the ubus namespace by calling hostapd.* methods
        # and seeing which ones respond. A simpler approach: try the
        # common interface naming patterns.
        interfaces: list[str] = []

        # Try to get the wireless config from UCI to discover interfaces
        try:
            uci_result = await self.client.get_uci_config("wireless")
            values = uci_result.get("values", {})
            for section_name, section_data in values.items():
                if section_data.get(".type") == "wifi-iface":
                    ifname = section_data.get("ifname")
                    if ifname:
                        try:
                            await self.client.get_hostapd_clients(ifname)
                            interfaces.append(ifname)
                        except UbusError:
                            pass
        except UbusError:
            _LOGGER.debug("Could not read wireless UCI config")

        # Fallback: try common interface names
        if not interfaces:
            for candidate in [
                "wlan0", "wlan1", "wlan2", "wlan3",
                "phy0-ap0", "phy1-ap0", "phy0-ap1", "phy1-ap1",
            ]:
                try:
                    await self.client.get_hostapd_clients(candidate)
                    interfaces.append(candidate)
                except UbusError:
                    continue

        return interfaces

    async def _get_ssid_for_interface(self, iface: str) -> str | None:
        """Get the SSID for a hostapd interface."""
        try:
            result = await self.client.get_iwinfo(iface)
            return result.get("ssid")
        except UbusError:
            return None

    async def _refresh_dhcp_cache(self) -> None:
        """Refresh the MAC-to-hostname/IP cache from DHCP leases."""
        if self.dhcp_software == DHCP_NONE:
            return

        try:
            if self.dhcp_software == DHCP_DNSMASQ:
                await self._parse_dnsmasq_leases()
            elif self.dhcp_software == DHCP_ODHCPD:
                await self._parse_odhcpd_leases()
        except UbusError:
            _LOGGER.debug("Failed to refresh DHCP lease cache")

    async def _parse_dnsmasq_leases(self) -> None:
        """Parse /tmp/dhcp.leases (dnsmasq format)."""
        try:
            result = await self.client.file_read("/tmp/dhcp.leases")
        except UbusError:
            return

        data = result.get("data", "")
        for line in data.splitlines():
            parts = line.split()
            if len(parts) >= 4:
                # Format: timestamp mac ip hostname client-id
                mac = format_mac(parts[1])
                ip_addr = parts[2]
                hostname = parts[3] if parts[3] != "*" else None
                self._dhcp_cache[mac] = (hostname, ip_addr)

    async def _parse_odhcpd_leases(self) -> None:
        """Parse odhcpd DHCP leases."""
        try:
            result = await self.client.get_dhcp_ipv4_leases()
        except UbusError:
            return

        for iface_data in result.get("device", {}).values():
            for lease in iface_data.get("leases", []):
                mac = format_mac(lease.get("mac", ""))
                if mac:
                    hostname = lease.get("hostname")
                    ip_addr = lease.get("ipaddr")
                    self._dhcp_cache[mac] = (hostname, ip_addr)


class StatsCoordinator(DataUpdateCoordinator[StatsData]):
    """Coordinator for system stats (slow polling)."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: UbusClient,
        scan_interval: int = DEFAULT_STATS_SCAN_INTERVAL,
    ) -> None:
        """Initialize the stats coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_stats",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self._board_cached: dict[str, Any] | None = None
        self._discovered_devices: list[str] | None = None
        self._discovered_radios: list[str] | None = None

    async def _async_update_data(self) -> StatsData:
        """Fetch system stats from the router."""
        try:
            return await self._fetch_data()
        except UbusAuthenticationError as err:
            raise UpdateFailed(f"Authentication failed: {err}") from err
        except UbusError as err:
            raise UpdateFailed(f"Error communicating with router: {err}") from err

    async def _fetch_data(self) -> StatsData:
        """Fetch and process all stats data."""
        data = StatsData()

        # System board (cache after first successful fetch)
        if self._board_cached is None:
            self._board_cached = await self.client.get_system_board()

        board = self._board_cached
        data.hostname = board.get("hostname")
        data.model = board.get("model")
        release = board.get("release", {})
        data.firmware_version = release.get("description")
        data.kernel_version = board.get("kernel")

        # System info
        sys_info = await self.client.get_system_info()
        data.uptime = sys_info.get("uptime", 0)

        memory = sys_info.get("memory", {})
        data.memory_total = memory.get("total", 0)
        data.memory_free = memory.get("free", 0)
        data.memory_buffered = memory.get("buffered", 0)

        load = sys_info.get("load", [0, 0, 0])
        data.load_1m = round(load[0] / _LOAD_DIVISOR, 2) if load else 0.0
        data.load_5m = round(load[1] / _LOAD_DIVISOR, 2) if len(load) > 1 else 0.0
        data.load_15m = round(load[2] / _LOAD_DIVISOR, 2) if len(load) > 2 else 0.0

        # Network interfaces
        await self._fetch_network_data(data)

        # Wireless radios
        await self._fetch_wireless_data(data)

        return data

    async def _fetch_network_data(self, data: StatsData) -> None:
        """Fetch network interface and device data."""
        try:
            dump = await self.client.get_network_interface_dump()
        except UbusError:
            _LOGGER.debug("Failed to fetch network interface dump")
            return

        for iface in dump.get("interface", []):
            name = iface.get("interface", "")
            if not name or name == "loopback":
                continue

            ipv4_addr = None
            ipv4_addrs = iface.get("ipv4-address", [])
            if ipv4_addrs:
                ipv4_addr = ipv4_addrs[0].get("address")

            iface_data = NetworkInterfaceData(
                name=name,
                up=iface.get("up", False),
                proto=iface.get("proto", ""),
                ipv4_address=ipv4_addr,
                uptime=iface.get("uptime", 0),
                device=iface.get("l3_device") or iface.get("device"),
            )
            data.interfaces[name] = iface_data

            # Track WAN status
            if name.startswith("wan") and iface_data.up:
                data.wan_up = True

        # Discover and fetch per-device stats
        devices_to_query = set()
        for iface_data in data.interfaces.values():
            if iface_data.device:
                devices_to_query.add(iface_data.device)

        for dev_name in devices_to_query:
            try:
                dev_status = await self.client.get_network_device_status(
                    dev_name
                )
                stats = dev_status.get("statistics", {})
                data.devices[dev_name] = NetworkDeviceData(
                    name=dev_name,
                    tx_bytes=stats.get("tx_bytes", 0),
                    rx_bytes=stats.get("rx_bytes", 0),
                )
            except UbusError:
                _LOGGER.debug("Failed to get status for device %s", dev_name)

    async def _fetch_wireless_data(self, data: StatsData) -> None:
        """Fetch wireless radio data."""
        if self._discovered_radios is None:
            self._discovered_radios = await self._discover_radios()
            _LOGGER.debug("Discovered radios: %s", self._discovered_radios)

        for radio_dev in self._discovered_radios:
            try:
                info = await self.client.get_iwinfo(radio_dev)
                data.radios[radio_dev] = WirelessRadioData(
                    device=radio_dev,
                    ssid=info.get("ssid"),
                    channel=info.get("channel"),
                    frequency=info.get("frequency"),
                    signal=info.get("signal"),
                    noise=info.get("noise"),
                )
            except UbusError:
                _LOGGER.debug("Failed to get iwinfo for %s", radio_dev)

    async def _discover_radios(self) -> list[str]:
        """Discover wireless radio devices."""
        radios: list[str] = []
        try:
            uci_result = await self.client.get_uci_config("wireless")
            values = uci_result.get("values", {})
            for section_name, section_data in values.items():
                if section_data.get(".type") == "wifi-iface":
                    ifname = section_data.get("ifname")
                    if ifname:
                        radios.append(ifname)
        except UbusError:
            _LOGGER.debug("Could not read wireless UCI config for radio discovery")

        # Fallback
        if not radios:
            for candidate in ["wlan0", "wlan1", "phy0-ap0", "phy1-ap0"]:
                try:
                    await self.client.get_iwinfo(candidate)
                    radios.append(candidate)
                except UbusError:
                    continue

        return radios

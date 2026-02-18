"""Async ubus JSON-RPC client for OpenWrt."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from .const import (
    UBUS_ERROR_ACCESS_DENIED,
    UBUS_SESSION_ANONYMOUS,
    UBUS_URL_PATH,
)

_LOGGER = logging.getLogger(__name__)

_RPC_ID = 1


class UbusError(Exception):
    """Base exception for ubus errors."""


class UbusConnectionError(UbusError):
    """Raised when we cannot connect to the router."""


class UbusAuthenticationError(UbusError):
    """Raised when authentication fails."""


class UbusClient:
    """Async client for OpenWrt ubus JSON-RPC interface."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        port: int,
        username: str,
        password: str,
        https: bool = False,
        verify_ssl: bool = True,
    ) -> None:
        """Initialize the ubus client."""
        self._session = session
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._https = https
        self._verify_ssl = verify_ssl
        self._ubus_session: str = UBUS_SESSION_ANONYMOUS
        self._url = (
            f"{'https' if https else 'http'}://{host}:{port}{UBUS_URL_PATH}"
        )
        self._request_lock = asyncio.Lock()

    @property
    def host(self) -> str:
        """Return the router host."""
        return self._host

    async def connect(self) -> None:
        """Authenticate and obtain a ubus session."""
        try:
            result = await self._raw_call(
                UBUS_SESSION_ANONYMOUS,
                "session",
                "login",
                {"username": self._username, "password": self._password},
            )
        except UbusConnectionError:
            raise
        except UbusError as err:
            raise UbusAuthenticationError(
                f"Authentication failed for {self._username}@{self._host}"
            ) from err

        ubus_rpc_session = result.get("ubus_rpc_session")
        if not ubus_rpc_session or ubus_rpc_session == UBUS_SESSION_ANONYMOUS:
            raise UbusAuthenticationError(
                f"Authentication failed for {self._username}@{self._host}: "
                "no session returned"
            )

        self._ubus_session = ubus_rpc_session
        _LOGGER.debug("Authenticated to %s, session obtained", self._host)

    async def disconnect(self) -> None:
        """Destroy the ubus session."""
        if self._ubus_session != UBUS_SESSION_ANONYMOUS:
            try:
                await self._raw_call(
                    self._ubus_session, "session", "destroy", {}
                )
            except UbusError:
                pass
            finally:
                self._ubus_session = UBUS_SESSION_ANONYMOUS

    async def call(
        self,
        obj: str,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        retry_auth: bool = True,
    ) -> dict[str, Any]:
        """Make an authenticated ubus call with auto-reconnect on auth failure."""
        try:
            return await self._raw_call(
                self._ubus_session, obj, method, params or {}
            )
        except UbusError as err:
            if retry_auth and UBUS_ERROR_ACCESS_DENIED == _extract_error_code(
                err
            ):
                _LOGGER.debug("Session expired, re-authenticating")
                await self.connect()
                return await self._raw_call(
                    self._ubus_session, obj, method, params or {}
                )
            raise

    async def _raw_call(
        self,
        session_id: str,
        obj: str,
        method: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a raw JSON-RPC call to ubus."""
        payload = {
            "jsonrpc": "2.0",
            "id": _RPC_ID,
            "method": "call",
            "params": [session_id, obj, method, params],
        }

        ssl_context: bool | None = None
        if self._https and not self._verify_ssl:
            ssl_context = False

        async with self._request_lock:
            try:
                async with self._session.post(
                    self._url,
                    json=payload,
                    ssl=ssl_context,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
            except (aiohttp.ClientError, TimeoutError) as err:
                raise UbusConnectionError(
                    f"Cannot connect to {self._host}: {err}"
                ) from err

        if "error" in data:
            code = data["error"].get("code", 0)
            message = data["error"].get("message", "Unknown error")
            if code == UBUS_ERROR_ACCESS_DENIED:
                raise UbusAuthenticationError(
                    f"Access denied ({code}): {message}"
                )
            raise UbusError(f"ubus error ({code}): {message}")

        result = data.get("result")
        if not isinstance(result, list) or len(result) < 1:
            raise UbusError(
                f"Unexpected response from {obj}.{method}: {result}"
            )

        status_code = result[0]
        if status_code != 0:
            raise UbusError(
                f"ubus call {obj}.{method} returned error code {status_code}"
            )

        # ubus returns [0, {data}] on success, or [0] if no data
        if len(result) < 2:
            return {}

        return result[1] if isinstance(result[1], dict) else {}

    # --- High-level API methods ---

    async def get_system_board(self) -> dict[str, Any]:
        """Get system board information (hostname, model, firmware)."""
        return await self.call("system", "board")

    async def get_system_info(self) -> dict[str, Any]:
        """Get system info (uptime, memory, load)."""
        return await self.call("system", "info")

    async def get_hostapd_clients(self, interface: str) -> dict[str, Any]:
        """Get WiFi clients connected to a hostapd interface."""
        return await self.call(f"hostapd.{interface}", "get_clients")

    async def get_network_interface_dump(self) -> dict[str, Any]:
        """Get all network interface information."""
        return await self.call("network.interface", "dump")

    async def get_network_device_status(self, device: str) -> dict[str, Any]:
        """Get status of a specific network device (tx/rx counters)."""
        return await self.call("network.device", "status", {"name": device})

    async def get_iwinfo(self, device: str) -> dict[str, Any]:
        """Get wireless info for a device."""
        return await self.call("iwinfo", "info", {"device": device})

    async def get_dhcp_ipv4_leases(self) -> dict[str, Any]:
        """Get DHCP IPv4 leases from odhcpd."""
        return await self.call("dhcp", "ipv4leases")

    async def file_read(self, path: str) -> dict[str, Any]:
        """Read a file on the router via ubus."""
        return await self.call("file", "read", {"path": path})

    async def get_uci_config(
        self, config: str, section: str | None = None
    ) -> dict[str, Any]:
        """Read UCI configuration."""
        params: dict[str, Any] = {"config": config}
        if section:
            params["section"] = section
        return await self.call("uci", "get", params)

    async def uci_set(
        self,
        config: str,
        section: str,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        """Set UCI configuration values."""
        return await self.call(
            "uci",
            "set",
            {"config": config, "section": section, "values": values},
        )

    async def uci_commit(self, config: str) -> dict[str, Any]:
        """Commit UCI configuration changes."""
        return await self.call("uci", "commit", {"config": config})

    async def system_reboot(self) -> dict[str, Any]:
        """Reboot the router."""
        return await self.call("system", "reboot")

    async def wireless_up(self) -> dict[str, Any]:
        """Bring up all wireless interfaces."""
        return await self.call("network.wireless", "up")

    async def wireless_down(self) -> dict[str, Any]:
        """Bring down all wireless interfaces."""
        return await self.call("network.wireless", "down")


def _extract_error_code(err: UbusError) -> int | None:
    """Extract the error code from an UbusError message."""
    msg = str(err)
    if "Access denied" in msg or str(UBUS_ERROR_ACCESS_DENIED) in msg:
        return UBUS_ERROR_ACCESS_DENIED
    return None

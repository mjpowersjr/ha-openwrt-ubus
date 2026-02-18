"""Tests for the ubus client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from aioresponses import aioresponses

from custom_components.openwrt_ubus.ubus_client import (
    UbusAuthenticationError,
    UbusClient,
    UbusConnectionError,
    UbusError,
)


@pytest.fixture
def mock_aiohttp():
    """Provide aioresponses mock."""
    with aioresponses() as m:
        yield m


@pytest.fixture
async def client():
    """Create a client with a real aiohttp session."""
    session = aiohttp.ClientSession()
    c = UbusClient(
        session=session,
        host="192.168.1.1",
        port=80,
        username="root",
        password="testpass",
    )
    yield c
    await session.close()


class TestConnect:
    """Tests for connect/disconnect."""

    async def test_connect_success(self, client, mock_aiohttp):
        """Test successful authentication."""
        mock_aiohttp.post(
            "http://192.168.1.1:80/ubus",
            payload={
                "jsonrpc": "2.0",
                "id": 1,
                "result": [
                    0,
                    {"ubus_rpc_session": "abc123session"},
                ],
            },
        )

        await client.connect()
        assert client._ubus_session == "abc123session"

    async def test_connect_invalid_credentials(self, client, mock_aiohttp):
        """Test authentication with wrong credentials."""
        mock_aiohttp.post(
            "http://192.168.1.1:80/ubus",
            payload={
                "jsonrpc": "2.0",
                "id": 1,
                "result": [0, {"ubus_rpc_session": "00000000000000000000000000000000"}],
            },
        )

        with pytest.raises(UbusAuthenticationError):
            await client.connect()

    async def test_connect_network_error(self, client, mock_aiohttp):
        """Test connection failure."""
        mock_aiohttp.post(
            "http://192.168.1.1:80/ubus",
            exception=aiohttp.ClientError("Connection refused"),
        )

        with pytest.raises(UbusConnectionError):
            await client.connect()

    async def test_disconnect(self, client, mock_aiohttp):
        """Test session destruction."""
        # First connect
        mock_aiohttp.post(
            "http://192.168.1.1:80/ubus",
            payload={
                "jsonrpc": "2.0",
                "id": 1,
                "result": [0, {"ubus_rpc_session": "abc123"}],
            },
        )
        await client.connect()

        # Then disconnect
        mock_aiohttp.post(
            "http://192.168.1.1:80/ubus",
            payload={"jsonrpc": "2.0", "id": 1, "result": [0]},
        )
        await client.disconnect()
        assert client._ubus_session == "00000000000000000000000000000000"


class TestCall:
    """Tests for the call method."""

    async def test_call_success(self, client, mock_aiohttp):
        """Test a successful ubus call."""
        # Connect first
        mock_aiohttp.post(
            "http://192.168.1.1:80/ubus",
            payload={
                "jsonrpc": "2.0",
                "id": 1,
                "result": [0, {"ubus_rpc_session": "session123"}],
            },
        )
        await client.connect()

        # Make a call
        mock_aiohttp.post(
            "http://192.168.1.1:80/ubus",
            payload={
                "jsonrpc": "2.0",
                "id": 1,
                "result": [0, {"hostname": "OpenWrt", "model": "Test"}],
            },
        )
        result = await client.get_system_board()
        assert result["hostname"] == "OpenWrt"
        assert result["model"] == "Test"

    async def test_call_auto_reconnect_on_access_denied(
        self, client, mock_aiohttp
    ):
        """Test auto-reconnect when session expires."""
        # Initial connect
        mock_aiohttp.post(
            "http://192.168.1.1:80/ubus",
            payload={
                "jsonrpc": "2.0",
                "id": 1,
                "result": [0, {"ubus_rpc_session": "session1"}],
            },
        )
        await client.connect()

        # Call returns access denied
        mock_aiohttp.post(
            "http://192.168.1.1:80/ubus",
            payload={
                "jsonrpc": "2.0",
                "id": 1,
                "error": {"code": -32002, "message": "Access denied"},
            },
        )
        # Re-auth succeeds
        mock_aiohttp.post(
            "http://192.168.1.1:80/ubus",
            payload={
                "jsonrpc": "2.0",
                "id": 1,
                "result": [0, {"ubus_rpc_session": "session2"}],
            },
        )
        # Retry succeeds
        mock_aiohttp.post(
            "http://192.168.1.1:80/ubus",
            payload={
                "jsonrpc": "2.0",
                "id": 1,
                "result": [0, {"uptime": 100}],
            },
        )

        result = await client.get_system_info()
        assert result["uptime"] == 100
        assert client._ubus_session == "session2"

    async def test_call_empty_result(self, client, mock_aiohttp):
        """Test call that returns no data (e.g., reboot)."""
        mock_aiohttp.post(
            "http://192.168.1.1:80/ubus",
            payload={
                "jsonrpc": "2.0",
                "id": 1,
                "result": [0, {"ubus_rpc_session": "session1"}],
            },
        )
        await client.connect()

        mock_aiohttp.post(
            "http://192.168.1.1:80/ubus",
            payload={"jsonrpc": "2.0", "id": 1, "result": [0]},
        )
        result = await client.system_reboot()
        assert result == {}

    async def test_call_ubus_error(self, client, mock_aiohttp):
        """Test call that returns a ubus error code."""
        mock_aiohttp.post(
            "http://192.168.1.1:80/ubus",
            payload={
                "jsonrpc": "2.0",
                "id": 1,
                "result": [0, {"ubus_rpc_session": "session1"}],
            },
        )
        await client.connect()

        mock_aiohttp.post(
            "http://192.168.1.1:80/ubus",
            payload={"jsonrpc": "2.0", "id": 1, "result": [6]},
        )
        with pytest.raises(UbusError, match="error code 6"):
            await client.call("nonexistent", "method")


class TestHighLevelMethods:
    """Test high-level API methods."""

    async def test_get_hostapd_clients(self, client, mock_aiohttp):
        """Test getting WiFi clients from hostapd."""
        mock_aiohttp.post(
            "http://192.168.1.1:80/ubus",
            payload={
                "jsonrpc": "2.0",
                "id": 1,
                "result": [0, {"ubus_rpc_session": "s"}],
            },
        )
        await client.connect()

        mock_aiohttp.post(
            "http://192.168.1.1:80/ubus",
            payload={
                "jsonrpc": "2.0",
                "id": 1,
                "result": [
                    0,
                    {"freq": 2437, "clients": {"AA:BB:CC:DD:EE:FF": {"authorized": True}}},
                ],
            },
        )
        result = await client.get_hostapd_clients("wlan0")
        assert "AA:BB:CC:DD:EE:FF" in result["clients"]

    async def test_file_read(self, client, mock_aiohttp):
        """Test reading a file from the router."""
        mock_aiohttp.post(
            "http://192.168.1.1:80/ubus",
            payload={
                "jsonrpc": "2.0",
                "id": 1,
                "result": [0, {"ubus_rpc_session": "s"}],
            },
        )
        await client.connect()

        mock_aiohttp.post(
            "http://192.168.1.1:80/ubus",
            payload={
                "jsonrpc": "2.0",
                "id": 1,
                "result": [0, {"data": "lease content"}],
            },
        )
        result = await client.file_read("/tmp/dhcp.leases")
        assert result["data"] == "lease content"

    async def test_uci_set_and_commit(self, client, mock_aiohttp):
        """Test UCI set and commit."""
        mock_aiohttp.post(
            "http://192.168.1.1:80/ubus",
            payload={
                "jsonrpc": "2.0",
                "id": 1,
                "result": [0, {"ubus_rpc_session": "s"}],
            },
        )
        await client.connect()

        # uci set
        mock_aiohttp.post(
            "http://192.168.1.1:80/ubus",
            payload={"jsonrpc": "2.0", "id": 1, "result": [0]},
        )
        await client.uci_set("wireless", "radio0", {"disabled": "1"})

        # uci commit
        mock_aiohttp.post(
            "http://192.168.1.1:80/ubus",
            payload={"jsonrpc": "2.0", "id": 1, "result": [0]},
        )
        await client.uci_commit("wireless")


class TestHttpsAndSsl:
    """Test HTTPS and SSL settings."""

    async def test_https_url(self):
        """Test that HTTPS URL is constructed correctly."""
        session = aiohttp.ClientSession()
        try:
            c = UbusClient(
                session=session,
                host="router.local",
                port=443,
                username="root",
                password="pass",
                https=True,
                verify_ssl=True,
            )
            assert c._url == "https://router.local:443/ubus"
        finally:
            await session.close()

    async def test_http_url(self):
        """Test that HTTP URL is constructed correctly."""
        session = aiohttp.ClientSession()
        try:
            c = UbusClient(
                session=session,
                host="192.168.1.1",
                port=80,
                username="root",
                password="pass",
                https=False,
            )
            assert c._url == "http://192.168.1.1:80/ubus"
        finally:
            await session.close()

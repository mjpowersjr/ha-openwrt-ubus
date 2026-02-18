"""Tests for the button platform."""

from __future__ import annotations

import pytest

from homeassistant.components.button import ButtonDeviceClass
from homeassistant.core import HomeAssistant

from custom_components.openwrt_ubus.button import OpenWrtRebootButton
from custom_components.openwrt_ubus.coordinator import StatsCoordinator

from .conftest import create_mock_client


class TestRebootButton:
    """Tests for the reboot button."""

    async def test_press_reboot(self, hass: HomeAssistant):
        """Test pressing the reboot button."""
        client = create_mock_client()
        coordinator = StatsCoordinator(hass, client, scan_interval=60)
        await coordinator.async_refresh()

        button = OpenWrtRebootButton(coordinator, "test", client)
        await button.async_press()

        client.system_reboot.assert_called_once()

    async def test_button_attributes(self, hass: HomeAssistant):
        """Test button attributes."""
        client = create_mock_client()
        coordinator = StatsCoordinator(hass, client, scan_interval=60)
        await coordinator.async_refresh()

        button = OpenWrtRebootButton(coordinator, "test", client)
        assert button.device_class == ButtonDeviceClass.RESTART
        assert button.name == "Reboot"

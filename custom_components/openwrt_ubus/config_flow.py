"""Config flow for the OpenWrt ubus integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    OptionsFlow,
)
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SSL,
    CONF_USERNAME,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_CONSIDER_HOME,
    CONF_DEVICE_TRACKER_SCAN_INTERVAL,
    CONF_DHCP_SOFTWARE,
    CONF_STATS_SCAN_INTERVAL,
    CONF_TRACK_DEVICES,
    CONF_VERIFY_SSL,
    DEFAULT_CONSIDER_HOME,
    DEFAULT_DEVICE_TRACKER_SCAN_INTERVAL,
    DEFAULT_DHCP_SOFTWARE,
    DEFAULT_HTTPS,
    DEFAULT_PORT,
    DEFAULT_STATS_SCAN_INTERVAL,
    DEFAULT_TRACK_DEVICES,
    DEFAULT_VERIFY_SSL,
    DHCP_DNSMASQ,
    DHCP_NONE,
    DHCP_ODHCPD,
    DOMAIN,
)
from .ubus_client import (
    UbusAuthenticationError,
    UbusClient,
    UbusConnectionError,
    UbusError,
)

_LOGGER = logging.getLogger(__name__)


def _user_schema(
    defaults: dict[str, Any] | None = None,
) -> vol.Schema:
    """Build the user setup schema."""
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=d.get(CONF_HOST, "")): str,
            vol.Required(
                CONF_PORT, default=d.get(CONF_PORT, DEFAULT_PORT)
            ): int,
            vol.Required(
                CONF_USERNAME, default=d.get(CONF_USERNAME, "root")
            ): str,
            vol.Required(CONF_PASSWORD, default=d.get(CONF_PASSWORD, "")): str,
            vol.Required(
                CONF_SSL, default=d.get(CONF_SSL, DEFAULT_HTTPS)
            ): bool,
            vol.Required(
                CONF_VERIFY_SSL,
                default=d.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
            ): bool,
            vol.Required(
                CONF_DHCP_SOFTWARE,
                default=d.get(CONF_DHCP_SOFTWARE, DEFAULT_DHCP_SOFTWARE),
            ): vol.In([DHCP_DNSMASQ, DHCP_ODHCPD, DHCP_NONE]),
        }
    )


class OpenWrtUbusConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OpenWrt ubus."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._reauth_entry: ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            self._async_abort_entries_match({CONF_HOST: host})

            error = await self._test_connection(user_input)
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(host)
                self._abort_if_unique_id_configured()

                title = await self._get_title(user_input)
                return self.async_create_entry(title=title, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(user_input),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> FlowResult:
        """Handle reauth when credentials become invalid."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context.get("entry_id", "")
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reauth confirmation step."""
        errors: dict[str, str] = {}
        entry = self._reauth_entry
        if entry is None:
            return self.async_abort(reason="reauth_failed")

        if user_input is not None:
            updated_data = {**entry.data, **user_input}
            error = await self._test_connection(updated_data)
            if error:
                errors["base"] = error
            else:
                self.hass.config_entries.async_update_entry(
                    entry, data=updated_data
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME,
                        default=entry.data.get(CONF_USERNAME, "root"),
                    ): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def _test_connection(
        self, data: dict[str, Any]
    ) -> str | None:
        """Test the connection and return an error key or None."""
        session = async_get_clientsession(
            self.hass, verify_ssl=data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
        )
        client = UbusClient(
            session=session,
            host=data[CONF_HOST],
            port=data[CONF_PORT],
            username=data[CONF_USERNAME],
            password=data[CONF_PASSWORD],
            https=data.get(CONF_SSL, DEFAULT_HTTPS),
            verify_ssl=data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
        )
        try:
            await client.connect()
            await client.get_system_board()
        except UbusConnectionError:
            return "cannot_connect"
        except UbusAuthenticationError:
            return "invalid_auth"
        except Exception:
            _LOGGER.exception("Unexpected error during connection test")
            return "unknown"
        finally:
            await client.disconnect()
        return None

    async def _get_title(self, data: dict[str, Any]) -> str:
        """Get a friendly title for the config entry."""
        session = async_get_clientsession(
            self.hass, verify_ssl=data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
        )
        client = UbusClient(
            session=session,
            host=data[CONF_HOST],
            port=data[CONF_PORT],
            username=data[CONF_USERNAME],
            password=data[CONF_PASSWORD],
            https=data.get(CONF_SSL, DEFAULT_HTTPS),
            verify_ssl=data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
        )
        try:
            await client.connect()
            board = await client.get_system_board()
            hostname = board.get("hostname", "")
            model = board.get("model", "")
            if hostname and model:
                return f"{hostname} ({model})"
            return hostname or model or data[CONF_HOST]
        except UbusError:
            return data[CONF_HOST]
        finally:
            await client.disconnect()

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OpenWrtUbusOptionsFlow:
        """Return the options flow handler."""
        return OpenWrtUbusOptionsFlow(config_entry)


class OpenWrtUbusOptionsFlow(OptionsFlow):
    """Handle options for OpenWrt ubus."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self._config_entry.options

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_TRACK_DEVICES,
                        default=options.get(
                            CONF_TRACK_DEVICES, DEFAULT_TRACK_DEVICES
                        ),
                    ): bool,
                    vol.Required(
                        CONF_CONSIDER_HOME,
                        default=options.get(
                            CONF_CONSIDER_HOME, DEFAULT_CONSIDER_HOME
                        ),
                    ): vol.All(
                        vol.Coerce(int), vol.Range(min=0, max=600)
                    ),
                    vol.Required(
                        CONF_DEVICE_TRACKER_SCAN_INTERVAL,
                        default=options.get(
                            CONF_DEVICE_TRACKER_SCAN_INTERVAL,
                            DEFAULT_DEVICE_TRACKER_SCAN_INTERVAL,
                        ),
                    ): vol.All(
                        vol.Coerce(int), vol.Range(min=10, max=300)
                    ),
                    vol.Required(
                        CONF_STATS_SCAN_INTERVAL,
                        default=options.get(
                            CONF_STATS_SCAN_INTERVAL,
                            DEFAULT_STATS_SCAN_INTERVAL,
                        ),
                    ): vol.All(
                        vol.Coerce(int), vol.Range(min=30, max=600)
                    ),
                }
            ),
        )

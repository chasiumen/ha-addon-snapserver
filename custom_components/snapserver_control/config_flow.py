"""Config flow for Snapserver Control integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_TOKEN, CONF_URL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_MA_TOKEN,
    CONF_MA_URL,
    CONF_RPC_HOST,
    CONF_RPC_PORT,
    DEFAULT_MA_URL,
    DEFAULT_RPC_HOST,
    DEFAULT_RPC_PORT,
    DOMAIN,
    MA_INTEGRATION_DOMAIN,
)
from .ma_client import (
    MusicAssistantApiError,
    MusicAssistantAuthError,
    MusicAssistantClient,
)
from .rpc import SnapcastRpcClient
from .supervisor import SupervisorClient

CONF_SKIP_MA = "configure_ma_later"


def _rpc_schema(host: str, port: int) -> vol.Schema:
    """Build the control-socket form, pre-filled with the current values."""
    return vol.Schema(
        {
            vol.Required(CONF_RPC_HOST, default=host): str,
            vol.Required(CONF_RPC_PORT, default=port): vol.Coerce(int),
        }
    )


def _ma_defaults(hass: HomeAssistant) -> tuple[str, str]:
    """Prefill MA URL/token from HA's own Music Assistant integration entry.

    MA announces its URL and an auto-minted token to that integration via
    Supervisor discovery. NOTE: the announced token has role SERVICE, which
    cannot write provider config (admin only) — so it usually fails the write
    probe and the user must paste an admin long-lived token; the URL prefill
    is the part that reliably helps.
    """
    for entry in hass.config_entries.async_entries(MA_INTEGRATION_DOMAIN):
        url = entry.data.get(CONF_URL)
        if url:
            return url, entry.data.get(CONF_TOKEN) or ""
    return DEFAULT_MA_URL, ""


async def _validate_ma(
    hass: HomeAssistant, url: str, token: str
) -> tuple[str | None, dict[str, str]]:
    """Validate an MA connection; return (error_key, description_placeholders)."""
    client = MusicAssistantClient(url, token, async_get_clientsession(hass))
    try:
        instance_id = await client.get_snapcast_instance_id()
        if not await client.probe_write_access(instance_id):
            return "ma_token_not_admin", {}
    except MusicAssistantAuthError:
        return "invalid_ma_token", {}
    except MusicAssistantApiError as err:
        return "cannot_connect_ma", {"error": str(err)}
    except OSError as err:
        return "cannot_connect_ma", {"error": str(err)}
    return None, {}


class SnapserverControlConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Snapserver Control."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._rpc_data: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> SnapserverControlOptionsFlow:
        """Return the options flow."""
        return SnapserverControlOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step: addon presence + control socket."""
        # Only allow one instance
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}
        host = DEFAULT_RPC_HOST
        port = DEFAULT_RPC_PORT

        if user_input is not None:
            host = user_input[CONF_RPC_HOST]
            port = user_input[CONF_RPC_PORT]

            client = SupervisorClient()
            if not await client.is_addon_installed():
                errors["base"] = "addon_not_found"
            elif not await SnapcastRpcClient.async_test_connection(host, port):
                errors["base"] = "cannot_connect"
            else:
                self._rpc_data = {CONF_RPC_HOST: host, CONF_RPC_PORT: port}
                return await self.async_step_ma()

        return self.async_show_form(
            step_id="user",
            data_schema=_rpc_schema(host, port),
            errors=errors,
        )

    async def async_step_ma(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the Music Assistant connection (for sample-format control)."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        default_url, default_token = _ma_defaults(self.hass)

        if user_input is not None:
            if user_input.get(CONF_SKIP_MA):
                return self.async_create_entry(
                    title="Snapserver Control", data=dict(self._rpc_data)
                )
            url = user_input.get(CONF_MA_URL, default_url)
            token = user_input.get(CONF_MA_TOKEN, "")
            default_url, default_token = url, token
            if not token:
                errors["base"] = "invalid_ma_token"
            else:
                error, placeholders = await _validate_ma(self.hass, url, token)
                if error:
                    errors["base"] = error
                else:
                    return self.async_create_entry(
                        title="Snapserver Control",
                        data={
                            **self._rpc_data,
                            CONF_MA_URL: url,
                            CONF_MA_TOKEN: token,
                        },
                    )

        return self.async_show_form(
            step_id="ma",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MA_URL, default=default_url): str,
                    vol.Optional(CONF_MA_TOKEN, default=default_token): str,
                    vol.Optional(CONF_SKIP_MA, default=False): bool,
                }
            ),
            errors=errors,
            description_placeholders=placeholders,
        )


class SnapserverControlOptionsFlow(OptionsFlow):
    """Adjust the control socket and the Music Assistant connection."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        entry = self.config_entry
        host = entry.options.get(
            CONF_RPC_HOST, entry.data.get(CONF_RPC_HOST, DEFAULT_RPC_HOST)
        )
        port = entry.options.get(
            CONF_RPC_PORT, entry.data.get(CONF_RPC_PORT, DEFAULT_RPC_PORT)
        )
        discovered_url, _ = _ma_defaults(self.hass)
        ma_url = entry.options.get(
            CONF_MA_URL, entry.data.get(CONF_MA_URL, discovered_url)
        )
        ma_token = entry.options.get(CONF_MA_TOKEN, entry.data.get(CONF_MA_TOKEN, ""))

        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_RPC_HOST]
            port = user_input[CONF_RPC_PORT]
            ma_url = user_input.get(CONF_MA_URL, "")
            ma_token = user_input.get(CONF_MA_TOKEN, "")

            if not await SnapcastRpcClient.async_test_connection(host, port):
                errors["base"] = "cannot_connect"
            elif ma_url and ma_token:
                error, placeholders = await _validate_ma(self.hass, ma_url, ma_token)
                if error:
                    errors["base"] = error

            if not errors:
                # Saving triggers the entry update listener, which reloads.
                return self.async_create_entry(
                    data={
                        CONF_RPC_HOST: host,
                        CONF_RPC_PORT: port,
                        CONF_MA_URL: ma_url,
                        CONF_MA_TOKEN: ma_token,
                    }
                )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_RPC_HOST, default=host): str,
                    vol.Required(CONF_RPC_PORT, default=port): vol.Coerce(int),
                    vol.Optional(CONF_MA_URL, default=ma_url): str,
                    vol.Optional(CONF_MA_TOKEN, default=ma_token): str,
                }
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

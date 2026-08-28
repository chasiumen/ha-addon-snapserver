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
from homeassistant.core import callback

from .const import (
    CONF_RPC_HOST,
    CONF_RPC_PORT,
    DEFAULT_RPC_HOST,
    DEFAULT_RPC_PORT,
    DOMAIN,
)
from .rpc import SnapcastRpcClient
from .supervisor import SupervisorClient


def _schema(host: str, port: int) -> vol.Schema:
    """Build the host/port form, pre-filled with the current values."""
    return vol.Schema(
        {
            vol.Required(CONF_RPC_HOST, default=host): str,
            vol.Required(CONF_RPC_PORT, default=port): vol.Coerce(int),
        }
    )


class SnapserverControlConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Snapserver Control."""

    VERSION = 1

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
        """Handle the initial step."""
        # Only allow one instance
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}
        host = DEFAULT_RPC_HOST
        port = DEFAULT_RPC_PORT

        if user_input is not None:
            host = user_input[CONF_RPC_HOST]
            port = user_input[CONF_RPC_PORT]

            # Verify addon is installed
            client = SupervisorClient()
            if not await client.is_addon_installed():
                errors["base"] = "addon_not_found"
            elif not await SnapcastRpcClient.async_test_connection(host, port):
                # The addon is installed but its control socket isn't answering
                # -- usually because it is stopped, occasionally a typo here.
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title="Snapserver Control",
                    data={CONF_RPC_HOST: host, CONF_RPC_PORT: port},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(host, port),
            errors=errors,
        )


class SnapserverControlOptionsFlow(OptionsFlow):
    """Allow the control socket to be corrected without re-adding the entry."""

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

        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_RPC_HOST]
            port = user_input[CONF_RPC_PORT]
            if await SnapcastRpcClient.async_test_connection(host, port):
                # Saving options triggers a reload, which reconnects.
                return self.async_create_entry(data=user_input)
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="init",
            data_schema=_schema(host, port),
            errors=errors,
        )

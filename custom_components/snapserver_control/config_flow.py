"""Config flow for Snapserver Control integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN
from .supervisor import SupervisorClient


class SnapserverControlConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Snapserver Control."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        # Only allow one instance
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}

        if user_input is not None:
            # Verify addon is installed
            client = SupervisorClient()
            if await client.is_addon_installed():
                return self.async_create_entry(
                    title="Snapserver Control",
                    data={},
                )
            errors["base"] = "addon_not_found"

        return self.async_show_form(
            step_id="user",
            errors=errors,
        )

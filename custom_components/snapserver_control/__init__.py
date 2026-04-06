"""The Snapserver Control integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN, LOGGER
from .supervisor import SupervisorClient, SupervisorApiError

type SnapserverControlConfigEntry = ConfigEntry[SupervisorClient]

PLATFORMS = [Platform.SELECT, Platform.NUMBER]


async def async_setup_entry(
    hass: HomeAssistant, entry: SnapserverControlConfigEntry
) -> bool:
    """Set up Snapserver Control from a config entry."""
    client = SupervisorClient()

    try:
        if not await client.is_addon_installed():
            raise ConfigEntryNotReady("Snapserver addon not found")
    except Exception as err:
        raise ConfigEntryNotReady(f"Cannot connect to Supervisor: {err}") from err

    entry.runtime_data = client

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services
    async def handle_set_codec(call) -> None:
        """Handle set_codec service call."""
        codec = call.data["codec"]
        options = await client.get_addon_options()
        options["codec"] = codec
        await client.set_addon_options(options)
        await client.restart_addon()

    async def handle_set_sampleformat(call) -> None:
        """Handle set_sampleformat service call."""
        sampleformat = call.data["sampleformat"]
        options = await client.get_addon_options()
        options["sampleformat"] = sampleformat
        await client.set_addon_options(options)
        await client.restart_addon()

    async def handle_set_buffer(call) -> None:
        """Handle set_buffer service call."""
        buffer_ms = call.data["buffer_ms"]
        options = await client.get_addon_options()
        options["buffer_ms"] = buffer_ms
        await client.set_addon_options(options)
        await client.restart_addon()

    hass.services.async_register(DOMAIN, "set_codec", handle_set_codec)
    hass.services.async_register(DOMAIN, "set_sampleformat", handle_set_sampleformat)
    hass.services.async_register(DOMAIN, "set_buffer", handle_set_buffer)

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: SnapserverControlConfigEntry
) -> bool:
    """Unload a config entry."""
    hass.services.async_remove(DOMAIN, "set_codec")
    hass.services.async_remove(DOMAIN, "set_sampleformat")
    hass.services.async_remove(DOMAIN, "set_buffer")
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

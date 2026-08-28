"""The Snapserver Control integration."""

from __future__ import annotations

from dataclasses import dataclass

import voluptuous as vol

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .const import (
    ATTR_CLIENT_ID,
    CARD_FILENAME,
    CARD_URL,
    CARD_VERSION,
    CONF_RPC_HOST,
    CONF_RPC_PORT,
    DEFAULT_RPC_HOST,
    DEFAULT_RPC_PORT,
    DOMAIN,
    LOGGER,
    SERVICE_DELETE_CLIENT,
)
from .coordinator import SnapserverCoordinator
from .entity import server_device_info
from .supervisor import SupervisorApiError, SupervisorClient


@dataclass
class SnapserverControlData:
    """Runtime objects shared by the platforms."""

    supervisor: SupervisorClient
    coordinator: SnapserverCoordinator


type SnapserverControlConfigEntry = ConfigEntry[SnapserverControlData]

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
]

CARD_REGISTERED = f"{DOMAIN}_card_registered"

DELETE_CLIENT_SCHEMA = vol.Schema({vol.Required(ATTR_CLIENT_ID): cv.string})


def get_rpc_target(entry: ConfigEntry) -> tuple[str, int]:
    """Return the configured control socket, falling back to the defaults.

    Entries created before this option existed have neither key, so both lookups
    fall through -- no migration needed.
    """
    host = entry.options.get(
        CONF_RPC_HOST, entry.data.get(CONF_RPC_HOST, DEFAULT_RPC_HOST)
    )
    port = entry.options.get(
        CONF_RPC_PORT, entry.data.get(CONF_RPC_PORT, DEFAULT_RPC_PORT)
    )
    return host, int(port)


async def async_setup_entry(
    hass: HomeAssistant, entry: SnapserverControlConfigEntry
) -> bool:
    """Set up Snapserver Control from a config entry."""
    client = SupervisorClient()

    try:
        installed = await client.is_addon_installed()
    except (SupervisorApiError, OSError) as err:
        raise ConfigEntryNotReady(f"Cannot connect to Supervisor: {err}") from err

    if not installed:
        raise ConfigEntryNotReady("Snapserver addon not found")

    host, port = get_rpc_target(entry)
    coordinator = SnapserverCoordinator(hass, entry, host, port)
    # Deliberately not awaited to a first result: the addon may still be
    # starting, and client state arrives by push once it is up.
    await coordinator.async_start()
    entry.async_on_unload(coordinator.async_stop)

    entry.runtime_data = SnapserverControlData(supervisor=client, coordinator=coordinator)

    # Per-client devices hang off this one via via_device, and binary_sensor sets
    # up before the platforms that would otherwise create it -- so create it here
    # rather than letting the parent link resolve to nothing.
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, **server_device_info(entry)
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await _async_register_frontend(hass)

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    # Register services
    async def handle_set_codec(call: ServiceCall) -> None:
        """Handle set_codec service call."""
        codec = call.data["codec"]
        options = await client.get_addon_options()
        options["codec"] = codec
        await client.set_addon_options(options)
        await client.restart_addon()

    async def handle_set_sampleformat(call: ServiceCall) -> None:
        """Handle set_sampleformat service call."""
        sampleformat = call.data["sampleformat"]
        options = await client.get_addon_options()
        options["sampleformat"] = sampleformat
        await client.set_addon_options(options)
        await client.restart_addon()

    async def handle_set_buffer(call: ServiceCall) -> None:
        """Handle set_buffer service call."""
        buffer_ms = call.data["buffer_ms"]
        options = await client.get_addon_options()
        options["buffer_ms"] = buffer_ms
        await client.set_addon_options(options)
        await client.restart_addon()

    async def handle_delete_client(call: ServiceCall) -> None:
        """Forget a client that is never coming back."""
        await coordinator.async_delete_client(call.data[ATTR_CLIENT_ID])

    hass.services.async_register(DOMAIN, "set_codec", handle_set_codec)
    hass.services.async_register(DOMAIN, "set_sampleformat", handle_set_sampleformat)
    hass.services.async_register(DOMAIN, "set_buffer", handle_set_buffer)
    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_CLIENT,
        handle_delete_client,
        schema=DELETE_CLIENT_SCHEMA,
    )

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: SnapserverControlConfigEntry
) -> bool:
    """Unload a config entry."""
    hass.services.async_remove(DOMAIN, "set_codec")
    hass.services.async_remove(DOMAIN, "set_sampleformat")
    hass.services.async_remove(DOMAIN, "set_buffer")
    hass.services.async_remove(DOMAIN, SERVICE_DELETE_CLIENT)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_options_updated(
    hass: HomeAssistant, entry: SnapserverControlConfigEntry
) -> None:
    """Reconnect against the new host/port when the options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Serve the client status card and load it into the dashboard."""
    if hass.data.get(CARD_REGISTERED):
        return
    hass.data[CARD_REGISTERED] = True

    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                CARD_URL,
                hass.config.path(f"custom_components/{DOMAIN}/www/{CARD_FILENAME}"),
                False,
            )
        ]
    )
    add_extra_js_url(hass, f"{CARD_URL}?v={CARD_VERSION}")
    LOGGER.debug("Registered Snapcast clients card at %s", CARD_URL)

"""Select entities for Snapserver Control."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SnapserverControlConfigEntry
from .const import (
    CODEC_OPTIONS,
    CONF_CODEC,
    CONF_SAMPLEFORMAT,
    DOMAIN,
    LOGGER,
    SAMPLEFORMAT_OPTIONS,
)
from .supervisor import SupervisorClient


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SnapserverControlConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Snapserver Control select entities."""
    client = entry.runtime_data
    options = await client.get_addon_options()

    async_add_entities([
        SnapserverCodecSelect(entry, client, options.get("codec", "flac")),
        SnapserverSampleformatSelect(entry, client, options.get("sampleformat", "48000:16:2")),
    ])


class SnapserverBaseSelect(SelectEntity):
    """Base select entity for Snapserver settings."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: SnapserverControlConfigEntry,
        client: SupervisorClient,
        current_value: str,
    ) -> None:
        """Initialize the select entity."""
        self._client = client
        self._attr_current_option = current_value
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer="Snapcast",
            model="Snapserver",
            name="Snapserver",
        )

    async def _update_and_restart(self, option_key: str, value: str) -> None:
        """Update addon option and restart."""
        options = await self._client.get_addon_options()
        options[option_key] = value
        await self._client.set_addon_options(options)
        await self._client.restart_addon()
        self._attr_current_option = value
        self.async_write_ha_state()


class SnapserverCodecSelect(SnapserverBaseSelect):
    """Select entity for audio codec."""

    _attr_name = "Audio Codec"
    _attr_icon = "mdi:file-music"
    _attr_options = CODEC_OPTIONS

    def __init__(
        self,
        entry: SnapserverControlConfigEntry,
        client: SupervisorClient,
        current_value: str,
    ) -> None:
        """Initialize."""
        super().__init__(entry, client, current_value)
        self._attr_unique_id = f"{entry.entry_id}_codec"

    async def async_select_option(self, option: str) -> None:
        """Change the codec."""
        LOGGER.info("Setting Snapserver codec to %s", option)
        await self._update_and_restart(CONF_CODEC, option)


class SnapserverSampleformatSelect(SnapserverBaseSelect):
    """Select entity for sample format."""

    _attr_name = "Sample Format"
    _attr_icon = "mdi:tune"
    _attr_options = SAMPLEFORMAT_OPTIONS

    def __init__(
        self,
        entry: SnapserverControlConfigEntry,
        client: SupervisorClient,
        current_value: str,
    ) -> None:
        """Initialize."""
        super().__init__(entry, client, current_value)
        self._attr_unique_id = f"{entry.entry_id}_sampleformat"

    async def async_select_option(self, option: str) -> None:
        """Change the sample format."""
        LOGGER.info("Setting Snapserver sample format to %s", option)
        await self._update_and_restart(CONF_SAMPLEFORMAT, option)

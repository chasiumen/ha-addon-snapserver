"""Select entities for Snapserver Control.

Two selects with deliberately different backends:
- Codec writes the ADDON's config and restarts it — MA omits codec= from its
  stream URI, so snapserver's global default genuinely applies.
- Sample format writes MUSIC ASSISTANT's provider config via its API — MA bakes
  sampleformat= into its stream URI, so the addon-side value can never win.
See docs/PLAN_ma_sampleformat.md for the verified ground truth behind this split.
"""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SnapserverControlConfigEntry
from .const import (
    CODEC_OPTIONS,
    CONF_CODEC,
    DOMAIN,
    LOGGER,
    SAMPLEFORMAT_OPTIONS,
)
from .ma_client import (
    KEY_BIT_DEPTH,
    KEY_SAMPLE_RATE,
    MusicAssistantApiError,
    MusicAssistantClient,
    MusicAssistantScopeError,
)
from .resume import resume_players, snapshot_playing_players
from .supervisor import SupervisorClient


def _server_device_info(entry: SnapserverControlConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer="Snapcast",
        model="Snapserver",
        name="Snapserver",
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SnapserverControlConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Snapserver Control select entities."""
    data = entry.runtime_data
    options = await data.supervisor.get_addon_options()

    # Seed the sample format from MA's config — the only place it is honored.
    current_format: str | None = None
    if data.ma is not None and data.ma_instance_id is not None:
        try:
            rate = await data.ma.get_value(data.ma_instance_id, KEY_SAMPLE_RATE)
            depth = await data.ma.get_value(data.ma_instance_id, KEY_BIT_DEPTH)
        except MusicAssistantApiError as err:
            LOGGER.warning("Cannot read the sample format from Music Assistant: %s", err)
        else:
            if rate and depth:
                current_format = f"{rate}:{depth}:2"
                if int(depth) == 24:
                    LOGGER.warning(
                        "Music Assistant is set to 24-bit, which snapserver"
                        " <= 0.35.0 misparses (no packed_s24le support) —"
                        " select a 16-bit format to fix the audio"
                    )

    async_add_entities(
        [
            SnapserverCodecSelect(entry, data.supervisor, options.get("codec", "flac")),
            SnapserverSampleformatSelect(
                entry, data.ma, data.ma_instance_id, current_format
            ),
        ]
    )


class SnapserverCodecSelect(SelectEntity):
    """Select entity for the addon's audio codec (verified working end-to-end)."""

    _attr_has_entity_name = True
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
        self._client = client
        self._attr_current_option = current_value
        self._attr_unique_id = f"{entry.entry_id}_codec"
        self._attr_device_info = _server_device_info(entry)

    async def async_select_option(self, option: str) -> None:
        """Change the codec: update the addon option and restart the addon."""
        LOGGER.info("Setting Snapserver codec to %s", option)
        options = await self._client.get_addon_options()
        options[CONF_CODEC] = option
        await self._client.set_addon_options(options)
        await self._client.restart_addon()
        self._attr_current_option = option
        self.async_write_ha_state()


class SnapserverSampleformatSelect(SelectEntity):
    """Select entity for the stream sample format, backed by Music Assistant."""

    _attr_has_entity_name = True
    _attr_name = "Sample Format"
    _attr_icon = "mdi:tune"

    def __init__(
        self,
        entry: SnapserverControlConfigEntry,
        ma: MusicAssistantClient | None,
        instance_id: str | None,
        current_value: str | None,
    ) -> None:
        """Initialize from MA's current config (None when MA is unconfigured)."""
        self._ma = ma
        self._instance_id = instance_id
        # Keep the pre-rework unique_id so the entity id and history survive.
        self._attr_unique_id = f"{entry.entry_id}_sampleformat"
        self._attr_device_info = _server_device_info(entry)
        self._attr_options = list(SAMPLEFORMAT_OPTIONS)
        # An out-of-list value (e.g. 24-bit set in MA's own UI) is still shown.
        if current_value is not None and current_value not in self._attr_options:
            self._attr_options.append(current_value)
        self._attr_current_option = current_value

    @property
    def available(self) -> bool:
        """Only available once a working MA connection is configured."""
        return self._ma is not None and self._instance_id is not None

    async def async_select_option(self, option: str) -> None:
        """Write the format to MA's provider config; MA reloads itself (~10s)."""
        if self._ma is None or self._instance_id is None:
            raise HomeAssistantError(
                "Music Assistant is not configured — add its URL and an admin"
                " token in the Snapserver Control options"
            )
        rate = int(option.split(":")[0])
        LOGGER.info("Setting the Music Assistant stream sample rate to %d", rate)

        # Snapshot BEFORE the write: the provider reload stops these players.
        playing = snapshot_playing_players(self.hass)

        try:
            await self._ma.apply_sampleformat(self._instance_id, rate)
        except MusicAssistantScopeError as err:
            raise HomeAssistantError(
                "The configured Music Assistant token lacks admin rights —"
                " create a long-lived token for an admin user in the MA web UI"
            ) from err
        except MusicAssistantApiError as err:
            raise HomeAssistantError(
                f"Failed to update Music Assistant: {err}"
            ) from err

        self._attr_options = list(SAMPLEFORMAT_OPTIONS)
        self._attr_current_option = option
        self.async_write_ha_state()

        if playing:
            self.hass.async_create_task(resume_players(self.hass, playing))

"""Number entities for Snapserver Control."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SnapserverControlConfigEntry
from .const import (
    BUFFER_MAX,
    BUFFER_MIN,
    BUFFER_STEP,
    CONF_BUFFER_MS,
    DOMAIN,
    LOGGER,
)
from .supervisor import SupervisorClient


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SnapserverControlConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Snapserver Control number entities."""
    client = entry.runtime_data
    options = await client.get_addon_options()

    async_add_entities([
        SnapserverBufferNumber(entry, client, options.get("buffer_ms", 1000)),
    ])


class SnapserverBufferNumber(NumberEntity):
    """Number entity for buffer size."""

    _attr_has_entity_name = True
    _attr_name = "Buffer Size"
    _attr_icon = "mdi:timer-sand"
    _attr_native_unit_of_measurement = "ms"
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = BUFFER_MIN
    _attr_native_max_value = BUFFER_MAX
    _attr_native_step = BUFFER_STEP

    def __init__(
        self,
        entry: SnapserverControlConfigEntry,
        client: SupervisorClient,
        current_value: int,
    ) -> None:
        """Initialize the number entity."""
        self._client = client
        self._attr_native_value = float(current_value)
        self._attr_unique_id = f"{entry.entry_id}_buffer"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer="Snapcast",
            model="Snapserver",
            name="Snapserver",
        )

    async def async_set_native_value(self, value: float) -> None:
        """Set the buffer size."""
        buffer_ms = int(value)
        LOGGER.info("Setting Snapserver buffer to %d ms", buffer_ms)
        options = await self._client.get_addon_options()
        options[CONF_BUFFER_MS] = buffer_ms
        await self._client.set_addon_options(options)
        await self._client.restart_addon()
        self._attr_native_value = float(buffer_ms)
        self.async_write_ha_state()

"""Connectivity binary sensors for Snapcast clients."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import SnapserverCoordinator
from .entity import SnapclientEntity, SnapserverEntity

if TYPE_CHECKING:
    from . import SnapserverControlConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SnapserverControlConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the connectivity sensors."""
    coordinator = entry.runtime_data.coordinator
    known: set[str] = set()

    @callback
    def _add_new_clients() -> None:
        """Create entities for clients we haven't seen before."""
        new = [
            client_id
            for client_id in coordinator.data.clients
            if client_id not in known
        ]
        if not new:
            return
        known.update(new)
        async_add_entities(
            SnapclientConnectivity(coordinator, entry, coordinator.data.clients[cid])
            for cid in new
        )

    # Clients can appear at any time, so keep watching rather than only
    # enumerating whatever exists at setup.
    entry.async_on_unload(coordinator.async_add_listener(_add_new_clients))

    async_add_entities([SnapserverOnline(coordinator, entry)])
    _add_new_clients()


class SnapclientConnectivity(SnapclientEntity, BinarySensorEntity):
    """Whether one Snapcast client is currently connected."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_name = "Connected"

    def __init__(
        self,
        coordinator: SnapserverCoordinator,
        entry: SnapserverControlConfigEntry,
        client: dict[str, Any],
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, client)
        self._attr_unique_id = f"{entry.entry_id}_{client['id']}_connected"

    @property
    def is_on(self) -> bool:
        """Return True while the client is connected."""
        return bool(self.client.get("connected"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return everything useful for diagnosing a dropped client."""
        client = self.client
        last_seen = client.get("last_seen")
        return {
            "client_id": client.get("id"),
            "ip": client.get("ip"),
            "mac": client.get("mac"),
            "host_name": client.get("host_name"),
            "os": client.get("os"),
            "arch": client.get("arch"),
            "snapclient_version": client.get("version"),
            "instance": client.get("instance"),
            "latency_ms": client.get("latency_ms"),
            "volume_percent": client.get("volume_percent"),
            "muted": client.get("muted"),
            "group_id": client.get("group_id"),
            "stream_id": client.get("stream_id"),
            "last_seen": (
                dt_util.utc_from_timestamp(last_seen).isoformat()
                if last_seen
                else None
            ),
        }


class SnapserverOnline(SnapserverEntity, BinarySensorEntity):
    """Whether the control connection to Snapserver itself is up.

    Lets a dashboard distinguish "the server is gone" from "a client dropped".
    """

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_name = "Control connection"

    def __init__(
        self,
        coordinator: SnapserverCoordinator,
        entry: SnapserverControlConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_online"

    @property
    def is_on(self) -> bool:
        """Return True while the RPC connection is established."""
        return self.coordinator.data.online

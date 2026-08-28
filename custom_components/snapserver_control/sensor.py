"""Sensors describing Snapcast clients and streams."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR_DOMAIN
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import SnapserverCoordinator
from .entity import SnapclientEntity, SnapserverEntity

if TYPE_CHECKING:
    from . import SnapserverControlConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SnapserverControlConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Snapserver sensors."""
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
            SnapclientLastSeen(coordinator, entry, coordinator.data.clients[cid])
            for cid in new
        )

    entry.async_on_unload(coordinator.async_add_listener(_add_new_clients))

    async_add_entities(
        [
            SnapserverClients(coordinator, entry),
            SnapserverStreamStatus(coordinator, entry),
        ]
    )
    _add_new_clients()


class SnapclientLastSeen(SnapclientEntity, SensorEntity):
    """When a client was last heard from.

    A timestamp device class means the UI renders this as "12 minutes ago",
    which is the thing you actually want to know about a dead client.
    """

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_name = "Last seen"

    def __init__(
        self,
        coordinator: SnapserverCoordinator,
        entry: SnapserverControlConfigEntry,
        client: dict[str, Any],
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, client)
        self._attr_unique_id = f"{entry.entry_id}_{client['id']}_last_seen"

    @property
    def native_value(self) -> datetime | None:
        """Return the last-seen timestamp, or None if never seen."""
        last_seen = self.client.get("last_seen")
        return dt_util.utc_from_timestamp(last_seen) if last_seen else None


class SnapserverClients(SnapserverEntity, SensorEntity):
    """Number of connected clients, with the full roster as an attribute.

    The dashboard card renders off this one entity's attribute rather than
    discovering per-client entities itself.
    """

    _attr_name = "Clients connected"
    _attr_icon = "mdi:speaker-multiple"

    def __init__(
        self,
        coordinator: SnapserverCoordinator,
        entry: SnapserverControlConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_clients"

    @property
    def native_value(self) -> int:
        """Return how many clients are currently connected."""
        return sum(
            1 for client in self.coordinator.data.clients.values() if client["connected"]
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the client roster the frontend card renders."""
        data = self.coordinator.data
        registry = er.async_get(self.hass)

        clients = []
        for client in sorted(
            data.clients.values(), key=lambda item: (item["name"] or "").lower()
        ):
            last_seen = client.get("last_seen")
            clients.append(
                {
                    "id": client["id"],
                    "name": client["name"],
                    "connected": client["connected"],
                    "ip": client.get("ip"),
                    "version": client.get("version"),
                    "latency_ms": client.get("latency_ms"),
                    "volume_percent": client.get("volume_percent"),
                    "muted": client.get("muted"),
                    "stream_id": client.get("stream_id"),
                    "last_seen": (
                        dt_util.utc_from_timestamp(last_seen).isoformat()
                        if last_seen
                        else None
                    ),
                    # Lets the card open the right more-info dialog without
                    # having to walk the entity registry itself.
                    "entity_id": registry.async_get_entity_id(
                        BINARY_SENSOR_DOMAIN,
                        DOMAIN,
                        f"{self._entry_id}_{client['id']}_connected",
                    ),
                }
            )

        return {
            "total_clients": len(clients),
            "server_online": data.online,
            "clients": clients,
        }


class SnapserverStreamStatus(SnapserverEntity, SensorEntity):
    """Status of the audio stream feeding the clients.

    Separates "nothing is playing" from "the client died mid-song".
    """

    _attr_name = "Stream status"
    _attr_icon = "mdi:cast-audio"

    def __init__(
        self,
        coordinator: SnapserverCoordinator,
        entry: SnapserverControlConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_stream_status"

    @property
    def native_value(self) -> str | None:
        """Return the status of the first stream, if any."""
        streams = self.coordinator.data.streams
        if not streams:
            return None
        # Prefer a stream that is actually doing something over a list order.
        for stream in streams:
            if stream.get("status") == "playing":
                return "playing"
        return streams[0].get("status")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return every stream and its status."""
        return {"streams": self.coordinator.data.streams}

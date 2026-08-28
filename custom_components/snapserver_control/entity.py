"""Shared entity bases for Snapserver Control."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SnapserverCoordinator


def server_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Return the Snapserver device, shared with the select/number entities."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer="Snapcast",
        model="Snapserver",
        name="Snapserver",
    )


class SnapserverEntity(CoordinatorEntity[SnapserverCoordinator]):
    """Base entity for things describing the server as a whole."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: SnapserverCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._entry_id = entry.entry_id
        self._attr_device_info = server_device_info(entry)


class SnapclientEntity(CoordinatorEntity[SnapserverCoordinator]):
    """Base entity for a single Snapcast client.

    Each client becomes its own device hanging off the Snapserver device, so a
    speaker's connectivity and last-seen entities group together in the UI.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SnapserverCoordinator,
        entry: ConfigEntry,
        client: dict[str, Any],
    ) -> None:
        """Initialize the entity from a client snapshot."""
        super().__init__(coordinator)
        self._entry_id = entry.entry_id
        self._client_id = client["id"]
        self._client = client

        connections = set()
        if client.get("mac"):
            connections.add((CONNECTION_NETWORK_MAC, client["mac"]))

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{client['id']}")},
            connections=connections,
            manufacturer="Snapcast",
            model="Snapclient",
            name=client["name"],
            sw_version=client.get("version"),
            via_device=(DOMAIN, entry.entry_id),
        )

    @property
    def client(self) -> dict[str, Any]:
        """Return the most recent snapshot of this client."""
        return self._client

    @property
    def available(self) -> bool:
        """Return whether the client is still known to the server.

        While the control connection is down we keep reporting the last known
        state rather than going unavailable -- otherwise "the server restarted"
        would look exactly like "every client died", which is the confusion this
        integration exists to remove.
        """
        data = self.coordinator.data
        if not data.online:
            return True
        return self._client_id in data.clients

    @callback
    def _handle_coordinator_update(self) -> None:
        """Cache the latest snapshot, then write state."""
        client = self.coordinator.data.clients.get(self._client_id)
        if client is not None:
            self._client = client
        super()._handle_coordinator_update()

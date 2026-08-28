"""Keeps Snapcast client state in sync with Snapserver.

This coordinator is push-driven: Snapserver notifies us on every client connect
and disconnect, so there is no polling interval. rpc.py re-fetches a full status
periodically as a safety net.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, LOGGER
from .rpc import (
    SnapcastRpcClient,
    flatten_clients,
    normalize_client,
    parse_streams,
)


@dataclass(frozen=True)
class SnapserverData:
    """Snapshot of everything the entities render."""

    clients: dict[str, dict[str, Any]] = field(default_factory=dict)
    streams: list[dict[str, Any]] = field(default_factory=list)
    online: bool = False


class SnapserverCoordinator(DataUpdateCoordinator[SnapserverData]):
    """Maintains the control connection and publishes client state."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        host: str,
        port: int,
    ) -> None:
        """Initialize the coordinator. No connection is opened until started."""
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            config_entry=entry,
            # Push-driven: Snapserver tells us when something changes.
            update_interval=None,
        )
        self.data = SnapserverData()
        self.rpc = SnapcastRpcClient(
            host,
            port,
            on_status=self._handle_status,
            on_client=self._handle_client,
            on_connection_change=self._handle_connection_change,
        )

    async def async_start(self) -> None:
        """Begin connecting to Snapserver in the background."""
        await self.rpc.async_start()

    async def async_stop(self) -> None:
        """Close the control connection."""
        await self.rpc.async_stop()

    async def async_delete_client(self, client_id: str) -> None:
        """Remove a client from Snapserver's state for good."""
        LOGGER.info("Deleting Snapcast client %s", client_id)
        self._handle_status(await self.rpc.async_delete_client(client_id))

    @callback
    def _handle_status(self, server: dict[str, Any]) -> None:
        """Publish a full server status."""
        self.async_set_updated_data(
            SnapserverData(
                clients=flatten_clients(server),
                streams=parse_streams(server),
                online=True,
            )
        )

    @callback
    def _handle_client(self, raw: dict[str, Any]) -> None:
        """Publish a single client update pushed by the server."""
        client_id = raw.get("id")
        if not client_id:
            return

        current = self.data
        # A Client.On* notification carries no group context, so keep whatever
        # grouping the last full status told us about.
        previous = current.clients.get(client_id, {})
        client = normalize_client(
            raw, previous.get("group_id"), previous.get("stream_id")
        )
        LOGGER.debug(
            "Snapcast client %s is now %s",
            client["name"],
            "connected" if client["connected"] else "disconnected",
        )
        self.async_set_updated_data(
            replace(current, clients={**current.clients, client_id: client}, online=True)
        )

    @callback
    def _handle_connection_change(self, connected: bool) -> None:
        """Record whether the control connection itself is up.

        Client state is deliberately left alone: if we blanked it out here, a
        server restart would look exactly like every client dying.
        """
        if not connected:
            LOGGER.warning("Lost the Snapserver control connection; reconnecting")
        self.async_set_updated_data(replace(self.data, online=connected))

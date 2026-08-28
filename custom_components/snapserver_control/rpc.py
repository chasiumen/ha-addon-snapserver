"""Snapcast JSON-RPC client over the raw TCP control socket.

Snapserver exposes a JSON-RPC 2.0 API on port 1705 with newline-delimited JSON
messages (ndjson). That transport is always available -- unlike the HTTP/WebSocket
endpoint on 1780, which only exists while the addon's ``snapweb_enabled`` option is
on.

This module deliberately imports nothing from Home Assistant so it can be tested
standalone against a fake ndjson server (see tests/test_rpc.py).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Callable
from typing import Any

LOGGER = logging.getLogger(__name__)

DEFAULT_RPC_HOST = "127.0.0.1"
DEFAULT_RPC_PORT = 1705

CONNECT_TIMEOUT = 10.0
REQUEST_TIMEOUT = 10.0
RESYNC_INTERVAL = 60.0
RESYNC_DEBOUNCE = 0.5
BACKOFF_START = 1.0
BACKOFF_MAX = 60.0

# Server.GetStatus grows with the number of known clients; the asyncio default
# stream limit of 64 KiB is generous but not obviously enough forever.
READ_LIMIT = 4 * 1024 * 1024


class SnapcastRpcError(Exception):
    """Error talking to the Snapserver control API."""


def normalize_client(
    raw: dict[str, Any],
    group_id: str | None = None,
    stream_id: str | None = None,
) -> dict[str, Any]:
    """Flatten one client object from the API into the shape entities consume.

    The documented client object nests config/host/snapclient/lastSeen; entity
    code is much easier to read against a flat dict.
    """
    config = raw.get("config") or {}
    host = raw.get("host") or {}
    snapclient = raw.get("snapclient") or {}
    volume = config.get("volume") or {}
    last_seen = raw.get("lastSeen") or {}

    # A client that has genuinely never been seen reports sec 0; surfacing that
    # as 1970-01-01 would be worse than reporting nothing.
    sec = last_seen.get("sec") or 0
    last_seen_ts: float | None = None
    if sec:
        last_seen_ts = sec + (last_seen.get("usec") or 0) / 1_000_000

    # config.name is the user-assigned label and is often empty; the hostname is
    # the next best thing, and the id (a MAC) is the last resort.
    client_id = raw.get("id") or ""
    name = config.get("name") or host.get("name") or client_id

    return {
        "id": client_id,
        "name": name,
        "connected": bool(raw.get("connected")),
        "ip": host.get("ip") or None,
        "mac": host.get("mac") or None,
        "host_name": host.get("name") or None,
        "os": host.get("os") or None,
        "arch": host.get("arch") or None,
        "version": snapclient.get("version") or None,
        "protocol_version": snapclient.get("protocolVersion"),
        "instance": config.get("instance"),
        "latency_ms": config.get("latency"),
        "volume_percent": volume.get("percent"),
        "muted": volume.get("muted"),
        "group_id": group_id,
        "stream_id": stream_id,
        "last_seen": last_seen_ts,
    }


def flatten_clients(server: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Turn a server object's nested groups into {client_id: client}."""
    clients: dict[str, dict[str, Any]] = {}
    for group in server.get("groups") or []:
        group_id = group.get("id")
        stream_id = group.get("stream_id")
        for raw in group.get("clients") or []:
            client = normalize_client(raw, group_id, stream_id)
            if client["id"]:
                clients[client["id"]] = client
    return clients


def parse_streams(server: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract the stream list (id + idle/playing status) from a server object."""
    return [
        {"id": stream.get("id"), "status": stream.get("status")}
        for stream in server.get("streams") or []
    ]


class SnapcastRpcClient:
    """Persistent ndjson JSON-RPC connection to Snapserver.

    Holds one long-lived socket: requests are matched to responses by id, and the
    server's pushed notifications drive the callbacks. Drops are recovered from
    with exponential backoff.
    """

    def __init__(
        self,
        host: str = DEFAULT_RPC_HOST,
        port: int = DEFAULT_RPC_PORT,
        *,
        on_status: Callable[[dict[str, Any]], None] | None = None,
        on_client: Callable[[dict[str, Any]], None] | None = None,
        on_connection_change: Callable[[bool], None] | None = None,
    ) -> None:
        """Initialize the client. No I/O happens until async_start()."""
        self.host = host
        self.port = port
        self._on_status = on_status
        self._on_client = on_client
        self._on_connection_change = on_connection_change

        self._writer: asyncio.StreamWriter | None = None
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._next_id = 0
        self._connected = False
        self._run_task: asyncio.Task[None] | None = None
        self._resync_event = asyncio.Event()

    @property
    def connected(self) -> bool:
        """Return True while the control connection is up."""
        return self._connected

    async def async_start(self) -> None:
        """Start the connect/reconnect loop in the background."""
        if self._run_task is None:
            self._run_task = asyncio.create_task(self._run())

    async def async_stop(self) -> None:
        """Cancel the background task and close the socket."""
        task, self._run_task = self._run_task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await self._close_writer()
        self._set_connected(False)

    async def async_request(
        self, method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Send a request and wait for its response."""
        writer = self._writer
        if writer is None or writer.is_closing():
            raise SnapcastRpcError("Not connected to Snapserver")

        self._next_id += 1
        request_id = self._next_id
        message: dict[str, Any] = {
            "id": request_id,
            "jsonrpc": "2.0",
            "method": method,
        }
        if params:
            message["params"] = params

        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            writer.write((json.dumps(message) + "\n").encode())
            await writer.drain()
            return await asyncio.wait_for(future, REQUEST_TIMEOUT)
        except TimeoutError as err:
            raise SnapcastRpcError(f"Timed out waiting for {method}") from err
        except OSError as err:
            raise SnapcastRpcError(f"Failed to send {method}: {err}") from err
        finally:
            self._pending.pop(request_id, None)

    async def async_get_status(self) -> dict[str, Any]:
        """Call Server.GetStatus and return the server object."""
        result = await self.async_request("Server.GetStatus")
        return result.get("server") or {}

    async def async_delete_client(self, client_id: str) -> dict[str, Any]:
        """Permanently remove a client from the server's state."""
        result = await self.async_request(
            "Server.DeleteClient", {"id": client_id}
        )
        return result.get("server") or {}

    @staticmethod
    async def async_test_connection(host: str, port: int) -> bool:
        """One-shot reachability check used by the config flow."""
        writer: asyncio.StreamWriter | None = None
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port, limit=READ_LIMIT),
                CONNECT_TIMEOUT,
            )
            request = {"id": 1, "jsonrpc": "2.0", "method": "Server.GetRPCVersion"}
            writer.write((json.dumps(request) + "\n").encode())
            await writer.drain()
            line = await asyncio.wait_for(reader.readuntil(b"\n"), REQUEST_TIMEOUT)
            return "result" in json.loads(line)
        except (OSError, TimeoutError, asyncio.IncompleteReadError, ValueError):
            return False
        finally:
            if writer is not None:
                writer.close()
                with contextlib.suppress(OSError, asyncio.CancelledError):
                    await writer.wait_closed()

    # --- internals ------------------------------------------------------

    async def _run(self) -> None:
        """Connect, serve until the socket drops, then retry with backoff."""
        backoff = BACKOFF_START
        while True:
            try:
                await self._connect_and_serve()
                backoff = BACKOFF_START
            except asyncio.CancelledError:
                raise
            except (OSError, TimeoutError, SnapcastRpcError) as err:
                LOGGER.debug(
                    "Snapserver control connection to %s:%s failed: %s",
                    self.host,
                    self.port,
                    err,
                )
            except Exception:  # noqa: BLE001 - the loop must never die
                LOGGER.exception("Unexpected error on the Snapserver connection")
            finally:
                await self._teardown()

            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, BACKOFF_MAX)

    async def _connect_and_serve(self) -> None:
        """Open the socket, publish a baseline status, then read until EOF."""
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port, limit=READ_LIMIT),
            CONNECT_TIMEOUT,
        )
        self._writer = writer

        read_task = asyncio.create_task(self._read_loop(reader))
        resync_task: asyncio.Task[None] | None = None
        try:
            server = await self.async_get_status()
            self._set_connected(True)
            self._publish_status(server)
            LOGGER.info(
                "Connected to Snapserver control API at %s:%s", self.host, self.port
            )
            resync_task = asyncio.create_task(self._resync_loop())
            await read_task
        finally:
            for task in (resync_task, read_task):
                if task is not None and not task.done():
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task

    async def _read_loop(self, reader: asyncio.StreamReader) -> None:
        """Consume ndjson lines until the connection closes."""
        while True:
            try:
                line = await reader.readuntil(b"\n")
            except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, OSError):
                return
            if not line.strip():
                continue
            try:
                message = json.loads(line)
            except ValueError:
                LOGGER.debug("Discarding unparseable line from Snapserver: %r", line)
                continue
            # The spec permits batched responses.
            for item in message if isinstance(message, list) else [message]:
                if isinstance(item, dict):
                    self._handle_message(item)

    def _handle_message(self, message: dict[str, Any]) -> None:
        """Route one decoded message to a pending request or a notification."""
        if "method" in message:
            self._handle_notification(
                message["method"], message.get("params") or {}
            )
            return

        future = self._pending.get(message.get("id"))
        if future is None or future.done():
            return
        if "error" in message:
            error = message["error"]
            future.set_exception(
                SnapcastRpcError(
                    f"{error.get('message', 'RPC error')} ({error.get('code')})"
                )
            )
        else:
            future.set_result(message.get("result") or {})

    def _handle_notification(self, method: str, params: dict[str, Any]) -> None:
        """Handle a pushed notification."""
        if method in ("Client.OnConnect", "Client.OnDisconnect"):
            client = params.get("client")
            if isinstance(client, dict) and self._on_client:
                self._on_client(client)
            return

        if method == "Server.OnUpdate":
            server = params.get("server")
            if isinstance(server, dict):
                self._publish_status(server)
            return

        # Volume/latency/name/stream notifications carry only partial state, so
        # rather than merging each shape by hand, ask for a fresh full status.
        self._resync_event.set()

    async def _resync_loop(self) -> None:
        """Re-fetch full status periodically, and after partial notifications."""
        while True:
            try:
                async with asyncio.timeout(RESYNC_INTERVAL):
                    await self._resync_event.wait()
                # Coalesce bursts of notifications into a single refresh.
                await asyncio.sleep(RESYNC_DEBOUNCE)
            except TimeoutError:
                pass
            self._resync_event.clear()

            try:
                self._publish_status(await self.async_get_status())
            except SnapcastRpcError as err:
                # If the socket is really gone the read loop ends and _run
                # reconnects; nothing to do here but keep going.
                LOGGER.debug("Snapserver resync failed: %s", err)

    def _publish_status(self, server: dict[str, Any]) -> None:
        """Hand a full server object to the consumer."""
        if self._on_status:
            self._on_status(server)

    def _set_connected(self, connected: bool) -> None:
        """Update connection state and notify on transitions only."""
        if connected == self._connected:
            return
        self._connected = connected
        if self._on_connection_change:
            self._on_connection_change(connected)

    async def _teardown(self) -> None:
        """Close the socket and fail any in-flight requests."""
        await self._close_writer()
        self._set_connected(False)
        for future in list(self._pending.values()):
            if not future.done():
                future.set_exception(SnapcastRpcError("Connection lost"))
        self._pending.clear()

    async def _close_writer(self) -> None:
        """Close the stream writer if we have one."""
        writer, self._writer = self._writer, None
        if writer is None:
            return
        writer.close()
        with contextlib.suppress(OSError, asyncio.CancelledError):
            await writer.wait_closed()

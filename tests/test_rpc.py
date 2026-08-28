"""Functional tests for the Snapcast JSON-RPC client.

Runs against a fake ndjson server on localhost -- no Home Assistant and no real
Snapserver required, which is why rpc.py is kept free of HA imports.

Run: python3 tests/test_rpc.py
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import pathlib
import sys
import unittest

sys.path.insert(
    0,
    str(
        pathlib.Path(__file__).resolve().parent.parent
        / "custom_components"
        / "snapserver_control"
    ),
)

import rpc  # noqa: E402

# The documented Server.GetStatus payload, trimmed to two clients: one up, one
# down. Shapes copied from badaix/snapcast doc/json_rpc_api/control.md.
SERVER_STATUS = {
    "groups": [
        {
            "id": "4dcc4e3b-c699-a04b-7f0c-8260d23c43e1",
            "muted": False,
            "name": "",
            "stream_id": "TCP",
            "clients": [
                {
                    "config": {
                        "instance": 1,
                        "latency": 0,
                        "name": "Windows PC",
                        "volume": {"muted": False, "percent": 74},
                    },
                    "connected": True,
                    "host": {
                        "arch": "x86_64",
                        "ip": "192.168.1.42",
                        "mac": "00:21:6a:7d:74:fc",
                        "name": "WIN10",
                        "os": "Windows 10",
                    },
                    "id": "00:21:6a:7d:74:fc",
                    "lastSeen": {"sec": 1488026416, "usec": 135973},
                    "snapclient": {
                        "name": "Snapclient",
                        "protocolVersion": 2,
                        "version": "0.31.0",
                    },
                },
                {
                    "config": {
                        "instance": 1,
                        "latency": 10,
                        "name": "",
                        "volume": {"muted": True, "percent": 48},
                    },
                    "connected": False,
                    "host": {
                        "arch": "aarch64",
                        "ip": "192.168.1.55",
                        "mac": "b8:27:eb:00:11:22",
                        "name": "kitchen-pi",
                        "os": "Raspbian",
                    },
                    "id": "b8:27:eb:00:11:22",
                    "lastSeen": {"sec": 1488020000, "usec": 0},
                    "snapclient": {
                        "name": "Snapclient",
                        "protocolVersion": 2,
                        "version": "0.30.0",
                    },
                },
            ],
        }
    ],
    "server": {
        "host": {"arch": "x86_64", "ip": "", "mac": "", "name": "ha", "os": "HAOS"},
        "snapserver": {
            "controlProtocolVersion": 1,
            "name": "Snapserver",
            "protocolVersion": 1,
            "version": "0.31.0",
        },
    },
    "streams": [{"id": "TCP", "status": "playing"}],
}

WIN_CLIENT_ID = "00:21:6a:7d:74:fc"
PI_CLIENT_ID = "b8:27:eb:00:11:22"


class FakeSnapserver:
    """Minimal ndjson JSON-RPC server that speaks enough of the protocol."""

    def __init__(self) -> None:
        self.port = 0
        self.requests: list[dict] = []
        self.connection_count = 0
        self._server: asyncio.AbstractServer | None = None
        self._writers: list[asyncio.StreamWriter] = []
        self._connected = asyncio.Event()

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        self.drop_connections()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    def drop_connections(self) -> None:
        """Hang up on every connected client, as a restarting server would."""
        for writer in self._writers:
            writer.close()
        self._writers.clear()
        self._connected.clear()

    async def wait_connected(self) -> None:
        await asyncio.wait_for(self._connected.wait(), timeout=5)

    async def notify(self, method: str, params: dict) -> None:
        """Push a notification to every connected client."""
        line = (
            json.dumps({"jsonrpc": "2.0", "method": method, "params": params}) + "\n"
        ).encode()
        for writer in self._writers:
            writer.write(line)
            await writer.drain()

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self.connection_count += 1
        self._writers.append(writer)
        self._connected.set()
        try:
            while True:
                line = await reader.readuntil(b"\n")
                request = json.loads(line)
                self.requests.append(request)
                method = request.get("method")
                if method == "Server.GetStatus":
                    result = {"server": SERVER_STATUS}
                elif method == "Server.GetRPCVersion":
                    result = {"major": 2, "minor": 0, "patch": 0}
                elif method == "Server.DeleteClient":
                    result = {"server": SERVER_STATUS}
                else:
                    writer.write(
                        (
                            json.dumps(
                                {
                                    "id": request.get("id"),
                                    "jsonrpc": "2.0",
                                    "error": {
                                        "code": -32601,
                                        "message": "Method not found",
                                    },
                                }
                            )
                            + "\n"
                        ).encode()
                    )
                    await writer.drain()
                    continue

                writer.write(
                    (
                        json.dumps(
                            {
                                "id": request.get("id"),
                                "jsonrpc": "2.0",
                                "result": result,
                            }
                        )
                        + "\n"
                    ).encode()
                )
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionResetError, OSError):
            pass
        finally:
            if writer in self._writers:
                self._writers.remove(writer)
            # Python 3.12's Server.wait_closed() blocks until every connection
            # is closed, so the handler must close its own side too.
            writer.close()
            with contextlib.suppress(OSError, ConnectionResetError):
                await writer.wait_closed()


async def wait_until(predicate, timeout: float = 5.0) -> None:
    """Poll until predicate() is true or the timeout expires."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("Condition not met within timeout")


class TestParsing(unittest.TestCase):
    """Pure-function tests over the documented payload shapes."""

    def test_flatten_clients(self) -> None:
        clients = rpc.flatten_clients(SERVER_STATUS)

        self.assertEqual(set(clients), {WIN_CLIENT_ID, PI_CLIENT_ID})

        win = clients[WIN_CLIENT_ID]
        self.assertTrue(win["connected"])
        self.assertEqual(win["name"], "Windows PC")
        self.assertEqual(win["ip"], "192.168.1.42")
        self.assertEqual(win["version"], "0.31.0")
        self.assertEqual(win["volume_percent"], 74)
        self.assertFalse(win["muted"])
        self.assertEqual(win["stream_id"], "TCP")
        self.assertEqual(win["group_id"], "4dcc4e3b-c699-a04b-7f0c-8260d23c43e1")
        self.assertAlmostEqual(win["last_seen"], 1488026416.135973, places=3)

        pi = clients[PI_CLIENT_ID]
        self.assertFalse(pi["connected"])
        # config.name is empty, so the hostname is used as the display name.
        self.assertEqual(pi["name"], "kitchen-pi")

    def test_never_seen_client_has_no_timestamp(self) -> None:
        client = rpc.normalize_client(
            {"id": "aa:bb", "connected": False, "lastSeen": {"sec": 0, "usec": 0}}
        )
        self.assertIsNone(client["last_seen"])
        # Falls back to the id when neither a name nor a hostname is available.
        self.assertEqual(client["name"], "aa:bb")

    def test_parse_streams(self) -> None:
        self.assertEqual(
            rpc.parse_streams(SERVER_STATUS), [{"id": "TCP", "status": "playing"}]
        )


class TestRpcClient(unittest.IsolatedAsyncioTestCase):
    """End-to-end tests against the fake server."""

    async def asyncSetUp(self) -> None:
        # Keep the reconnect test fast.
        self._orig_backoff = rpc.BACKOFF_START
        rpc.BACKOFF_START = 0.05

        self.server = FakeSnapserver()
        await self.server.start()

        self.statuses: list[dict] = []
        self.client_updates: list[dict] = []
        self.connection_events: list[bool] = []

        self.client = rpc.SnapcastRpcClient(
            "127.0.0.1",
            self.server.port,
            on_status=self.statuses.append,
            on_client=self.client_updates.append,
            on_connection_change=self.connection_events.append,
        )

    async def asyncTearDown(self) -> None:
        await self.client.async_stop()
        await self.server.stop()
        rpc.BACKOFF_START = self._orig_backoff

    async def test_baseline_status_on_connect(self) -> None:
        await self.client.async_start()
        await wait_until(lambda: bool(self.statuses))

        self.assertTrue(self.client.connected)
        self.assertEqual(self.connection_events, [True])

        methods = [request["method"] for request in self.server.requests]
        self.assertIn("Server.GetStatus", methods)
        # Requests must carry a jsonrpc version and an id to match responses on.
        first = self.server.requests[0]
        self.assertEqual(first["jsonrpc"], "2.0")
        self.assertIsInstance(first["id"], int)

        clients = rpc.flatten_clients(self.statuses[0])
        self.assertTrue(clients[WIN_CLIENT_ID]["connected"])

    async def test_disconnect_notification_flips_state(self) -> None:
        await self.client.async_start()
        await wait_until(lambda: bool(self.statuses))

        dead = json.loads(json.dumps(SERVER_STATUS["groups"][0]["clients"][0]))
        dead["connected"] = False
        await self.server.notify("Client.OnDisconnect", {"client": dead, "id": dead["id"]})

        await wait_until(lambda: bool(self.client_updates))
        pushed = rpc.normalize_client(self.client_updates[0])
        self.assertEqual(pushed["id"], WIN_CLIENT_ID)
        self.assertFalse(pushed["connected"])

    async def test_partial_notification_triggers_resync(self) -> None:
        await self.client.async_start()
        await wait_until(lambda: bool(self.statuses))
        before = len(self.statuses)

        # Volume changes carry no full client object, so the client should ask
        # for a fresh status rather than trying to merge a partial shape.
        await self.server.notify(
            "Client.OnVolumeChanged",
            {"id": WIN_CLIENT_ID, "volume": {"muted": False, "percent": 20}},
        )
        await wait_until(lambda: len(self.statuses) > before)

    async def test_reconnects_after_connection_drop(self) -> None:
        await self.client.async_start()
        await self.server.wait_connected()
        await wait_until(lambda: bool(self.statuses))

        self.server.drop_connections()

        # Goes offline, then comes back and republishes a baseline status.
        await wait_until(lambda: self.connection_events[-1] is False)
        await wait_until(lambda: self.server.connection_count >= 2)
        await wait_until(lambda: self.client.connected)
        await wait_until(lambda: len(self.statuses) >= 2)

    async def test_delete_client(self) -> None:
        await self.client.async_start()
        await wait_until(lambda: bool(self.statuses))

        await self.client.async_delete_client(PI_CLIENT_ID)

        deletes = [
            request
            for request in self.server.requests
            if request["method"] == "Server.DeleteClient"
        ]
        self.assertEqual(deletes[0]["params"], {"id": PI_CLIENT_ID})

    async def test_rpc_error_is_raised(self) -> None:
        await self.client.async_start()
        await wait_until(lambda: bool(self.statuses))

        with self.assertRaises(rpc.SnapcastRpcError):
            await self.client.async_request("Server.NoSuchMethod")

    async def test_test_connection(self) -> None:
        self.assertTrue(
            await rpc.SnapcastRpcClient.async_test_connection(
                "127.0.0.1", self.server.port
            )
        )

    async def test_test_connection_fails_on_closed_port(self) -> None:
        await self.server.stop()
        self.assertFalse(
            await rpc.SnapcastRpcClient.async_test_connection(
                "127.0.0.1", self.server.port
            )
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

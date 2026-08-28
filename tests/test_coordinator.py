"""Tests for the coordinator's client-state merging.

Home Assistant isn't installed in this repo's dev environment, so the base
DataUpdateCoordinator is stubbed with a minimal stand-in. That means these tests
prove *our* merge logic, not that the integration loads inside HA -- which is
what the structural checks in test_companion.sh cover.

Run: python3 tests/test_coordinator.py
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
COMPONENT = REPO / "custom_components" / "snapserver_control"

sys.path.insert(0, str(REPO / "tests"))


def _install_homeassistant_stubs() -> None:
    """Register just enough of Home Assistant for coordinator.py to import."""

    class DataUpdateCoordinator:
        """Stand-in mirroring the parts of the real coordinator we rely on."""

        # The real class is generic: DataUpdateCoordinator[SnapserverData].
        def __class_getitem__(cls, _item):
            return cls

        def __init__(
            self,
            hass,
            logger,
            *,
            name=None,
            config_entry=None,
            update_interval=None,
        ) -> None:
            self.hass = hass
            self.logger = logger
            self.name = name
            self.config_entry = config_entry
            self.update_interval = update_interval
            self.data = None
            self._listeners: list = []

        def async_set_updated_data(self, data) -> None:
            self.data = data
            for listener in list(self._listeners):
                listener()

        def async_add_listener(self, listener):
            self._listeners.append(listener)
            return lambda: self._listeners.remove(listener)

    homeassistant = types.ModuleType("homeassistant")
    homeassistant.__path__ = []

    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = object
    core.callback = lambda func: func

    config_entries = types.ModuleType("homeassistant.config_entries")
    config_entries.ConfigEntry = object

    helpers = types.ModuleType("homeassistant.helpers")
    helpers.__path__ = []

    update_coordinator = types.ModuleType("homeassistant.helpers.update_coordinator")
    update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator

    for name, module in {
        "homeassistant": homeassistant,
        "homeassistant.core": core,
        "homeassistant.config_entries": config_entries,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.update_coordinator": update_coordinator,
    }.items():
        sys.modules[name] = module


def _load_coordinator_module():
    """Import coordinator.py without executing the package's __init__.py."""
    package = types.ModuleType("sscontrol")
    package.__path__ = [str(COMPONENT)]
    sys.modules["sscontrol"] = package

    spec = importlib.util.spec_from_file_location(
        "sscontrol.coordinator", COMPONENT / "coordinator.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_install_homeassistant_stubs()
coordinator_module = _load_coordinator_module()

from test_rpc import PI_CLIENT_ID, SERVER_STATUS, WIN_CLIENT_ID  # noqa: E402

SnapserverCoordinator = coordinator_module.SnapserverCoordinator


def make_coordinator():
    """Build a coordinator with no live connection."""
    return SnapserverCoordinator(hass=object(), entry=object(), host="h", port=1705)


def disconnected_win_client() -> dict:
    """Return the Windows client as a disconnect notification would carry it."""
    raw = SERVER_STATUS["groups"][0]["clients"][0]
    return {
        **raw,
        "connected": False,
        "lastSeen": {"sec": 1488030000, "usec": 0},
    }


class TestCoordinator(unittest.TestCase):
    def setUp(self) -> None:
        self.coordinator = make_coordinator()

    def test_starts_empty_and_offline(self) -> None:
        self.assertEqual(self.coordinator.data.clients, {})
        self.assertFalse(self.coordinator.data.online)

    def test_status_populates_clients_and_streams(self) -> None:
        self.coordinator._handle_status(SERVER_STATUS)
        data = self.coordinator.data

        self.assertTrue(data.online)
        self.assertEqual(set(data.clients), {WIN_CLIENT_ID, PI_CLIENT_ID})
        self.assertEqual(data.streams, [{"id": "TCP", "status": "playing"}])

    def test_client_notification_keeps_group_context(self) -> None:
        self.coordinator._handle_status(SERVER_STATUS)

        self.coordinator._handle_client(disconnected_win_client())
        client = self.coordinator.data.clients[WIN_CLIENT_ID]

        self.assertFalse(client["connected"])
        # The notification carries no group, so the last known one must survive;
        # otherwise the client would appear to leave its stream when it dies.
        self.assertEqual(client["stream_id"], "TCP")
        self.assertEqual(client["group_id"], "4dcc4e3b-c699-a04b-7f0c-8260d23c43e1")
        # Other clients are untouched.
        self.assertIn(PI_CLIENT_ID, self.coordinator.data.clients)

    def test_client_notification_without_id_is_ignored(self) -> None:
        self.coordinator._handle_status(SERVER_STATUS)
        before = self.coordinator.data

        self.coordinator._handle_client({"connected": False})

        self.assertIs(self.coordinator.data, before)

    def test_losing_connection_keeps_last_known_clients(self) -> None:
        self.coordinator._handle_status(SERVER_STATUS)

        self.coordinator._handle_connection_change(False)
        data = self.coordinator.data

        # A server restart must not look like every client dying.
        self.assertFalse(data.online)
        self.assertEqual(set(data.clients), {WIN_CLIENT_ID, PI_CLIENT_ID})
        self.assertTrue(data.clients[WIN_CLIENT_ID]["connected"])

    def test_listeners_are_notified(self) -> None:
        calls = []
        self.coordinator.async_add_listener(lambda: calls.append(self.coordinator.data))

        self.coordinator._handle_status(SERVER_STATUS)
        self.coordinator._handle_client(disconnected_win_client())
        self.coordinator._handle_connection_change(False)

        self.assertEqual(len(calls), 3)

    def test_new_client_appears_from_notification(self) -> None:
        self.coordinator._handle_status(SERVER_STATUS)

        self.coordinator._handle_client(
            {
                "id": "aa:bb:cc:dd:ee:ff",
                "connected": True,
                "config": {"name": "Study", "volume": {"percent": 50, "muted": False}},
                "host": {"ip": "192.168.1.99", "name": "study"},
                "snapclient": {"version": "0.31.0"},
                "lastSeen": {"sec": 1488030000, "usec": 0},
            }
        )

        client = self.coordinator.data.clients["aa:bb:cc:dd:ee:ff"]
        self.assertEqual(client["name"], "Study")
        self.assertTrue(client["connected"])
        # Nothing is known about its grouping until the next full status.
        self.assertIsNone(client["group_id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Regression tests for the Music Assistant URL/port bug.

A real user hit this: the config flow prefilled MA's URL from Home Assistant's
own music_assistant integration entry, which is frequently the HA-Ingress
address (port 8094) — a listener that requires Supervisor-injected
X-Remote-User-* headers and has NO Bearer-token fallback at all
(music-assistant/server auth_middleware.py get_authenticated_user). Every
token, however valid, was rejected there as unauthenticated. The fix rewrites
that one known-bad port to the real API port (8095) and fails fast, with a
specific message, if a user manually enters the ingress port — instead of the
generic "token rejected" message that sent them chasing the wrong thing.

Home Assistant and voluptuous aren't installed in this dev environment, so
both are stubbed; only _ma_defaults and _validate_ma (plain module-level
functions, not the ConfigFlow class itself) are exercised.

Run: python tests/test_config_flow.py
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
COMPONENT = REPO / "custom_components" / "snapserver_control"


def _install_stubs() -> None:
    aiohttp_stub = types.ModuleType("aiohttp")

    class _ClientTimeout:
        def __init__(self, total=None) -> None:
            self.total = total

    aiohttp_stub.ClientTimeout = _ClientTimeout
    aiohttp_stub.ClientError = type("ClientError", (Exception,), {})

    voluptuous_stub = types.ModuleType("voluptuous")
    voluptuous_stub.Schema = lambda *a, **k: None
    voluptuous_stub.Required = lambda *a, **k: None
    voluptuous_stub.Optional = lambda *a, **k: None
    voluptuous_stub.Coerce = lambda *a, **k: None

    homeassistant = types.ModuleType("homeassistant")
    homeassistant.__path__ = []

    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = object
    core.callback = lambda func: func

    const_mod = types.ModuleType("homeassistant.const")
    const_mod.CONF_TOKEN = "token"
    const_mod.CONF_URL = "url"

    config_entries_mod = types.ModuleType("homeassistant.config_entries")

    class _ConfigFlow:
        def __init_subclass__(cls, *, domain=None, **kwargs) -> None:
            super().__init_subclass__(**kwargs)

    class _OptionsFlow:
        pass

    config_entries_mod.ConfigEntry = object
    config_entries_mod.ConfigFlow = _ConfigFlow
    config_entries_mod.ConfigFlowResult = dict
    config_entries_mod.OptionsFlow = _OptionsFlow

    helpers = types.ModuleType("homeassistant.helpers")
    helpers.__path__ = []

    aiohttp_client_mod = types.ModuleType("homeassistant.helpers.aiohttp_client")
    aiohttp_client_mod.async_get_clientsession = lambda hass: None

    for name, module in {
        "aiohttp": aiohttp_stub,
        "voluptuous": voluptuous_stub,
        "homeassistant": homeassistant,
        "homeassistant.core": core,
        "homeassistant.const": const_mod,
        "homeassistant.config_entries": config_entries_mod,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.aiohttp_client": aiohttp_client_mod,
    }.items():
        sys.modules[name] = module

    package = types.ModuleType("sscontrol")
    package.__path__ = [str(COMPONENT)]
    sys.modules["sscontrol"] = package

    rpc_stub = types.ModuleType("sscontrol.rpc")

    class _SnapcastRpcClient:
        @staticmethod
        async def async_test_connection(host, port):
            return True

    rpc_stub.SnapcastRpcClient = _SnapcastRpcClient
    sys.modules["sscontrol.rpc"] = rpc_stub

    supervisor_stub = types.ModuleType("sscontrol.supervisor")
    supervisor_stub.SupervisorClient = object
    sys.modules["sscontrol.supervisor"] = supervisor_stub


def _load(module_name: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(
        f"sscontrol.{module_name}", COMPONENT / f"{module_name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_install_stubs()
# The real ma_client is used unmodified — it's already HA-free and tested.
ma_client_module = _load("ma_client")
config_flow_module = _load("config_flow")


class FakeMaEntry:
    def __init__(self, url: str, token: str = "") -> None:
        self.data = {"url": url, "token": token}


class FakeConfigEntries:
    def __init__(self, entries: list[FakeMaEntry]) -> None:
        self._entries = entries

    def async_entries(self, domain: str) -> list[FakeMaEntry]:
        return list(self._entries)


class FakeHass:
    def __init__(self, entries: list[FakeMaEntry]) -> None:
        self.config_entries = FakeConfigEntries(entries)


class TestMaDefaults(unittest.TestCase):
    def test_rewrites_the_ingress_port_to_the_api_port(self) -> None:
        hass = FakeHass(
            [FakeMaEntry("http://d5369777-music-assistant:8094", "auto-minted-token")]
        )

        url, token = config_flow_module._ma_defaults(hass)

        self.assertEqual(url, "http://d5369777-music-assistant:8095")

    def test_never_prefills_the_auto_minted_token(self) -> None:
        """That token is always SERVICE-role and always fails the write probe."""
        hass = FakeHass(
            [FakeMaEntry("http://d5369777-music-assistant:8094", "auto-minted-token")]
        )

        _url, token = config_flow_module._ma_defaults(hass)

        self.assertEqual(token, "")

    def test_leaves_a_non_ingress_port_untouched(self) -> None:
        hass = FakeHass([FakeMaEntry("http://192.168.1.34:8095")])

        url, _token = config_flow_module._ma_defaults(hass)

        self.assertEqual(url, "http://192.168.1.34:8095")

    def test_leaves_a_custom_port_untouched(self) -> None:
        hass = FakeHass([FakeMaEntry("http://ma.example.local:9000")])

        url, _token = config_flow_module._ma_defaults(hass)

        self.assertEqual(url, "http://ma.example.local:9000")

    def test_falls_back_when_no_ma_integration_is_configured(self) -> None:
        hass = FakeHass([])

        url, token = config_flow_module._ma_defaults(hass)

        self.assertEqual(url, config_flow_module.DEFAULT_MA_URL)
        self.assertEqual(token, "")


class TestValidateMaFailsFastOnIngressPort(unittest.IsolatedAsyncioTestCase):
    async def test_ingress_port_is_rejected_before_any_network_call(self) -> None:
        # async_get_clientsession is stubbed to return None; if _validate_ma
        # tried to actually use it, this would raise instead of returning
        # cleanly -- so a clean return here proves the fast-fail path ran.
        error, placeholders = await config_flow_module._validate_ma(
            FakeHass([]), "http://d5369777-music-assistant:8094", "any-token-at-all"
        )

        self.assertEqual(error, "ma_url_is_ingress_port")
        self.assertEqual(placeholders, {"port": "8095"})


if __name__ == "__main__":
    unittest.main(verbosity=2)

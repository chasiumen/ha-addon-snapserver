"""Functional tests for the Music Assistant API client.

Runs against a fake aiohttp session — no Home Assistant, no aiohttp, and no
real MA server required, which is why ma_client.py is kept free of HA imports.

Run: python tests/test_ma_client.py
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
COMPONENT = REPO / "custom_components" / "snapserver_control"

# ma_client imports aiohttp (absent in this dev env) only for ClientTimeout;
# stub the module before importing it.
_aiohttp = types.ModuleType("aiohttp")


class _ClientTimeout:
    def __init__(self, total=None) -> None:
        self.total = total


class _ClientError(Exception):
    pass


_aiohttp.ClientTimeout = _ClientTimeout
_aiohttp.ClientError = _ClientError
sys.modules.setdefault("aiohttp", _aiohttp)

_spec = importlib.util.spec_from_file_location("ma_client", COMPONENT / "ma_client.py")
ma_client = importlib.util.module_from_spec(_spec)
sys.modules["ma_client"] = ma_client
_spec.loader.exec_module(ma_client)


class FakeResponse:
    """One canned HTTP response, usable as an async context manager."""

    def __init__(self, status=200, json_body=None, text_body="") -> None:
        self.status = status
        self._json = json_body
        self._text = text_body

    async def json(self):
        return self._json

    async def text(self):
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    """Records every post() and replays queued responses in order."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.responses: list[FakeResponse] = []

    def queue(self, *responses: FakeResponse) -> None:
        self.responses.extend(responses)

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append(
            {"url": url, "json": json, "headers": headers, "timeout": timeout}
        )
        if not self.responses:
            raise AssertionError("FakeSession ran out of queued responses")
        return self.responses.pop(0)


INSTANCE_ID = "snapcast--abc123"

PROVIDER_LIST = [
    # Extra keys and an unrelated provider must be tolerated.
    {"instance_id": "spotify--x", "domain": "spotify", "name": "Spotify"},
    {"instance_id": INSTANCE_ID, "domain": "snapcast", "name": "Snapcast", "type": "player"},
]


def make_client(session: FakeSession, url: str = "http://ha.local:8095"):
    return ma_client.MusicAssistantClient(url, "tok3n", session)


class TestCommandTransport(unittest.IsolatedAsyncioTestCase):
    async def test_request_shape(self) -> None:
        session = FakeSession()
        session.queue(FakeResponse(json_body=[]))
        client = make_client(session)

        await client._command("config/providers", {"provider_domain": "snapcast"})

        call = session.calls[0]
        self.assertEqual(call["url"], "http://ha.local:8095/api")
        self.assertEqual(call["headers"], {"Authorization": "Bearer tok3n"})
        body = call["json"]
        self.assertEqual(body["command"], "config/providers")
        self.assertEqual(body["args"], {"provider_domain": "snapcast"})
        self.assertIsInstance(body["message_id"], str)

    async def test_trailing_slash_url_normalized(self) -> None:
        session = FakeSession()
        session.queue(FakeResponse(json_body=None))
        client = make_client(session, url="http://ha.local:8095/")

        await client._command("x")

        self.assertEqual(session.calls[0]["url"], "http://ha.local:8095/api")

    async def test_200_returns_parsed_json_as_is(self) -> None:
        session = FakeSession()
        session.queue(FakeResponse(json_body={"a": 1}))

        result = await make_client(session)._command("x")

        self.assertEqual(result, {"a": 1})

    async def test_401_raises_auth_error(self) -> None:
        session = FakeSession()
        session.queue(FakeResponse(status=401, text_body="Authentication required"))

        with self.assertRaises(ma_client.MusicAssistantAuthError):
            await make_client(session)._command("x")

    async def test_403_raises_scope_error(self) -> None:
        session = FakeSession()
        session.queue(FakeResponse(status=403, text_body="requires the scope"))

        with self.assertRaises(ma_client.MusicAssistantScopeError):
            await make_client(session)._command("x")

    async def test_500_raises_api_error_with_status(self) -> None:
        session = FakeSession()
        session.queue(FakeResponse(status=500, text_body="Internal server error"))

        with self.assertRaises(ma_client.MusicAssistantApiError) as ctx:
            await make_client(session)._command("x")
        self.assertEqual(ctx.exception.status, 500)

    async def test_read_and_save_timeouts_differ(self) -> None:
        session = FakeSession()
        session.queue(FakeResponse(json_body=None), FakeResponse(json_body={}))
        client = make_client(session)

        await client.get_value(INSTANCE_ID, "k")
        await client.save_snapcast_config(INSTANCE_ID, {"k": 1})

        read_timeout, save_timeout = (c["timeout"].total for c in session.calls)
        self.assertEqual(read_timeout, ma_client.READ_TIMEOUT)
        self.assertEqual(save_timeout, ma_client.SAVE_TIMEOUT)
        self.assertGreater(save_timeout, read_timeout)


class TestCommands(unittest.IsolatedAsyncioTestCase):
    async def test_get_instance_id_filters_domain(self) -> None:
        session = FakeSession()
        session.queue(FakeResponse(json_body=PROVIDER_LIST))
        client = make_client(session)

        instance_id = await client.get_snapcast_instance_id()

        self.assertEqual(instance_id, INSTANCE_ID)
        self.assertEqual(
            session.calls[0]["json"]["args"], {"provider_domain": "snapcast"}
        )

    async def test_get_instance_id_raises_when_absent(self) -> None:
        session = FakeSession()
        session.queue(FakeResponse(json_body=[{"instance_id": "x", "domain": "sonos"}]))

        with self.assertRaises(ma_client.MusicAssistantApiError):
            await make_client(session).get_snapcast_instance_id()

    async def test_get_instance_id_rejects_non_list(self) -> None:
        session = FakeSession()
        session.queue(FakeResponse(json_body={"oops": True}))

        with self.assertRaises(ma_client.MusicAssistantApiError):
            await make_client(session).get_snapcast_instance_id()

    async def test_save_arg_shape(self) -> None:
        session = FakeSession()
        session.queue(FakeResponse(json_body={}))
        client = make_client(session)

        await client.save_snapcast_config(INSTANCE_ID, {"a": 1})

        args = session.calls[0]["json"]["args"]
        self.assertEqual(
            args,
            {"provider_domain": "snapcast", "instance_id": INSTANCE_ID, "values": {"a": 1}},
        )

    async def test_probe_true_on_200(self) -> None:
        session = FakeSession()
        session.queue(FakeResponse(json_body=48000), FakeResponse(json_body={}))
        client = make_client(session)

        self.assertTrue(await client.probe_write_access(INSTANCE_ID))
        # It must save back exactly the value it read.
        self.assertEqual(
            session.calls[1]["json"]["args"]["values"],
            {ma_client.KEY_SAMPLE_RATE: 48000},
        )

    async def test_probe_false_on_403(self) -> None:
        session = FakeSession()
        session.queue(FakeResponse(json_body=48000), FakeResponse(status=403))

        self.assertFalse(await make_client(session).probe_write_access(INSTANCE_ID))

    async def test_probe_reraises_401(self) -> None:
        session = FakeSession()
        session.queue(FakeResponse(json_body=48000), FakeResponse(status=401))

        with self.assertRaises(ma_client.MusicAssistantAuthError):
            await make_client(session).probe_write_access(INSTANCE_ID)

    async def test_verify_values_match(self) -> None:
        session = FakeSession()
        session.queue(FakeResponse(json_body=96000), FakeResponse(json_body=16))
        client = make_client(session)

        mismatches = await client.verify_values(
            INSTANCE_ID, {ma_client.KEY_SAMPLE_RATE: 96000, ma_client.KEY_BIT_DEPTH: 16}
        )

        self.assertEqual(mismatches, {})

    async def test_verify_values_reports_actual(self) -> None:
        session = FakeSession()
        session.queue(FakeResponse(json_body=48000))
        client = make_client(session)

        mismatches = await client.verify_values(
            INSTANCE_ID, {ma_client.KEY_SAMPLE_RATE: 96000}
        )

        self.assertEqual(mismatches, {ma_client.KEY_SAMPLE_RATE: 48000})


class TestApplySampleformat(unittest.IsolatedAsyncioTestCase):
    async def test_apply_sends_all_five_keys_then_verifies(self) -> None:
        session = FakeSession()
        session.queue(
            FakeResponse(json_body={}),      # save
            FakeResponse(json_body=96000),   # readback rate
            FakeResponse(json_body=16),      # readback depth
        )
        client = make_client(session)

        await client.apply_sampleformat(INSTANCE_ID, 96000)

        values = session.calls[0]["json"]["args"]["values"]
        self.assertEqual(
            values,
            {
                ma_client.KEY_SAMPLE_RATE: 96000,
                ma_client.KEY_BIT_DEPTH: 16,
                ma_client.KEY_USE_EXTERNAL: True,
                ma_client.KEY_HOST: "127.0.0.1",
                ma_client.KEY_PORT: 1705,
            },
        )
        # 24-bit must never be sent: snapserver <= 0.35.0 lacks packed_s24le.
        self.assertEqual(values[ma_client.KEY_BIT_DEPTH], 16)

    async def test_apply_raises_when_readback_mismatches(self) -> None:
        session = FakeSession()
        session.queue(
            FakeResponse(json_body={}),      # save "succeeds"
            FakeResponse(json_body=48000),   # ...but the rate did not take
            FakeResponse(json_body=16),
        )

        with self.assertRaises(ma_client.MusicAssistantApiError) as ctx:
            await make_client(session).apply_sampleformat(INSTANCE_ID, 96000)
        self.assertIn("did not accept", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)

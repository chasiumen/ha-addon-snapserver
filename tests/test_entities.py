"""Functional tests for the select and number entities.

Home Assistant isn't installed in this repo's dev environment, so the HA base
classes are stubbed and the modules are imported under a synthetic package name
to avoid executing the HA-heavy __init__.py. That means these tests prove *our*
logic — the option-update call sequences — not that the entities load inside HA.

The split under test (see docs/PLAN_ma_sampleformat.md):
- codec + buffer write the ADDON's config via the Supervisor and restart it;
- sample format writes MUSIC ASSISTANT's provider config via ma_client and
  must NOT touch the Supervisor at all.

Run: python tests/test_entities.py
"""

from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys
import types
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
COMPONENT = REPO / "custom_components" / "snapserver_control"


class FakeSupervisorClient:
    """Records the Supervisor calls each entity makes, in order."""

    def __init__(self, options: dict | None = None) -> None:
        self.options = options if options is not None else {
            "codec": "flac",
            "buffer_ms": 1000,
            "sampleformat": "48000:16:2",
            "snapweb_enabled": True,
            "librespot_enabled": False,
            "librespot_name": "Snapserver",
            "librespot_bitrate": 320,
            "initial_volume": 100,
        }
        self.calls: list[tuple] = []

    async def get_addon_options(self) -> dict:
        self.calls.append(("get",))
        return dict(self.options)

    async def set_addon_options(self, options: dict) -> None:
        self.calls.append(("set", dict(options)))
        self.options = dict(options)

    async def restart_addon(self) -> None:
        self.calls.append(("restart",))

    @property
    def call_names(self) -> list[str]:
        return [call[0] for call in self.calls]

    @property
    def last_set(self) -> dict:
        for name, *rest in reversed(self.calls):
            if name == "set":
                return rest[0]
        raise AssertionError("set_addon_options was never called")


def _install_stubs() -> tuple[types.ModuleType, types.ModuleType]:
    """Register minimal HA stand-ins plus fake supervisor/resume modules."""

    class _BaseEntity:
        """Stand-in for the HA entity bases we inherit from."""

        def async_write_ha_state(self) -> None:
            """No-op; HA would push state to the state machine here."""

    class NumberMode:
        SLIDER = "slider"

    # ma_client imports aiohttp only for ClientTimeout; stub it.
    aiohttp_stub = types.ModuleType("aiohttp")

    class _ClientTimeout:
        def __init__(self, total=None) -> None:
            self.total = total

    aiohttp_stub.ClientTimeout = _ClientTimeout
    aiohttp_stub.ClientError = type("ClientError", (Exception,), {})

    homeassistant = types.ModuleType("homeassistant")
    homeassistant.__path__ = []

    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = object
    core.callback = lambda func: func

    exceptions = types.ModuleType("homeassistant.exceptions")
    exceptions.HomeAssistantError = type("HomeAssistantError", (Exception,), {})

    components = types.ModuleType("homeassistant.components")
    components.__path__ = []

    select_mod = types.ModuleType("homeassistant.components.select")
    select_mod.SelectEntity = _BaseEntity

    number_mod = types.ModuleType("homeassistant.components.number")
    number_mod.NumberEntity = _BaseEntity
    number_mod.NumberMode = NumberMode

    helpers = types.ModuleType("homeassistant.helpers")
    helpers.__path__ = []

    device_registry = types.ModuleType("homeassistant.helpers.device_registry")
    device_registry.DeviceInfo = dict
    device_registry.CONNECTION_NETWORK_MAC = "mac"

    entity_platform = types.ModuleType("homeassistant.helpers.entity_platform")
    entity_platform.AddConfigEntryEntitiesCallback = object

    for name, module in {
        "aiohttp": aiohttp_stub,
        "homeassistant": homeassistant,
        "homeassistant.core": core,
        "homeassistant.exceptions": exceptions,
        "homeassistant.components": components,
        "homeassistant.components.select": select_mod,
        "homeassistant.components.number": number_mod,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.device_registry": device_registry,
        "homeassistant.helpers.entity_platform": entity_platform,
    }.items():
        sys.modules[name] = module

    # Synthetic parent package: lets the modules' relative imports resolve
    # without executing the real __init__.py (which pulls in http/frontend).
    package = types.ModuleType("sscontrol")
    package.__path__ = [str(COMPONENT)]
    package.SnapserverControlConfigEntry = object
    sys.modules["sscontrol"] = package

    # Stub the supervisor module so the entities talk to our recorder.
    supervisor = types.ModuleType("sscontrol.supervisor")
    supervisor.SupervisorClient = FakeSupervisorClient
    supervisor.SupervisorApiError = RuntimeError
    sys.modules["sscontrol.supervisor"] = supervisor

    # Fake resume module (the real one imports HA's entity registry). It
    # records calls and returns a preset "currently playing" list.
    resume = types.ModuleType("sscontrol.resume")
    resume.playing = []
    resume.snapshot_calls = []
    resume.resume_calls = []

    def snapshot_playing_players(hass):
        resume.snapshot_calls.append(hass)
        return list(resume.playing)

    async def resume_players(hass, entity_ids):
        resume.resume_calls.append(list(entity_ids))

    resume.snapshot_playing_players = snapshot_playing_players
    resume.resume_players = resume_players
    sys.modules["sscontrol.resume"] = resume

    return exceptions, resume


def _load(module_name: str) -> types.ModuleType:
    """Import one component module under the synthetic package."""
    spec = importlib.util.spec_from_file_location(
        f"sscontrol.{module_name}", COMPONENT / f"{module_name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


exceptions_module, resume_stub = _install_stubs()
HomeAssistantError = exceptions_module.HomeAssistantError
# The real ma_client loads fine (aiohttp stubbed) and select.py imports its
# error classes, so entity tests can raise the genuine exception types.
ma_client_module = _load("ma_client")
select_module = _load("select")
number_module = _load("number")
const_module = _load("const")

INSTANCE_ID = "snapcast--abc123"


class FakeMaClient:
    """Duck-typed stand-in for MusicAssistantClient."""

    def __init__(self, rate: int = 48000, depth: int = 16) -> None:
        self.values = {
            ma_client_module.KEY_SAMPLE_RATE: rate,
            ma_client_module.KEY_BIT_DEPTH: depth,
        }
        self.apply_calls: list[tuple[str, int]] = []
        self.apply_error: Exception | None = None
        self.timeline: list[str] = []

    async def get_value(self, instance_id: str, key: str):
        return self.values.get(key)

    async def apply_sampleformat(self, instance_id: str, rate: int) -> None:
        self.timeline.append("apply")
        if self.apply_error is not None:
            raise self.apply_error
        self.apply_calls.append((instance_id, rate))


class FakeHass:
    """Just enough of hass for the sampleformat entity."""

    def __init__(self) -> None:
        self.created_tasks: list = []

    def async_create_task(self, coro):
        self.created_tasks.append(coro)
        return asyncio.get_event_loop().create_task(coro)


def make_entry(
    client: FakeSupervisorClient,
    ma: FakeMaClient | None = None,
    ma_instance_id: str | None = None,
) -> types.SimpleNamespace:
    """Build a stand-in config entry carrying our fakes."""
    return types.SimpleNamespace(
        entry_id="testentry",
        runtime_data=types.SimpleNamespace(
            supervisor=client, ma=ma, ma_instance_id=ma_instance_id
        ),
    )


def make_sampleformat_entity(
    ma: FakeMaClient | None,
    instance_id: str | None = INSTANCE_ID,
    current: str | None = "48000:16:2",
):
    entry = make_entry(FakeSupervisorClient(), ma, instance_id)
    entity = select_module.SnapserverSampleformatSelect(entry, ma, instance_id, current)
    entity.hass = FakeHass()
    return entity


class TestCodecSelect(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.client = FakeSupervisorClient()
        self.entry = make_entry(self.client)

    async def test_codec_change_writes_option_then_restarts(self) -> None:
        entity = select_module.SnapserverCodecSelect(self.entry, self.client, "flac")

        await entity.async_select_option("opus")

        # Order matters: read current options, write the change, then restart.
        self.assertEqual(self.client.call_names, ["get", "set", "restart"])
        self.assertEqual(self.client.last_set["codec"], "opus")
        self.assertEqual(entity._attr_current_option, "opus")

    async def test_codec_change_preserves_every_other_option(self) -> None:
        """A partial write would wipe unrelated addon settings on restart."""
        before = dict(self.client.options)

        entity = select_module.SnapserverCodecSelect(self.entry, self.client, "flac")
        await entity.async_select_option("pcm")

        written = self.client.last_set
        self.assertEqual(set(written), set(before))
        for key, value in before.items():
            if key != "codec":
                self.assertEqual(written[key], value, f"{key} was altered")

    async def test_codec_options_match_const(self) -> None:
        entity = select_module.SnapserverCodecSelect(self.entry, self.client, "flac")
        self.assertEqual(entity._attr_options, const_module.CODEC_OPTIONS)


class TestSampleformatSelect(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        resume_stub.playing = []
        resume_stub.snapshot_calls.clear()
        resume_stub.resume_calls.clear()

    async def test_change_calls_ma_not_supervisor(self) -> None:
        ma = FakeMaClient()
        supervisor = FakeSupervisorClient()
        entry = make_entry(supervisor, ma, INSTANCE_ID)
        entity = select_module.SnapserverSampleformatSelect(
            entry, ma, INSTANCE_ID, "48000:16:2"
        )
        entity.hass = FakeHass()

        await entity.async_select_option("96000:16:2")

        self.assertEqual(ma.apply_calls, [(INSTANCE_ID, 96000)])
        # The whole point of the rework: the Supervisor is never touched and
        # the addon is never restarted on this path.
        self.assertEqual(supervisor.calls, [])
        self.assertEqual(entity._attr_current_option, "96000:16:2")

    async def test_apply_failure_raises_and_keeps_state(self) -> None:
        ma = FakeMaClient()
        ma.apply_error = ma_client_module.MusicAssistantApiError(
            "Music Assistant did not accept the new sample format"
        )
        entity = make_sampleformat_entity(ma)

        with self.assertRaises(HomeAssistantError) as ctx:
            await entity.async_select_option("96000:16:2")

        self.assertIn("Failed to update Music Assistant", str(ctx.exception))
        self.assertEqual(entity._attr_current_option, "48000:16:2")

    async def test_scope_error_gives_token_guidance(self) -> None:
        ma = FakeMaClient()
        ma.apply_error = ma_client_module.MusicAssistantScopeError("403")
        entity = make_sampleformat_entity(ma)

        with self.assertRaises(HomeAssistantError) as ctx:
            await entity.async_select_option("96000:16:2")

        self.assertIn("admin", str(ctx.exception).lower())

    async def test_unconfigured_is_unavailable_and_raises_cleanly(self) -> None:
        entity = make_sampleformat_entity(None, instance_id=None, current=None)

        self.assertFalse(entity.available)
        with self.assertRaises(HomeAssistantError):
            await entity.async_select_option("96000:16:2")

    async def test_snapshot_before_apply_and_resume_scheduled(self) -> None:
        ma = FakeMaClient()
        resume_stub.playing = ["media_player.fvm_win10"]
        original_snapshot = resume_stub.snapshot_playing_players

        def tracking_snapshot(hass):
            ma.timeline.append("snapshot")
            return original_snapshot(hass)

        select_module.snapshot_playing_players = tracking_snapshot
        try:
            entity = make_sampleformat_entity(ma)
            await entity.async_select_option("96000:16:2")
        finally:
            select_module.snapshot_playing_players = original_snapshot

        # Snapshot must run BEFORE the write (the reload stops the players).
        self.assertEqual(ma.timeline, ["snapshot", "apply"])
        await asyncio.sleep(0)  # let the created task run
        self.assertEqual(resume_stub.resume_calls, [["media_player.fvm_win10"]])

    async def test_no_resume_task_when_nothing_playing(self) -> None:
        ma = FakeMaClient()
        entity = make_sampleformat_entity(ma)

        await entity.async_select_option("96000:16:2")

        self.assertEqual(entity.hass.created_tasks, [])

    async def test_out_of_list_current_value_still_displayed(self) -> None:
        """A 24-bit value set in MA's own UI must show, not break the entity."""
        entity = make_sampleformat_entity(FakeMaClient(), current="96000:24:2")

        self.assertIn("96000:24:2", entity._attr_options)
        self.assertEqual(entity._attr_current_option, "96000:24:2")
        self.assertEqual(
            entity._attr_options[:-1], const_module.SAMPLEFORMAT_OPTIONS
        )

    async def test_options_match_const_for_normal_value(self) -> None:
        entity = make_sampleformat_entity(FakeMaClient(), current="48000:16:2")
        self.assertEqual(entity._attr_options, const_module.SAMPLEFORMAT_OPTIONS)

    async def test_unique_ids_are_distinct_and_entry_scoped(self) -> None:
        supervisor = FakeSupervisorClient()
        entry = make_entry(supervisor, FakeMaClient(), INSTANCE_ID)
        codec = select_module.SnapserverCodecSelect(entry, supervisor, "flac")
        fmt = select_module.SnapserverSampleformatSelect(
            entry, FakeMaClient(), INSTANCE_ID, "48000:16:2"
        )

        self.assertNotEqual(codec._attr_unique_id, fmt._attr_unique_id)
        for entity in (codec, fmt):
            self.assertTrue(entity._attr_unique_id.startswith("testentry"))
        # The pre-rework unique_id must survive so the entity keeps its history.
        self.assertEqual(fmt._attr_unique_id, "testentry_sampleformat")

    async def test_setup_entry_seeds_from_supervisor_and_ma(self) -> None:
        supervisor = FakeSupervisorClient()
        supervisor.options["codec"] = "vorbis"
        ma = FakeMaClient(rate=96000, depth=16)
        entry = make_entry(supervisor, ma, INSTANCE_ID)
        added: list = []

        await select_module.async_setup_entry(
            None, entry, lambda entities: added.extend(entities)
        )

        by_uid = {e._attr_unique_id: e for e in added}
        self.assertEqual(by_uid["testentry_codec"]._attr_current_option, "vorbis")
        self.assertEqual(
            by_uid["testentry_sampleformat"]._attr_current_option, "96000:16:2"
        )

    async def test_setup_entry_without_ma_yields_unavailable_entity(self) -> None:
        entry = make_entry(FakeSupervisorClient(), None, None)
        added: list = []

        await select_module.async_setup_entry(
            None, entry, lambda entities: added.extend(entities)
        )

        fmt = next(e for e in added if e._attr_unique_id == "testentry_sampleformat")
        self.assertFalse(fmt.available)
        self.assertIsNone(fmt._attr_current_option)


class TestNumberEntity(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.client = FakeSupervisorClient()
        self.entry = make_entry(self.client)

    async def test_buffer_change_writes_option_then_restarts(self) -> None:
        entity = number_module.SnapserverBufferNumber(self.entry, self.client, 1000)

        await entity.async_set_native_value(2500)

        self.assertEqual(self.client.call_names, ["get", "set", "restart"])
        self.assertEqual(entity._attr_native_value, 2500.0)

    async def test_buffer_is_written_as_int(self) -> None:
        """The addon schema is int(500,10000); a float would fail validation."""
        entity = number_module.SnapserverBufferNumber(self.entry, self.client, 1000)

        await entity.async_set_native_value(1500.0)

        written = self.client.last_set["buffer_ms"]
        self.assertIsInstance(written, int)
        self.assertEqual(written, 1500)

    async def test_buffer_change_preserves_every_other_option(self) -> None:
        before = dict(self.client.options)

        entity = number_module.SnapserverBufferNumber(self.entry, self.client, 1000)
        await entity.async_set_native_value(3000)

        written = self.client.last_set
        self.assertEqual(set(written), set(before))
        for key, value in before.items():
            if key != "buffer_ms":
                self.assertEqual(written[key], value, f"{key} was altered")

    async def test_slider_bounds_match_const(self) -> None:
        entity = number_module.SnapserverBufferNumber(self.entry, self.client, 1000)

        self.assertEqual(entity._attr_native_min_value, const_module.BUFFER_MIN)
        self.assertEqual(entity._attr_native_max_value, const_module.BUFFER_MAX)
        self.assertEqual(entity._attr_native_step, const_module.BUFFER_STEP)

    async def test_setup_entry_seeds_value_from_current_options(self) -> None:
        self.client.options["buffer_ms"] = 2200
        added: list = []

        await number_module.async_setup_entry(
            None, self.entry, lambda entities: added.extend(entities)
        )

        self.assertEqual(len(added), 1)
        self.assertEqual(added[0]._attr_native_value, 2200.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

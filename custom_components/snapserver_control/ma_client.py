"""Client for Music Assistant's HTTP JSON-RPC API.

Talks to MA's webserver (default port 8095): POST {url}/api with a body of
{"message_id": ..., "command": ..., "args": {...}} and a Bearer token. Success
is HTTP 200 with the command's return value serialized directly as the JSON
body (no envelope); errors are plain-text 401/403/4xx/5xx responses. (Verified
against music-assistant/server webserver/controller.py, 2026-08-29 — see
docs/PLAN_ma_sampleformat.md for the full ground-truth table.)

Why this exists: MA bakes sampleformat= into the Stream.AddStream URI of the
stream it creates, overriding the addon's global default — so the sample format
can only be changed by writing MA's own provider config, and only while MA's
"use external server" option is on (built-in mode hardcodes 48000:16:2).

Writing provider config requires an ADMIN token: config/providers/save is gated
on Scope.CONFIG_PROVIDERS_WRITE, which only the ADMIN role holds. The token MA
auto-mints for the Home Assistant integration has role SERVICE and gets a 403.

This module deliberately imports nothing from Home Assistant so it can be unit
tested standalone (see tests/test_ma_client.py).
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

LOGGER = logging.getLogger(__name__)

READ_TIMEOUT = 15.0
# config/providers/save reloads the provider INSIDE the request (the snapcast
# provider's unload includes an up-to-10s stream-idle wait), so the call can
# legitimately take 10-20+ seconds.
SAVE_TIMEOUT = 90.0

SNAPCAST_DOMAIN = "snapcast"

# MA's snapcast provider config keys (music_assistant/providers/snapcast/constants.py).
# MA silently DROPS unknown keys on save instead of rejecting them, so a rename
# upstream would make writes no-op — which is why verify_values() exists.
KEY_USE_EXTERNAL = "snapcast_use_external_server"
KEY_HOST = "snapcast_server_host"
KEY_PORT = "snapcast_server_control_port"
KEY_SAMPLE_RATE = "snapcast_stream_sample_rate"
KEY_BIT_DEPTH = "snapcast_stream_bit_depth"

# Where MA reaches the addon's snapserver: both containers are host-networked.
SNAPSERVER_HOST = "127.0.0.1"
SNAPSERVER_CONTROL_PORT = 1705

# Always 16: snapserver <= 0.35.0 lacks packed_s24le ingest (snapcast PR #1532
# is unmerged), so MA's packed 24-bit output would be misparsed into noise.
FORCED_BIT_DEPTH = 16


class MusicAssistantApiError(Exception):
    """Error talking to the Music Assistant API."""

    def __init__(self, message: str, status: int | None = None) -> None:
        """Initialize with a message and the HTTP status, when there was one."""
        super().__init__(message)
        self.status = status


class MusicAssistantAuthError(MusicAssistantApiError):
    """The token is missing, invalid, or expired (HTTP 401)."""


class MusicAssistantScopeError(MusicAssistantApiError):
    """The token is valid but lacks admin rights (HTTP 403)."""


class MusicAssistantClient:
    """Thin client for the commands this integration needs."""

    def __init__(self, url: str, token: str, session: Any) -> None:
        """Initialize with the MA base URL, an admin token, and an aiohttp session."""
        self._url = url.rstrip("/")
        self._token = token
        self._session = session
        self._next_id = 0

    async def _command(
        self,
        command: str,
        args: dict[str, Any] | None = None,
        timeout: float = READ_TIMEOUT,
    ) -> Any:
        """POST one command and return its bare result."""
        self._next_id += 1
        body = {
            "message_id": str(self._next_id),
            "command": command,
            "args": args or {},
        }
        async with self._session.post(
            f"{self._url}/api",
            json=body,
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            if resp.status == 401:
                raise MusicAssistantAuthError(
                    "Music Assistant rejected the token (invalid or expired)",
                    status=401,
                )
            if resp.status == 403:
                raise MusicAssistantScopeError(
                    "The Music Assistant token lacks admin rights — create a"
                    " long-lived token for an admin user in the MA web UI",
                    status=403,
                )
            if resp.status != 200:
                text = await resp.text()
                raise MusicAssistantApiError(
                    f"Music Assistant returned {resp.status} for {command}: {text}",
                    status=resp.status,
                )
            return await resp.json()

    async def get_snapcast_instance_id(self) -> str:
        """Return the instance id of MA's snapcast player provider."""
        result = await self._command(
            "config/providers", {"provider_domain": SNAPCAST_DOMAIN}
        )
        if not isinstance(result, list):
            raise MusicAssistantApiError(
                "Unexpected response shape for the provider list:"
                f" {type(result).__name__}"
            )
        for item in result:
            if (
                isinstance(item, dict)
                and item.get("domain") == SNAPCAST_DOMAIN
                and item.get("instance_id")
            ):
                return str(item["instance_id"])
        raise MusicAssistantApiError(
            "No Snapcast provider is configured in Music Assistant"
        )

    async def get_value(self, instance_id: str, key: str) -> Any:
        """Return one raw provider config value."""
        return await self._command(
            "config/providers/get_value", {"instance_id": instance_id, "key": key}
        )

    async def save_snapcast_config(
        self, instance_id: str, values: dict[str, Any]
    ) -> Any:
        """Save (merge) provider config values. MA reloads the provider itself."""
        return await self._command(
            "config/providers/save",
            {
                "provider_domain": SNAPCAST_DOMAIN,
                "instance_id": instance_id,
                "values": values,
            },
            timeout=SAVE_TIMEOUT,
        )

    async def probe_write_access(self, instance_id: str) -> bool:
        """Check whether the token can write provider config, without changing it.

        Saving the current value back is a safe probe: the 403 scope gate runs
        before the merge logic, and an unchanged value short-circuits to a no-op.
        """
        current = await self.get_value(instance_id, KEY_SAMPLE_RATE)
        if current is None:
            current = 48000
        try:
            await self.save_snapcast_config(instance_id, {KEY_SAMPLE_RATE: current})
        except MusicAssistantScopeError:
            return False
        return True

    async def verify_values(
        self, instance_id: str, expected: dict[str, Any]
    ) -> dict[str, Any]:
        """Read back the given keys; return {key: actual} for any that mismatch.

        Needed because MA silently drops unknown keys on save — without this, a
        key rename in a future MA version would turn every write into a no-op.
        """
        mismatches: dict[str, Any] = {}
        for key, want in expected.items():
            got = await self.get_value(instance_id, key)
            if got != want:
                mismatches[key] = got
        return mismatches

    async def apply_sampleformat(self, instance_id: str, rate: int) -> None:
        """Apply a new stream sample rate, verified.

        Also flips MA onto the external snapserver (the addon's), since the
        stream format keys are only honored in external mode.
        """
        values = {
            KEY_SAMPLE_RATE: rate,
            KEY_BIT_DEPTH: FORCED_BIT_DEPTH,
            KEY_USE_EXTERNAL: True,
            KEY_HOST: SNAPSERVER_HOST,
            KEY_PORT: SNAPSERVER_CONTROL_PORT,
        }
        await self.save_snapcast_config(instance_id, values)
        mismatches = await self.verify_values(
            instance_id,
            {KEY_SAMPLE_RATE: rate, KEY_BIT_DEPTH: FORCED_BIT_DEPTH},
        )
        if mismatches:
            raise MusicAssistantApiError(
                "Music Assistant did not accept the new sample format"
                f" (readback: {mismatches}) — its config key names may have"
                " changed in a newer version"
            )

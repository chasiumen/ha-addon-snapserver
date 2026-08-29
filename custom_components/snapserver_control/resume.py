"""Best-effort playback auto-resume around a Music Assistant provider reload.

Changing the sample format makes MA reload its snapcast provider, which tears
down every MA media_player for ~5-15 seconds and drops any play command issued
in that window. Rather than leaving the user to click play repeatedly, we
snapshot which MA players were playing before the write and re-issue play once
each one comes back. Everything here is best-effort: it logs, never raises.
"""

from __future__ import annotations

import asyncio

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import LOGGER, MA_INTEGRATION_DOMAIN

RESUME_TOTAL_SECONDS = 60
RESUME_POLL_SECONDS = 3

_GONE_STATES = ("unavailable", "unknown")


def snapshot_playing_players(hass: HomeAssistant) -> list[str]:
    """Return the entity_ids of Music Assistant media players currently playing."""
    registry = er.async_get(hass)
    playing: list[str] = []
    for entity in registry.entities.values():
        if entity.platform != MA_INTEGRATION_DOMAIN or entity.domain != "media_player":
            continue
        state = hass.states.get(entity.entity_id)
        if state is not None and state.state == "playing":
            playing.append(entity.entity_id)
    return playing


async def resume_players(hass: HomeAssistant, entity_ids: list[str]) -> None:
    """Re-issue play on the given players once they come back from the reload."""
    if not entity_ids:
        return
    try:
        pending = set(entity_ids)
        nudged: set[str] = set()
        for _ in range(int(RESUME_TOTAL_SECONDS / RESUME_POLL_SECONDS)):
            for entity_id in list(pending):
                state = hass.states.get(entity_id)
                if state is None or state.state in _GONE_STATES:
                    # Still mid-reload; check again next round.
                    continue
                if state.state == "playing":
                    pending.discard(entity_id)
                    continue
                if entity_id not in nudged:
                    nudged.add(entity_id)
                    await hass.services.async_call(
                        "media_player",
                        "media_play",
                        {"entity_id": entity_id},
                        blocking=False,
                    )
            if not pending:
                break
            await asyncio.sleep(RESUME_POLL_SECONDS)

        if pending:
            LOGGER.warning(
                "Gave up resuming playback on %s after %ss — press play manually",
                sorted(pending),
                RESUME_TOTAL_SECONDS,
            )
        else:
            LOGGER.info("Resumed playback on %s after the sample format change", entity_ids)
    except Exception:  # noqa: BLE001 - fire-and-forget task must never blow up
        LOGGER.exception("Auto-resume after the sample format change failed")

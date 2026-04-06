"""Supervisor API client for managing the Snapserver addon."""

from __future__ import annotations

import os
from typing import Any

import aiohttp

from .const import ADDON_SLUG, LOGGER


class SupervisorApiError(Exception):
    """Error communicating with Supervisor API."""


class SupervisorClient:
    """Client to interact with the HA Supervisor API."""

    def __init__(self) -> None:
        """Initialize the client."""
        self._base_url = f"http://{os.environ.get('SUPERVISOR', '172.30.32.2')}"
        self._token = os.environ.get("SUPERVISOR_TOKEN", "")

    @property
    def _headers(self) -> dict[str, str]:
        """Return auth headers."""
        return {"Authorization": f"Bearer {self._token}"}

    async def get_addon_options(self) -> dict[str, Any]:
        """Get current addon options."""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self._base_url}/addons/{ADDON_SLUG}/info",
                headers=self._headers,
            ) as resp:
                if resp.status != 200:
                    raise SupervisorApiError(
                        f"Failed to get addon info: {resp.status}"
                    )
                data = await resp.json()
                return data.get("data", {}).get("options", {})

    async def set_addon_options(self, options: dict[str, Any]) -> None:
        """Update addon options."""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self._base_url}/addons/{ADDON_SLUG}/options",
                headers=self._headers,
                json={"options": options},
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise SupervisorApiError(
                        f"Failed to set addon options: {resp.status} {text}"
                    )
        LOGGER.info("Updated Snapserver addon options: %s", options)

    async def restart_addon(self) -> None:
        """Restart the Snapserver addon."""
        LOGGER.info("Restarting Snapserver addon...")
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self._base_url}/addons/{ADDON_SLUG}/restart",
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise SupervisorApiError(
                        f"Failed to restart addon: {resp.status} {text}"
                    )
        LOGGER.info("Snapserver addon restarted")

    async def is_addon_installed(self) -> bool:
        """Check if the Snapserver addon is installed."""
        try:
            await self.get_addon_options()
            return True
        except (SupervisorApiError, aiohttp.ClientError):
            return False

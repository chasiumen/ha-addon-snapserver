"""Constants for the Snapserver Control integration."""

from __future__ import annotations

import logging

DOMAIN = "snapserver_control"
LOGGER = logging.getLogger(__package__)

ADDON_SLUG = "24c8c63c_snapserver"

CONF_CODEC = "codec"
CONF_SAMPLEFORMAT = "sampleformat"
CONF_BUFFER_MS = "buffer_ms"

CODEC_OPTIONS = ["flac", "pcm", "opus", "vorbis"]

SAMPLEFORMAT_OPTIONS = [
    "44100:16:1",
    "44100:16:2",
    "48000:16:2",
    "48000:24:2",
    "96000:24:2",
]

BUFFER_MIN = 500
BUFFER_MAX = 5000
BUFFER_STEP = 100

# Snapserver's JSON-RPC control socket. 127.0.0.1 works because the addon runs
# with host_network: true and HA Core is host-networked on HAOS; the options
# flow exists as an escape hatch for installs where it isn't.
CONF_RPC_HOST = "rpc_host"
CONF_RPC_PORT = "rpc_port"
DEFAULT_RPC_HOST = "127.0.0.1"
DEFAULT_RPC_PORT = 1705

SERVICE_DELETE_CLIENT = "delete_client"
ATTR_CLIENT_ID = "client_id"

# Frontend card served from custom_components/snapserver_control/www/.
CARD_FILENAME = "snapcast-clients-card.js"
CARD_URL = f"/{DOMAIN}/{CARD_FILENAME}"
CARD_VERSION = "1"

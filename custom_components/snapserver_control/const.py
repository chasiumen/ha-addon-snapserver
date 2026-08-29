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

# Sample format is owned by MUSIC ASSISTANT, not the addon: MA bakes
# sampleformat= into its Stream.AddStream URI, overriding the addon's global
# default, so the select entity writes MA's provider config via ma_client.py.
# 16-bit only: snapserver <= 0.35.0 lacks packed_s24le ingest (snapcast PR
# #1532 unmerged) and MA's packed 24-bit output would be misparsed into noise.
# No 44100 / no mono: MA offers rates (48000, 96000, 192000) and hardcodes
# channels=2. See docs/PLAN_ma_sampleformat.md for the verified ground truth.
SAMPLEFORMAT_OPTIONS = [
    "48000:16:2",
    "96000:16:2",
    "192000:16:2",
]

# Music Assistant connection (stored in this integration's config entry).
CONF_MA_URL = "ma_url"
CONF_MA_TOKEN = "ma_token"
MA_INTEGRATION_DOMAIN = "music_assistant"
DEFAULT_MA_URL = "http://127.0.0.1:8095"
# The API port. NOT the same as the HA-Ingress-only port (8094): that listener
# requires Supervisor-injected X-Remote-User-* headers and has no Bearer-token
# fallback at all (auth_middleware.py get_authenticated_user), so it rejects
# every token as unauthenticated, valid or not. See docs/PLAN_ma_sampleformat.md.
MA_API_PORT = 8095
MA_INGRESS_ONLY_PORT = 8094

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

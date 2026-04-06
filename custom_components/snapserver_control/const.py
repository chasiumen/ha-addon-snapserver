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

#!/usr/bin/with-contenv bashio
# shellcheck shell=bash

# Read configuration from HA
CODEC=$(bashio::config 'codec')
BUFFER_MS=$(bashio::config 'buffer_ms')
SAMPLEFORMAT=$(bashio::config 'sampleformat')
SNAPWEB_ENABLED=$(bashio::config 'snapweb_enabled')
LIBRESPOT_ENABLED=$(bashio::config 'librespot_enabled')
LIBRESPOT_NAME=$(bashio::config 'librespot_name')
LIBRESPOT_BITRATE=$(bashio::config 'librespot_bitrate')
INITIAL_VOLUME=$(bashio::config 'initial_volume')

# Build stream sources
STREAM_SOURCES=""

# Default TCP stream source (for Music Assistant / other apps to send audio)
STREAM_SOURCES="source = tcp://0.0.0.0:4953?name=TCP&mode=server"

# Add librespot source if enabled (snapserver has built-in librespot support)
if bashio::config.true 'librespot_enabled'; then
    STREAM_SOURCES="${STREAM_SOURCES}
source = librespot:///librespot?name=Spotify&devicename=${LIBRESPOT_NAME}&bitrate=${LIBRESPOT_BITRATE}&volume=${INITIAL_VOLUME}"
    bashio::log.info "Librespot enabled as '${LIBRESPOT_NAME}' (bitrate: ${LIBRESPOT_BITRATE})"
fi

# Determine snapweb doc_root
if bashio::config.true 'snapweb_enabled'; then
    DOC_ROOT="/usr/share/snapserver/snapweb"
    bashio::log.info "Snapweb enabled on port 1780"
else
    DOC_ROOT=""
fi

# Generate snapserver.conf
cat > /etc/snapserver.conf << EOF
[server]
threads = -1
datadir = /var/lib/snapserver

[http]
enabled = ${SNAPWEB_ENABLED}
bind_to_address = 0.0.0.0
port = 1780
doc_root = ${DOC_ROOT}

[tcp-control]
enabled = true
bind_to_address = 0.0.0.0
port = 1705

[tcp-streaming]
enabled = true
bind_to_address = 0.0.0.0
port = 1704

[stream]
codec = ${CODEC}
buffer = ${BUFFER_MS}
sampleformat = ${SAMPLEFORMAT}
send_to_muted = false
${STREAM_SOURCES}

[logging]
filter = *:info
EOF

bashio::log.info "Starting Snapserver (codec: ${CODEC}, buffer: ${BUFFER_MS}ms)"
bashio::log.info "--- snapserver.conf ---"
cat /etc/snapserver.conf
bashio::log.info "-----------------------"

# Create data directory
mkdir -p /var/lib/snapserver

# Start snapserver in foreground
exec snapserver --config /etc/snapserver.conf

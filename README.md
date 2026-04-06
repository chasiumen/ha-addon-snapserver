# Snapserver Add-on for Home Assistant

A Home Assistant add-on that runs [Snapcast](https://github.com/snapcast/snapcast) server for synchronized multi-room audio streaming.

Includes optional [Snapweb](https://github.com/badaix/snapweb) UI and [Librespot](https://github.com/librespot-org/librespot) (Spotify Connect) support.

## Architecture

```
Audio Source (Music Assistant, Navidrome, Spotify, etc.)
  --> Snapserver (this addon, port 1704)
  --> Snapclients (Windows PC, Raspberry Pi, Linux, etc.)
  --> Speakers
```

## Installation

1. In Home Assistant, go to **Settings > Add-ons > Add-on Store**
2. Click the three dots menu > **Repositories**
3. Add: `https://github.com/chasiumen/ha-addon-snapserver`
4. Find **Snapserver** in the store and click **Install**
5. Configure options and start the add-on

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `codec` | `flac` | Audio codec: `flac`, `pcm`, `opus`, or `vorbis` |
| `buffer_ms` | `1000` | Buffer size in milliseconds |
| `sampleformat` | `48000:16:2` | Sample rate:bit depth:channels |
| `snapweb_enabled` | `true` | Enable Snapweb browser UI on port 1780 |
| `librespot_enabled` | `false` | Enable Spotify Connect receiver |
| `librespot_name` | `Snapserver` | Spotify device name |
| `librespot_bitrate` | `320` | Spotify bitrate: `96`, `160`, or `320` |
| `initial_volume` | `100` | Initial volume for Spotify (0-100) |

## Ports

| Port | Protocol | Description |
|------|----------|-------------|
| 1704 | TCP | Snapcast client connections |
| 1705 | TCP | Snapcast control / JSON-RPC |
| 1780 | TCP | Snapweb UI (if enabled) |
| 4953 | TCP | TCP audio input stream |

## Audio Sources

### TCP Stream (default)

The add-on listens on port 4953 for TCP audio input. Music Assistant and other apps can send PCM audio here.

In **Music Assistant**, add a Snapcast player provider pointing at your HA server.

### Spotify Connect (optional)

Enable `librespot_enabled` in the config. Snapserver uses its built-in librespot source — your server appears as a Spotify Connect device named after `librespot_name`. Audio from Spotify is streamed to all connected Snapclients.

## Client Setup

### Windows

1. Download `snapclient_win64.zip` from [Snapcast releases](https://github.com/snapcast/snapcast/releases/tag/v0.35.0)
2. Extract and run:
   ```
   snapclient.exe -h <HA-server-ip>
   ```
3. Optional: create a Task Scheduler entry to auto-start on login

### Linux

```bash
# Debian/Ubuntu — download .deb from GitHub releases
wget https://github.com/snapcast/snapcast/releases/download/v0.35.0/snapclient_0.35.0-1_amd64_bookworm.deb
sudo apt install ./snapclient_0.35.0-1_amd64_bookworm.deb
snapclient -h <HA-server-ip>
```

### macOS

```bash
brew install snapcast
snapclient -h <HA-server-ip>
```

### Android

Install [Snapdroid](https://play.google.com/store/apps/details?id=de.badaix.snapcast) from the Play Store.

## HA Integration

After the add-on is running, add the built-in **Snapcast** integration in HA:

1. Go to **Settings > Devices & Services > Add Integration**
2. Search for **Snapcast** and add it
3. Host: `localhost`, Port: `1705`

This creates `media_player` entities for each connected Snapclient that you can control from HA (volume, mute, group).

### Using with Navidrome

If you have the [Navidrome integration](https://github.com/chasiumen/ha-music-assistant), set the Snapcast player as the **target media player** in the Navidrome integration options. Voice commands and dashboard playback will then stream through Snapcast to your speakers.

## Snapweb UI

If `snapweb_enabled` is true, access the web UI at:

```
http://<HA-server-ip>:1780
```

From here you can see connected clients, adjust volumes, and manage groups.

## Technical Details

- **Base image**: Alpine Linux (hassio-addons/base)
- **Snapcast**: v0.35.0 from Alpine edge/community
- **Librespot**: v0.8.0 from Alpine edge/testing
- **Snapweb**: v0.9.2 from Alpine edge/community
- **Supported architectures**: amd64, aarch64

## Running Tests

```bash
bash tests/test_config.sh
```

## Troubleshooting

- **No sound on client**: Ensure the client can reach port 1704 on your HA server. Check firewall rules.
- **Choppy audio**: Increase `buffer_ms` (try 1500 or 2000).
- **Spotify not showing**: Ensure `librespot_enabled` is true and restart the add-on. Your Spotify app must be on the same network.
- **Check logs**: Go to the add-on page in HA and click the **Log** tab.

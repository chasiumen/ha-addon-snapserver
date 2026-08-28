# Snapserver Add-on for Home Assistant

A Home Assistant add-on that runs [Snapcast](https://github.com/snapcast/snapcast) server for synchronized multi-room audio streaming.

Includes optional [Snapweb](https://github.com/snapcast/snapweb) UI and [Librespot](https://github.com/librespot-org/librespot) (Spotify Connect) support.

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

### Audio Quality Presets

Audio quality is controlled server-side via `sampleformat` and `codec`. All clients receive the same format.

| Preset | `sampleformat` | `codec` | Use Case |
|--------|---------------|---------|----------|
| CD Quality | `44100:16:2` | `flac` | Standard music listening |
| High Quality (default) | `48000:16:2` | `flac` | Good balance of quality and bandwidth |
| Hi-Res | `96000:24:2` | `flac` | Audiophile, requires more bandwidth |
| Low Bandwidth | `44100:16:2` | `opus` | Remote clients or slow networks |
| Mono Output | `48000:16:1` | `flac` | Single speaker setups |

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

#### Basic Setup

1. Download `snapclient_win64.zip` from [Snapcast releases](https://github.com/snapcast/snapcast/releases/tag/v0.35.0)
2. Extract to a folder (e.g., `C:\snapclient\`)
3. Open Command Prompt or PowerShell in that folder and run:
   ```
   snapclient.exe -h <HA-server-ip>
   ```

#### List Available Audio Outputs

```
snapclient.exe -l
```

This shows all audio devices with their IDs, e.g.:

```
0: Speakers (Realtek High Definition Audio)
1: Digital Audio (S/PDIF) (Realtek High Definition Audio)
2: Headphones (USB Audio Device)
```

#### Select a Specific Output Device

```
snapclient.exe -h <HA-server-ip> -s <device_id>
```

For example, to play through the USB headphones (device 2):

```
snapclient.exe -h 192.168.1.34 -s 2
```

#### Multiple Outputs (Multi-Room on One PC)

Run multiple instances, each targeting a different audio device:

```
snapclient.exe -h <HA-server-ip> -s 0 --instance 1
snapclient.exe -h <HA-server-ip> -s 2 --instance 2
```

Each instance appears as a separate client in Snapweb and HA, so you can control volumes independently.

#### Auto-Start on Login (Task Scheduler)

1. Open **Task Scheduler** and click **Create Basic Task**
2. Name: `Snapclient`
3. Trigger: **When I log on**
4. Action: **Start a program**
   - Program: `C:\snapclient\snapclient.exe`
   - Arguments: `-h <HA-server-ip> -s <device_id>`
5. Finish and check **Open the Properties dialog** → under General, check **Run whether user is logged on or not**

#### Auto-Start as a Windows Service

For headless/always-on setups, install as a Windows service using [NSSM](https://nssm.cc/):

```
nssm install Snapclient "C:\snapclient\snapclient.exe" "-h <HA-server-ip> -s <device_id>"
nssm start Snapclient
```

#### All Client Options

```
snapclient.exe --help
```

Key options:

| Option | Description | Example |
|--------|-------------|---------|
| `-h <ip>` | Server IP address | `-h 192.168.1.34` |
| `-s <id>` | Audio output device ID (from `-l`) | `-s 2` |
| `--instance <n>` | Instance number (for multiple clients) | `--instance 1` |
| `-p <port>` | Server port (default 1704) | `-p 1704` |
| `--latency <ms>` | Additional latency in ms | `--latency 0` |

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

### Snapserver Control Integration (optional)

A companion integration is included in `custom_components/snapserver_control/` that lets you control audio quality settings from the HA UI:

1. Copy `custom_components/snapserver_control/` to your HA `config/custom_components/` directory
2. Restart HA
3. Go to **Settings > Devices & Services > Add Integration > Snapserver Control**

During setup you are asked for the Snapserver control socket. Leave it at `127.0.0.1:1705` unless Home Assistant cannot reach the addon over localhost; you can change it later via the integration's **Configure** button.

This creates:

| Entity | Type | Description |
|--------|------|-------------|
| `select.snapserver_audio_codec` | Select | Switch between flac, pcm, opus, vorbis |
| `select.snapserver_sample_format` | Select | Change sample rate/depth/channels |
| `number.snapserver_buffer_size` | Slider | Adjust buffer 500-5000ms |
| `sensor.snapserver_clients_connected` | Sensor | How many clients are connected, with the full roster as an attribute |
| `sensor.snapserver_stream_status` | Sensor | Whether the stream is `playing` or `idle` |
| `binary_sensor.snapserver_control_connection` | Connectivity | Whether the integration can reach Snapserver at all |

Plus, for every Snapcast client the server knows about, its own device with:

| Entity | Type | Description |
|--------|------|-------------|
| `binary_sensor.<client>_connected` | Connectivity | On while that client is connected |
| `sensor.<client>_last_seen` | Timestamp | Renders as "12 minutes ago" once a client drops |

Services for automations: `snapserver_control.set_codec`, `snapserver_control.set_sampleformat`, `snapserver_control.set_buffer`, and `snapserver_control.delete_client` (permanently forget a client that will never reconnect, e.g. a machine whose network adapter changed).

**Note:** Changing codec, sample format, or buffer restarts the Snapserver addon, which briefly disconnects all clients (1-3 seconds). The status entities do not — they read Snapserver's control API and never restart anything.

### Client Status Card

The integration ships a Lovelace card showing which clients are up and, for the ones that aren't, how long they've been gone. It is registered automatically — just add it to a dashboard:

```yaml
type: custom:snapcast-clients-card
entity: sensor.snapserver_clients_connected
title: Speakers
```

```
● Windows PC          192.168.1.42 · v0.31.0          Connected
● Kitchen Pi          192.168.1.55 · v0.31.0     Last seen 12m ago
```

Options: `title` (default "Speakers") and `hide_disconnected: true` to show only live clients. Clicking a row opens that client's more-info dialog. If Snapserver itself becomes unreachable the card says so, rather than showing every client as dead.

If the card doesn't appear after copying the integration, hard-refresh the browser (Ctrl+F5) to clear the cached resource list.

To be told about a drop instead of having to look:

```yaml
automation:
  - alias: Snapcast client went offline
    triggers:
      - trigger: state
        entity_id: binary_sensor.windows_pc_connected
        to: "off"
        for: "00:02:00"
    actions:
      - action: notify.mobile_app_your_phone
        data:
          message: "Snapcast client 'Windows PC' has been offline for 2 minutes."
```

### Using with Navidrome

If you have the [Navidrome integration](https://github.com/chasiumen/ha-music-assistant), set the Snapcast player as the **target media player** in the Navidrome integration options. Voice commands and dashboard playback will then stream through Snapcast to your speakers.

## Snapweb UI

If `snapweb_enabled` is true, access the web UI at:

```
http://<HA-server-ip>:1780
```

From here you can see connected clients, adjust volumes, and manage groups.

## Music Assistant Compatibility

This addon includes the Music Assistant control script (`control.py`) that enables full integration with [Music Assistant](https://music-assistant.io/). When MA creates Snapcast streams, the control script bridges playback commands (play, pause, next, previous, seek, shuffle, repeat) between MA and Snapserver.

No additional configuration is needed — the control script is automatically available at `/usr/share/snapserver/plug-ins/control.py`.

## Technical Details

- **Base image**: Alpine Linux (hassio-addons/base)
- **Snapcast**: v0.35.0 from Alpine edge/community
- **Librespot**: v0.8.0 from Alpine edge/testing
- **Snapweb**: v0.9.3 from [GitHub releases](https://github.com/snapcast/snapweb/releases)
- **MA control script**: from [music-assistant/server](https://github.com/music-assistant/server) with inlined helpers
- **Supported architectures**: amd64, aarch64

## Running Tests

```bash
# Addon tests (68 tests)
bash tests/test_config.sh

# Companion integration tests (76 tests, includes the Python suites below)
bash tests/test_companion.sh

# Protocol and coordinator unit tests (18 tests, no Home Assistant needed)
python3 tests/test_rpc.py
python3 tests/test_coordinator.py
```

## Troubleshooting

- **No sound on client**: Ensure the client can reach port 1704 on your HA server. Check firewall rules.
- **Choppy audio**: Increase `buffer_ms` (try 1500 or 2000).
- **Spotify not showing**: Ensure `librespot_enabled` is true and restart the add-on. Your Spotify app must be on the same network.
- **Windows client keeps dying**: `snapclient.exe` exits when Windows switches the default output device (e.g. line-out to headphones). Pin the device with `-s <device>` so a default change is ignored, and run it as a service with restart-on-failure (see [Auto-Start as a Windows Service](#auto-start-as-a-windows-service)) so it recovers on its own. The Client Status Card tells you when this has happened.
- **Client status entities never appear**: The integration talks to Snapserver's control API on port 1705. Check `binary_sensor.snapserver_control_connection` — if it is off, the addon is stopped or the host/port in the integration's **Configure** dialog is wrong.
- **Check logs**: Go to the add-on page in HA and click the **Log** tab.

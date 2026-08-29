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

Each device is printed as two lines — an index and endpoint GUID, then the friendly name:

```
0: default
Speakers (Realtek(R) Audio)

1: {0.0.0.00000000}.{88299c40-4cc9-45df-80ce-5570d740ace9}
Speakers (Realtek(R) Audio)

2: {0.0.0.00000000}.{1d2e3f40-5a6b-7c8d-9e0f-a1b2c3d4e5f6}
Headphones (USB Audio Device)
```

#### Select a Specific Output Device

```
snapclient.exe -h <HA-server-ip> -s "<endpoint-GUID>"
```

**Use the GUID, not the friendly name.** On Windows, snapclient stores the endpoint GUID in the field `-s` matches against, and the friendly name only as a description — so `-s "Headphones"` matches nothing.

```
snapclient.exe -h 192.168.1.34 -s "{0.0.0.00000000}.{1d2e3f40-5a6b-7c8d-9e0f-a1b2c3d4e5f6}"
```

**Avoid numeric indices.** They come from an enumeration of *currently active* devices only, so they shift as devices are plugged in, unplugged, or disabled — `-s 2` can silently become a different device. And on Windows a `-s` value that matches nothing isn't reported as an error; snapclient crashes immediately instead.

Omit `-s` entirely to follow whatever Windows' current default output device is.

#### Multiple Outputs (Multi-Room on One PC)

Run multiple instances, each pinned to a different device:

```
snapclient.exe -h <HA-server-ip> -s "<speakers-GUID>"  --instance 1
snapclient.exe -h <HA-server-ip> -s "<headphones-GUID>" --instance 2
```

Each instance appears as a separate client in Snapweb, in HA, and in Music Assistant (which registers one player per Snapclient), so you can control them independently. Instance 2 and up get a `#N` suffix on their client ID, e.g. `00:21:6a:7d:74:fc#2`.

Note both instances play at once unless you mute one. Since the add-on sets `send_to_muted = false`, muting a client genuinely stops audio being sent to it, so mute/unmute from HA works as an output selector.

#### Keeping the Client Alive (Windows Default-Device Changes)

**snapclient dies when Windows switches the default output device** — e.g. plugging in headphones. Its WASAPI backend has no device-change handling, so the audio client is invalidated, the player thread throws, and the exception escapes into `std::terminate()`, aborting the process. There is no auto-switch option and no in-process recovery.

The fix is to supervise it externally. A ready-made script is included at [`clients/windows/start_snapclient.vbs`](clients/windows/start_snapclient.vbs): it launches snapclient, blocks until it exits, and restarts it. Because it passes no `-s`, each restart re-resolves the *current* default device — so changing the Windows output device switches snapclient too, after a few seconds of silence.

Edit the `SNAPCLIENT` and `SERVER` values at the top, then drop it in your Startup folder:

```
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\
```

If Windows pops a "snapclient.exe has stopped working" dialog on each crash, it will stall the restart. Suppress it for that one program:

```
reg add "HKCU\Software\Microsoft\Windows\Windows Error Reporting\ExcludedApplications" /v snapclient.exe /t REG_DWORD /d 1 /f
```

With the Snapserver Control integration installed, `binary_sensor.<client>_connected` and `sensor.<client>_last_seen` will show you when a client dropped and for how long.

#### Auto-Start on Login (Task Scheduler)

1. Open **Task Scheduler** and click **Create Basic Task**
2. Name: `Snapclient`
3. Trigger: **When I log on**
4. Action: **Start a program**
   - Program: `C:\snapclient\snapclient.exe`
   - Arguments: `-h <HA-server-ip> -s "<endpoint-GUID>"`
5. Finish and check **Open the Properties dialog** → under General, check **Run whether user is logged on or not**

#### Auto-Start as a Windows Service

For headless/always-on setups, install as a Windows service using [NSSM](https://nssm.cc/). NSSM restarts the process on exit by default, so this also covers the crash described below — and unlike the Startup-folder script it runs without anyone logged in:

```
nssm install Snapclient "C:\snapclient\snapclient.exe" "-h <HA-server-ip> -s ""<endpoint-GUID>"""
nssm set Snapclient AppExit Default Restart
nssm set Snapclient AppRestartDelay 3000
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
| `-s <id>` | Output device: endpoint GUID from `-l` (name match, not the friendly name). Omit to follow the Windows default | `-s "{0.0.0.00000000}.{88299c40-...}"` |
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

A companion integration is included in `custom_components/snapserver_control/` that lets you control audio quality settings, and see which Snapcast clients are connected, from the HA UI.

This repo is both an add-on repository (`repository.yaml`, used above for the Snapserver add-on) **and** a HACS integration repository (`hacs.json`, used here) — the two live side by side and don't interfere with each other. Install this piece through HACS rather than copying files by hand:

1. In HACS, go to the three-dot menu > **Custom repositories**
2. Add `https://github.com/chasiumen/ha-addon-snapserver`, category **Integration**
   (this is separate from adding it to the Add-on Store — you'll have added the same URL twice, once per store)
3. Find **Snapserver Control** in HACS and install it
4. Restart HA
5. Go to **Settings > Devices & Services > Add Integration > Snapserver Control**

Future updates: click **Update** in HACS, then restart HA — no manual file copying.

During setup you are asked for the Snapserver control socket (leave it at `127.0.0.1:1705` unless Home Assistant cannot reach the addon over localhost) and for a Music Assistant connection — see below. Both can be changed later via the integration's **Configure** button.

This creates:

| Entity | Type | Description |
|--------|------|-------------|
| `select.snapserver_audio_codec` | Select | Switch between flac, pcm, opus, vorbis |
| `select.snapserver_sample_format` | Select | Change Music Assistant's stream sample rate (16-bit stereo) |
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

**Who owns which audio setting** (each control targets the one place its value is actually honored):

| Setting | Written to | Effect of changing it |
|---------|-----------|----------------------|
| Codec | Snapserver addon config | Addon restarts (~1-3s client disconnect) |
| Buffer | Snapserver addon config | Addon restarts (~1-3s client disconnect) |
| Sample format | **Music Assistant provider config** | MA reloads its Snapcast provider (~10s audio dip); the addon is NOT restarted |

The split exists because Music Assistant bakes its own `sampleformat` into every stream it creates, overriding the addon's global default — while codec and buffer genuinely come from the addon. The status entities never restart anything.

#### Sample format setup (Music Assistant connection)

The sample-format entity needs a **long-lived token for an admin user** of Music Assistant — the token MA hands to Home Assistant automatically cannot write provider settings. One-time setup:

1. Open the Music Assistant web UI → **Settings** → open your (admin) user's profile → create a **long-lived token**.
2. In HA: **Settings > Devices & Services > Snapserver Control > Configure** → fill in the MA URL (usually `http://127.0.0.1:8095`) and paste the token.

Behavior on change: MA is switched to "use external server" mode automatically (pointing at this addon), the provider reloads (~10 seconds of silence), and if music was playing the integration re-issues play automatically once the players return. Options are 16-bit only — snapserver v0.35.0 cannot ingest MA's packed 24-bit format (snapcast PR #1532 is unreleased), so don't select 24-bit inside MA's own UI either.

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

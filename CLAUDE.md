# Snapserver HA Addon

## Goal
Create a Home Assistant Snapserver addon. The user wants to stream audio from Navidrome (via Music Assistant on HA) to a Windows PC's speakers using Snapcast.

## Why
- Existing community Snapserver addons are broken or abandoned:
  - **Art-Ev/addon-snapserver** — last release Nov 2024, build fails on newer HA Supervisor (open issue #21)
  - **EvTheFuture/hassio-addon-snapcast** — abandoned since Aug 2022
- User does not want to manually install snapserver via package manager outside HA's framework (not portable)

## Architecture
```
Navidrome -> Music Assistant (HA) -> Snapserver (addon) -> Snapclient (Windows PC speakers)
```

## Addon Design Decisions
- **Three components:**
  - Snapserver (always on, core)
  - Snapweb (toggleable via config bool) — browser-based client control UI on port 1780
  - Librespot (toggleable via config bool) — Spotify Connect via snapserver's built-in librespot:// source
- Use Alpine edge packages: snapcast-server 0.35.0, librespot 0.8.0
- Snapweb 0.9.3 downloaded from https://github.com/snapcast/snapweb/releases (not available as Alpine package)
- Base image: ghcr.io/hassio-addons/base:16.3.2 (Alpine-based, includes bashio)
- Support amd64 and aarch64 architectures
- Librespot has NO pre-built binaries on GitHub — must use Alpine package

## Addon File Structure
```
repo-root/
├── repository.yaml          # HA addon repo metadata
├── README.md
├── CLAUDE.md                # This file — project context and plans
├── snapserver/
│   ├── config.yaml          # Addon metadata, ports, options schema
│   ├── Dockerfile           # Alpine-based, installs snapserver + librespot + snapweb
│   ├── run.sh               # Reads HA config, conditionally starts components
│   ├── icon.png             # 256x256
│   └── README.md
```

## Config Options to Expose in HA UI
- `librespot_enabled` (bool)
- `snapweb_enabled` (bool)
- `codec` (flac/pcm/opus/vorbis)
- `buffer_ms` (int, default 1000)
- `librespot_name` (str, Spotify device name)

## Ports
- 1704/tcp — Snapcast protocol (client connections)
- 1705/tcp — Snapcast control
- 1780/tcp — Snapweb UI / JSON-RPC API
- 4953-5153/tcp — TCP audio input streams (Music Assistant dynamically creates streams in this range)

## Windows Client Setup
- Download `snapclient.exe` from https://github.com/snapcast/snapcast/releases
- Run: `snapclient.exe -h <HA-server-ip>`
- Optionally auto-start via Task Scheduler

## HA Integration Side
- Install built-in **Snapcast integration** in HA, point at localhost:1704
- In **Music Assistant**, add Snapcast player provider pointing at Snapserver

## Related Repo
- The Navidrome HA integration lives at ha-music-assistant (separate repo)

## Validation
- 51 tests pass (bash tests/test_config.sh)
- Verified Alpine edge has all packages at correct versions
- Verified snapserver.conf section names match official docs ([tcp-control], [tcp-streaming], [stream])
- Verified librespot:// is a built-in snapserver source type (no separate pipe/process needed)
- Verified snapweb must be downloaded from GitHub releases (not an Alpine package)

## Known Issues & Required Fixes

### ISSUE 1: Missing Music Assistant control script (CRITICAL)
**Error:** `controlscript '/usr/share/snapserver/plug-ins/control.py' does not exist`

Music Assistant sends a `Stream.AddStream` JSON-RPC request to Snapserver that references `controlscript=control.py`. This is a Music Assistant-specific plugin that must be bundled in the addon at `/usr/share/snapserver/plug-ins/control.py`.

**Fix:** Research the MA Snapcast control script (check the Music Assistant source code at https://github.com/music-assistant/server — look for `control.py` or snapcast-related plugin files). Download or bundle it in the Dockerfile and place it at `/usr/share/snapserver/plug-ins/control.py`.

**Actual error log:**
```
Server::onMessageReceived JsonRequestException: {"error":{"code":-32602,"data":"controlscript '/usr/share/snapserver/plug-ins/control.py' does not exist","message":"Invalid params"},"id":null,"jsonrpc":"2.0"}, message: {"id":491,"jsonrpc":"2.0","method":"Stream.AddStream","params":{"streamUri":"tcp://0.0.0.0:5097?sampleformat=48000:16:2&idle_threshold=60000&controlscript=control.py&controlscriptparams=--queueid=ma_74563c4f1317%20--socket=%2Ftmp%2Fma-snapcast-ma_74563c4f1317.sock%20--streamserver-ip=192.168.1.34%20--streamserver-port=8097&name=Music Assistant - ma74563c4f1317"}}
```

### ISSUE 2: TCP port range for Music Assistant streams
**Error:** `Unable to create stream - No free port found`

Music Assistant dynamically creates TCP streams on Snapserver using ports in the range **4953-5153**. The addon currently only exposes port 4953. The full range needs to be available.

**Fix options (pick one):**
- Expose the full port range 4953-5153 in config.yaml
- Or use `host_network: true` in config.yaml to avoid port mapping entirely (simpler, recommended for audio addons)

## Plan / TODO

1. **Research the MA control script** — find `control.py` in the Music Assistant server source code and determine how to bundle it
2. **Update Dockerfile** — include the control script at `/usr/share/snapserver/plug-ins/control.py`
3. **Fix port range** — either expose 4953-5153 or switch to host networking in config.yaml
4. **Rebuild and test** — verify Music Assistant can create streams and audio reaches the Windows Snapclient

## Status
Addon is built and running. Snapclient on Windows connects successfully. But playback fails due to the two issues above. These must be fixed before audio can flow.

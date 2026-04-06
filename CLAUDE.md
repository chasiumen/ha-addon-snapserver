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

## Status
Implementation complete. Ready for deployment and testing on HA.

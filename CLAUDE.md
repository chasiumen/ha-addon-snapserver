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

## Resolved Issues

### ISSUE 1: Missing Music Assistant control script — FIXED
**Problem:** MA sends `Stream.AddStream` referencing `controlscript=control.py` which must exist at `/usr/share/snapserver/plug-ins/control.py`.

**Fix:** Bundled control.py from `music-assistant/server` repo (`music_assistant/providers/snapcast/control.py`). Inlined the `format_ip_for_url` helper to avoid depending on the full MA package. Added `python3` and `shortuuid` to Dockerfile.

### ISSUE 2: TCP port range for Music Assistant streams — FIXED
**Problem:** MA uses ports 4953-5153 dynamically; only 4953 was exposed.

**Fix:** Already resolved — `host_network: true` makes all ports available without mapping.

## Planned: Server-Side Audio Quality Controls via HA Entities

### Goal
Expose Snapserver audio quality settings as HA entities so users can adjust codec, sample format, and buffer from the HA UI or automations — without going to the addon config page.

### Architecture
This requires a **companion HA integration** (separate from the addon) that communicates with the Snapserver addon.

```
HA UI / Automation → Snapserver Integration (custom_components/snapserver_control/)
  → Reads/writes addon config via Supervisor API
  → Restarts addon when settings change
```

### Entities to Create

| Entity Type | Entity | Values | Notes |
|---|---|---|---|
| `select` | `select.snapserver_codec` | flac, pcm, opus, vorbis | Changing restarts snapserver |
| `select` | `select.snapserver_sampleformat` | 44100:16:2, 48000:16:2, 96000:24:2, etc. | Preset list + custom option |
| `number` | `number.snapserver_buffer` | 500-5000 ms | Changing restarts snapserver |
| `select` | `select.snapserver_channels` | Stereo (2), Mono (1) | Derived from sampleformat |

### Implementation Approach

**Option A: Companion HA integration (recommended)**
- New repo or folder: `custom_components/snapserver_control/`
- Uses HA Supervisor API to read/write addon options: `POST /addons/24c8c63c_snapserver/options`
- Uses HA Supervisor API to restart addon: `POST /addons/24c8c63c_snapserver/restart`
- Creates select/number entities that reflect current addon config
- On entity change → update addon config → restart addon
- Warning: restart drops all client connections for a few seconds

**Option B: Snapserver JSON-RPC API**
- Snapserver has a JSON-RPC API on port 1705
- Some settings can be changed at runtime via `Server.SetProperty` or `Stream.SetStream`
- Limited: codec and sampleformat may require restart anyway
- Advantage: no addon restart for supported settings

**Option C: Custom services only (simplest)**
- Register services like `snapserver.set_codec(codec)`, `snapserver.set_quality(preset)`
- No entities, just callable services
- Can be used in automations and scripts
- Least UI-friendly but fastest to implement

### Recommended: Start with Option C, evolve to Option A
1. First implement custom services (quick, useful for automations)
2. Then add select/number entities that call those services
3. Investigate JSON-RPC for runtime changes without restart

### Implementation Steps
1. Create `custom_components/snapserver_control/` integration
2. Config flow: auto-detect Snapserver addon by slug
3. Register services: `set_codec`, `set_sampleformat`, `set_buffer`
4. Services read current addon config via Supervisor API, update, restart
5. Add select/number entities that wrap the services
6. Tests for service calls and entity state

### Caveat
Changing codec/sampleformat/buffer **restarts snapserver**, which temporarily disconnects all clients (1-3 seconds). The integration should warn the user or require confirmation for changes that trigger a restart.

## Status
All known issues fixed. Addon includes MA control script, config descriptions, and 68 validation tests. Server-side audio quality controls planned as next enhancement.

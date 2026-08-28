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
- Verified snapserver.conf section names match official docs ([tcp-control], [tcp-streaming],
  [stream]) — re-confirmed against the v0.35.0 tag; an uncommitted working-tree edit currently
  breaks them (see ISSUE 3)
- Verified librespot:// is a built-in snapserver source type (no separate pipe/process needed)
- Verified snapweb must be downloaded from GitHub releases (not an Alpine package)

## Resolved Issues

### ISSUE 1: Missing Music Assistant control script — FIXED
**Problem:** MA sends `Stream.AddStream` referencing `controlscript=control.py` which must exist at `/usr/share/snapserver/plug-ins/control.py`.

**Fix:** Bundled control.py from `music-assistant/server` repo (`music_assistant/providers/snapcast/control.py`). Inlined the `format_ip_for_url` helper to avoid depending on the full MA package. Added `python3` and `shortuuid` to Dockerfile.

### ISSUE 2: TCP port range for Music Assistant streams — FIXED
**Problem:** MA uses ports 4953-5153 dynamically; only 4953 was exposed.

**Fix:** Already resolved — `host_network: true` makes all ports available without mapping.

### ISSUE 3: uncommitted run.sh edit broke the snapserver.conf sections — OPEN
**Problem:** the **working tree** (not the committed code) replaces `[tcp-control]` with `[tcp]`
and deletes the `[tcp-streaming]` block entirely. Checked against `server/etc/snapserver.conf`
at tag **v0.35.0** — the exact version the addon installs — the real sections are
`[tcp-control]` (port 1705) and `[tcp-streaming]` (port 1704). There is no `[tcp]`.

`git diff snapserver/run.sh` shows the committed version was correct; this is an uncommitted
local regression, which is why `tests/test_config.sh` reports 66/68 instead of 68/68. The
tests are right.

**Impact today:** low but real. Upstream defaults both sections to `enabled = true` on their
standard ports, so 1704 and 1705 are open anyway — which is why clients still connect and why
the client-status integration works. But both blocks are now dead config: the addon controls
neither port, and any future attempt to move or disable them will silently do nothing.

**Fix:** `git checkout snapserver/run.sh`, or re-apply `[tcp-control]` / `[tcp-streaming]` by
hand if some other part of that edit was wanted. Deliberately not done as part of the
client-status work: it is someone's uncommitted change, and editing run.sh forces an addon
rebuild and restart that drops every client mid-stream.

Note `snapserver/config.yaml` also has an uncommitted edit (`buffer_ms: int` →
`int(500,10000)`), which looks intentional and correct — it matches the documented range.

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

## Implemented: Client Status Monitoring in the Dashboard

### Problem
When `snapclient.exe` on the Windows host dies — most often because Windows switched the
default output device (line-out → headphones) — nothing on the HA side indicates it. The
Music dashboard keeps showing a playing queue while no audio reaches the speakers, and the
only way to notice is to walk to the PC. We need a visible, at-a-glance indication of each
Snapcast client's connection state, plus state an automation can trigger a notification off.

### Verified protocol facts
Checked against upstream `badaix/snapcast` `doc/json_rpc_api/control.md`:

- The control API is **JSON-RPC 2.0 over a raw TCP socket on port 1705**, messages are
  **newline-delimited JSON (ndjson)**. `[tcp] enabled = true` is hardcoded in `run.sh`, so
  this transport is always available.
- There is also a WebSocket / POST endpoint at port 1780 `/jsonrpc`, but that lives behind
  `[http] enabled = ${SNAPWEB_ENABLED}` — it disappears if the user turns off Snapweb.
  **Therefore: use TCP 1705, not 1780.**
- `Server.GetStatus` returns `result.server.groups[].clients[]`, each client being:
  ```json
  {"config":{"instance":1,"latency":0,"name":"","volume":{"muted":false,"percent":74}},
   "connected":true,
   "host":{"arch":"x86_64","ip":"127.0.0.1","mac":"00:21:6a:7d:74:fc","name":"T400","os":"Linux Mint 17.3"},
   "id":"00:21:6a:7d:74:fc",
   "lastSeen":{"sec":1488026416,"usec":135973},
   "snapclient":{"name":"Snapclient","protocolVersion":2,"version":"0.10.0"}}
  ```
- A dead client is **not** removed from the server's state — it stays in `GetStatus` with
  `connected: false` and a frozen `lastSeen`. This is exactly the signal we need.
- The server **pushes** `Client.OnConnect` / `Client.OnDisconnect` notifications carrying the
  full client object, plus `Server.OnUpdate` for structural changes. So this can be genuine
  `local_push` (the manifest already claims that iot_class).
- `Server.DeleteClient` removes a stale client permanently (needed when a NIC/MAC changes and
  a ghost client would otherwise sit disconnected on the dashboard forever).

### Architecture
```
Snapserver addon (host network, TCP 1705)
        │  ndjson JSON-RPC: Server.GetStatus + pushed Client.On* notifications
        ▼
snapserver_control/rpc.py         ← persistent connection, reconnect w/ backoff
        ▼
snapserver_control/coordinator.py ← DataUpdateCoordinator, {client_id: ClientState}
        ├── binary_sensor.py  per-client connectivity  (automations, history)
        ├── sensor.py         per-client last-seen + summary sensor with clients[] attr
        └── www/snapcast-clients-card.js  ← renders off the summary sensor's attribute
```

Only the companion integration changes. **No addon rebuild** — port 1705 is already exposed
in `snapserver/config.yaml`, so the running stream is never interrupted by this work.

### Transport design
`rpc.py` holds one long-lived asyncio TCP connection:

- `asyncio.open_connection(host, 1705)`, read with `readuntil(b"\n")`, one JSON object per line.
- Requests get an incrementing int `id`; responses are matched to a pending-future map.
- Lines with no `id` are notifications → dispatched to a callback on the coordinator.
- On connect: issue `Server.GetStatus` for a full baseline, then live on notifications.
- Re-issue `Server.GetStatus` every 60s as a resync safety net (cheap, catches missed pushes).
- On read error / EOF: mark server offline, reconnect with backoff (1s → 60s, capped).
- **`rpc.py` imports nothing from Home Assistant.** That keeps it unit-testable standalone
  against a fake ndjson server (see Test plan).

Push updates state instantly; a client that dies shows red within a second or two rather
than at the next poll tick.

### Entity model

| Platform | Entity (example) | State | Notes |
|---|---|---|---|
| `binary_sensor` | `binary_sensor.<client>_connected` | `client.connected` | `device_class: connectivity`, one per client, added dynamically |
| `sensor` | `sensor.<client>_last_seen` | `client.lastSeen.sec` → UTC datetime | `device_class: timestamp`, so the UI shows "12 minutes ago" |
| `sensor` | `sensor.snapserver_clients_connected` | count of connected clients | Carries the full `clients[]` list as an attribute — the card reads this |
| `binary_sensor` | `binary_sensor.snapserver_control_connection` | RPC connection up | Distinguishes "server down" from "client down" |
| `sensor` | `sensor.snapserver_stream_status` | `streams[0].status` (idle/playing) | Distinguishes "nothing playing" from "client dead" |

Attributes on each per-client connectivity sensor: `ip`, `mac`, `host_name`, `os`, `arch`,
`snapclient_version`, `latency_ms`, `volume_percent`, `muted`, `group_id`, `stream_id`,
`instance`, `last_seen`.

Naming and identity:
- Display name = `config.name` if non-empty, else `host.name`, else the client id.
- `unique_id` = `f"{entry_id}_{client_id}_connected"`; `client_id` is the MAC, or `MAC#instance`
  for a second snapclient on the same host — stable across reconnects.
- Each client becomes its own **HA device** (`identifiers={(DOMAIN, client_id)}`,
  `via_device` → the existing Snapserver device), so connectivity + last-seen group together
  and the existing codec/buffer entities stay on the parent Snapserver device.

Availability rule: when the RPC connection is down, per-client entities keep their last known
state and are **not** marked unavailable — only `binary_sensor.snapserver_online` goes off.
Marking everything unavailable would make "server restarted" look identical to "client died".

### Frontend card
`www/snapcast-clients-card.js`, registered in `__init__.py` the same way the Navidrome cards
are (`async_register_static_paths` + `add_extra_js_url`) — see
`ha-music-assistant/custom_components/navidrome/__init__.py:154-171` for the pattern to copy.

The card reads **one** entity, `sensor.snapserver_clients`, and renders its `clients[]`
attribute — the same shape as the Navidrome queue card reading `tracks[]`. That avoids the
card having to query the entity registry to discover clients.

```yaml
type: custom:snapcast-clients-card
entity: sensor.snapserver_clients_connected
title: Speakers
```

One row per client: status dot (green connected / red disconnected), display name,
`192.168.1.42 · v0.31.0` as subtext, and on the right either `Connected` or
`Last seen 12m ago`. Clicking a row opens the more-info dialog for that client's binary
sensor — the summary sensor includes each client's `entity_id`, resolved via the entity
registry (`er.async_get(hass).async_get_entity_id(...)` by unique_id), so the card needs no
registry access of its own. Styling matches the existing dark cards; HTML is escaped through
the same `esc()` helper the Navidrome cards use (client names and hostnames are attacker-
influenced text, so this is not optional).

### Config flow changes
- Add `rpc_host` (default `127.0.0.1`) and `rpc_port` (default `1705`) to the config flow.
  `127.0.0.1` works because the addon runs with `host_network: true` and HA Core is
  host-networked on HAOS; the field exists as an escape hatch for supervised installs where
  it isn't.
- Add an **options flow** so host/port can be corrected without deleting the config entry.
- Existing config entries have neither key — read with `entry.options.get(..., default)` so
  they keep working untouched. No migration needed.

### New service
`snapserver_control.delete_client` → `Server.DeleteClient`, to purge a ghost client that will
never reconnect (MAC change, decommissioned machine). Registered alongside the existing three
services, with matching `services.yaml` / `strings.json` / `translations/en.json` entries —
note the test suite asserts `strings.json` and `translations/en.json` are byte-identical.

### Failure modes to handle explicitly
| Case | Expected behavior |
|---|---|
| Snapserver addon stopped / restarting | `snapserver_online` off, client entities hold last state, reconnect loop retries with backoff |
| Config entry unloaded / HA shutdown | Reader task cancelled and socket closed cleanly — no orphan task, no "Task was destroyed" warnings |
| Client reconnects with same MAC | Existing entity flips back on; no duplicate entity created |
| Brand-new client appears while running | Entities created dynamically without a reload |
| Malformed / partial line on the socket | Log at debug, skip the line, keep the connection |
| `lastSeen.sec == 0` (never seen) | Report `None` rather than 1970-01-01 |

### Test plan
Extends `tests/test_companion.sh` (structural, matching existing style) with checks that the
new files exist, that `PLATFORMS` includes `BINARY_SENSOR`/`SENSOR`, that the card is
registered, and that the new service appears in all three strings files.

Adds one genuinely functional test, `tests/test_rpc.py` — runnable with plain `python3`, no
Home Assistant install required, which is why `rpc.py` is kept HA-free:
1. Spin up a fake ndjson server on an ephemeral localhost port.
2. Assert the client sends well-formed `Server.GetStatus` and parses the documented response
   into the expected client dicts.
3. Push a `Client.OnDisconnect` notification and assert the parsed state flips to disconnected.
4. Kill the fake server and assert the client reconnects rather than raising.

### Implementation order (all steps done)
1. `rpc.py` + `tests/test_rpc.py` — get the protocol layer right and proven first.
2. `const.py` additions, `coordinator.py`.
3. `binary_sensor.py`, `sensor.py`, `PLATFORMS` wiring in `__init__.py`.
4. `config_flow.py` host/port + options flow.
5. `delete_client` service + the three strings files.
6. `www/snapcast-clients-card.js` + static path registration.
7. Extend `tests/test_companion.sh`; README section with the card YAML and an example
   "notify me if the client has been down 2 minutes" automation.

### As built — deviations from the plan
- Added `entity.py` holding the shared `SnapserverEntity` / `SnapclientEntity` bases, rather
  than repeating device wiring in both platforms.
- Added `tests/test_coordinator.py` (7 tests). Home Assistant isn't installed in this repo's
  dev environment, so it stubs `DataUpdateCoordinator` and imports `coordinator.py` under a
  synthetic package name to avoid executing the HA-heavy `__init__.py`. It proves the merge
  logic, **not** that the integration loads inside HA — that remains unverified here and is
  only exercised by installing it on the real HA instance.
- The card re-renders on a 30s timer as well as on state change, because "last seen 3m ago"
  goes stale on its own with no state update to trigger a repaint.
- `tests/test_companion.sh` probes each Python candidate by running it, because on Windows
  `python3` resolves to the Microsoft Store stub, which exits non-zero without running.

### Out of scope (host-side, worth doing separately)
This surfaces *when* to restart the client; it does not stop the client from dying. Two
mitigations on the Windows host, outside this repo:
- `snapclient.exe -s <device>` to pin the output device so a default-device change is ignored.
- Run it under NSSM (or a Scheduled Task with restart-on-failure) so it self-recovers.

## Status
Addon includes MA control script and config descriptions. Server-side audio quality controls
and client status monitoring are both shipped in the `snapserver_control` companion
integration.

**Tests:** `tests/test_companion.sh` 76/76 pass (this runs the two Python suites, 18 tests,
as its last section). `tests/test_config.sh` 66/68 — the 2 failures come from an uncommitted
edit to `snapserver/run.sh` (ISSUE 3), not from the client-status work.

**Not verified locally:** Home Assistant is not installed in this dev environment, so the
HA-facing modules (`__init__.py`, platforms, `config_flow.py`, `entity.py`) are syntax-checked
and structurally tested but have never been imported against a real HA runtime. First install
on the live instance is the real test.

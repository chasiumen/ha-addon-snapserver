# Implementation Plan: Working Sample-Format Control (MA-backed)

> **For the executing model:** This plan is self-contained. Every behavioral claim in it was
> verified from source on 2026-08-29 with file:line citations — treat the Ground Truth section
> as fact and do NOT re-derive it from memory. If you need to re-check something, fetch with
> `gh api 'repos/<owner>/<repo>/contents/<path>' --jq '.content' | base64 -d` (append
> `?ref=<tag>` inside the quotes to pin). The GitHub search API is NOT available. Follow the
> "RULE: Verify from source" section at the top of CLAUDE.md at all times.

## 0. Mission

`select.snapserver_sample_format` in the `snapserver_control` integration currently writes the
Snapserver addon's `sampleformat` option and restarts the addon. That has **zero audible
effect**: Music Assistant (MA) creates its own stream with `sampleformat=` baked into its
`Stream.AddStream` URI, overriding the addon's global default. Rework the entity so it writes
**Music Assistant's provider config** via MA's HTTP API instead — the only place the value is
actually honored. Codec and buffer entities are verified working and must NOT change.

## 1. Ground truth (verified, do not re-litigate)

| # | Fact | Source |
|---|---|---|
| 1 | MA overrides `sampleformat` per-stream; snapserver only falls back to the global `[stream]` default when the URI omits the key. MA always includes it. Codec IS omitted by MA (global default applies → codec select works). Buffer is server-global with no per-stream override (→ buffer slider works). | snapcast `server/streamreader/stream_manager.cpp:73-80`; user's addon log showing MA's AddStream URI |
| 2 | MA honors `snapcast_stream_sample_rate` + `snapcast_stream_bit_depth` **only when `snapcast_use_external_server` is true**; built-in mode hardcodes 48000:16:2. | music-assistant/server `music_assistant/providers/snapcast/provider.py:288-295` |
| 3 | Supported values: rates `(48000, 96000, 192000)`, depths `(16, 24)`, `channels=2` hardcoded. 44100 and mono are impossible. | `music_assistant/providers/snapcast/constants.py` (`SNAPCAST_SAMPLE_RATES`, `SNAPCAST_BIT_DEPTHS`, `snapcast_stream_format`) |
| 4 | **24-bit must be EXCLUDED.** MA appends `packed_s24le=true` for 24-bit, but snapcast v0.35.0 (what the addon ships) has no `packed_s24le` support — PR snapcast/snapcast#1532 is unmerged, in NO release. Snapserver silently ignores the param and misparses packed 24-bit as 24-in-32 → corrupted audio. | grep of `server/streamreader/*` + `common/*` at `?ref=v0.35.0` (zero matches); `gh api repos/badaix/snapcast/issues/1532` (state=open, merged=false) |
| 5 | MA API endpoint: `POST /api` on the MA webserver (port 8095). Body: `{"message_id": "<any string>", "command": "<cmd>", "args": {...}}`. Auth: `Authorization: Bearer <token>`. Success = HTTP 200, the handler's return value serialized **directly** as the JSON body (no envelope). Errors: 401 (bad/missing token, plain text, `WWW-Authenticate: Bearer` header), 403 (insufficient scope, plain text "This command requires the ... scope"), 400, 500. | `music_assistant/controllers/webserver/controller.py:328` (route), `:760-830` (handler), `:864-868` (scope check) |
| 6 | **The HA integration's auto-minted token CANNOT write provider config.** `config/providers/save` requires `Scope.CONFIG_PROVIDERS_WRITE`; `ROLE_SCOPES` grants that to **ADMIN only** (via `Scope.ALL`). The auto-minted token is role SERVICE. → the user must supply an **admin long-lived token**. | `music_assistant/controllers/webserver/helpers/auth_middleware.py:32-63,184-192`; `controllers/config/providers.py:279`; `controllers/webserver/auth.py:418-429` |
| 7 | `config/providers/save` semantics: **MERGE** (send only changed keys; others preserved, including undeclared stored values), **auto-reloads the provider inside the save call** (no separate reload needed), no-op short-circuit when nothing changed, and **unknown keys are silently DROPPED** (not rejected). → verify-after-write is mandatory. | `controllers/config/providers.py:279-301,500-545`; `models/provider.py:120-145`; music-assistant/models `config_entries.py:534` |
| 8 | Because the reload happens inside the save handler, **the save HTTP request can take 10–20+ seconds** (snapcast provider unload includes an up-to-10 s stream-idle wait: `providers/snapcast/ma_stream.py:404-421`, `timeout=10.0`). Use a ≥90 s client timeout for save. | ibid. |
| 9 | HA core's `music_assistant` integration: DOMAIN `"music_assistant"`, config entry stores `CONF_URL` (always) and `CONF_TOKEN` (optional — absent for old servers; present = the discovery-announced SERVICE token OR a user-pasted token). It exposes NO service/entity that writes provider config. Pins `music-assistant-client==1.5.1`. | home-assistant/core `homeassistant/components/music_assistant/` const.py:5, config_flow.py:118-200, `__init__.py:88-93`, manifest.json |
| 10 | Useful read commands (all need only `CONFIG_PROVIDERS_READ`, which even SERVICE has): `config/providers` (args may include `provider_domain`), `config/providers/get` (`instance_id`), `config/providers/get_value` (`instance_id`, `key` → returns the raw value). | `controllers/config/providers.py:83-196`; client-lib signatures in music-assistant/client `music_assistant_client/config.py:31-117` |
| 11 | Scope-probe trick: calling `save` with **current values** is a safe write-permission probe — the 403 scope gate runs BEFORE the merge/no-op logic, so: 403 → token lacks admin; 200 → token good and nothing changed. | order of checks in `controller.py:_handle_jsonrpc_api_command` (auth at ~:798 before handler execution at :808) |
| 12 | Reload cost on THIS path (config-save, external mode already on): no 5 s disconnect debounce, no built-in-server spawn. Expect ~8–12 s if music is playing (≈5 s stream-idle drain + reconnect), ~2–3 s if idle. The user's measured 20–40 s was the crash path; do not cite it as this feature's cost. | decomposition in CLAUDE.md; `provider.py:_handle_disconnect` (debounce only on disconnect path); `unload()` at `provider.py:340-357` |
| 13 | The MERGE in fact 7 means our first write also flips `snapcast_use_external_server: true` + host + port in the same call — one-time transition off MA's built-in server (which currently fails to bind 1704/1705/1780 every reload anyway, per the user's MA log). | user's MA log; `provider.py:256` |

**MA config keys to write** (exact names, from `providers/snapcast/constants.py`):

```python
"snapcast_use_external_server": True      # bool
"snapcast_server_host": "127.0.0.1"       # str
"snapcast_server_control_port": 1705      # int
"snapcast_stream_sample_rate": 48000      # int — one of 48000/96000/192000
"snapcast_stream_bit_depth": 16           # int — ALWAYS 16 (fact 4)
```

## 2. Architecture

```
select.snapserver_sample_format ──> ma_client.py ──POST /api──> MA config/providers/save
        │                                                             │ (auto-reloads snapcast provider)
        │<── verify-after-write (config/providers/get_value ×2) ──────┘
        └──> background auto-resume: wait for MA media_players to return, re-issue play
Codec select / buffer number ──> supervisor.py (UNCHANGED — verified working)
```

## 3. File-by-file specification

### 3.1 NEW `custom_components/snapserver_control/ma_client.py` (~170 LOC)

Zero HA imports (same rule as `rpc.py` — this is what makes it unit-testable standalone).
Uses `aiohttp` (available in HA; tests inject a fake session). Constructor:
`MusicAssistantClient(url: str, token: str, session: aiohttp.ClientSession)`.
Strip trailing `/` from url; endpoint is `f"{url}/api"`.

Request helper `_command(command, args, timeout)` → POST JSON
`{"message_id": str(self._next_id), "command": command, "args": args}` with
`Authorization: Bearer <token>`. Response handling:
- 200 → `await resp.json()` (result is the bare handler return value — a list, dict, scalar, or null)
- 401 → raise `MusicAssistantAuthError` ("invalid or expired token")
- 403 → raise `MusicAssistantScopeError` ("token lacks admin rights — create a long-lived token for an admin user")
- other → raise `MusicAssistantApiError` with status + body text

Methods:
- `async get_snapcast_instance_id() -> str` — `config/providers` with args `{"provider_domain": "snapcast"}`; result is a list of provider-config dicts; parse defensively (require `instance_id` and `domain` keys; filter `domain == "snapcast"`; raise `MusicAssistantApiError` if none). Timeout 15 s.
- `async get_value(instance_id, key)` — `config/providers/get_value`, args `{"instance_id":..., "key":...}` → raw value. Timeout 15 s.
- `async save_snapcast_config(instance_id, values: dict)` — `config/providers/save`, args `{"provider_domain": "snapcast", "instance_id": instance_id, "values": values}`. **Timeout 90 s** (fact 8). Returns the response (full ProviderConfig dict) but callers must not rely on its shape.
- `async probe_write_access(instance_id) -> bool` — fact 11: read `snapcast_stream_sample_rate` via `get_value`, then `save` it back unchanged as the only key. Return True on 200; False on `MusicAssistantScopeError`; re-raise everything else.
- `async verify_values(instance_id, expected: dict) -> dict` — `get_value` per key; return dict of mismatches (empty = success). Used post-save (fact 7: silent key-drop).

Error classes at module top: `MusicAssistantApiError(Exception)` → `MusicAssistantAuthError`, `MusicAssistantScopeError` subclasses.

### 3.2 `const.py` — replace the sample-format matrix

```python
# 16-bit only: snapserver <= 0.35.0 lacks packed_s24le ingest (snapcast PR #1532 unmerged);
# MA sends packed s24le for 24-bit which v0.35.0 would misparse into corrupted audio.
# 44100 and mono are not offered: MA supports rates (48000, 96000, 192000) and hardcodes channels=2.
SAMPLEFORMAT_OPTIONS = ["48000:16:2", "96000:16:2", "192000:16:2"]
```
Add: `CONF_MA_URL = "ma_url"`, `CONF_MA_TOKEN = "ma_token"`, `MA_INTEGRATION_DOMAIN = "music_assistant"`,
`MA_KEY_USE_EXTERNAL = "snapcast_use_external_server"`, `MA_KEY_HOST = "snapcast_server_host"`,
`MA_KEY_PORT = "snapcast_server_control_port"`, `MA_KEY_SAMPLE_RATE = "snapcast_stream_sample_rate"`,
`MA_KEY_BIT_DEPTH = "snapcast_stream_bit_depth"`.
Keep `CODEC_OPTIONS`, buffer constants, and all existing keys untouched.

### 3.3 `config_flow.py` — MA credentials step

- After the existing addon check succeeds, add `async_step_ma`:
  - Pre-fill URL: `hass.config_entries.async_entries("music_assistant")` → first entry's `data[CONF_URL]`; fall back to `http://127.0.0.1:8095`. Token field: pre-fill from that entry's `data.get(CONF_TOKEN)` if present.
  - On submit: build client (session via `async_get_clientsession(hass)`), `get_snapcast_instance_id()` (errors → `cannot_connect_ma` / `invalid_ma_token` for 401), then `probe_write_access()`; False → error `ma_token_not_admin` with the form shown again (description tells the user to create a long-lived token for an admin user in MA → Settings → Users). True → create entry with `ma_url`/`ma_token` in data.
  - A "skip" checkbox (`configure_ma_later`, default False): if checked, create the entry WITHOUT MA creds — sample-format entity will be unavailable until configured via options.
- Options flow: add the same two fields alongside the existing rpc host/port; saving re-validates (same probe) and reloads the entry (existing listener already does this).
- **Existing entries have no MA keys** — everything reads with `.get(...)`; no migration.

### 3.4 `select.py` — rework `SnapserverSampleformatSelect`

Keep `unique_id` = `f"{entry.entry_id}_sampleformat"` (preserves entity id + history). New behavior:
- Constructed with the MA client (or `None` when unconfigured) + current value read from MA at setup: `get_value(instance_id, MA_KEY_SAMPLE_RATE)` + bit depth → `f"{rate}:{depth}:2"`; if depth is 24 (user set it in MA's own UI), still display it but log a warning citing fact 4. If MA unreachable/unconfigured at setup → current option None, `available = False`.
- `async_select_option(option)`:
  1. Parse rate from `option.split(":")[0]`.
  2. `values = {MA_KEY_SAMPLE_RATE: rate, MA_KEY_BIT_DEPTH: 16, MA_KEY_USE_EXTERNAL: True, MA_KEY_HOST: "127.0.0.1", MA_KEY_PORT: 1705}` (facts 2, 13).
  3. Snapshot playing MA players (see 3.6) BEFORE the save.
  4. `await save_snapcast_config(...)` — this blocks through MA's provider reload (fact 8); surface `MusicAssistantScopeError`/`MusicAssistantAuthError` as `HomeAssistantError` with the token guidance.
  5. `mismatches = await verify_values(...)` for the two stream keys; non-empty → raise `HomeAssistantError(f"MA did not accept: {mismatches} — key names may have changed in a newer MA version")` and do NOT update state (fact 7).
  6. Update `_attr_current_option`, write state.
  7. `hass.async_create_task(auto_resume(snapshot))` — fire-and-forget (3.6).
- **Must NOT call `restart_addon()` or touch the Supervisor** on this path. `SnapserverCodecSelect` and its `_update_and_restart` base stay exactly as they are — restructure the base class so the codec path is untouched (e.g. move `_update_and_restart` into `SnapserverCodecSelect` or keep base and override).

### 3.5 `__init__.py` — wiring

- `SnapserverControlData` gains `ma: MusicAssistantClient | None` and `ma_instance_id: str | None`.
- In `async_setup_entry`: if `ma_url`+`ma_token` in entry data/options → build client, resolve `ma_instance_id` once (wrap in try; on failure log warning, set both None — do NOT fail the whole entry; codec/buffer/status must keep working).
- Rework service `set_sampleformat` to call the same MA path (or, where the client is None, raise a clear error). `services.yaml`/strings: update its description and its options list to the three 16-bit values.

### 3.6 Auto-resume (best-effort, ~80 LOC — helper in `__init__.py` or new `resume.py`)

- Snapshot: entity registry entities where `platform == "music_assistant"` and domain `media_player`, whose current state is `playing`. Record entity_ids.
- After save: loop up to 60 s (3 s interval): for each snapshotted entity, when its state is no longer `unavailable`/`unknown`, call `media_player.media_play` on it once, then keep polling; stop early when all report `playing`. Log (info) what was resumed; log (warning) on give-up. **Never raise** — wrap everything.

### 3.7 Strings ×3 + services.yaml

- `strings.json` and `translations/en.json` MUST stay byte-identical (test asserts `diff`).
- New config-flow step `ma` strings (title, data labels for `ma_url`/`ma_token`, `data_description` explaining the admin long-lived token + where to create it), errors: `cannot_connect_ma`, `invalid_ma_token`, `ma_token_not_admin`. Same additions under `options`.
- Update `set_sampleformat` service description: "Changes Music Assistant's Snapcast stream format. Reloads the MA Snapcast provider (~10 s audio interruption). Does NOT restart the Snapserver addon."
- `services.yaml`: sampleformat selector options → the three 16-bit values.

### 3.8 `manifest.json`

Version → `0.3.0`. No new `requirements` (aiohttp is a HA core dependency already used by `supervisor.py`).

### 3.9 Docs

- README "Snapserver Control Integration" section: sample-format now controls MA (the only place it works); token setup steps (MA UI → Settings → Users → your admin user → create long-lived token); expected ~8–12 s dip + auto-resume; note that codec/buffer still restart the addon; warning not to select 24-bit inside MA's own UI (fact 4).
- CLAUDE.md: update the "Implemented" section status; add a short "Who owns which audio setting" table (codec=addon, buffer=addon, sampleformat=MA).

## 4. Tests

Local env: **no HA, no aiohttp installed**. Run with `python` (NOT `python3` — MS Store stub). Wrap runs in `timeout`.

### 4.1 NEW `tests/test_ma_client.py` (~250 LOC)

Import `ma_client.py` directly (it has no HA imports). Stub aiohttp before import:
`sys.modules["aiohttp"] = types.ModuleType("aiohttp")` with minimal `ClientTimeout`, `ClientError` attrs — then inject a **FakeSession** into the client (records every `post(url, json=..., headers=..., timeout=...)`; returns queued fake responses with `.status`, `.json()`, `.text()`, async-context-manager protocol).
Cases (≥12):
1. `_command` sends Bearer header, correct URL (`<url>/api`), correct body shape (message_id str, command, args).
2. 200 returns parsed JSON as-is.
3. 401 → `MusicAssistantAuthError`; 403 → `MusicAssistantScopeError`; 500 → `MusicAssistantApiError` (status preserved).
4. `get_snapcast_instance_id`: filters `domain=="snapcast"`, passes `provider_domain` arg, raises when absent, tolerates extra keys in items.
5. `save_snapcast_config` arg shape: `provider_domain`, `instance_id`, `values` — and uses the 90 s timeout while reads use 15 s (assert recorded timeout values differ).
6. `probe_write_access`: 200→True, 403→False, 401 re-raised.
7. `verify_values`: all-match → `{}`; mismatch → reported with actual value.
8. Trailing-slash URL normalized.

### 4.2 Extend `tests/test_entities.py`

The stub harness already exists — extend `_install_stubs` with a fake `ma_client` module + a FakeMaClient recorder, and stub `homeassistant.exceptions.HomeAssistantError` + `homeassistant.helpers.aiohttp_client` as needed. New cases (≥6):
1. Sampleformat change calls `save_snapcast_config` with exactly the 5 keys (values asserted, incl. `bit_depth == 16` and `use_external_server is True`).
2. Sampleformat change performs verify-after-write and does NOT touch the supervisor (FakeSupervisorClient records zero calls).
3. Verify mismatch → raises, state NOT updated.
4. Scope error → raises with guidance text.
5. Codec test unchanged: still `get → set → restart` on supervisor (guards the split).
6. Unconfigured MA (client None) → entity `available is False`, select raises cleanly.

### 4.3 `tests/test_companion.sh` additions (structural)

- `ma_client.py` exists; has no `homeassistant` imports; defines the three error classes.
- `select.py` references `save_snapcast_config` and does NOT contain `restart_addon` in the sampleformat class (grep between class markers, or simply assert `ma_client` referenced).
- const.py contains `192000:16:2` and does NOT contain `44100:16:1`; contains no `:24:` option.
- strings/en.json still identical.
- Add `test_ma_client.py` to the python-suite loop.

### 4.4 Run everything

```bash
timeout 120 python tests/test_ma_client.py
timeout 120 python tests/test_entities.py
timeout 180 bash tests/test_companion.sh   # must end 0 failed
timeout 120 bash tests/test_config.sh      # 2 pre-existing failures are ISSUE 3 (uncommitted
                                           # run.sh edit) — NOT yours; do not fix, do not commit it
```

## 5. Environment & repo gotchas (read before coding)

1. **Working tree contains uncommitted user edits to `snapserver/run.sh` and `snapserver/config.yaml` (ISSUE 3 in CLAUDE.md). NEVER stage, commit, revert, or "fix" them.** Stage files explicitly by name; never `git add -A`/`git add .`.
2. Git workflow per the user's global rules: branch off master (`git fetch origin && git checkout master && git pull` first — PRs may have merged), feature branch e.g. `feature/ma-sampleformat`, present a description and WAIT for explicit approval before committing, no AI attribution in commits/PRs, PR via `gh pr create`.
3. Windows Git Bash. `python` = 3.12; `python3` = broken Store stub. Long-running commands need `timeout N`. `strings.json` ↔ `translations/en.json` byte-identical (a test enforces it — edit one, `cp` to the other).
4. The repo is private; `gh api` works for reading upstream repos; GitHub *search* API does not.
5. Do not add `music-assistant-client` as a requirement (WebSocket-only transport; version-pinned by HA core — hand-rolled HTTP is the design decision, already settled).
6. MA server source was verified at the default branch on 2026-08-29 (MA addon v2.10.1 era). If a save silently no-ops in live testing, suspect key renames (fact 7) — the verify-after-write error message covers this.

## 6. Execution order

1. `ma_client.py` + `tests/test_ma_client.py` → green.
2. `const.py` changes → run `test_entities.py` (options-match test will fail until select.py updated — fine, proceed).
3. `select.py` rework + `__init__.py` wiring + auto-resume helper.
4. `config_flow.py` + strings ×3 + `services.yaml`.
5. Extend `test_entities.py` + `test_companion.sh` → all suites green.
6. `manifest.json` 0.3.0, README, CLAUDE.md.
7. Present PR description → wait for approval → branch, commit, push, `gh pr create`.

## 7. Live verification (user does this after merge)

1. Update the integration via HACS → restart HA.
2. Integration options → confirm MA URL; create + paste an **admin long-lived token** (MA UI → Settings → Users). Expect the probe to pass.
3. Start music. Flip `select.snapserver_sample_format` to `96000:16:2`.
4. Watch the Snapserver **addon** log: MA should re-add its stream with `sampleformat=96000:16:2` in the `Stream.AddStream` URI within ~15 s. Audio should auto-resume without manual clicks.
5. In MA UI → Settings → Providers → Snapcast: confirm "use external server" is now ON and MA's log no longer shows `Starting builtin Snapserver` / `Address already in use` on provider reload.
6. `sensor.snapserver_stream_status` should return to `playing`.

## 8. Out of scope

- 24-bit (blocked upstream: snapcast PR #1532 unmerged — revisit when a snapcast release includes it AND the addon ships that version).
- Mono / 44100 (MA hardcodes `channels=2`; 44100 not offered — fact 3).
- Hot-swap without provider reload (needs an upstream MA change; candidate future PR to music-assistant/server).
- The pre-existing `control.py` Unix-socket errors in the addon log (separate cross-container issue, tracked in CLAUDE.md; expected to disappear for MA-created streams once external mode is active, but not a goal here).

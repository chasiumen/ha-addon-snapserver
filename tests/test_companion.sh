#!/bin/bash
# Tests for Snapserver Control companion integration
# Run: bash tests/test_companion.sh

set -e

PASS=0
FAIL=0
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
COMP_DIR="$REPO_DIR/custom_components/snapserver_control"

pass() { PASS=$((PASS + 1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL + 1)); echo "  FAIL: $1"; }

echo "=== Snapserver Control Integration Tests ==="
echo ""

# --- Test 1: Required files exist ---
echo "--- File structure ---"

for f in \
    "__init__.py" \
    "binary_sensor.py" \
    "config_flow.py" \
    "const.py" \
    "coordinator.py" \
    "entity.py" \
    "ma_client.py" \
    "manifest.json" \
    "number.py" \
    "resume.py" \
    "rpc.py" \
    "select.py" \
    "sensor.py" \
    "services.yaml" \
    "strings.json" \
    "supervisor.py" \
    "translations/en.json" \
    "www/snapcast-clients-card.js"; do
    if [ -f "$COMP_DIR/$f" ]; then
        pass "$f exists"
    else
        fail "$f missing"
    fi
done

# --- Test 2: manifest.json ---
echo ""
echo "--- manifest.json ---"

MANIFEST="$COMP_DIR/manifest.json"

for field in '"domain"' '"name"' '"config_flow"' '"version"'; do
    if grep -q "$field" "$MANIFEST"; then
        pass "manifest has $field"
    else
        fail "manifest missing $field"
    fi
done

if grep -q '"snapserver_control"' "$MANIFEST"; then
    pass "manifest domain is snapserver_control"
else
    fail "manifest domain incorrect"
fi

# --- Test 3: const.py ---
echo ""
echo "--- const.py ---"

CONST="$COMP_DIR/const.py"

if grep -q 'ADDON_SLUG' "$CONST"; then
    pass "const.py defines ADDON_SLUG"
else
    fail "const.py missing ADDON_SLUG"
fi

if grep -q 'CODEC_OPTIONS' "$CONST"; then
    pass "const.py defines CODEC_OPTIONS"
else
    fail "const.py missing CODEC_OPTIONS"
fi

if grep -q 'SAMPLEFORMAT_OPTIONS' "$CONST"; then
    pass "const.py defines SAMPLEFORMAT_OPTIONS"
else
    fail "const.py missing SAMPLEFORMAT_OPTIONS"
fi

for codec in flac pcm opus vorbis; do
    if grep -q "\"$codec\"" "$CONST"; then
        pass "const.py has codec '$codec'"
    else
        fail "const.py missing codec '$codec'"
    fi
done

# --- Test 4: supervisor.py ---
echo ""
echo "--- supervisor.py ---"

SUPERVISOR="$COMP_DIR/supervisor.py"

if grep -q 'SUPERVISOR_TOKEN' "$SUPERVISOR"; then
    pass "supervisor.py uses SUPERVISOR_TOKEN"
else
    fail "supervisor.py missing SUPERVISOR_TOKEN"
fi

for method in get_addon_options set_addon_options restart_addon is_addon_installed; do
    if grep -q "async def $method" "$SUPERVISOR"; then
        pass "supervisor.py has method $method"
    else
        fail "supervisor.py missing method $method"
    fi
done

if grep -q "addons.*options" "$SUPERVISOR"; then
    pass "supervisor.py calls addon options API"
else
    fail "supervisor.py missing addon options API call"
fi

if grep -q "addons.*restart" "$SUPERVISOR"; then
    pass "supervisor.py calls addon restart API"
else
    fail "supervisor.py missing addon restart API call"
fi

# --- Test 5: select.py ---
echo ""
echo "--- select.py ---"

SELECT="$COMP_DIR/select.py"

if grep -q 'SnapserverCodecSelect' "$SELECT"; then
    pass "select.py has SnapserverCodecSelect"
else
    fail "select.py missing SnapserverCodecSelect"
fi

if grep -q 'SnapserverSampleformatSelect' "$SELECT"; then
    pass "select.py has SnapserverSampleformatSelect"
else
    fail "select.py missing SnapserverSampleformatSelect"
fi

if grep -q 'async_select_option' "$SELECT"; then
    pass "select.py implements async_select_option"
else
    fail "select.py missing async_select_option"
fi

if grep -q 'restart_addon' "$SELECT"; then
    pass "select.py restarts addon on change"
else
    fail "select.py should restart addon on change"
fi

# --- Test 6: number.py ---
echo ""
echo "--- number.py ---"

NUMBER="$COMP_DIR/number.py"

if grep -q 'SnapserverBufferNumber' "$NUMBER"; then
    pass "number.py has SnapserverBufferNumber"
else
    fail "number.py missing SnapserverBufferNumber"
fi

if grep -q 'async_set_native_value' "$NUMBER"; then
    pass "number.py implements async_set_native_value"
else
    fail "number.py missing async_set_native_value"
fi

if grep -q 'restart_addon' "$NUMBER"; then
    pass "number.py restarts addon on change"
else
    fail "number.py should restart addon on change"
fi

if grep -q 'SLIDER' "$NUMBER"; then
    pass "number.py uses slider mode"
else
    fail "number.py should use slider mode"
fi

# --- Test 7: services.yaml ---
echo ""
echo "--- services.yaml ---"

SERVICES="$COMP_DIR/services.yaml"

for svc in set_codec set_sampleformat set_buffer; do
    if grep -q "$svc:" "$SERVICES"; then
        pass "services.yaml defines $svc"
    else
        fail "services.yaml missing $svc"
    fi
done

# --- Test 8: __init__.py services ---
echo ""
echo "--- __init__.py ---"

INIT="$COMP_DIR/__init__.py"

for svc in set_codec set_sampleformat set_buffer; do
    if grep -q "\"$svc\"" "$INIT"; then
        pass "__init__.py registers service $svc"
    else
        fail "__init__.py missing service registration for $svc"
    fi
done

if grep -q 'async_remove' "$INIT"; then
    pass "__init__.py removes services on unload"
else
    fail "__init__.py should remove services on unload"
fi

# --- Test 9: strings consistency ---
echo ""
echo "--- Strings consistency ---"

STRINGS="$COMP_DIR/strings.json"
TRANSLATIONS="$COMP_DIR/translations/en.json"

if diff -q "$STRINGS" "$TRANSLATIONS" > /dev/null 2>&1; then
    pass "strings.json matches translations/en.json"
else
    fail "strings.json and translations/en.json differ"
fi

# --- Test 10: client status monitoring ---
echo ""
echo "--- Client status monitoring ---"

RPC="$COMP_DIR/rpc.py"
COORD="$COMP_DIR/coordinator.py"
BINARY_SENSOR="$COMP_DIR/binary_sensor.py"
SENSOR="$COMP_DIR/sensor.py"
CARD="$COMP_DIR/www/snapcast-clients-card.js"

# The control socket is on 1705, which is always enabled. Port 1780 only exists
# while the addon's snapweb_enabled option is on, so it must not be used here.
if grep -q '1705' "$COMP_DIR/const.py"; then
    pass "const.py uses control port 1705"
else
    fail "const.py should default to control port 1705"
fi

if grep -qE '[=(]\s*1780' "$RPC"; then
    fail "rpc.py must not depend on the snapweb port (1780)"
else
    pass "rpc.py does not depend on the snapweb port"
fi

# rpc.py stays free of Home Assistant imports so tests/test_rpc.py can exercise
# it standalone; breaking this breaks the only real protocol test.
if grep -q '^from homeassistant\|^import homeassistant' "$RPC"; then
    fail "rpc.py must not import homeassistant"
else
    pass "rpc.py has no homeassistant imports"
fi

for symbol in Server.GetStatus Client.OnDisconnect Server.DeleteClient; do
    if grep -q "$symbol" "$RPC"; then
        pass "rpc.py handles $symbol"
    else
        fail "rpc.py missing $symbol"
    fi
done

if grep -q 'async def _read_loop' "$RPC" && grep -q 'BACKOFF_MAX' "$RPC"; then
    pass "rpc.py reads ndjson with reconnect backoff"
else
    fail "rpc.py missing ndjson read loop or reconnect backoff"
fi

for symbol in _handle_status _handle_client _handle_connection_change; do
    if grep -q "def $symbol" "$COORD"; then
        pass "coordinator.py has $symbol"
    else
        fail "coordinator.py missing $symbol"
    fi
done

if grep -q 'CONNECTIVITY' "$BINARY_SENSOR"; then
    pass "binary_sensor.py uses the connectivity device class"
else
    fail "binary_sensor.py should use the connectivity device class"
fi

if grep -q 'async_add_listener' "$BINARY_SENSOR" && grep -q 'async_add_listener' "$SENSOR"; then
    pass "platforms add newly discovered clients dynamically"
else
    fail "platforms should add newly discovered clients dynamically"
fi

if grep -q 'TIMESTAMP' "$SENSOR"; then
    pass "sensor.py exposes last-seen as a timestamp"
else
    fail "sensor.py should expose last-seen as a timestamp"
fi

if grep -q '"clients"' "$SENSOR"; then
    pass "sensor.py publishes the client roster attribute"
else
    fail "sensor.py missing the client roster attribute the card reads"
fi

# --- Test 11: platform and frontend wiring ---
echo ""
echo "--- Platform and frontend wiring ---"

for platform in BINARY_SENSOR SENSOR SELECT NUMBER; do
    if grep -q "Platform.$platform" "$INIT"; then
        pass "__init__.py registers the $platform platform"
    else
        fail "__init__.py missing the $platform platform"
    fi
done

if grep -q 'async_register_static_paths' "$INIT" && grep -q 'add_extra_js_url' "$INIT"; then
    pass "__init__.py serves and loads the frontend card"
else
    fail "__init__.py should serve and load the frontend card"
fi

if grep -q 'delete_client' "$INIT" && grep -q 'delete_client' "$SERVICES"; then
    pass "delete_client service is registered and declared"
else
    fail "delete_client service missing from __init__.py or services.yaml"
fi

if grep -q 'async_get_options_flow' "$COMP_DIR/config_flow.py"; then
    pass "config_flow.py exposes an options flow"
else
    fail "config_flow.py should expose an options flow"
fi

if grep -q 'customElements.define("snapcast-clients-card"' "$CARD"; then
    pass "card registers the snapcast-clients-card element"
else
    fail "card missing customElements.define"
fi

# Client names and hostnames come from the network, so they must be escaped.
if grep -q 'function esc(' "$CARD" && grep -q 'esc(client.name)' "$CARD"; then
    pass "card escapes client-supplied text"
else
    fail "card must escape client-supplied text"
fi

# --- Test 11b: MA-backed sample format ---
echo ""
echo "--- MA-backed sample format ---"

MACLIENT="$COMP_DIR/ma_client.py"

# ma_client.py stays free of Home Assistant imports so tests/test_ma_client.py
# can exercise it standalone.
if grep -q '^from homeassistant\|^import homeassistant' "$MACLIENT"; then
    fail "ma_client.py must not import homeassistant"
else
    pass "ma_client.py has no homeassistant imports"
fi

for symbol in MusicAssistantApiError MusicAssistantAuthError MusicAssistantScopeError; do
    if grep -q "class $symbol" "$MACLIENT"; then
        pass "ma_client.py defines $symbol"
    else
        fail "ma_client.py missing $symbol"
    fi
done

for cmd in "config/providers" "config/providers/get_value" "config/providers/save"; do
    if grep -q "\"$cmd\"" "$MACLIENT"; then
        pass "ma_client.py uses $cmd"
    else
        fail "ma_client.py missing command $cmd"
    fi
done

# The sample-format select must go through MA, not the Supervisor.
if grep -q 'apply_sampleformat' "$SELECT"; then
    pass "select.py routes sample format through Music Assistant"
else
    fail "select.py should call ma_client's apply_sampleformat"
fi

# Sample format options: 16-bit only (snapserver <= 0.35.0 lacks packed_s24le),
# no 44100 and no mono (MA does not support either).
if grep -q '"192000:16:2"' "$COMP_DIR/const.py"; then
    pass "const.py offers 192000:16:2"
else
    fail "const.py missing 192000:16:2"
fi

if grep -q '"44100' "$COMP_DIR/const.py"; then
    fail "const.py must not offer 44100 (MA does not support it)"
else
    pass "const.py has no 44100 option"
fi

if grep -q ':24:' "$COMP_DIR/const.py"; then
    fail "const.py must not offer 24-bit (snapserver <= 0.35.0 lacks packed_s24le)"
else
    pass "const.py has no 24-bit option"
fi

if grep -q 'ma_url' "$COMP_DIR/config_flow.py" && grep -q 'probe_write_access' "$COMP_DIR/config_flow.py"; then
    pass "config_flow.py collects MA credentials and probes write access"
else
    fail "config_flow.py missing MA credentials step or write probe"
fi

# --- Test 12: python unit tests ---
echo ""
echo "--- Python unit tests ---"

# On Windows, `python3` is often the Microsoft Store stub, which exits non-zero
# without running anything -- so probe each candidate rather than trusting PATH.
PYTHON=""
for candidate in python3 python; do
    if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info[0] == 3 else 1)' \
        > /dev/null 2>&1; then
        PYTHON="$candidate"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "  SKIP: python not found, skipping rpc/coordinator tests"
else
    for suite in test_rpc.py test_coordinator.py test_entities.py test_ma_client.py; do
        if "$PYTHON" "$SCRIPT_DIR/$suite" > /tmp/snapserver_$suite.log 2>&1; then
            pass "$suite"
        else
            fail "$suite (see /tmp/snapserver_$suite.log)"
        fi
    done
fi

# --- Summary ---
echo ""
echo "================================"
echo "Results: $PASS passed, $FAIL failed"
echo "================================"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi

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
    "config_flow.py" \
    "const.py" \
    "manifest.json" \
    "number.py" \
    "select.py" \
    "services.yaml" \
    "strings.json" \
    "supervisor.py" \
    "translations/en.json"; do
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

# --- Summary ---
echo ""
echo "================================"
echo "Results: $PASS passed, $FAIL failed"
echo "================================"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi

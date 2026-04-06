#!/bin/bash
# Tests for Snapserver addon configuration validation
# Run: bash tests/test_config.sh

set -e

PASS=0
FAIL=0
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

pass() { PASS=$((PASS + 1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL + 1)); echo "  FAIL: $1"; }

echo "=== Snapserver Addon Tests ==="
echo ""

# --- Test 1: Required files exist ---
echo "--- File structure ---"

for f in \
    "repository.yaml" \
    "snapserver/config.yaml" \
    "snapserver/Dockerfile" \
    "snapserver/run.sh" \
    "snapserver/build.yaml"; do
    if [ -f "$REPO_DIR/$f" ]; then
        pass "$f exists"
    else
        fail "$f missing"
    fi
done

# --- Test 2: config.yaml validation ---
echo ""
echo "--- config.yaml ---"

CONFIG="$REPO_DIR/snapserver/config.yaml"

# Check required fields
for field in "name:" "version:" "slug:" "arch:" "ports:" "options:" "schema:"; do
    if grep -q "$field" "$CONFIG"; then
        pass "config.yaml has '$field'"
    else
        fail "config.yaml missing '$field'"
    fi
done

# Check architectures
for arch in "amd64" "aarch64"; do
    if grep -q "$arch" "$CONFIG"; then
        pass "config.yaml supports $arch"
    else
        fail "config.yaml missing arch $arch"
    fi
done

# Check all required ports
for port in "1704" "1705" "1780" "4953"; do
    if grep -q "$port" "$CONFIG"; then
        pass "config.yaml has port $port"
    else
        fail "config.yaml missing port $port"
    fi
done

# Check all options have matching schema entries
echo ""
echo "--- Options/Schema consistency ---"

OPTIONS=$(grep -A 100 '^options:' "$CONFIG" | grep -B 100 '^schema:' | grep '^\s\s\w' | sed 's/:.*//' | sed 's/^  //' | sort)
SCHEMA=$(grep -A 100 '^schema:' "$CONFIG" | grep '^\s\s\w' | sed 's/:.*//' | sed 's/^  //' | sort)

if [ "$OPTIONS" = "$SCHEMA" ]; then
    pass "All options have matching schema entries"
else
    fail "Options and schema mismatch"
    echo "    Options: $(echo $OPTIONS | tr '\n' ' ')"
    echo "    Schema:  $(echo $SCHEMA | tr '\n' ' ')"
fi

# --- Test 3: Dockerfile validation ---
echo ""
echo "--- Dockerfile ---"

DOCKERFILE="$REPO_DIR/snapserver/Dockerfile"

if grep -q 'ARG BUILD_FROM' "$DOCKERFILE"; then
    pass "Dockerfile uses BUILD_FROM arg"
else
    fail "Dockerfile missing BUILD_FROM arg"
fi

if grep -q 'FROM.*BUILD_FROM' "$DOCKERFILE"; then
    pass "Dockerfile uses BUILD_FROM in FROM"
else
    fail "Dockerfile missing FROM BUILD_FROM"
fi

if grep -q 'snapcast-server' "$DOCKERFILE"; then
    pass "Dockerfile installs snapcast-server"
else
    fail "Dockerfile missing snapcast-server"
fi

if grep -q 'librespot' "$DOCKERFILE"; then
    pass "Dockerfile installs librespot"
else
    fail "Dockerfile missing librespot"
fi

if grep -q 'snapweb' "$DOCKERFILE"; then
    pass "Dockerfile installs snapweb"
else
    fail "Dockerfile missing snapweb"
fi

if grep -q 'run.sh' "$DOCKERFILE"; then
    pass "Dockerfile copies run.sh"
else
    fail "Dockerfile missing run.sh copy"
fi

if grep -q 'alpine' "$DOCKERFILE"; then
    pass "Dockerfile uses Alpine repos"
else
    fail "Dockerfile should use Alpine repos (not Debian)"
fi

if grep -q 'github.com/snapcast/snapweb' "$DOCKERFILE"; then
    pass "Dockerfile downloads snapweb from snapcast/snapweb"
else
    fail "Dockerfile should download snapweb from github.com/snapcast/snapweb"
fi


# --- Test 4: run.sh validation ---
echo ""
echo "--- run.sh ---"

RUNSH="$REPO_DIR/snapserver/run.sh"

if head -1 "$RUNSH" | grep -q 'bashio'; then
    pass "run.sh uses bashio shebang"
else
    fail "run.sh missing bashio shebang"
fi

if [ -x "$RUNSH" ] || grep -q 'chmod' "$DOCKERFILE"; then
    pass "run.sh is executable (or made executable in Dockerfile)"
else
    fail "run.sh not executable"
fi

# Check all config options are read
for opt in codec buffer_ms sampleformat snapweb_enabled librespot_enabled librespot_name librespot_bitrate initial_volume; do
    if grep -q "bashio::config '$opt'" "$RUNSH"; then
        pass "run.sh reads config '$opt'"
    else
        fail "run.sh missing config read for '$opt'"
    fi
done

# Check snapserver.conf sections
for section in '\[server\]' '\[http\]' '\[tcp-control\]' '\[tcp-streaming\]' '\[stream\]'; do
    if grep -q "$section" "$RUNSH"; then
        pass "run.sh generates $section section"
    else
        fail "run.sh missing $section section in config"
    fi
done

# Check TCP source is configured
if grep -q 'tcp://.*4953' "$RUNSH"; then
    pass "run.sh configures TCP stream source on port 4953"
else
    fail "run.sh missing TCP stream source"
fi

# Check librespot source uses built-in snapserver support
if grep -q 'source = librespot://' "$RUNSH"; then
    pass "run.sh uses snapserver's built-in librespot source"
else
    fail "run.sh should use built-in librespot:// source type"
fi

# Check snapserver is started with exec
if grep -q 'exec snapserver' "$RUNSH"; then
    pass "run.sh uses exec to start snapserver"
else
    fail "run.sh should use exec to start snapserver (proper signal handling)"
fi

# --- Test 5: build.yaml validation ---
echo ""
echo "--- build.yaml ---"

BUILDYAML="$REPO_DIR/snapserver/build.yaml"

if [ -f "$BUILDYAML" ]; then
    pass "build.yaml exists"
    for arch in "aarch64" "amd64"; do
        if grep -q "$arch:" "$BUILDYAML"; then
            pass "build.yaml has $arch base image"
        else
            fail "build.yaml missing $arch base image"
        fi
    done
    if grep -q 'hassio-addons/base' "$BUILDYAML"; then
        pass "build.yaml uses hassio-addons base image"
    else
        fail "build.yaml should use hassio-addons/base"
    fi
else
    fail "build.yaml missing"
fi

# --- Test 6: repository.yaml validation ---
echo ""
echo "--- repository.yaml ---"

REPOYAML="$REPO_DIR/repository.yaml"

for field in "name:" "url:" "maintainer:"; do
    if grep -q "$field" "$REPOYAML"; then
        pass "repository.yaml has '$field'"
    else
        fail "repository.yaml missing '$field'"
    fi
done

# --- Test 7: MA control script ---
echo ""
echo "--- MA control script ---"

CONTROLPY="$REPO_DIR/snapserver/plug-ins/control.py"

if [ -f "$CONTROLPY" ]; then
    pass "control.py exists"
else
    fail "control.py missing at snapserver/plug-ins/control.py"
fi

if grep -q 'MusicAssistantControl' "$CONTROLPY"; then
    pass "control.py has MusicAssistantControl class"
else
    fail "control.py missing MusicAssistantControl class"
fi

if grep -q 'import shortuuid' "$CONTROLPY"; then
    pass "control.py imports shortuuid"
else
    fail "control.py missing shortuuid import"
fi

if grep -q 'def format_ip_for_url' "$CONTROLPY"; then
    pass "control.py has inlined format_ip_for_url helper"
else
    fail "control.py missing format_ip_for_url (should be inlined, not imported from MA)"
fi

if grep -q 'plug-ins/control.py' "$DOCKERFILE"; then
    pass "Dockerfile copies control.py to plug-ins directory"
else
    fail "Dockerfile missing COPY for control.py"
fi

if grep -q 'shortuuid' "$DOCKERFILE"; then
    pass "Dockerfile installs shortuuid dependency"
else
    fail "Dockerfile missing shortuuid pip install"
fi

if grep -q 'python3' "$DOCKERFILE"; then
    pass "Dockerfile installs python3"
else
    fail "Dockerfile missing python3 installation"
fi

# --- Test 8: translations ---
echo ""
echo "--- translations ---"

TRANSLATIONS="$REPO_DIR/snapserver/translations/en.yaml"

if [ -f "$TRANSLATIONS" ]; then
    pass "translations/en.yaml exists"
else
    fail "translations/en.yaml missing"
fi

# Check all config options have translations
for opt in codec buffer_ms sampleformat snapweb_enabled librespot_enabled librespot_name librespot_bitrate initial_volume; do
    if grep -q "$opt:" "$TRANSLATIONS"; then
        pass "translations has description for '$opt'"
    else
        fail "translations missing description for '$opt'"
    fi
done

# --- Summary ---
echo ""
echo "================================"
echo "Results: $PASS passed, $FAIL failed"
echo "================================"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi

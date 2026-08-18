#!/usr/bin/env bash
# Linux install script for OmniScribe.
#
# F5-14 audit fix: previously the only path for Linux operators was
# the ``Makefile`` (and the Windows one-click ``install.bat`` /
# ``install.ps1``). This script gives the same one-command surface
# on a fresh Ubuntu / Debian host:
#
#   curl -LsSf https://raw.githubusercontent.com/.../install.sh | bash
#
# It mirrors ``install.ps1`` semantically, not syntactically — the
# Windows path uses PowerShell + VBScript for the desktop-installer
# bits, this script uses POSIX shell + the project Makefile. The
# hard requirement is the same: bring up a working Python venv with
# the ``web`` + ``preprocessing`` extras, build the frontend, and
# leave a ``start_app`` shim next to the project.
#
# The script is intentionally minimal — it does NOT install Docker
# (operators who need Redis install it themselves) and does NOT
# create desktop shortcuts (Linux desktops are too varied to do this
# well in a one-liner). For the full developer experience see
# ``Makefile help``.
#
# Fail-fast: every step that can fail sets ``pipefail`` and uses
# short-circuit ``&&`` so a single broken step aborts the install
# rather than leaving a half-built environment behind.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "======================================================="
echo "Installing OmniScribe Dependencies (Linux)"
echo "======================================================="

# 1. Install uv if missing.
#
# The official standalone installer is preferred over a distro
# package because (a) it pins to a known version matching the
# Dockerfile's ``ARG UV_VERSION=0.11.16``, and (b) it puts uv on
# ``~/.local/bin`` which the rest of the script can rely on
# without ``sudo``. Matches ``install.ps1``'s version-pinned
# download for the Windows fallback path.
if ! command -v uv >/dev/null 2>&1; then
    echo "uv not found. Installing uv..."
    UV_VERSION="0.11.16"
    if ! curl -LsSf "https://astral.sh/uv/${UV_VERSION}/install.sh" | env UV_INSTALL_DIR="$HOME/.local/bin" sh; then
        echo "ERROR: uv installer failed. Install manually: https://docs.astral.sh/uv/" >&2
        exit 1
    fi
    # Make uv available to the rest of this script.
    export PATH="$HOME/.local/bin:$PATH"
    if ! command -v uv >/dev/null 2>&1; then
        echo "ERROR: uv still not on PATH after install. Try: export PATH=\$HOME/.local/bin:\$PATH" >&2
        exit 1
    fi
else
    echo "uv is already installed."
fi

# 2. Sync Python dependencies.
echo
echo "Syncing Python dependencies with uv..."
uv sync --extra web --extra preprocessing --extra async-translation

# 3. Build the frontend static assets.
#
# ``npm ci`` is the reproducible install (``package-lock.json`` is
# the source of truth). Building the static bundle is required for
# the FastAPI app to serve the SPA — without this step the UI
# would 404 on every route.
if command -v npm >/dev/null 2>&1; then
    echo
    echo "Building Svelte 5 + Tailwind v4 frontend..."
    (
        cd frontend
        npm ci
        npm run build
    )
else
    echo
    echo "Note: npm not found in PATH; skipping frontend build (pre-built static assets will be used)." >&2
fi

# 4. Sanity check.
echo
echo "Verifying the install..."
uv run python --version
echo "Python environment OK."

# 5. Drop a ``start_app`` shim that mirrors ``start_app.vbs`` on Windows.
#
# The Windows shim launches Docker, starts Redis, starts the server,
# and opens the browser. On Linux we don't have a cross-distro way
# to do all of that, so this shim just starts the server in the
# background and prints a follow-up command. Operators who want the
# full Docker + Redis path use ``docker compose up`` directly.
cat > "$SCRIPT_DIR/start_app.sh" <<'SHIM_EOF'
#!/usr/bin/env bash
# Linux start shim for OmniScribe. Starts the web server in the
# background and tails the log. For the full Docker + Redis path
# use ``docker compose up`` instead.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
LOG_FILE="$SCRIPT_DIR/start_app.log"
: > "$LOG_FILE"
nohup uv run omniscribe-server --port 8000 >>"$LOG_FILE" 2>&1 &
echo $! > "$SCRIPT_DIR/.omniscribe.pid"
echo "omniscribe-server started (pid $(cat "$SCRIPT_DIR/.omniscribe.pid"))."
echo "Open http://localhost:8000 in your browser."
echo "Log: $LOG_FILE"
SHIM_EOF
chmod +x "$SCRIPT_DIR/start_app.sh"

cat > "$SCRIPT_DIR/stop_app.sh" <<'SHIM_EOF'
#!/usr/bin/env bash
# Linux stop shim — counterpart to start_app.sh.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/.omniscribe.pid"
if [ -f "$PID_FILE" ]; then
    PID="$(cat "$PID_FILE")"
    if kill "$PID" 2>/dev/null; then
        echo "Stopped omniscribe-server (pid $PID)."
    else
        echo "omniscribe-server (pid $PID) was already stopped."
    fi
    rm -f "$PID_FILE"
else
    echo "No .omniscribe.pid file found; nothing to stop."
fi
SHIM_EOF
chmod +x "$SCRIPT_DIR/stop_app.sh"

echo
echo "======================================================="
echo "Installation Complete!"
echo "======================================================="
echo
echo "To start the server:   ./start_app.sh"
echo "To stop the server:    ./stop_app.sh"
echo "For the full dev loop: make help"
echo

#!/usr/bin/env bash
# =============================================================================
# 911 Fiesta V7 - SHOW GUI Launcher
# =============================================================================
#
# Wrapper script that activates the venv, sets up Qt/display environment,
# and launches the PySide6 GUI (main.py).
#
# Intended to be called from:
#   - XDG autostart (.desktop file) when the fiesta911 user logs in
#   - Manual launch: bash /opt/911fiesta/scripts/run_show.sh
#
# Prerequisites:
#   - Active graphical session (X11/Wayland with XWayland)
#   - bootstrap_linux.sh --profile show  (installs xcb deps)
#   - install_911fiesta.sh --profile show (installs PySide6 + deps)
#
# =============================================================================
set -euo pipefail

readonly FIESTA_HOME="/opt/911fiesta"
readonly VENV_DIR="${FIESTA_HOME}/.venv"
readonly LOG_TAG="[run_show]"

log() { echo "${LOG_TAG} $(date '+%Y-%m-%d %H:%M:%S') $*"; }
err() { echo "${LOG_TAG} ERROR: $*" >&2; }

# ---------------------------------------------------------------------------
# 1. Verify venv
# ---------------------------------------------------------------------------
if [[ ! -x "${VENV_DIR}/bin/python3" ]]; then
    err "Python venv not found at ${VENV_DIR}."
    err "Run: sudo bash scripts/install_911fiesta.sh --profile show"
    exit 1
fi

# ---------------------------------------------------------------------------
# 2. Verify display
# ---------------------------------------------------------------------------
if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
    err "No DISPLAY or WAYLAND_DISPLAY set. SHOW requires a graphical session."
    err "Log in to a desktop session, then run this script."
    exit 1
fi

# ---------------------------------------------------------------------------
# 3. GNOME kiosk settings (idempotent, persists across reboots)
# ---------------------------------------------------------------------------
if command -v gsettings &>/dev/null; then
    log "Applying GNOME kiosk settings ..."
    gsettings set org.gnome.shell enable-hot-corners false    2>/dev/null || true
    gsettings set org.gnome.shell favorite-apps "[]"          2>/dev/null || true
    gsettings set org.gnome.mutter center-new-windows true    2>/dev/null || true
fi

# ---------------------------------------------------------------------------
# 4. Qt environment
# ---------------------------------------------------------------------------
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
export QT_AUTO_SCREEN_SCALE_FACTOR="${QT_AUTO_SCREEN_SCALE_FACTOR:-1}"

# ---------------------------------------------------------------------------
# 5. Launch
# ---------------------------------------------------------------------------
log "Starting 911 Fiesta SHOW GUI ..."
log "  DISPLAY=${DISPLAY:-<not set>}"
log "  WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-<not set>}"
log "  QT_QPA_PLATFORM=${QT_QPA_PLATFORM}"
log "  Venv: ${VENV_DIR}"
log "  Working dir: ${FIESTA_HOME}"

cd "${FIESTA_HOME}"
exec "${VENV_DIR}/bin/python3" main.py "$@"

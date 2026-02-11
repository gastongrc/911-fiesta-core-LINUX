#!/usr/bin/env bash
# =============================================================================
# 911 Fiesta V7 - SHOW GUI Launcher
# =============================================================================
#
# Wrapper script that activates the venv, sets up Qt/display environment,
# and launches the PySide6 GUI (main.py).
#
# Called from:
#   - xinitrc_show  (Xorg kiosk session — primary path)
#   - Manual launch: bash /opt/911fiesta/scripts/run_show.sh
#
# Prerequisites:
#   - Xorg running with DISPLAY set (via startx / xinitrc_show)
#   - bootstrap_linux.sh --profile show  (installs openbox + xcb deps)
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
if [[ -z "${DISPLAY:-}" ]]; then
    err "No DISPLAY set. SHOW requires Xorg (startx via xinitrc_show)."
    exit 1
fi

# ---------------------------------------------------------------------------
# 3. Qt environment
# ---------------------------------------------------------------------------
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
# Disable Qt auto-scaling: force 1:1 pixel mapping to physical framebuffer.
# QT_AUTO_SCREEN_SCALE_FACTOR=1 causes Qt6 to read EDID DPI and scale down
# the logical viewport if the monitor reports >96 DPI, resulting in content
# that renders smaller than the physical screen.
export QT_AUTO_SCREEN_SCALE_FACTOR=0
export QT_SCALE_FACTOR=1

# ---------------------------------------------------------------------------
# 4. Launch
# ---------------------------------------------------------------------------
log "Starting 911 Fiesta SHOW GUI ..."
log "  DISPLAY=${DISPLAY}"
log "  QT_QPA_PLATFORM=${QT_QPA_PLATFORM}"
log "  Venv: ${VENV_DIR}"
log "  Working dir: ${FIESTA_HOME}"

cd "${FIESTA_HOME}"
exec "${VENV_DIR}/bin/python3" main.py "$@"

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
    err "  If running from SSH: export DISPLAY=:0 && xhost +local:"
    exit 1
fi

# ---------------------------------------------------------------------------
# 3. Verify user groups (warn only, don't block)
# ---------------------------------------------------------------------------
CURRENT_USER=$(whoami)
MISSING_GROUPS=""
for grp in video tty render audio; do
    if getent group "${grp}" >/dev/null 2>&1; then
        if ! id -nG "${CURRENT_USER}" 2>/dev/null | grep -qw "${grp}"; then
            MISSING_GROUPS="${MISSING_GROUPS} ${grp}"
        fi
    fi
done

if [[ -n "${MISSING_GROUPS}" ]]; then
    log "WARN: User '${CURRENT_USER}' is NOT in groups:${MISSING_GROUPS}"
    log "  Fix: sudo usermod -aG video,tty,render,audio ${CURRENT_USER}"
    log "  (Xorg may fail without video+tty groups)"
fi

# ---------------------------------------------------------------------------
# 4. Qt environment — NEVER use offscreen for GUI
# ---------------------------------------------------------------------------
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
# Disable Qt auto-scaling: force 1:1 pixel mapping to physical framebuffer.
# QT_AUTO_SCREEN_SCALE_FACTOR=1 causes Qt6 to read EDID DPI and scale down
# the logical viewport if the monitor reports >96 DPI, resulting in content
# that renders smaller than the physical screen.
export QT_AUTO_SCREEN_SCALE_FACTOR=0
export QT_SCALE_FACTOR=1

# Safety: refuse to run with offscreen (would be invisible GUI)
if [[ "${QT_QPA_PLATFORM}" == "offscreen" ]]; then
    err "QT_QPA_PLATFORM=offscreen — refusing to launch invisible GUI."
    err "  Unset the variable or set QT_QPA_PLATFORM=xcb"
    exit 1
fi

# ---------------------------------------------------------------------------
# 5. Launch
# ---------------------------------------------------------------------------
log "Starting 911 Fiesta SHOW GUI ..."
log "  DISPLAY=${DISPLAY}"
log "  QT_QPA_PLATFORM=${QT_QPA_PLATFORM}"
log "  User=${CURRENT_USER} Groups=$(id -nG 2>/dev/null || echo 'unknown')"
log "  Venv: ${VENV_DIR}"
log "  Working dir: ${FIESTA_HOME}"

cd "${FIESTA_HOME}"
exec "${VENV_DIR}/bin/python3" main.py "$@"

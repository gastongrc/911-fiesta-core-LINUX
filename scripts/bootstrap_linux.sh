#!/usr/bin/env bash
# =============================================================================
# 911 Fiesta V7 - Bootstrap Script for Ubuntu 22.04.5 Desktop
# =============================================================================
#
# Prepares a clean Ubuntu 22.04.5 Desktop server for 911 Fiesta installation.
# Installs system packages, creates the fiesta911 user, and sets up directories.
#
# Usage:
#   sudo bash scripts/bootstrap_linux.sh [--profile server|show]
#
# Profiles:
#   server (default) - headless API, system user with nologin shell
#   show             - GUI with display, login user with /bin/bash shell,
#                      extra xcb/Qt packages for PySide6 GUI
#
# Idempotent: safe to re-run.
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
readonly FIESTA_USER="fiesta911"
readonly FIESTA_HOME="/opt/911fiesta"
readonly CONFIG_DIR="/etc/911fiesta"
readonly LOG_TAG="[bootstrap]"
readonly REQUIRED_OS="Ubuntu"
readonly REQUIRED_VERSION="22.04"

# Defaults
INSTALL_PROFILE="server"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log()  { echo "${LOG_TAG} $(date '+%Y-%m-%d %H:%M:%S') $*"; }
err()  { echo "${LOG_TAG} ERROR: $*" >&2; }
die()  { err "$@"; exit 1; }

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --profile)
            INSTALL_PROFILE="${2:?'--profile requires a value (server|show)'}"
            shift 2
            ;;
        --help|-h)
            grep '^#' "$0" | head -20 | sed 's/^# \?//'
            exit 0
            ;;
        *)
            die "Unknown argument: $1"
            ;;
    esac
done

if [[ "${INSTALL_PROFILE}" != "server" && "${INSTALL_PROFILE}" != "show" ]]; then
    die "Invalid profile '${INSTALL_PROFILE}'. Use 'server' or 'show'."
fi

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
if [[ $EUID -ne 0 ]]; then
    die "This script must be run as root (sudo)."
fi

# Verify we are on Ubuntu 22.04
if [[ -f /etc/os-release ]]; then
    # shellcheck source=/dev/null
    source /etc/os-release
    if [[ "${NAME:-}" != *"${REQUIRED_OS}"* ]]; then
        log "WARNING: Expected ${REQUIRED_OS}, detected '${NAME:-unknown}'. Proceeding anyway."
    fi
    if [[ "${VERSION_ID:-}" != "${REQUIRED_VERSION}"* ]]; then
        log "WARNING: Expected ${REQUIRED_VERSION}.x, detected '${VERSION_ID:-unknown}'. Proceeding anyway."
    fi
else
    log "WARNING: /etc/os-release not found. Cannot verify OS version."
fi

log "Starting bootstrap on $(hostname) (profile=${INSTALL_PROFILE}) ..."

# ---------------------------------------------------------------------------
# 1. System packages (common to both profiles)
# ---------------------------------------------------------------------------
log "Updating apt package index ..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq

log "Installing system packages ..."

# Core build tools
apt-get install -y -qq \
    build-essential \
    pkg-config \
    git \
    curl \
    wget \
    ca-certificates \
    gnupg \
    lsb-release \
    software-properties-common

# Python 3 runtime
apt-get install -y -qq \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev

# OpenCV / GL dependencies
apt-get install -y -qq \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1

# Qt / PySide6 base dependencies (headless-safe)
apt-get install -y -qq \
    libegl1 \
    libxkbcommon0 \
    libdbus-1-3 \
    libfontconfig1 \
    libxcb-xinerama0

# FFmpeg (vision + audio streaming)
apt-get install -y -qq \
    ffmpeg \
    libavformat-dev \
    libavcodec-dev \
    libavdevice-dev \
    libavutil-dev \
    libswscale-dev \
    libswresample-dev

# Audio: PortAudio + libsndfile
apt-get install -y -qq \
    libportaudio2 \
    portaudio19-dev \
    libsndfile1 \
    libsndfile1-dev

# ALSA utilities (USB audio device detection: Maono PS22 etc.)
apt-get install -y -qq \
    alsa-utils

# HDF5 (for tensorflow/keras model loading)
apt-get install -y -qq \
    libhdf5-dev

# Networking tools
apt-get install -y -qq \
    net-tools \
    iputils-ping

log "Common system packages installed."

# ---------------------------------------------------------------------------
# 1b. SHOW profile: extra Qt/xcb packages for GUI (PySide6 on X11)
# ---------------------------------------------------------------------------
if [[ "${INSTALL_PROFILE}" == "show" ]]; then
    log "Installing GUI/xcb dependencies for SHOW profile ..."
    apt-get install -y -qq \
        libxcb-cursor0 \
        libxcb-icccm4 \
        libxcb-image0 \
        libxcb-keysyms1 \
        libxcb-randr0 \
        libxcb-render-util0 \
        libxcb-shape0 \
        libxcb-xfixes0
    log "GUI dependencies installed."

    # Xorg kiosk: minimal X + window manager (NO desktop environment)
    log "Installing Xorg kiosk packages ..."
    apt-get install -y -qq \
        xinit \
        x11-xserver-utils \
        openbox
    # Optional: hide cursor after inactivity
    apt-get install -y -qq unclutter 2>/dev/null || true
    log "Kiosk packages installed."
fi

# ---------------------------------------------------------------------------
# 1c. NVIDIA GPU driver (documentation only - manual step)
# ---------------------------------------------------------------------------
# The core911 machine has an NVIDIA 1080 Ti.
# The NVIDIA driver is NOT installed automatically because:
#   - Ubuntu 22.04 desktop may already have the driver via HWE kernel
#   - The correct driver version depends on the specific kernel
#   - Wrong driver can break the display / boot
#
# To install (if not already present):
#   sudo ubuntu-drivers install
#   # or for a specific version:
#   sudo apt install nvidia-driver-535
#   sudo reboot
#
# After reboot, verify with:
#   nvidia-smi
#
if command -v nvidia-smi &>/dev/null; then
    log "NVIDIA driver detected: $(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null || echo 'unknown version')"
else
    log "NOTE: NVIDIA driver not detected. If this machine has a GPU (e.g. 1080 Ti),"
    log "  install the driver manually: sudo ubuntu-drivers install && sudo reboot"
fi

# ---------------------------------------------------------------------------
# 2. Create fiesta911 user
# ---------------------------------------------------------------------------
if id "${FIESTA_USER}" &>/dev/null; then
    log "User '${FIESTA_USER}' already exists."

    # If SHOW profile, ensure user has a real login shell
    if [[ "${INSTALL_PROFILE}" == "show" ]]; then
        CURRENT_SHELL=$(getent passwd "${FIESTA_USER}" | cut -d: -f7)
        if [[ "${CURRENT_SHELL}" == */nologin || "${CURRENT_SHELL}" == */false ]]; then
            log "Upgrading '${FIESTA_USER}' shell to /bin/bash for SHOW (GUI login) ..."
            usermod --shell /bin/bash "${FIESTA_USER}"
        fi
    fi
else
    if [[ "${INSTALL_PROFILE}" == "show" ]]; then
        # SHOW: real user with login shell (can log into graphical session)
        log "Creating user '${FIESTA_USER}' with login shell (SHOW profile) ..."
        useradd \
            --create-home \
            --home-dir "${FIESTA_HOME}" \
            --shell /bin/bash \
            --comment "911 Fiesta SHOW operator" \
            "${FIESTA_USER}"
    else
        # SERVER: system user with nologin shell
        log "Creating system user '${FIESTA_USER}' (SERVER profile) ..."
        useradd \
            --system \
            --create-home \
            --home-dir "${FIESTA_HOME}" \
            --shell /usr/sbin/nologin \
            --comment "911 Fiesta service account" \
            "${FIESTA_USER}"
    fi
    log "User '${FIESTA_USER}' created."
fi

# Ensure fiesta911 user is in required groups
GROUPS_LIST="audio video"
if [[ "${INSTALL_PROFILE}" == "show" ]]; then
    GROUPS_LIST="audio video render"
fi

for grp in ${GROUPS_LIST}; do
    if getent group "${grp}" &>/dev/null; then
        usermod -aG "${grp}" "${FIESTA_USER}" 2>/dev/null || true
        log "User '${FIESTA_USER}' added to '${grp}' group."
    fi
done

# ---------------------------------------------------------------------------
# 3. Create directories
# ---------------------------------------------------------------------------
log "Setting up directories ..."

# Application directory
if [[ ! -d "${FIESTA_HOME}" ]]; then
    mkdir -p "${FIESTA_HOME}"
fi
chown "${FIESTA_USER}:${FIESTA_USER}" "${FIESTA_HOME}"
chmod 755 "${FIESTA_HOME}"

# Configuration directory
if [[ ! -d "${CONFIG_DIR}" ]]; then
    mkdir -p "${CONFIG_DIR}"
fi
chown "${FIESTA_USER}:${FIESTA_USER}" "${CONFIG_DIR}"
chmod 755 "${CONFIG_DIR}"

# Log directory
if [[ ! -d /var/log/911fiesta ]]; then
    mkdir -p /var/log/911fiesta
fi
chown "${FIESTA_USER}:${FIESTA_USER}" /var/log/911fiesta
chmod 755 /var/log/911fiesta

log "Directories ready."

# ---------------------------------------------------------------------------
# 4. Install systemd unit (disabled, not started)
# ---------------------------------------------------------------------------
# The unit file will be properly installed by install_911fiesta.sh.
# Here we just ensure the path exists so enable works later.
log "Systemd unit will be installed by install_911fiesta.sh."

# ---------------------------------------------------------------------------
# 5. Summary
# ---------------------------------------------------------------------------
log "=========================================="
log "Bootstrap complete."
log "=========================================="
log ""
log "  Profile:    ${INSTALL_PROFILE}"
log "  User:       ${FIESTA_USER}"
log "  App dir:    ${FIESTA_HOME}"
log "  Config dir: ${CONFIG_DIR}"
log "  Log dir:    /var/log/911fiesta"
log ""
log "Next step:"
log "  sudo bash scripts/install_911fiesta.sh --profile ${INSTALL_PROFILE}"
log ""

exit 0

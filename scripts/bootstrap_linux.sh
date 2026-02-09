#!/usr/bin/env bash
# =============================================================================
# 911 Fiesta V7 - Bootstrap Script for Ubuntu 24.04.3
# =============================================================================
#
# Prepares a clean Ubuntu 24.04.3 server for 911 Fiesta installation.
# Installs system packages, creates the fiesta user, and sets up directories.
#
# Usage:
#   sudo bash scripts/bootstrap_linux.sh
#
# Idempotent: safe to re-run.
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
readonly FIESTA_USER="fiesta"
readonly FIESTA_HOME="/opt/911fiesta"
readonly CONFIG_DIR="/etc/911fiesta"
readonly LOG_TAG="[bootstrap]"
readonly REQUIRED_OS="Ubuntu"
readonly REQUIRED_VERSION="24.04"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log()  { echo "${LOG_TAG} $(date '+%Y-%m-%d %H:%M:%S') $*"; }
err()  { echo "${LOG_TAG} ERROR: $*" >&2; }
die()  { err "$@"; exit 1; }

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
if [[ $EUID -ne 0 ]]; then
    die "This script must be run as root (sudo)."
fi

# Verify we are on Ubuntu 24.04
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

log "Starting bootstrap on $(hostname) ..."

# ---------------------------------------------------------------------------
# 1. System packages
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

# Qt / PySide6 headless dependencies
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

log "System packages installed."

# ---------------------------------------------------------------------------
# 1b. NVIDIA GPU driver (documentation only - manual step)
# ---------------------------------------------------------------------------
# The core911 machine has an NVIDIA 1080 Ti.
# The NVIDIA driver is NOT installed automatically because:
#   - Ubuntu 24.04 server may already have the driver via HWE kernel
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
# 2. Create fiesta user
# ---------------------------------------------------------------------------
if id "${FIESTA_USER}" &>/dev/null; then
    log "User '${FIESTA_USER}' already exists."
else
    log "Creating system user '${FIESTA_USER}' ..."
    useradd \
        --system \
        --create-home \
        --home-dir "${FIESTA_HOME}" \
        --shell /usr/sbin/nologin \
        --comment "911 Fiesta service account" \
        "${FIESTA_USER}"
    log "User '${FIESTA_USER}' created."
fi

# Ensure fiesta user is in audio and video groups (for USB audio + GPU access)
for grp in audio video; do
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
log "  User:       ${FIESTA_USER}"
log "  App dir:    ${FIESTA_HOME}"
log "  Config dir: ${CONFIG_DIR}"
log "  Log dir:    /var/log/911fiesta"
log ""
log "Next step:"
log "  sudo bash scripts/install_911fiesta.sh"
log ""

exit 0

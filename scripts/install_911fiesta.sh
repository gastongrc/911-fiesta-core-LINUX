#!/usr/bin/env bash
# =============================================================================
# 911 Fiesta V7 - Install Script for Ubuntu 22.04.5 Desktop
# =============================================================================
#
# Clones the repo, creates the Python venv, installs pinned dependencies,
# deploys the systemd service, and runs the healthcheck.
#
# Prerequisites:
#   sudo bash scripts/bootstrap_linux.sh
#
# Usage:
#   sudo bash scripts/install_911fiesta.sh [OPTIONS]
#
# Options:
#   --profile server   Install server-only deps (default, headless API)
#   --profile show     Install full SHOW deps (GUI + vision + audio)
#   --repo-url URL     Git clone URL (default: github)
#   --branch BRANCH    Git branch to clone (default: baseline/linux-foja-cero)
#   --skip-healthcheck Skip final healthcheck
#   --torch-gpu        Install PyTorch with CUDA 12.1 (default: CPU-only)
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
readonly VENV_DIR="${FIESTA_HOME}/.venv"
readonly SYSTEMD_UNIT="911fiesta.service"
readonly SYSTEMD_DEST="/etc/systemd/system/${SYSTEMD_UNIT}"
readonly LOG_TAG="[install]"

# Defaults
INSTALL_PROFILE="server"
REPO_URL="https://github.com/gastongrc/911-fiesta-core-LINUX.git"
REPO_BRANCH="baseline/linux-foja-cero"
SKIP_HEALTHCHECK=false
TORCH_GPU=false

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log()  { echo "${LOG_TAG} $(date '+%Y-%m-%d %H:%M:%S') $*"; }
err()  { echo "${LOG_TAG} ERROR: $*" >&2; }
die()  { err "$@"; exit 1; }

usage() {
    grep '^#' "$0" | head -20 | sed 's/^# \?//'
    exit 1
}

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --profile)
            INSTALL_PROFILE="${2:?'--profile requires a value (server|show)'}"
            shift 2
            ;;
        --repo-url)
            REPO_URL="${2:?'--repo-url requires a value'}"
            shift 2
            ;;
        --branch)
            REPO_BRANCH="${2:?'--branch requires a value'}"
            shift 2
            ;;
        --skip-healthcheck)
            SKIP_HEALTHCHECK=true
            shift
            ;;
        --torch-gpu)
            TORCH_GPU=true
            shift
            ;;
        --help|-h)
            usage
            ;;
        *)
            die "Unknown argument: $1"
            ;;
    esac
done

# Validate profile
if [[ "${INSTALL_PROFILE}" != "server" && "${INSTALL_PROFILE}" != "show" ]]; then
    die "Invalid profile '${INSTALL_PROFILE}'. Use 'server' or 'show'."
fi

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
if [[ $EUID -ne 0 ]]; then
    die "This script must be run as root (sudo)."
fi

if ! id "${FIESTA_USER}" &>/dev/null; then
    die "User '${FIESTA_USER}' not found. Run bootstrap_linux.sh first."
fi

if ! command -v python3 &>/dev/null; then
    die "python3 not found. Run bootstrap_linux.sh first."
fi

if ! command -v git &>/dev/null; then
    die "git not found. Run bootstrap_linux.sh first."
fi

log "Starting install (profile=${INSTALL_PROFILE}) ..."

# ---------------------------------------------------------------------------
# 1. Clone or update repository
# ---------------------------------------------------------------------------
if [[ -d "${FIESTA_HOME}/.git" ]]; then
    log "Repository already exists at ${FIESTA_HOME}. Pulling latest ..."
    sudo -u "${FIESTA_USER}" git -C "${FIESTA_HOME}" fetch origin "${REPO_BRANCH}"
    sudo -u "${FIESTA_USER}" git -C "${FIESTA_HOME}" checkout "${REPO_BRANCH}" 2>/dev/null || \
        sudo -u "${FIESTA_USER}" git -C "${FIESTA_HOME}" checkout -b "${REPO_BRANCH}" "origin/${REPO_BRANCH}"
    sudo -u "${FIESTA_USER}" git -C "${FIESTA_HOME}" pull origin "${REPO_BRANCH}"
else
    log "Cloning repository into ${FIESTA_HOME} ..."
    # Clone into a temp dir first if FIESTA_HOME exists but is not a git repo
    if [[ -d "${FIESTA_HOME}" ]]; then
        # Directory exists from bootstrap but is empty
        sudo -u "${FIESTA_USER}" git clone \
            --branch "${REPO_BRANCH}" \
            "${REPO_URL}" \
            "${FIESTA_HOME}.tmp"
        # Move .git and contents into existing dir
        cp -a "${FIESTA_HOME}.tmp/." "${FIESTA_HOME}/"
        rm -rf "${FIESTA_HOME}.tmp"
        chown -R "${FIESTA_USER}:${FIESTA_USER}" "${FIESTA_HOME}"
    else
        sudo -u "${FIESTA_USER}" git clone \
            --branch "${REPO_BRANCH}" \
            "${REPO_URL}" \
            "${FIESTA_HOME}"
    fi
fi

log "Repository ready at ${FIESTA_HOME}."

# Tag current commit as last-known-good for rollback
CURRENT_COMMIT=$(git -C "${FIESTA_HOME}" rev-parse --short HEAD)
log "Current commit: ${CURRENT_COMMIT}"

# ---------------------------------------------------------------------------
# 2. Create Python virtual environment
# ---------------------------------------------------------------------------
if [[ -d "${VENV_DIR}" ]]; then
    log "Virtual environment already exists at ${VENV_DIR}."
else
    log "Creating virtual environment at ${VENV_DIR} ..."
    sudo -u "${FIESTA_USER}" python3 -m venv "${VENV_DIR}"
fi

# Upgrade pip inside venv
log "Upgrading pip ..."
sudo -u "${FIESTA_USER}" "${VENV_DIR}/bin/pip" install --upgrade pip setuptools wheel --quiet

# ---------------------------------------------------------------------------
# 3. Install Python dependencies
# ---------------------------------------------------------------------------
log "Installing Python dependencies (profile=${INSTALL_PROFILE}) ..."

if [[ "${INSTALL_PROFILE}" == "server" ]]; then
    # Server mode: headless API, pinned deps
    REQUIREMENTS_FILE="${FIESTA_HOME}/requirements/server.lock.txt"
    if [[ ! -f "${REQUIREMENTS_FILE}" ]]; then
        die "Requirements file not found: ${REQUIREMENTS_FILE}"
    fi
    sudo -u "${FIESTA_USER}" "${VENV_DIR}/bin/pip" install \
        -r "${REQUIREMENTS_FILE}" \
        --quiet

elif [[ "${INSTALL_PROFILE}" == "show" ]]; then
    # Show mode: full GUI + vision + audio

    # Install PyTorch first (GPU or CPU)
    if [[ "${TORCH_GPU}" == true ]]; then
        log "Installing PyTorch with CUDA 12.1 ..."
        sudo -u "${FIESTA_USER}" "${VENV_DIR}/bin/pip" install \
            torch torchvision torchaudio \
            --index-url https://download.pytorch.org/whl/cu121 \
            --quiet
    else
        log "Installing PyTorch CPU-only ..."
        sudo -u "${FIESTA_USER}" "${VENV_DIR}/bin/pip" install \
            torch torchvision torchaudio \
            --index-url https://download.pytorch.org/whl/cpu \
            --quiet
    fi

    # Install pinned SHOW deps
    REQUIREMENTS_FILE="${FIESTA_HOME}/requirements/show.lock.txt"
    if [[ ! -f "${REQUIREMENTS_FILE}" ]]; then
        die "Requirements file not found: ${REQUIREMENTS_FILE}"
    fi
    sudo -u "${FIESTA_USER}" "${VENV_DIR}/bin/pip" install \
        -r "${REQUIREMENTS_FILE}" \
        --quiet
fi

log "Python dependencies installed."

# ---------------------------------------------------------------------------
# 4. Copy example configs
# ---------------------------------------------------------------------------
log "Setting up configuration files ..."

# Copy vision config example if not already present
if [[ ! -f "${CONFIG_DIR}/vision_config.json" ]]; then
    if [[ -f "${FIESTA_HOME}/vision_config.json" ]]; then
        cp "${FIESTA_HOME}/vision_config.json" "${CONFIG_DIR}/vision_config.json"
        chown "${FIESTA_USER}:${FIESTA_USER}" "${CONFIG_DIR}/vision_config.json"
        log "Copied vision_config.json to ${CONFIG_DIR}/"
    fi
fi

# Copy avolites config example if not already present
if [[ ! -f "${CONFIG_DIR}/avolites_config.json" ]]; then
    if [[ -f "${FIESTA_HOME}/avolites_config.json" ]]; then
        cp "${FIESTA_HOME}/avolites_config.json" "${CONFIG_DIR}/avolites_config.json"
        chown "${FIESTA_USER}:${FIESTA_USER}" "${CONFIG_DIR}/avolites_config.json"
        log "Copied avolites_config.json to ${CONFIG_DIR}/"
    fi
fi

# Copy audio monitor config
if [[ ! -f "${CONFIG_DIR}/audio_monitor.json" ]]; then
    if [[ -f "${FIESTA_HOME}/config/audio_monitor.json" ]]; then
        cp "${FIESTA_HOME}/config/audio_monitor.json" "${CONFIG_DIR}/audio_monitor.json"
        chown "${FIESTA_USER}:${FIESTA_USER}" "${CONFIG_DIR}/audio_monitor.json"
        log "Copied audio_monitor.json to ${CONFIG_DIR}/"
    fi
fi

# Copy environment file (systemd entrypoint config)
if [[ ! -f "${CONFIG_DIR}/911fiesta.env" ]]; then
    if [[ -f "${FIESTA_HOME}/systemd/911fiesta.env" ]]; then
        cp "${FIESTA_HOME}/systemd/911fiesta.env" "${CONFIG_DIR}/911fiesta.env"
        chown "${FIESTA_USER}:${FIESTA_USER}" "${CONFIG_DIR}/911fiesta.env"
        chmod 640 "${CONFIG_DIR}/911fiesta.env"
        log "Copied 911fiesta.env to ${CONFIG_DIR}/"
    fi
fi

log "Configuration files ready in ${CONFIG_DIR}/."

# ---------------------------------------------------------------------------
# 5. Install systemd unit
# ---------------------------------------------------------------------------
log "Installing systemd service ..."

UNIT_SOURCE="${FIESTA_HOME}/systemd/${SYSTEMD_UNIT}"
if [[ ! -f "${UNIT_SOURCE}" ]]; then
    die "Systemd unit not found: ${UNIT_SOURCE}"
fi

cp "${UNIT_SOURCE}" "${SYSTEMD_DEST}"
chmod 644 "${SYSTEMD_DEST}"

systemctl daemon-reload
systemctl enable "${SYSTEMD_UNIT}"

log "Systemd service installed and enabled."

# ---------------------------------------------------------------------------
# 6. Start the service
# ---------------------------------------------------------------------------
log "Starting 911fiesta service ..."
systemctl start "${SYSTEMD_UNIT}"

# Give the service a moment to start
sleep 3

if systemctl is-active --quiet "${SYSTEMD_UNIT}"; then
    log "Service is running."
else
    log "WARNING: Service did not start cleanly. Check: journalctl -u ${SYSTEMD_UNIT} -n 50"
fi

# ---------------------------------------------------------------------------
# 7. Run healthcheck
# ---------------------------------------------------------------------------
if [[ "${SKIP_HEALTHCHECK}" == true ]]; then
    log "Healthcheck skipped (--skip-healthcheck)."
else
    log "Running healthcheck ..."
    HEALTHCHECK_SCRIPT="${FIESTA_HOME}/scripts/healthcheck_911fiesta.sh"
    if [[ -f "${HEALTHCHECK_SCRIPT}" ]]; then
        if bash "${HEALTHCHECK_SCRIPT}"; then
            log "Healthcheck PASSED."
        else
            err "Healthcheck FAILED. Review output above for details."
            err "The service is running but may not be fully functional."
            err "Fix issues and re-run: bash ${HEALTHCHECK_SCRIPT}"
            exit 1
        fi
    else
        log "WARNING: Healthcheck script not found at ${HEALTHCHECK_SCRIPT}."
    fi
fi

# ---------------------------------------------------------------------------
# 8. Tag known-good state
# ---------------------------------------------------------------------------
# Save the current commit as last-known-good for rollback purposes
echo "${CURRENT_COMMIT}" > "${CONFIG_DIR}/last-known-good-commit"
chown "${FIESTA_USER}:${FIESTA_USER}" "${CONFIG_DIR}/last-known-good-commit"
log "Tagged ${CURRENT_COMMIT} as last-known-good commit."

# ---------------------------------------------------------------------------
# 9. Summary
# ---------------------------------------------------------------------------
log "=========================================="
log "Installation complete."
log "=========================================="
log ""
log "  Profile:     ${INSTALL_PROFILE}"
log "  App dir:     ${FIESTA_HOME}"
log "  Venv:        ${VENV_DIR}"
log "  Config dir:  ${CONFIG_DIR}"
log "  Service:     ${SYSTEMD_UNIT}"
log "  Commit:      ${CURRENT_COMMIT}"
log ""
log "Useful commands:"
log "  systemctl status 911fiesta"
log "  journalctl -u 911fiesta -f"
log "  bash ${FIESTA_HOME}/scripts/healthcheck_911fiesta.sh"
log ""

exit 0

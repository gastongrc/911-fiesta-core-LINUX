#!/usr/bin/env bash
# =============================================================================
# 911 Fiesta V7 - Update Script for Ubuntu 22.04.5 Desktop
# =============================================================================
#
# Pulls the latest code, re-syncs Python dependencies, restarts the service,
# and runs the healthcheck. Supports rollback to last-known-good commit.
#
# Usage:
#   sudo bash scripts/update_911fiesta.sh [OPTIONS]
#
# Options:
#   --branch BRANCH       Git branch to pull (default: current branch)
#   --tag TAG             Checkout a specific git tag instead of pulling
#   --rollback            Rollback to last-known-good commit
#   --skip-healthcheck    Skip final healthcheck
#   --profile server      Dependency profile (default: server)
#   --profile show        Dependency profile (full SHOW)
#   --torch-gpu           Install PyTorch with CUDA 12.1 (show profile only)
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
readonly LOG_TAG="[update]"
readonly KNOWN_GOOD_FILE="${CONFIG_DIR}/last-known-good-commit"

# Defaults
UPDATE_BRANCH=""
UPDATE_TAG=""
DO_ROLLBACK=false
SKIP_HEALTHCHECK=false
INSTALL_PROFILE="server"
TORCH_GPU=false

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
        --branch)
            UPDATE_BRANCH="${2:?'--branch requires a value'}"
            shift 2
            ;;
        --tag)
            UPDATE_TAG="${2:?'--tag requires a value'}"
            shift 2
            ;;
        --rollback)
            DO_ROLLBACK=true
            shift
            ;;
        --skip-healthcheck)
            SKIP_HEALTHCHECK=true
            shift
            ;;
        --profile)
            INSTALL_PROFILE="${2:?'--profile requires a value (server|show)'}"
            shift 2
            ;;
        --torch-gpu)
            TORCH_GPU=true
            shift
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

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
if [[ $EUID -ne 0 ]]; then
    die "This script must be run as root (sudo)."
fi

if [[ ! -d "${FIESTA_HOME}/.git" ]]; then
    die "No git repository at ${FIESTA_HOME}. Run install_911fiesta.sh first."
fi

if [[ ! -d "${VENV_DIR}" ]]; then
    die "No venv at ${VENV_DIR}. Run install_911fiesta.sh first."
fi

# Save pre-update commit for potential rollback
PRE_UPDATE_COMMIT=$(git -C "${FIESTA_HOME}" rev-parse --short HEAD)
log "Current commit before update: ${PRE_UPDATE_COMMIT}"

# ---------------------------------------------------------------------------
# 1. Rollback mode
# ---------------------------------------------------------------------------
if [[ "${DO_ROLLBACK}" == true ]]; then
    if [[ ! -f "${KNOWN_GOOD_FILE}" ]]; then
        die "No last-known-good commit found at ${KNOWN_GOOD_FILE}."
    fi

    ROLLBACK_COMMIT=$(cat "${KNOWN_GOOD_FILE}")
    log "Rolling back to known-good commit: ${ROLLBACK_COMMIT} ..."

    sudo -u "${FIESTA_USER}" git -C "${FIESTA_HOME}" checkout "${ROLLBACK_COMMIT}"

    log "Rollback checkout complete. Re-syncing dependencies ..."
    # Fall through to dep sync and restart below
fi

# ---------------------------------------------------------------------------
# 2. Pull latest code (unless rollback or tag)
# ---------------------------------------------------------------------------
if [[ "${DO_ROLLBACK}" == false ]]; then
    if [[ -n "${UPDATE_TAG}" ]]; then
        log "Checking out tag: ${UPDATE_TAG} ..."
        sudo -u "${FIESTA_USER}" git -C "${FIESTA_HOME}" fetch origin --tags
        sudo -u "${FIESTA_USER}" git -C "${FIESTA_HOME}" checkout "tags/${UPDATE_TAG}"
    else
        BRANCH="${UPDATE_BRANCH}"
        if [[ -z "${BRANCH}" ]]; then
            BRANCH=$(git -C "${FIESTA_HOME}" rev-parse --abbrev-ref HEAD)
        fi
        log "Pulling branch '${BRANCH}' ..."
        sudo -u "${FIESTA_USER}" git -C "${FIESTA_HOME}" fetch origin "${BRANCH}"
        sudo -u "${FIESTA_USER}" git -C "${FIESTA_HOME}" pull origin "${BRANCH}"
    fi
fi

POST_UPDATE_COMMIT=$(git -C "${FIESTA_HOME}" rev-parse --short HEAD)
log "Commit after update: ${POST_UPDATE_COMMIT}"

# ---------------------------------------------------------------------------
# 3. Re-sync Python dependencies
# ---------------------------------------------------------------------------
log "Re-syncing Python dependencies (profile=${INSTALL_PROFILE}) ..."

if [[ "${INSTALL_PROFILE}" == "server" ]]; then
    REQUIREMENTS_FILE="${FIESTA_HOME}/requirements/server.lock.txt"
    if [[ ! -f "${REQUIREMENTS_FILE}" ]]; then
        die "Requirements file not found: ${REQUIREMENTS_FILE}"
    fi
    sudo -u "${FIESTA_USER}" "${VENV_DIR}/bin/pip" install \
        -r "${REQUIREMENTS_FILE}" \
        --quiet

elif [[ "${INSTALL_PROFILE}" == "show" ]]; then
    if [[ "${TORCH_GPU}" == true ]]; then
        log "Re-syncing PyTorch with CUDA 12.1 ..."
        sudo -u "${FIESTA_USER}" "${VENV_DIR}/bin/pip" install \
            torch torchvision torchaudio \
            --index-url https://download.pytorch.org/whl/cu121 \
            --quiet
    fi

    REQUIREMENTS_FILE="${FIESTA_HOME}/requirements/show.lock.txt"
    if [[ ! -f "${REQUIREMENTS_FILE}" ]]; then
        die "Requirements file not found: ${REQUIREMENTS_FILE}"
    fi
    sudo -u "${FIESTA_USER}" "${VENV_DIR}/bin/pip" install \
        -r "${REQUIREMENTS_FILE}" \
        --quiet
fi

log "Python dependencies synced."

# ---------------------------------------------------------------------------
# 4. Re-deploy systemd unit if changed
# ---------------------------------------------------------------------------
UNIT_SOURCE="${FIESTA_HOME}/systemd/${SYSTEMD_UNIT}"
UNIT_DEST="/etc/systemd/system/${SYSTEMD_UNIT}"
if [[ -f "${UNIT_SOURCE}" ]]; then
    if ! diff -q "${UNIT_SOURCE}" "${UNIT_DEST}" &>/dev/null 2>&1; then
        log "Systemd unit changed. Updating ..."
        cp "${UNIT_SOURCE}" "${UNIT_DEST}"
        chmod 644 "${UNIT_DEST}"
        systemctl daemon-reload
    fi
fi

# ---------------------------------------------------------------------------
# 5. Restart service
# ---------------------------------------------------------------------------
log "Restarting 911fiesta service ..."
systemctl restart "${SYSTEMD_UNIT}"
sleep 3

if systemctl is-active --quiet "${SYSTEMD_UNIT}"; then
    log "Service is running."
else
    err "Service did not start after update."
    err "Check: journalctl -u ${SYSTEMD_UNIT} -n 50"
    err "You can rollback with: sudo bash scripts/update_911fiesta.sh --rollback"
    exit 1
fi

# ---------------------------------------------------------------------------
# 6. Run healthcheck
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
            err "Healthcheck FAILED after update."
            err "Consider rolling back: sudo bash scripts/update_911fiesta.sh --rollback"
            exit 1
        fi
    else
        log "WARNING: Healthcheck script not found."
    fi
fi

# ---------------------------------------------------------------------------
# 7. Save new known-good state
# ---------------------------------------------------------------------------
echo "${POST_UPDATE_COMMIT}" > "${KNOWN_GOOD_FILE}"
chown "${FIESTA_USER}:${FIESTA_USER}" "${KNOWN_GOOD_FILE}"
log "Updated last-known-good to ${POST_UPDATE_COMMIT}."

# ---------------------------------------------------------------------------
# 8. Summary
# ---------------------------------------------------------------------------
log "=========================================="
log "Update complete."
log "=========================================="
log ""
log "  Before: ${PRE_UPDATE_COMMIT}"
log "  After:  ${POST_UPDATE_COMMIT}"
log "  Profile: ${INSTALL_PROFILE}"
log ""
if [[ "${DO_ROLLBACK}" == true ]]; then
    log "  Mode: ROLLBACK"
fi
log ""

exit 0

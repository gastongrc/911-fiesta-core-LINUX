#!/usr/bin/env bash
# =============================================================================
# 911 Fiesta V7 - Healthcheck Script
# =============================================================================
#
# Validates that the 911 Fiesta installation is functional:
#   1. System prerequisites (python3, ffmpeg, user, dirs)
#   2. Python venv and critical imports
#   3. Camera connectivity (RTSP/HTTP from vision_config.json)
#   4. Systemd service status
#   5. API endpoint responsiveness
#
# Usage:
#   bash scripts/healthcheck_911fiesta.sh
#
# Exit codes:
#   0 - All checks passed
#   1 - One or more checks failed
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
readonly FIESTA_HOME="/opt/911fiesta"
readonly VENV_DIR="${FIESTA_HOME}/.venv"
readonly CONFIG_DIR="/etc/911fiesta"
readonly VENV_PYTHON="${VENV_DIR}/bin/python3"
readonly SYSTEMD_UNIT="911fiesta.service"

# Counters
PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
pass()  { echo "[PASS] $*";  ((PASS_COUNT++)); }
fail()  { echo "[FAIL] $*";  ((FAIL_COUNT++)); }
warn()  { echo "[WARN] $*";  ((WARN_COUNT++)); }
info()  { echo "[INFO] $*"; }
sep()   { echo "-------------------------------------------"; }

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
echo "=========================================="
echo "HEALTHCHECK - 911 Fiesta V7"
echo "$(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="
echo ""

# ===================================================================
# Section 1: System Prerequisites
# ===================================================================
sep
info "Section 1: System Prerequisites"
sep

# Python 3
if command -v python3 &>/dev/null; then
    PY_VERSION=$(python3 --version 2>&1)
    pass "python3 found: ${PY_VERSION}"
else
    fail "python3 not found. Run bootstrap_linux.sh."
fi

# Git
if command -v git &>/dev/null; then
    pass "git found: $(git --version)"
else
    fail "git not found. Run bootstrap_linux.sh."
fi

# FFmpeg
if command -v ffmpeg &>/dev/null; then
    pass "ffmpeg found: $(ffmpeg -version 2>&1 | head -1)"
else
    fail "ffmpeg not found. Install: sudo apt install ffmpeg"
fi

# ffprobe (comes with ffmpeg, used for camera checks)
if command -v ffprobe &>/dev/null; then
    pass "ffprobe found."
else
    fail "ffprobe not found. Install: sudo apt install ffmpeg"
fi

# Fiesta user
if id fiesta &>/dev/null; then
    pass "User 'fiesta' exists."
else
    fail "User 'fiesta' not found. Run bootstrap_linux.sh."
fi

# Application directory
if [[ -d "${FIESTA_HOME}" ]]; then
    pass "App directory exists: ${FIESTA_HOME}"
else
    fail "App directory missing: ${FIESTA_HOME}"
fi

# Git repo
if [[ -d "${FIESTA_HOME}/.git" ]]; then
    COMMIT=$(git -C "${FIESTA_HOME}" rev-parse --short HEAD 2>/dev/null || echo "unknown")
    BRANCH=$(git -C "${FIESTA_HOME}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
    pass "Git repo present. Branch: ${BRANCH}, Commit: ${COMMIT}"
else
    fail "No git repository at ${FIESTA_HOME}. Run install_911fiesta.sh."
fi

# Config directory
if [[ -d "${CONFIG_DIR}" ]]; then
    pass "Config directory exists: ${CONFIG_DIR}"
else
    warn "Config directory missing: ${CONFIG_DIR}"
fi

echo ""

# ===================================================================
# Section 2: Python Virtual Environment & Imports
# ===================================================================
sep
info "Section 2: Python venv & Critical Imports"
sep

# Venv exists
if [[ -d "${VENV_DIR}" ]]; then
    pass "Virtual environment exists: ${VENV_DIR}"
else
    fail "Virtual environment missing: ${VENV_DIR}. Run install_911fiesta.sh."
    # Can't proceed with import checks
    echo ""
    echo "=========================================="
    echo "HEALTHCHECK RESULT: FAIL (${FAIL_COUNT} failures)"
    echo "=========================================="
    exit 1
fi

# Venv python works
if [[ -x "${VENV_PYTHON}" ]]; then
    VENV_PY_VERSION=$("${VENV_PYTHON}" --version 2>&1)
    pass "venv python3 works: ${VENV_PY_VERSION}"
else
    fail "venv python3 not executable: ${VENV_PYTHON}"
fi

# Critical Python imports check
check_python_import() {
    local module_name="$1"
    local display_name="${2:-$1}"

    local result
    result=$("${VENV_PYTHON}" -c "
import sys
try:
    mod = __import__('${module_name}')
    ver = getattr(mod, '__version__', 'ok')
    print(f'OK:{ver}')
except ImportError as e:
    print(f'FAIL:{e}')
except Exception as e:
    print(f'FAIL:{type(e).__name__}: {e}')
" 2>&1)

    if [[ "${result}" == OK:* ]]; then
        local version="${result#OK:}"
        pass "${display_name}: ${version}"
    else
        local error="${result#FAIL:}"
        fail "${display_name}: ${error}"
    fi
}

# Core imports
check_python_import "numpy" "numpy"
check_python_import "cv2" "cv2 (OpenCV)"

# FastAPI stack (server)
check_python_import "fastapi" "fastapi"
check_python_import "uvicorn" "uvicorn"
check_python_import "pydantic" "pydantic"

# Network
check_python_import "requests" "requests"

# Optional: Vision/ML (only warn, don't fail)
info "Vision/ML imports (optional for server profile):"

TORCH_RESULT=$("${VENV_PYTHON}" -c "
try:
    import torch
    cuda = torch.cuda.is_available()
    dev = ''
    if cuda:
        try: dev = torch.cuda.get_device_name(0)
        except: dev = 'CUDA device'
    print(f'OK:{torch.__version__} (CUDA: {cuda}{(\", \" + dev) if dev else \"\"})')
except ImportError as e:
    print(f'MISSING:{e}')
except Exception as e:
    print(f'ERROR:{e}')
" 2>&1)

if [[ "${TORCH_RESULT}" == OK:* ]]; then
    pass "torch: ${TORCH_RESULT#OK:}"
elif [[ "${TORCH_RESULT}" == MISSING:* ]]; then
    warn "torch: not installed (required for SHOW profile only)"
else
    warn "torch: ${TORCH_RESULT#ERROR:}"
fi

ULTRA_RESULT=$("${VENV_PYTHON}" -c "
try:
    from ultralytics import YOLO
    print('OK:YOLO available')
except ImportError as e:
    print(f'MISSING:{e}')
except Exception as e:
    print(f'ERROR:{e}')
" 2>&1)

if [[ "${ULTRA_RESULT}" == OK:* ]]; then
    pass "ultralytics: ${ULTRA_RESULT#OK:}"
elif [[ "${ULTRA_RESULT}" == MISSING:* ]]; then
    warn "ultralytics: not installed (required for SHOW profile only)"
else
    warn "ultralytics: ${ULTRA_RESULT#ERROR:}"
fi

# Audio (optional)
AUDIO_RESULT=$("${VENV_PYTHON}" -c "
try:
    import sounddevice; print(f'OK:{sounddevice.__version__}')
except ImportError as e:
    print(f'MISSING:{e}')
except Exception as e:
    print(f'ERROR:{e}')
" 2>&1)

if [[ "${AUDIO_RESULT}" == OK:* ]]; then
    pass "sounddevice: ${AUDIO_RESULT#OK:}"
elif [[ "${AUDIO_RESULT}" == MISSING:* ]]; then
    warn "sounddevice: not installed (required for SHOW profile only)"
else
    warn "sounddevice: ${AUDIO_RESULT#ERROR:}"
fi

# Internal module imports
info "Internal module imports:"
for mod in "api.main" "api.models" "services.app_state"; do
    INTERNAL_RESULT=$("${VENV_PYTHON}" -c "
import sys, os
sys.path.insert(0, '${FIESTA_HOME}')
os.chdir('${FIESTA_HOME}')
try:
    __import__('${mod}')
    print('OK')
except Exception as e:
    print(f'FAIL:{type(e).__name__}: {e}')
" 2>&1)

    if [[ "${INTERNAL_RESULT}" == "OK" ]]; then
        pass "${mod}: imported"
    else
        fail "${mod}: ${INTERNAL_RESULT#FAIL:}"
    fi
done

echo ""

# ===================================================================
# Section 3: Camera Connectivity
# ===================================================================
sep
info "Section 3: Camera Connectivity"
sep

# Try to read camera config
VISION_CONFIG=""
if [[ -f "${CONFIG_DIR}/vision_config.json" ]]; then
    VISION_CONFIG="${CONFIG_DIR}/vision_config.json"
elif [[ -f "${FIESTA_HOME}/vision_config.json" ]]; then
    VISION_CONFIG="${FIESTA_HOME}/vision_config.json"
fi

if [[ -z "${VISION_CONFIG}" ]]; then
    warn "No vision_config.json found. Skipping camera checks."
else
    info "Reading cameras from ${VISION_CONFIG}"

    # Extract camera URLs using Python (more reliable than jq for nested JSON)
    CAMERA_URLS=$("${VENV_PYTHON}" -c "
import json, sys
try:
    with open('${VISION_CONFIG}') as f:
        cfg = json.load(f)
    cameras = cfg.get('cameras', {})
    for name, cam in cameras.items():
        if not cam.get('enabled', False):
            continue
        host = cam.get('host', '')
        path = cam.get('path', '')
        user = cam.get('username', '')
        pwd  = cam.get('password', '')
        if host:
            auth = f'{user}:{pwd}@' if user else ''
            url = f'http://{auth}{host}{path}'
            print(f'{name}|{url}|{host}')
except Exception as e:
    print(f'ERROR|{e}|', file=sys.stderr)
" 2>&1)

    if [[ -z "${CAMERA_URLS}" ]]; then
        warn "No enabled cameras found in vision_config.json."
    else
        CAMERA_TESTED=false
        while IFS='|' read -r cam_name cam_url cam_host; do
            if [[ "${cam_name}" == "ERROR" ]]; then
                fail "Could not parse vision_config.json: ${cam_url}"
                continue
            fi

            CAMERA_TESTED=true
            info "Testing camera '${cam_name}' at ${cam_host} ..."

            # Test 1: Can we reach the host? (ping, 2 sec timeout)
            if ping -c 1 -W 2 "${cam_host}" &>/dev/null; then
                pass "Camera '${cam_name}': host ${cam_host} is reachable."
            else
                fail "Camera '${cam_name}': host ${cam_host} is NOT reachable."
                info "  Possible causes:"
                info "    - Camera is powered off or disconnected"
                info "    - Wrong IP in vision_config.json"
                info "    - Network/VLAN misconfiguration"
                info "    - Firewall blocking ICMP"
                continue
            fi

            # Test 2: Can ffprobe open the stream? (5 sec timeout)
            if timeout 5 ffprobe -v quiet -print_format json -show_streams "${cam_url}" &>/dev/null 2>&1; then
                pass "Camera '${cam_name}': stream is accessible."
            else
                # Try with just HTTP (no auth in URL, some cameras block ffprobe)
                warn "Camera '${cam_name}': ffprobe could not open stream."
                info "  URL: ${cam_url}"
                info "  Possible causes:"
                info "    - Camera requires different auth method"
                info "    - Incorrect path in vision_config.json"
                info "    - Camera firmware does not support MJPEG on this path"
                info "    - Network timeout (camera may be slow to respond)"
            fi
        done <<< "${CAMERA_URLS}"

        if [[ "${CAMERA_TESTED}" == false ]]; then
            warn "No cameras could be tested."
        fi
    fi
fi

echo ""

# ===================================================================
# Section 4: Systemd Service
# ===================================================================
sep
info "Section 4: Systemd Service"
sep

# Unit file installed
if [[ -f "/etc/systemd/system/${SYSTEMD_UNIT}" ]]; then
    pass "Systemd unit installed: /etc/systemd/system/${SYSTEMD_UNIT}"
else
    fail "Systemd unit not installed. Run install_911fiesta.sh."
fi

# Service enabled
if systemctl is-enabled --quiet "${SYSTEMD_UNIT}" 2>/dev/null; then
    pass "Service is enabled (starts on boot)."
else
    warn "Service is not enabled. Run: systemctl enable ${SYSTEMD_UNIT}"
fi

# Service active
if systemctl is-active --quiet "${SYSTEMD_UNIT}" 2>/dev/null; then
    pass "Service is active (running)."
else
    warn "Service is not running. Start with: systemctl start ${SYSTEMD_UNIT}"
    info "Check logs: journalctl -u ${SYSTEMD_UNIT} -n 30 --no-pager"
fi

echo ""

# ===================================================================
# Section 5: API Endpoint
# ===================================================================
sep
info "Section 5: API Responsiveness"
sep

# Check if the API is reachable on port 8000
API_URL="http://127.0.0.1:8000"
if command -v curl &>/dev/null; then
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 "${API_URL}/docs" 2>/dev/null || echo "000")
    if [[ "${HTTP_CODE}" == "200" ]]; then
        pass "API responding at ${API_URL} (HTTP ${HTTP_CODE})"
    elif [[ "${HTTP_CODE}" == "000" ]]; then
        warn "API not reachable at ${API_URL}. Service may still be starting."
        info "  If service is running, wait a few seconds and retry."
        info "  Check: curl -s ${API_URL}/docs"
    else
        warn "API returned HTTP ${HTTP_CODE} at ${API_URL}/docs"
    fi
else
    warn "curl not available. Cannot test API endpoint."
fi

echo ""

# ===================================================================
# Summary
# ===================================================================
echo "=========================================="
echo "HEALTHCHECK SUMMARY"
echo "=========================================="
echo ""
echo "  PASS: ${PASS_COUNT}"
echo "  FAIL: ${FAIL_COUNT}"
echo "  WARN: ${WARN_COUNT}"
echo ""

if [[ ${FAIL_COUNT} -gt 0 ]]; then
    echo "RESULT: FAIL"
    echo ""
    echo "Review [FAIL] items above and fix before operating."
    echo "Re-run: bash scripts/healthcheck_911fiesta.sh"
    exit 1
else
    if [[ ${WARN_COUNT} -gt 0 ]]; then
        echo "RESULT: PASS (with ${WARN_COUNT} warnings)"
    else
        echo "RESULT: PASS"
    fi
    echo ""
    echo "System is operational."
    exit 0
fi

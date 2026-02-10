#!/usr/bin/env bash
# =============================================================================
# 911 Fiesta V7 - Healthcheck Script
# =============================================================================
#
# Validates that the 911 Fiesta installation is functional:
#   1. System prerequisites (python3, ffmpeg, user, dirs)
#   2. Python venv and critical imports
#   3. Camera connectivity (MJPEG HTTP / RTSP from vision_config.json)
#   4. Hardware: GPU (NVIDIA) and Audio (USB device)
#   5. Systemd service status
#   6. API endpoint responsiveness
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
pass()  { echo "[PASS] $*";  PASS_COUNT=$((PASS_COUNT + 1)); }
fail()  { echo "[FAIL] $*";  FAIL_COUNT=$((FAIL_COUNT + 1)); }
warn()  { echo "[WARN] $*";  WARN_COUNT=$((WARN_COUNT + 1)); }
info()  { echo "[INFO] $*"; }
sep()   { echo "-------------------------------------------"; }

# Profile auto-detection: if PySide6 is installed, this is a SHOW machine.
# Camera failures are non-blocking (WARN) for SHOW profile.
IS_SHOW=false
if [[ -x "${VENV_PYTHON}" ]]; then
    if "${VENV_PYTHON}" -c "import PySide6" &>/dev/null; then
        IS_SHOW=true
    fi
fi

# Camera issue: WARN for SHOW, FAIL for server
cam_issue() { if [[ "${IS_SHOW}" == true ]]; then warn "$@"; else fail "$@"; fi; }

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

# Fiesta911 user
if id fiesta911 &>/dev/null; then
    FIESTA_GROUPS=$(id -Gn fiesta911 2>/dev/null | tr ' ' ',')
    pass "User 'fiesta911' exists. Groups: ${FIESTA_GROUPS}"
else
    fail "User 'fiesta911' not found. Run bootstrap_linux.sh."
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

# Env file
if [[ -f "${CONFIG_DIR}/911fiesta.env" ]]; then
    pass "Environment file exists: ${CONFIG_DIR}/911fiesta.env"
else
    warn "Environment file missing: ${CONFIG_DIR}/911fiesta.env"
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

# Core imports (required for all profiles)
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

    # Extract camera info using Python — matches real vision_config.py logic:
    #   type=mjpeg  -> build http://{user}:{pass}@{host}{path}
    #   type=rtsp   -> use url / url_main / url_sub directly
    CAMERA_LINES=$("${VENV_PYTHON}" -c "
import json, sys
try:
    with open('${VISION_CONFIG}') as f:
        cfg = json.load(f)
    cameras = cfg.get('cameras', {})
    for name, cam in cameras.items():
        if not cam.get('enabled', False):
            continue
        cam_type = cam.get('type', 'mjpeg').lower()
        host = cam.get('host', '')
        path = cam.get('path', '')
        user = cam.get('username', '')
        pwd  = cam.get('password', '')

        # RTSP mode: use url / url_main / url_sub
        if cam_type == 'rtsp' or cam.get('url_main') or cam.get('url_sub'):
            url = cam.get('url', '') or cam.get('url_sub', '') or cam.get('url_main', '')
            if not url:
                print(f'{name}|rtsp||{host}|NO_URL')
                continue
            # Inject credentials if not in URL
            if user and pwd and '@' not in url and url.startswith('rtsp://'):
                url = f'rtsp://{user}:{pwd}@{url[7:]}'
            target_host = host or url.split('@')[-1].split('/')[0].split(':')[0]
            print(f'{name}|rtsp|{url}|{target_host}|OK')

        # MJPEG mode: build from host + path
        elif host:
            auth = f'{user}:{pwd}@' if user else ''
            if host.startswith('http://') or host.startswith('https://'):
                url = f'{host}{path}'
            else:
                url = f'http://{auth}{host}{path}'
            print(f'{name}|mjpeg|{url}|{host}|OK')

        else:
            print(f'{name}|{cam_type}||{host}|NO_HOST')
except Exception as e:
    print(f'ERROR|error|{e}||PARSE_FAIL', file=sys.stderr)
    sys.exit(1)
" 2>&1)

    if [[ -z "${CAMERA_LINES}" ]]; then
        warn "No enabled cameras found in vision_config.json."
    else
        CAMERA_TESTED=false
        while IFS='|' read -r cam_name cam_proto cam_url cam_host cam_status; do
            if [[ "${cam_name}" == "ERROR" ]]; then
                cam_issue "Could not parse vision_config.json: ${cam_url}"
                continue
            fi

            if [[ "${cam_status}" == "NO_URL" ]]; then
                cam_issue "Camera '${cam_name}': type=${cam_proto} but no URL configured."
                continue
            fi

            if [[ "${cam_status}" == "NO_HOST" ]]; then
                cam_issue "Camera '${cam_name}': no host or URL configured."
                continue
            fi

            CAMERA_TESTED=true
            info "Testing camera '${cam_name}' (${cam_proto}) at ${cam_host} ..."

            # Test 1: Can we reach the host? (ping, 2 sec timeout)
            if ping -c 1 -W 2 "${cam_host}" &>/dev/null; then
                pass "Camera '${cam_name}': host ${cam_host} is reachable."
            else
                cam_issue "Camera '${cam_name}': host ${cam_host} is NOT reachable."
                info "  Protocol: ${cam_proto}"
                info "  Possible causes:"
                info "    - Camera is powered off or disconnected"
                info "    - Wrong IP in vision_config.json"
                info "    - Network/VLAN misconfiguration"
                info "    - Firewall blocking ICMP"
                continue
            fi

            # Test 2: Can ffprobe open the stream? (5 sec timeout)
            info "  Probing: ${cam_url}"
            FFPROBE_OUT=$(timeout 5 ffprobe -v error -print_format json -show_streams "${cam_url}" 2>&1) || true
            if echo "${FFPROBE_OUT}" | grep -q '"codec_type"'; then
                pass "Camera '${cam_name}': ${cam_proto} stream is accessible."
            else
                warn "Camera '${cam_name}': ffprobe could not open ${cam_proto} stream."
                info "  URL tested: ${cam_url}"
                info "  ffprobe output: $(echo "${FFPROBE_OUT}" | head -3)"
                info "  Possible causes:"
                if [[ "${cam_proto}" == "rtsp" ]]; then
                    info "    - RTSP port 554 blocked by firewall"
                    info "    - Wrong RTSP path or credentials"
                    info "    - Camera does not support RTSP on this URL"
                else
                    info "    - Camera requires different auth method (digest vs basic)"
                    info "    - Incorrect MJPEG path in vision_config.json"
                    info "    - Camera firmware does not serve MJPEG on this path"
                fi
                info "    - Network timeout (camera may be slow to respond)"
            fi
        done <<< "${CAMERA_LINES}"

        if [[ "${CAMERA_TESTED}" == false ]]; then
            warn "No cameras could be tested."
        fi
    fi
fi

echo ""

# ===================================================================
# Section 4: Hardware (GPU + Audio)
# ===================================================================
sep
info "Section 4: Hardware — GPU & Audio"
sep

# --- NVIDIA GPU ---
info "GPU check:"
if command -v nvidia-smi &>/dev/null; then
    GPU_INFO=$(nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader 2>/dev/null || echo "")
    if [[ -n "${GPU_INFO}" ]]; then
        pass "NVIDIA GPU detected: ${GPU_INFO}"
    else
        warn "nvidia-smi found but could not query GPU."
    fi

    # If torch is installed, verify CUDA is visible to PyTorch
    if [[ "${TORCH_RESULT:-}" == OK:* ]]; then
        CUDA_CHECK=$("${VENV_PYTHON}" -c "
import torch
if torch.cuda.is_available():
    print(f'OK:{torch.cuda.get_device_name(0)} (CUDA {torch.version.cuda})')
else:
    print('NOCUDA:torch installed but CUDA not available')
" 2>&1)
        if [[ "${CUDA_CHECK}" == OK:* ]]; then
            pass "PyTorch CUDA: ${CUDA_CHECK#OK:}"
        else
            warn "PyTorch CUDA: ${CUDA_CHECK#NOCUDA:}"
            info "  Check: nvidia-smi, driver version, and torch CUDA build match."
        fi
    fi
else
    warn "nvidia-smi not found. No NVIDIA driver installed."
    info "  If this machine has a GPU (e.g. 1080 Ti):"
    info "    sudo ubuntu-drivers install && sudo reboot"
fi

# --- USB Audio Device ---
info "Audio device check:"
if command -v arecord &>/dev/null; then
    AUDIO_DEVICES=$(arecord -l 2>/dev/null || true)
    if [[ -n "${AUDIO_DEVICES}" ]] && echo "${AUDIO_DEVICES}" | grep -q "card"; then
        pass "Audio capture devices found:"
        # Print each card line
        echo "${AUDIO_DEVICES}" | while IFS= read -r line; do
            if [[ "${line}" == *"card"* ]]; then
                info "  ${line}"
            fi
        done

        # Specifically look for Maono PS22
        if echo "${AUDIO_DEVICES}" | grep -qi "maono\|ps22"; then
            pass "Maono PS22 USB audio detected."
        else
            warn "Maono PS22 not detected. Found other device(s) above."
            info "  If Maono PS22 is connected, check: lsusb | grep -i maono"
        fi
    else
        warn "No audio capture devices found."
        info "  If a USB audio device (Maono PS22) should be present:"
        info "    1. Check USB connection: lsusb"
        info "    2. Check ALSA: cat /proc/asound/cards"
        info "    3. Ensure fiesta911 user is in 'audio' group: id fiesta911"
    fi
else
    warn "arecord not found. Install: sudo apt install alsa-utils"
fi

echo ""

# ===================================================================
# Section 4b: GUI / Display (SHOW profile)
# ===================================================================
sep
info "Section 4b: GUI / Display Readiness (SHOW profile)"
sep

# Check PySide6 import
PYSIDE_RESULT=$("${VENV_PYTHON}" -c "
try:
    import PySide6.QtWidgets; print(f'OK:{PySide6.__version__}')
except ImportError as e:
    print(f'MISSING:{e}')
except Exception as e:
    print(f'ERROR:{e}')
" 2>&1)

if [[ "${PYSIDE_RESULT}" == OK:* ]]; then
    pass "PySide6: ${PYSIDE_RESULT#OK:}"

    # If PySide6 is installed, this is a SHOW machine — check display
    if [[ -n "${DISPLAY:-}" ]]; then
        pass "DISPLAY is set: ${DISPLAY}"
    elif [[ -n "${WAYLAND_DISPLAY:-}" ]]; then
        pass "WAYLAND_DISPLAY is set: ${WAYLAND_DISPLAY}"
    else
        warn "No DISPLAY or WAYLAND_DISPLAY set."
        info "  SHOW requires a graphical session (X11 or Wayland)."
        info "  If running from SSH, this is expected. On the actual"
        info "  SHOW machine, the fiesta911 user must log into a desktop."
    fi

    # Check X socket exists
    if [[ -e "/tmp/.X11-unix/X0" ]]; then
        pass "X11 socket exists: /tmp/.X11-unix/X0"
    else
        warn "X11 socket /tmp/.X11-unix/X0 not found."
        info "  Expected on a machine with a running X server."
    fi

    # Check libxcb-cursor0 (common missing dep)
    if ldconfig -p 2>/dev/null | grep -q "libxcb-cursor"; then
        pass "libxcb-cursor0 is installed."
    else
        fail "libxcb-cursor0 NOT found. PySide6 xcb plugin will fail."
        info "  Fix: sudo apt install libxcb-cursor0"
    fi

    # Check autostart desktop file
    if [[ -f "/etc/xdg/autostart/911fiesta-show.desktop" ]]; then
        pass "XDG autostart file installed."
    else
        warn "XDG autostart file not installed."
        info "  Install: sudo cp /opt/911fiesta/systemd/911fiesta-show.desktop /etc/xdg/autostart/"
    fi
elif [[ "${PYSIDE_RESULT}" == MISSING:* ]]; then
    info "PySide6 not installed (server profile — GUI checks skipped)."
else
    warn "PySide6 import error: ${PYSIDE_RESULT#ERROR:}"
fi

echo ""

# ===================================================================
# Section 5: Systemd Service
# ===================================================================
sep
info "Section 5: Systemd Service"
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
# Section 6: API Endpoint
# ===================================================================
sep
info "Section 6: API Responsiveness"
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

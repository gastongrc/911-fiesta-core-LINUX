#!/usr/bin/env bash
# =============================================================================
# 911 Fiesta V7 - SHOW Boot Diagnostics
# =============================================================================
#
# Smoke test for the kiosk boot chain. Run on the SHOW machine to verify
# that all systemd units, Xorg, and the GUI are configured correctly.
#
# Usage:
#   bash /opt/911fiesta/scripts/diag_show_boot.sh
#
# =============================================================================
set -uo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "  ${GREEN}OK${NC}   $*"; }
warn() { echo -e "  ${YELLOW}WARN${NC} $*"; }
fail() { echo -e "  ${RED}FAIL${NC} $*"; }
info() { echo -e "  ---  $*"; }
tip()  { echo -e "       ${YELLOW}TIP:${NC} $*"; }

ERRORS=0
WARNINGS=0

echo ""
echo "============================================================"
echo " 911 FIESTA - SHOW BOOT DIAGNOSTICS"
echo "============================================================"
echo ""

# -------------------------------------------------------------------------
# 1. Default systemd target
# -------------------------------------------------------------------------
echo "[ Default Target ]"
DEFAULT_TARGET=$(systemctl get-default 2>/dev/null || echo "unknown")
info "systemctl get-default → ${DEFAULT_TARGET}"
if [[ "${DEFAULT_TARGET}" == "show.target" ]]; then
    pass "Default target is show.target"
else
    fail "Default target is '${DEFAULT_TARGET}', expected 'show.target'"
    tip "sudo systemctl set-default show.target"
    ((ERRORS++))
fi
echo ""

# -------------------------------------------------------------------------
# 2. show.target status
# -------------------------------------------------------------------------
echo "[ show.target ]"
if systemctl cat show.target &>/dev/null; then
    pass "show.target exists"
    # Check if it Wants show-gui.service
    if systemctl cat show.target 2>/dev/null | grep -q "show-gui.service"; then
        pass "show.target Wants show-gui.service"
    else
        fail "show.target does NOT reference show-gui.service"
        tip "Reinstall: sudo cp /opt/911fiesta/systemd/show.target /etc/systemd/system/"
        ((ERRORS++))
    fi
else
    fail "show.target not found"
    tip "sudo cp /opt/911fiesta/systemd/show.target /etc/systemd/system/"
    ((ERRORS++))
fi
echo ""

# -------------------------------------------------------------------------
# 3. show-gui.service
# -------------------------------------------------------------------------
echo "[ show-gui.service ]"
if systemctl cat show-gui.service &>/dev/null; then
    pass "show-gui.service exists"
else
    fail "show-gui.service NOT found in systemd"
    tip "sudo cp /opt/911fiesta/systemd/show-gui.service /etc/systemd/system/"
    tip "sudo systemctl daemon-reload && sudo systemctl enable show-gui.service"
    ((ERRORS++))
fi

ENABLED=$(systemctl is-enabled show-gui.service 2>/dev/null || echo "not-found")
if [[ "${ENABLED}" == "enabled" || "${ENABLED}" == "enabled-runtime" ]]; then
    pass "show-gui.service is enabled"
else
    fail "show-gui.service is ${ENABLED}"
    tip "sudo systemctl enable show-gui.service"
    ((ERRORS++))
fi

ACTIVE=$(systemctl is-active show-gui.service 2>/dev/null || echo "inactive")
if [[ "${ACTIVE}" == "active" ]]; then
    pass "show-gui.service is active (running)"
else
    warn "show-gui.service is ${ACTIVE}"
    tip "Check logs: journalctl -u show-gui.service -b --no-pager | tail -50"
    ((WARNINGS++))
fi
echo ""

# -------------------------------------------------------------------------
# 4. 911fiesta.service (API — should be independent)
# -------------------------------------------------------------------------
echo "[ 911fiesta.service (API) ]"
API_ACTIVE=$(systemctl is-active 911fiesta.service 2>/dev/null || echo "inactive")
if [[ "${API_ACTIVE}" == "active" ]]; then
    pass "API service is active (running)"
else
    info "API service is ${API_ACTIVE} (not required for SHOW GUI)"
fi
echo ""

# -------------------------------------------------------------------------
# 5. GDM / display-manager
# -------------------------------------------------------------------------
echo "[ Display Manager ]"
GDM_ENABLED=$(systemctl is-enabled gdm.service 2>/dev/null || echo "not-found")
if [[ "${GDM_ENABLED}" == "enabled" ]]; then
    warn "GDM is enabled — may conflict with show-gui.service"
    tip "sudo systemctl disable gdm"
    ((WARNINGS++))
else
    pass "GDM is ${GDM_ENABLED} (no conflict)"
fi
echo ""

# -------------------------------------------------------------------------
# 6. Xorg / DISPLAY
# -------------------------------------------------------------------------
echo "[ Xorg / Display ]"
if [[ -n "${DISPLAY:-}" ]]; then
    pass "DISPLAY=${DISPLAY}"
else
    info "DISPLAY not set (normal if running from SSH — check via show-gui.service logs)"
fi

# Check if any X server is running
if pgrep -x Xorg >/dev/null 2>&1 || pgrep -x X >/dev/null 2>&1; then
    pass "Xorg process is running"
else
    warn "No Xorg process detected"
    tip "If show-gui.service is active, Xorg should be running"
    ((WARNINGS++))
fi

# Check X socket
if [[ -e /tmp/.X11-unix/X0 ]]; then
    pass "X socket /tmp/.X11-unix/X0 exists"
else
    warn "X socket /tmp/.X11-unix/X0 not found"
    ((WARNINGS++))
fi
echo ""

# -------------------------------------------------------------------------
# 7. User & Groups
# -------------------------------------------------------------------------
echo "[ User: fiesta911 ]"
if id fiesta911 &>/dev/null; then
    pass "User fiesta911 exists"
    GROUPS_ACTUAL=$(id -nG fiesta911 2>/dev/null)
    info "Groups: ${GROUPS_ACTUAL}"
    for grp in video tty render audio; do
        if echo "${GROUPS_ACTUAL}" | grep -qw "${grp}"; then
            pass "fiesta911 in '${grp}' group"
        else
            if getent group "${grp}" &>/dev/null; then
                fail "fiesta911 NOT in '${grp}' group"
                tip "sudo usermod -aG ${grp} fiesta911"
                ((ERRORS++))
            else
                info "Group '${grp}' does not exist on this system (OK)"
            fi
        fi
    done
else
    fail "User fiesta911 does not exist"
    tip "Run: sudo bash scripts/bootstrap_linux.sh --profile show"
    ((ERRORS++))
fi
echo ""

# -------------------------------------------------------------------------
# 8. Key files
# -------------------------------------------------------------------------
echo "[ Key Files ]"
for f in /opt/911fiesta/.xinitrc \
         /opt/911fiesta/scripts/run_show.sh \
         /opt/911fiesta/.venv/bin/python3 \
         /opt/911fiesta/main.py; do
    if [[ -e "${f}" ]]; then
        pass "${f}"
    else
        fail "${f} MISSING"
        ((ERRORS++))
    fi
done
echo ""

# -------------------------------------------------------------------------
# 9. Recent journal (show-gui.service)
# -------------------------------------------------------------------------
echo "[ Recent Logs: show-gui.service (last 20 lines) ]"
echo "------------------------------------------------------------"
journalctl -u show-gui.service -b --no-pager -n 20 2>/dev/null || \
    echo "  (no journal entries for show-gui.service)"
echo "------------------------------------------------------------"
echo ""

# -------------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------------
echo "============================================================"
if [[ ${ERRORS} -eq 0 && ${WARNINGS} -eq 0 ]]; then
    echo -e " ${GREEN}ALL CHECKS PASSED${NC}"
elif [[ ${ERRORS} -eq 0 ]]; then
    echo -e " ${YELLOW}PASSED with ${WARNINGS} warning(s)${NC}"
else
    echo -e " ${RED}${ERRORS} error(s), ${WARNINGS} warning(s)${NC}"
fi
echo "============================================================"
echo ""

exit ${ERRORS}

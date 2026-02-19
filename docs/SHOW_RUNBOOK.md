# 911 Fiesta V7 - SHOW Runbook (Linux GUI)

## Overview

The **SHOW** profile runs the full 911 Fiesta application with a PySide6 GUI
on a dedicated Core911 machine with a physical display (monitor + keyboard).
It includes audio analysis, vision/camera pipelines, and the lighting cue engine.

**Entrypoint:** `main.py` (PySide6 QApplication)
**User:** `fiesta911` (login user with `/bin/bash` shell)
**Target OS:** Ubuntu 22.04.5 LTS (amd64)

---

## Architecture: API vs SHOW

Two independent processes, two independent systemd units:

```
                  ┌──────────────────────────────────────────┐
                  │           Ubuntu 22.04 LTS                │
                  │                                           │
  multi-user ──► │  911fiesta.service (headless API)          │
  .target         │    uvicorn api.main:app :8000              │
                  │    QT_QPA_PLATFORM=offscreen               │
                  │                                           │
  show.target ──► │  show-gui.service (Xorg + GUI)            │
                  │    startx → .xinitrc → openbox             │
                  │      → run_show.sh → python main.py        │
                  │        QT_QPA_PLATFORM=xcb, DISPLAY=:0     │
                  └──────────────────────────────────────────┘
```

- **API** (`911fiesta.service`): headless FastAPI on port 8000. No display needed.
- **SHOW GUI** (`show-gui.service`): PySide6 GUI on Xorg. Requires physical display.
- They do NOT conflict — different entry points, different processes.
- `show.target` conflicts with `graphical.target` (no GDM/GNOME alongside).

---

## Installation (Clean Machine)

```bash
# 1. Get the installer
git clone https://github.com/gastongrc/911-fiesta-core-LINUX.git /tmp/911fiesta-installer
cd /tmp/911fiesta-installer

# 2. Bootstrap with SHOW profile (installs GUI deps, creates login user)
sudo bash scripts/bootstrap_linux.sh --profile show

# 3. Set password for fiesta911 user
sudo passwd fiesta911

# 4. Install application with SHOW profile
sudo bash scripts/install_911fiesta.sh --profile show --torch-gpu

# 5. Verify
bash scripts/diag_show_boot.sh

# 6. Reboot — kiosk starts automatically
sudo reboot
```

---

## Kiosk Boot Chain

```
BIOS → systemd → show.target (default target)
  ├── multi-user.target (networking, 911fiesta.service API, etc.)
  └── show-gui.service
        → startx /opt/911fiesta/.xinitrc -- :0 vt7
          → xset (disable blanking/DPMS)
          → xrandr (detect connected output, set 1920x1080)
          → openbox (minimal WM)
          → run_show.sh
            → verify venv, DISPLAY, user groups
            → QT_QPA_PLATFORM=xcb
            → python main.py (PySide6 GUI)
```

### Key: systemd manages everything

- `show-gui.service` is a proper systemd service — not a `.bash_profile` hack
- Logs go to journal: `journalctl -u show-gui.service -f`
- Restarts on crash: `Restart=on-failure`, `RestartSec=5`
- Clean dependency: `show.target` → `Wants=show-gui.service`
- No GDM, no display manager, no desktop environment

### Key: Dynamic Video Output Detection

The `.xinitrc` uses `xrandr` to find the first connected output dynamically:
```sh
CONNECTED_OUTPUT=$(xrandr --query | grep " connected" | head -n1 | awk '{print $1}')
xrandr --output "${CONNECTED_OUTPUT}" --mode 1920x1080 --rate 60
```

Works with **any** output: `HDMI-0`, `HDMI-1`, `DP-1`, `VGA-1`, etc.

### Key: Driver-Agnostic Xorg

`xorg/10-monitor.conf` does NOT hardcode any GPU driver. Xorg auto-detects
the correct driver (nvidia, modesetting, intel, amdgpu).

---

## GDM + XDG Autostart (Alternative — dev/test only)

For development machines with GNOME desktop:

```bash
# 1. Disable show-gui.service (conflicts with GDM)
sudo systemctl disable show-gui.service

# 2. Set graphical target
sudo systemctl set-default graphical.target

# 3. Install XDG autostart file
sudo cp /opt/911fiesta/systemd/911fiesta-show.desktop /etc/xdg/autostart/

# 4. Configure GDM autologin
sudo nano /etc/gdm3/custom.conf
# Set:
#   [daemon]
#   AutomaticLoginEnable=true
#   AutomaticLogin=fiesta911

# 5. Reboot
sudo reboot
```

---

## User Permissions

The `fiesta911` user MUST be in these groups:

| Group | Why |
|-------|-----|
| `video` | Access to GPU device nodes (`/dev/dri/*`) |
| `tty` | Access to TTY/VT for Xorg |
| `render` | Access to GPU render nodes (DRM) |
| `audio` | Access to USB audio devices (ALSA) |

The bootstrap script adds these automatically. To verify/fix:

```bash
id fiesta911
# Fix if missing:
sudo usermod -aG video,tty,render,audio fiesta911
# Log out and back in for changes to take effect
```

---

## Service Management

```bash
# Status
systemctl status show-gui.service
systemctl status 911fiesta.service

# Logs (live)
journalctl -u show-gui.service -f
journalctl -u 911fiesta.service -f

# Restart GUI
sudo systemctl restart show-gui.service

# Stop GUI (Xorg stops too)
sudo systemctl stop show-gui.service

# Diagnostic
bash /opt/911fiesta/scripts/diag_show_boot.sh
```

---

## Manual Launch (testing only)

```bash
# As fiesta911 user, in a graphical session:
bash /opt/911fiesta/scripts/run_show.sh

# Or directly:
cd /opt/911fiesta
source .venv/bin/activate
export QT_QPA_PLATFORM=xcb
python main.py
```

---

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `DISPLAY` | `:0` (from startx) | X11 display server |
| `QT_QPA_PLATFORM` | `xcb` | Qt platform plugin (must be `xcb` for GUI) |
| `QT_AUTO_SCREEN_SCALE_FACTOR` | `0` | HiDPI scaling (disabled for kiosk) |
| `QT_SCALE_FACTOR` | `1` | Manual scale factor (1:1 pixel mapping) |
| `CUDA_VISIBLE_DEVICES` | (all) | Restrict GPU selection |

**Safety:** `run_show.sh` refuses to launch if `QT_QPA_PLATFORM=offscreen`.

---

## Updating

```bash
sudo bash /opt/911fiesta/scripts/update_911fiesta.sh --profile show
sudo systemctl restart show-gui.service
```

---

## Troubleshooting

### Run diagnostics first

```bash
bash /opt/911fiesta/scripts/diag_show_boot.sh
```

### show-gui.service fails to start

```bash
journalctl -u show-gui.service -b --no-pager | tail -50
```

Common causes:
- Missing groups: `id fiesta911` must show `video tty render audio`
- VT conflict: Another X server on `:0` or `vt7`. Stop GDM: `sudo systemctl stop gdm`
- Missing Xorg: `which startx` — if not found: `sudo apt install xinit`

### Xorg fails to start

1. Check Xorg log: `cat /var/log/Xorg.0.log | grep "(EE)"`
2. Check if `10-monitor.conf` is blocking: `sudo rm /etc/X11/xorg.conf.d/10-monitor.conf` and retry
3. Check user groups: `id fiesta911` — needs `video tty render`
4. Check NVIDIA driver: `nvidia-smi` — if not found, Xorg uses `modesetting` (OK)

### "Could not find or load the Qt platform plugin xcb"

```bash
sudo apt install libxcb-cursor0 libxcb-icccm4 libxcb-image0 \
    libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 \
    libxcb-shape0 libxcb-xfixes0
```

### "No DISPLAY set"

- If from `show-gui.service`: check journal for Xorg startup errors
- If from SSH: `export DISPLAY=:0 && xhost +local:`

### "QT_QPA_PLATFORM=offscreen — refusing to launch"

API env leaked. Fix: `export QT_QPA_PLATFORM=xcb`

### SHOW starts but no audio

- Check USB audio: `arecord -l`
- Check group: `id fiesta911` — needs `audio`
- Check config: `/etc/911fiesta/audio_monitor.json`

---

## Rollback to GNOME Desktop

```bash
sudo systemctl disable show-gui.service
sudo systemctl set-default graphical.target
sudo systemctl enable gdm
sudo reboot
```

---

## Files Reference

| File | Purpose |
|---|---|
| `main.py` | SHOW entrypoint (PySide6 GUI) |
| `api/main.py` | API entrypoint (FastAPI, headless) |
| `systemd/show-gui.service` | **Xorg kiosk service (systemd-managed)** |
| `systemd/show.target` | Custom kiosk target (Wants show-gui.service) |
| `systemd/911fiesta.service` | API systemd unit (headless) |
| `scripts/run_show.sh` | GUI wrapper: venv + groups check + display + launch |
| `scripts/xinitrc_show` | Xorg session: xrandr + openbox + run_show.sh |
| `scripts/diag_show_boot.sh` | Boot diagnostics / smoke test |
| `xorg/10-monitor.conf` | Xorg config (driver-agnostic, 1920x1080) |
| `systemd/show-getty-autologin.conf` | TTY1 autologin (fallback) |
| `systemd/911fiesta-show.desktop` | XDG autostart (GDM alternative) |
| `scripts/bootstrap_linux.sh` | System setup (packages, user, groups) |
| `scripts/install_911fiesta.sh` | App install (deploys show-gui.service) |

## Validation Checklist

After install + reboot, these must all pass:

```bash
# 1. Default target
systemctl get-default
# Expected: show.target

# 2. show-gui.service running
systemctl status show-gui.service
# Expected: active (running)

# 3. Xorg running
pgrep Xorg
# Expected: PID

# 4. App running
pgrep -f "python.*main.py"
# Expected: PID

# 5. Journal clean (no crash loop)
journalctl -u show-gui.service -b --no-pager | tail -20
# Expected: startup messages, no errors

# 6. Diagnostics
bash /opt/911fiesta/scripts/diag_show_boot.sh
# Expected: ALL CHECKS PASSED
```

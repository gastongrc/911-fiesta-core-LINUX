# 911 Fiesta V7 - SHOW Runbook (Linux GUI)

## Overview

The **SHOW** profile runs the full 911 Fiesta application with a PySide6 GUI
on a dedicated Core911 machine with a physical display (monitor + keyboard).
It includes audio analysis, vision/camera pipelines, and the lighting cue engine.

**Entrypoint:** `main.py` (PySide6 QApplication)
**User:** `fiesta911` (login user with `/bin/bash` shell)
**Target OS:** Ubuntu 22.04.5 LTS (amd64)

### Two Launch Paths

| Path | When to use |
|------|-------------|
| **Kiosk (primary)** | Production Core911: no desktop, boots straight to app |
| **GDM + XDG autostart** | Dev/test: Ubuntu Desktop with GNOME, app auto-starts at login |

The `install_911fiesta.sh --profile show` deploys the **kiosk** path by default.

---

## Architecture: API vs SHOW

```
                  ┌─────────────────────────────────────────┐
                  │           Ubuntu 22.04 LTS               │
                  │                                          │
  systemd ──────► │  911fiesta.service (headless API)        │
  (always on)     │    uvicorn api.main:app :8000            │
                  │    QT_QPA_PLATFORM=offscreen             │
                  │                                          │
  show.target ──► │  getty@tty1 autologin → .bash_profile    │
  (kiosk only)    │    → startx → .xinitrc → openbox         │
                  │      → run_show.sh → python main.py      │
                  │        QT_QPA_PLATFORM=xcb               │
                  └─────────────────────────────────────────┘
```

- The **API** runs as a systemd service (headless, no display).
- The **SHOW GUI** runs as a user session process (requires Xorg + display).
- They do NOT conflict — different entry points, different processes.

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
bash scripts/healthcheck_911fiesta.sh

# 6. Reboot — kiosk starts automatically
sudo reboot
```

---

## Kiosk Boot Chain (Primary)

```
BIOS → systemd → show.target → multi-user.target
  → getty@tty1 (autologin fiesta911)
    → .bash_profile (checks TTY1 + no DISPLAY)
      → startx ~/.xinitrc
        → xset (disable blanking/DPMS)
        → xrandr (detect connected output, set 1920x1080)
        → openbox (minimal WM)
        → run_show.sh
          → verify venv, DISPLAY, user groups
          → QT_QPA_PLATFORM=xcb
          → python main.py
```

### Key: Dynamic Video Output Detection

The `.xinitrc` uses `xrandr` to find the first connected output dynamically:
```sh
CONNECTED_OUTPUT=$(xrandr --query | grep " connected" | head -n1 | awk '{print $1}')
xrandr --output "${CONNECTED_OUTPUT}" --mode 1920x1080 --rate 60
```

This works with **any** output name: `HDMI-0`, `HDMI-1`, `DP-1`, `VGA-1`, etc.
No hardcoded output names.

### Key: Driver-Agnostic Xorg Config

`xorg/10-monitor.conf` does NOT hardcode `Driver "nvidia"`. Xorg auto-detects
the correct driver (nvidia, modesetting, intel, amdgpu). The config only sets
the preferred resolution.

---

## GDM + XDG Autostart (Alternative)

For development machines with GNOME desktop:

```bash
# 1. Install XDG autostart file
sudo cp /opt/911fiesta/systemd/911fiesta-show.desktop /etc/xdg/autostart/

# 2. Configure GDM autologin
sudo nano /etc/gdm3/custom.conf
# Set:
#   [daemon]
#   AutomaticLoginEnable=true
#   AutomaticLogin=fiesta911

# 3. Reboot
sudo reboot
```

> **Note:** LightDM uses `/etc/lightdm/lightdm.conf`:
> ```ini
> [Seat:*]
> autologin-user=fiesta911
> autologin-user-timeout=0
> ```

---

## User Permissions

The `fiesta911` user MUST be in these groups:

| Group | Why |
|-------|-----|
| `video` | Access to GPU device nodes (`/dev/dri/*`) |
| `tty` | Access to TTY for startx without root |
| `render` | Access to GPU render nodes (DRM) |
| `audio` | Access to USB audio devices (ALSA) |

The bootstrap script adds these automatically. To verify/fix:

```bash
# Check
id fiesta911

# Fix if missing
sudo usermod -aG video,tty,render,audio fiesta911
# User must log out and back in for group changes to take effect
```

---

## Manual Launch

For testing only (autologin should be configured on production machines):

```bash
# As the fiesta911 user, in a graphical session:
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
| `DISPLAY` | (from session) | X11 display server |
| `QT_QPA_PLATFORM` | `xcb` | Qt platform plugin (must be `xcb` for GUI) |
| `QT_AUTO_SCREEN_SCALE_FACTOR` | `0` | HiDPI scaling (disabled for kiosk) |
| `QT_SCALE_FACTOR` | `1` | Manual scale factor (1:1 pixel mapping) |
| `CUDA_VISIBLE_DEVICES` | (all) | Restrict GPU selection |

**Safety:** `run_show.sh` refuses to launch if `QT_QPA_PLATFORM=offscreen`.

---

## Updating

```bash
sudo bash /opt/911fiesta/scripts/update_911fiesta.sh --profile show
# If GPU torch needs updating:
sudo bash /opt/911fiesta/scripts/update_911fiesta.sh --profile show --torch-gpu
```

---

## Troubleshooting

### Xorg fails to start (startx crash)

1. Check Xorg log: `cat /var/log/Xorg.0.log | grep "(EE)"`
2. Check if `10-monitor.conf` is blocking: `sudo rm /etc/X11/xorg.conf.d/10-monitor.conf` and retry
3. Check user groups: `id fiesta911` — needs `video tty render`
4. Check NVIDIA driver: `nvidia-smi` — if not found, Xorg will use `modesetting` (OK)

### "Could not find or load the Qt platform plugin xcb"

Missing xcb libraries. Run:
```bash
sudo apt install libxcb-cursor0 libxcb-icccm4 libxcb-image0 \
    libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 \
    libxcb-shape0 libxcb-xfixes0
```

Or re-run bootstrap: `sudo bash scripts/bootstrap_linux.sh --profile show`

### "Could not connect to display"

- Ensure you are in a graphical session (not SSH without X forwarding).
- Check: `echo $DISPLAY` — should be `:0` or `:1`.
- If running from SSH for testing: `export DISPLAY=:0` and `xhost +local:`.

### "QT_QPA_PLATFORM=offscreen — refusing to launch"

The `run_show.sh` script detected that `QT_QPA_PLATFORM=offscreen` is set.
This happens when the API service's env file leaks into the GUI session.
Fix: `unset QT_QPA_PLATFORM` or `export QT_QPA_PLATFORM=xcb` before launching.

### PySide6 not found

```bash
source /opt/911fiesta/.venv/bin/activate
pip install PySide6==6.9.0
```

### SHOW starts but no audio

- Check USB audio device: `arecord -l`
- Ensure fiesta911 is in `audio` group: `id fiesta911`
- Check config: `/etc/911fiesta/audio_monitor.json`

### SHOW starts but cameras fail

- Check camera connectivity: `ping 192.168.1.110`
- Check config: `/etc/911fiesta/vision_config.json`
- Run healthcheck: `bash /opt/911fiesta/scripts/healthcheck_911fiesta.sh`

---

## Files Reference

| File | Purpose |
|---|---|
| `main.py` | SHOW entrypoint (PySide6 GUI) |
| `api/main.py` | API entrypoint (FastAPI, headless) |
| `scripts/run_show.sh` | GUI wrapper: venv + groups check + display + launch |
| `scripts/xinitrc_show` | Xorg session: xrandr output detection + openbox + launch |
| `xorg/10-monitor.conf` | Xorg monitor config (driver-agnostic, 1920x1080) |
| `systemd/911fiesta.service` | API systemd unit (headless) |
| `systemd/show.target` | Kiosk systemd target |
| `systemd/show-getty-autologin.conf` | TTY1 autologin drop-in |
| `systemd/911fiesta-show.desktop` | XDG autostart (GDM alternative) |
| `scripts/bootstrap_linux.sh` | System setup (packages, user, groups) |
| `scripts/install_911fiesta.sh` | App install (venv, deps, kiosk config) |
| `scripts/healthcheck_911fiesta.sh` | Validation script |

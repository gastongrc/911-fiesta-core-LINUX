# 911 Fiesta V7 - SHOW Runbook (Linux GUI)

## Overview

The **SHOW** profile runs the full 911 Fiesta application with a PySide6 GUI
on a dedicated Core911 machine with a physical display (monitor + keyboard).
It includes audio analysis, vision/camera pipelines, and the lighting cue engine.

**Entrypoint:** `main.py` (PySide6 QApplication)
**Launch method:** XDG autostart via `.desktop` file + GDM autologin
**User:** `fiesta911` (login user with `/bin/bash` shell)
**Target OS:** Ubuntu 22.04.5 LTS Desktop (amd64)

---

## Prerequisites

- Ubuntu 22.04.5 LTS Desktop (amd64) — only supported target
- Physical display connected (HDMI/DP)
- NVIDIA GPU with driver installed (for YOLO/vision)
- USB audio device (Maono PS22) connected

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

# 5. Install autostart desktop file
sudo cp /opt/911fiesta/systemd/911fiesta-show.desktop /etc/xdg/autostart/

# 6. Configure GDM autologin (MANDATORY for Core911)
sudo nano /etc/gdm3/custom.conf
# Set: AutomaticLoginEnable=true / AutomaticLogin=fiesta911

# 7. Verify
bash scripts/healthcheck_911fiesta.sh

# 8. Reboot — SHOW starts automatically
sudo reboot
```

---

## How SHOW Starts

1. Machine boots → GDM auto-logs in as `fiesta911` (autologin is mandatory)
2. The desktop environment reads `/etc/xdg/autostart/911fiesta-show.desktop`
3. The `.desktop` file calls `/opt/911fiesta/scripts/run_show.sh`
4. `run_show.sh` activates the venv, sets `QT_QPA_PLATFORM=xcb`, and executes
   `python main.py`
5. The PySide6 GUI opens fullscreen

### Why XDG Autostart (not systemd)?

The SHOW needs a real graphical session with `DISPLAY` set. A systemd system
service runs before any user logs in and has no access to the display server.
`systemd --user` units are possible but require careful `DISPLAY` forwarding
and are harder to debug. XDG autostart is the standard mechanism for launching
GUI applications at login, and it works across GNOME, KDE, XFCE, etc.

---

## GDM Autologin (Mandatory)

Core911 is a dedicated SHOW machine. GDM autologin is **mandatory** so
the machine boots directly into the GUI without manual login.

```bash
sudo nano /etc/gdm3/custom.conf
```

Set:
```ini
[daemon]
AutomaticLoginEnable=true
AutomaticLogin=fiesta911
```

Then reboot. The machine will auto-login as `fiesta911` and the SHOW starts
via XDG autostart.

> **Note:** LightDM is NOT the default on Ubuntu 22.04 Desktop. If your
> install uses LightDM instead of GDM, set:
> ```ini
> # /etc/lightdm/lightdm.conf
> [Seat:*]
> autologin-user=fiesta911
> autologin-user-timeout=0
> ```

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
| `QT_AUTO_SCREEN_SCALE_FACTOR` | `1` | HiDPI scaling |
| `CUDA_VISIBLE_DEVICES` | (all) | Restrict GPU selection |

---

## Updating

```bash
sudo bash /opt/911fiesta/scripts/update_911fiesta.sh --profile show
# If GPU torch needs updating:
sudo bash /opt/911fiesta/scripts/update_911fiesta.sh --profile show --torch-gpu
```

---

## Troubleshooting

### "Could not find or load the Qt platform plugin xcb"

Missing xcb libraries. Run:
```bash
sudo apt install libxcb-cursor0 libxcb-icccm4 libxcb-image0 \
    libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 \
    libxcb-shape0 libxcb-xfixes0
```

Or re-run bootstrap:
```bash
sudo bash scripts/bootstrap_linux.sh --profile show
```

### "Could not connect to display"

- Ensure you are in a graphical session (not SSH without X forwarding).
- Check: `echo $DISPLAY` — should be `:0` or `:1`.
- If running from SSH for testing: `export DISPLAY=:0` and `xhost +local:`.

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
| `scripts/run_show.sh` | Wrapper: venv + display + launch |
| `systemd/911fiesta-show.desktop` | XDG autostart source |
| `/etc/xdg/autostart/911fiesta-show.desktop` | Installed autostart |
| `requirements/show.lock.txt` | Pinned SHOW dependencies |
| `/etc/911fiesta/vision_config.json` | Camera configuration |
| `/etc/911fiesta/audio_monitor.json` | Audio configuration |
| `/etc/911fiesta/avolites_config.json` | Lighting console configuration |

# 911 Fiesta V7 - Linux Installation Guide (Ubuntu 24.04.3)

## Overview

This guide covers a reproducible, one-command installation of 911 Fiesta V7 on
Ubuntu 24.04.3 Live Server. The entire flow is scripted and non-interactive.

**Target OS:** Ubuntu 24.04.3 LTS (server or desktop)
**Best effort:** Ubuntu 22.04 LTS (see `docs/TROUBLESHOOTING_LINUX.md`)
**Runtime:** Python 3.11 via system `python3-venv`
**Profiles:** `server` (headless API) or `show` (full GUI + vision + audio)

---

## Quick Start

### Server (headless API)

```bash
git clone https://github.com/gastongrc/911-fiesta-core-LINUX.git /tmp/911fiesta-installer
cd /tmp/911fiesta-installer
sudo bash scripts/bootstrap_linux.sh
sudo bash scripts/install_911fiesta.sh
systemctl status 911fiesta
bash scripts/healthcheck_911fiesta.sh
```

### SHOW (GUI with display)

```bash
git clone https://github.com/gastongrc/911-fiesta-core-LINUX.git /tmp/911fiesta-installer
cd /tmp/911fiesta-installer
sudo bash scripts/bootstrap_linux.sh --profile show
sudo passwd fiesta
sudo bash scripts/install_911fiesta.sh --profile show --torch-gpu
sudo cp /opt/911fiesta/systemd/911fiesta-show.desktop /etc/xdg/autostart/
bash scripts/healthcheck_911fiesta.sh
# Log in as fiesta in the desktop — SHOW starts automatically
```

See `docs/SHOW_RUNBOOK.md` for detailed SHOW setup including auto-login.

---

## Prerequisites

- Ubuntu 24.04.3 LTS (server or desktop)
- Root/sudo access
- Internet connectivity (for apt and pip)
- Minimum 4 GB RAM, 20 GB disk (more for SHOW profile with ML models)

---

## Installation Profiles

| Profile  | Use case               | Includes                                    |
|----------|------------------------|---------------------------------------------|
| `server` | Headless API server    | FastAPI, uvicorn, opencv-headless, numpy     |
| `show`   | Full show runtime      | All of server + PySide6, torch, YOLO, audio  |

Default is `server`. To install with full SHOW dependencies:

```bash
sudo bash scripts/install_911fiesta.sh --profile show
```

For GPU-accelerated vision (NVIDIA):

```bash
sudo bash scripts/install_911fiesta.sh --profile show --torch-gpu
```

---

## Step-by-Step Walkthrough

### Step 1: Bootstrap (`bootstrap_linux.sh`)

Run as root. This script:

1. **Installs system packages** via apt (non-interactive):
   - Build tools: `build-essential`, `pkg-config`, `git`, `curl`, `wget`
   - Python: `python3`, `python3-pip`, `python3-venv`, `python3-dev`
   - OpenCV deps: `libgl1`, `libglib2.0-0`, `libsm6`, `libxext6`, `libxrender1`
   - Qt/PySide6: `libegl1`, `libxkbcommon0`, `libdbus-1-3`, `libfontconfig1`
   - FFmpeg: `ffmpeg` + dev libraries
   - Audio: `libportaudio2`, `portaudio19-dev`, `libsndfile1`, `libsndfile1-dev`
   - HDF5: `libhdf5-dev`
   - Network tools: `net-tools`, `iputils-ping`

2. **Creates system user** `fiesta` (nologin shell, home at `/opt/911fiesta`)

3. **Creates directories**:
   - `/opt/911fiesta` - Application root
   - `/etc/911fiesta` - Configuration files
   - `/var/log/911fiesta` - Log files

```bash
sudo bash scripts/bootstrap_linux.sh
```

### Step 2: Install (`install_911fiesta.sh`)

Run as root. This script:

1. **Clones the repository** into `/opt/911fiesta` (or pulls if already cloned)
2. **Creates a Python venv** at `/opt/911fiesta/.venv`
3. **Installs pinned Python dependencies** from:
   - `server` profile: `requirements/server.lock.txt`
   - `show` profile: `requirements/show.lock.txt` + PyTorch
4. **Copies example configs** to `/etc/911fiesta/`
5. **Installs and enables** the systemd service
6. **Starts the service**
7. **Runs the healthcheck** (fails the install if healthcheck fails)
8. **Tags the current commit** as last-known-good for rollback

```bash
# Server profile (default)
sudo bash scripts/install_911fiesta.sh

# Full SHOW profile with GPU
sudo bash scripts/install_911fiesta.sh --profile show --torch-gpu

# Custom repo/branch
sudo bash scripts/install_911fiesta.sh --repo-url https://github.com/yourfork/repo.git --branch main
```

### Step 3: Verify

```bash
# Check service status
systemctl status 911fiesta

# View logs
journalctl -u 911fiesta -f

# Run healthcheck
bash scripts/healthcheck_911fiesta.sh

# Test API
curl http://127.0.0.1:8000/docs
```

---

## Network Configuration

### Static IP with Netplan

Ubuntu 24.04 uses **netplan** for network configuration. 911 Fiesta reads camera
and console IPs from its own config files -- it does not manage network interfaces.

To set a static IP for the server:

1. Identify your network interface:
   ```bash
   ip link show
   # Look for: enp3s0, ens33, eth0, etc.
   ```

2. Edit the netplan config:
   ```bash
   sudo nano /etc/netplan/01-static.yaml
   ```

3. Example static IP configuration:
   ```yaml
   network:
     version: 2
     renderer: networkd
     ethernets:
       enp3s0:
         dhcp4: false
         addresses:
           - 192.168.1.100/24
         routes:
           - to: default
             via: 192.168.1.1
         nameservers:
           addresses:
             - 8.8.8.8
             - 8.8.4.4
   ```

4. Apply:
   ```bash
   sudo netplan apply
   ```

5. Verify:
   ```bash
   ip addr show enp3s0
   ping -c 2 192.168.1.1
   ```

### Multiple NICs

If the server has multiple interfaces (e.g., one for management, one for camera
VLAN), configure each in netplan:

```yaml
network:
  version: 2
  ethernets:
    enp3s0:
      dhcp4: true                  # Management (DHCP)
    enp4s0:
      dhcp4: false
      addresses:
        - 192.168.1.100/24         # Camera VLAN (static)
      routes: []                   # No default route on this NIC
```

### Firewall

If UFW is enabled, allow the API port:

```bash
sudo ufw allow 8000/tcp comment "911 Fiesta API"
sudo ufw allow 5000/tcp comment "911 Fiesta Vision API"
```

---

## Camera Configuration

Cameras are configured in `/etc/911fiesta/vision_config.json` (or
`vision_config.json` in the repo root). The system supports MJPEG over HTTP
and RTSP. See `docs/CAMERAS_PROTOCOLS.md` for full protocol reference.

Example camera entry:

```json
{
  "cameras": {
    "dj": {
      "type": "mjpeg",
      "enabled": true,
      "host": "192.168.1.110",
      "path": "/axis-cgi/mjpg/video.cgi?fps=10",
      "username": "root",
      "password": "root",
      "fps_target": 10,
      "timeout_s": 5.0,
      "reconnect_s": 2.0
    }
  }
}
```

To verify camera connectivity:

```bash
# Quick test with ffprobe
ffprobe -v quiet http://root:root@192.168.1.110/axis-cgi/mjpg/video.cgi

# Or run the full healthcheck
bash scripts/healthcheck_911fiesta.sh
```

---

## Architecture: Server vs SHOW

| Aspect | Server | SHOW |
|--------|--------|------|
| Entrypoint | `uvicorn api.main:app` | `python main.py` |
| Launch | systemd (`911fiesta.service`) | XDG autostart (`.desktop`) |
| Display | None (headless) | Physical display (X11) |
| User shell | `/usr/sbin/nologin` | `/bin/bash` |
| Qt platform | `offscreen` | `xcb` |

The systemd service is **only for the server profile**. The SHOW profile
launches via XDG autostart when the fiesta user logs into a desktop session.

To change the server port, use a systemd drop-in:
```bash
sudo systemctl edit 911fiesta
# Add:
# [Service]
# ExecStart=
# ExecStart=/opt/911fiesta/.venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 9000
```

## GUI / SHOW Mode

The SHOW does **not** use systemd. It launches via XDG autostart when the
`fiesta` user logs into a graphical desktop session.

For full setup instructions, see **`docs/SHOW_RUNBOOK.md`**.

Quick overview:
1. Bootstrap with `--profile show` (installs xcb/Qt GUI deps, creates login user)
2. Install with `--profile show` (installs PySide6, torch, audio, vision deps)
3. Copy autostart file: `sudo cp systemd/911fiesta-show.desktop /etc/xdg/autostart/`
4. Set fiesta password: `sudo passwd fiesta`
5. Log in as fiesta — SHOW starts automatically

For kiosk mode (auto-login), configure GDM or LightDM auto-login.
See `docs/SHOW_RUNBOOK.md` for details.

## Related Documentation

- `docs/SHOW_RUNBOOK.md` — SHOW GUI setup, autostart, kiosk mode
- `docs/SERVER_RUNBOOK.md` — Server headless API setup
- `docs/TROUBLESHOOTING_LINUX.md` — Qt xcb, uvicorn, permissions, CUDA, audio
- `docs/DEPENDENCIES_LINUX.md` — Package inventory and lock file regeneration
- `docs/CAMERAS_PROTOCOLS.md` — MJPEG and RTSP protocol details
- `docs/HARDWARE_CORE911.md` — NVIDIA 1080 Ti and Maono PS22 setup
- `docs/UPDATE_RUNBOOK.md` — Update and rollback procedures

---

## Directory Structure After Install

```
/opt/911fiesta/              # Application root (owned by fiesta)
  .git/                      # Git repository
  .venv/                     # Python virtual environment
  api/                       # FastAPI server
  core/                      # Core engine
  core_vision/               # Vision/ML pipeline
  sensors/                   # Camera sensors
  scripts/                   # Installer/healthcheck scripts
  systemd/                   # Service unit source
  requirements/              # Pinned dependency files
  vision_config.json         # Vision config (default)
  avolites_config.json       # Lighting console config (default)
  main.py                    # GUI entrypoint

/etc/911fiesta/              # Configuration (persists across updates)
  vision_config.json         # Vision config (active)
  avolites_config.json       # Console config (active)
  audio_monitor.json         # Audio monitor config
  last-known-good-commit     # Rollback reference

/var/log/911fiesta/          # Log directory

/etc/systemd/system/
  911fiesta.service          # Systemd unit
```

---

## Dependency Management

### Source of Truth

Dependencies are managed via pip lock files in `requirements/`:

| File                      | Purpose                        |
|---------------------------|--------------------------------|
| `requirements/server.lock.txt` | Pinned server-only deps   |
| `requirements/show.lock.txt`   | Pinned SHOW runtime deps  |
| `requirements/base.in`         | Unpinned base deps        |
| `requirements/vision.in`       | Unpinned vision deps      |
| `requirements/audio.in`        | Unpinned audio deps       |
| `requirements/server.in`       | Unpinned server deps      |
| `requirements/show.in`         | Unpinned SHOW deps        |

The `.lock.txt` files are the install targets. The `.in` files are used
to regenerate locks:

```bash
pip-compile requirements/server.in -o requirements/server.lock.txt --resolver=backtracking
```

### Conda / environment.yml

The repo includes `environment.yml` and `environment.lock.yml` from the
original Windows development environment (conda). These are kept as reference
but **not used for Linux installation**. The venv + pip approach is preferred
for reproducibility on Ubuntu servers.

If you need to convert conda deps to pip:

```bash
# Extract pip-installable packages from environment.lock.yml
python3 -c "
import yaml
with open('environment.lock.yml') as f:
    env = yaml.safe_load(f)
for dep in env.get('dependencies', []):
    if isinstance(dep, dict) and 'pip' in dep:
        for pkg in dep['pip']:
            print(pkg)
"
```

---

## Troubleshooting

### Service won't start

```bash
# Check logs
journalctl -u 911fiesta -n 50 --no-pager

# Common issues:
# - Missing Python dependencies -> re-run install
# - Port 8000 already in use -> check: ss -tlnp | grep 8000
# - Permission issues -> check ownership: ls -la /opt/911fiesta
```

### "libGL.so.1: cannot open shared object file"

```bash
sudo apt install libgl1
```

### "Qt platform plugin could not be initialized"

For headless servers, ensure `QT_QPA_PLATFORM=offscreen` is set (already
configured in the systemd unit).

### "PortAudio not found" / sounddevice errors

```bash
sudo apt install libportaudio2 portaudio19-dev
```

### Camera not reachable

```bash
# Test network path
ping 192.168.1.110

# Check if camera HTTP responds
curl -u root:root http://192.168.1.110/axis-cgi/mjpg/video.cgi --max-time 5

# Check routing
ip route get 192.168.1.110
```

### PyTorch CUDA not detected

```bash
# Check NVIDIA driver
nvidia-smi

# Reinstall torch with CUDA
/opt/911fiesta/.venv/bin/pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

---

## Security Notes

- The `fiesta` system user has `nologin` shell and cannot be used for SSH.
- The systemd service runs with `NoNewPrivileges=true` and `ProtectSystem=strict`.
- Write access is limited to `/opt/911fiesta`, `/etc/911fiesta`, and `/tmp`.
- Camera credentials in `vision_config.json` should be protected:
  ```bash
  chmod 600 /etc/911fiesta/vision_config.json
  ```

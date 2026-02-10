# 911 Fiesta V7 - Linux Troubleshooting Guide

## Qt / PySide6

### "Could not find or load the Qt platform plugin xcb"

**Cause:** Missing xcb libraries on Ubuntu.

**Fix:**
```bash
sudo apt install libxcb-cursor0 libxcb-icccm4 libxcb-image0 \
    libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 \
    libxcb-shape0 libxcb-xfixes0 libxcb-xinerama0
```

Or re-run bootstrap with SHOW profile:
```bash
sudo bash scripts/bootstrap_linux.sh --profile show
```

### "Could not connect to display" / "Cannot connect to X server"

**Cause:** No `DISPLAY` environment variable, or no X server running.

**Fix (on the actual machine):**
- Ensure a graphical session is running (log in via GDM/LightDM).
- Check: `echo $DISPLAY` — should show `:0` or `:1`.

**Fix (from SSH for testing):**
```bash
export DISPLAY=:0
xhost +local:   # run this in the local GUI session first
python main.py
```

### "qt.qpa.plugin: Could not load the Qt platform plugin" (headless server)

**Cause:** Server profile needs offscreen rendering.

**Fix:**
```bash
export QT_QPA_PLATFORM=offscreen
```

This is already set in the systemd unit for the server profile.

---

## uvicorn / FastAPI

### "uvicorn: command not found"

**Cause:** The venv is not activated, or uvicorn is not installed.

**Fix:**
```bash
# Check if uvicorn exists in venv
/opt/911fiesta/.venv/bin/uvicorn --version

# If missing:
sudo -u fiesta /opt/911fiesta/.venv/bin/pip install uvicorn
```

### "ModuleNotFoundError: No module named 'fastapi'"

**Cause:** Server dependencies not installed.

**Fix:**
```bash
sudo -u fiesta /opt/911fiesta/.venv/bin/pip install -r /opt/911fiesta/requirements/server.lock.txt
```

### Port 8000 already in use

```bash
# Find what's using the port
ss -tlnp | grep 8000

# Kill the process or change the port via systemd drop-in
sudo systemctl edit 911fiesta
# Add: ExecStart=/opt/911fiesta/.venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 9000
```

---

## Permissions

### "Permission denied" on /opt/911fiesta

```bash
sudo chown -R fiesta:fiesta /opt/911fiesta
sudo chmod 755 /opt/911fiesta
```

### git "fatal: detected dubious ownership"

```bash
sudo -u fiesta git config --global --add safe.directory /opt/911fiesta
```

### Camera config not readable

```bash
sudo chown fiesta:fiesta /etc/911fiesta/vision_config.json
sudo chmod 640 /etc/911fiesta/vision_config.json
```

---

## Audio

### "PortAudio not found" / sounddevice errors

```bash
sudo apt install libportaudio2 portaudio19-dev
```

### No audio capture devices found

```bash
# Check USB device is connected
lsusb | grep -i "audio\|maono"

# List ALSA devices
arecord -l

# Check user is in audio group
id fiesta
# If not:
sudo usermod -aG audio fiesta
# Log out and back in for group change to take effect
```

### "ALSA lib pcm.c: Unknown PCM"

```bash
sudo apt install alsa-utils
```

---

## Vision / Cameras

### Camera not reachable

```bash
# Test network path
ping -c 3 192.168.1.110

# Check if HTTP responds
curl -u root:root http://192.168.1.110/axis-cgi/mjpg/video.cgi --max-time 5

# Check routing (if multiple NICs)
ip route get 192.168.1.110
```

### ffprobe errors during healthcheck

This is a WARN, not a FAIL. Possible causes:
- Camera is powered off or disconnected
- Camera firmware doesn't serve on the configured path
- Wrong credentials in `vision_config.json`
- Network timeout

### "libGL.so.1: cannot open shared object file"

```bash
sudo apt install libgl1
```

---

## GPU / CUDA

### nvidia-smi not found

```bash
# Install NVIDIA driver
sudo ubuntu-drivers install
sudo reboot

# Verify after reboot
nvidia-smi
```

### PyTorch CUDA not detected

```bash
# Check driver
nvidia-smi

# Check PyTorch CUDA
/opt/911fiesta/.venv/bin/python -c "import torch; print(torch.cuda.is_available())"

# Reinstall with CUDA
/opt/911fiesta/.venv/bin/pip install torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cu121
```

---

## Systemd Service

### Service keeps restarting (crash loop)

```bash
# Check recent logs
journalctl -u 911fiesta -n 100 --no-pager

# Check if rate-limited
systemctl status 911fiesta
# Look for "start-limit-hit" message

# Reset rate limit
sudo systemctl reset-failed 911fiesta
sudo systemctl start 911fiesta
```

### Service doesn't start on boot

```bash
sudo systemctl enable 911fiesta
```

### Need to change ExecStart (port, options)

Use a drop-in override (preferred over editing the unit directly):
```bash
sudo systemctl edit 911fiesta
```

Add:
```ini
[Service]
ExecStart=
ExecStart=/opt/911fiesta/.venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 9000
```

---

## Venv / Python

### "No module named ..." (generic)

```bash
# Ensure you're using the venv python
/opt/911fiesta/.venv/bin/python -c "import <module>"

# Reinstall deps
sudo -u fiesta /opt/911fiesta/.venv/bin/pip install -r /opt/911fiesta/requirements/show.lock.txt
```

### Rebuild venv from scratch

```bash
sudo rm -rf /opt/911fiesta/.venv
sudo -u fiesta python3 -m venv /opt/911fiesta/.venv
sudo -u fiesta /opt/911fiesta/.venv/bin/pip install --upgrade pip setuptools wheel
sudo -u fiesta /opt/911fiesta/.venv/bin/pip install -r /opt/911fiesta/requirements/show.lock.txt
```

---

## Ubuntu 22.04 Notes (Best Effort)

Ubuntu 22.04 is supported on a best-effort basis. Known differences:

- systemd is older (< 250): `StartLimitIntervalSec` must be in `[Unit]`,
  not `[Service]`. The current unit file already handles this.
- Python 3.10 is the default (not 3.12). Lock files are tested with 3.10/3.11.
- Some `libxcb-*` packages may have different names. If installation fails,
  check with `apt-cache search libxcb`.

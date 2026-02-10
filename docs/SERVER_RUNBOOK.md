# 911 Fiesta V7 - SERVER Runbook (Linux Headless API)

## Overview

The **SERVER** profile runs the 911 Fiesta FastAPI/uvicorn REST API on a
headless machine (no display required). It serves the web control interface
and provides endpoints for status, analyzers, cues, presets, and vision proxy.

**Entrypoint:** `uvicorn api.main:app --host 0.0.0.0 --port 8000`
**Launch method:** systemd service `911fiesta.service`
**User:** `fiesta911` (system user with `/usr/sbin/nologin` shell)

---

## Installation (Clean Machine)

```bash
# 1. Get the installer
git clone https://github.com/gastongrc/911-fiesta-core-LINUX.git /tmp/911fiesta-installer
cd /tmp/911fiesta-installer

# 2. Bootstrap (packages, system user, directories)
sudo bash scripts/bootstrap_linux.sh

# 3. Install application (venv, deps, systemd, healthcheck)
sudo bash scripts/install_911fiesta.sh

# 4. Verify
systemctl status 911fiesta
curl http://127.0.0.1:8000/docs
bash scripts/healthcheck_911fiesta.sh
```

---

## Service Management

```bash
# Start / stop / restart
sudo systemctl start 911fiesta
sudo systemctl stop 911fiesta
sudo systemctl restart 911fiesta

# View status
systemctl status 911fiesta

# View logs (live)
journalctl -u 911fiesta -f

# View recent logs
journalctl -u 911fiesta -n 50 --no-pager

# Enable/disable on boot
sudo systemctl enable 911fiesta
sudo systemctl disable 911fiesta
```

---

## Configuration

### Environment File

Runtime overrides are in `/etc/911fiesta/911fiesta.env`:

```bash
sudo nano /etc/911fiesta/911fiesta.env
sudo systemctl restart 911fiesta
```

The systemd unit has `QT_QPA_PLATFORM=offscreen` hardcoded for headless
operation. Do NOT change this for the server profile.

### API Port

The default port is 8000. To change, create a systemd drop-in:

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

## Updating

```bash
sudo bash /opt/911fiesta/scripts/update_911fiesta.sh

# With explicit branch:
sudo bash /opt/911fiesta/scripts/update_911fiesta.sh --branch main

# Rollback to last known good:
sudo bash /opt/911fiesta/scripts/update_911fiesta.sh --rollback
```

---

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/docs` | GET | Swagger UI |
| `/health` | GET | Health check |
| `/api/v1/status/*` | GET | System status |
| `/api/v1/analyzers/*` | GET/POST | Audio analyzers |
| `/api/v1/cues/*` | GET/POST | Cue engine |
| `/api/v1/presets/*` | GET/POST | Preset management |
| `/api/v1/network/*` | GET/POST | Network config |
| `/api/v1/config/*` | GET/POST | App configuration |
| `/api/v1/vision/*` | GET | Vision proxy (to Flask 5000) |

---

## Firewall

```bash
sudo ufw allow 8000/tcp comment "911 Fiesta API"
sudo ufw allow 5000/tcp comment "911 Fiesta Vision API"
```

---

## Troubleshooting

### Service won't start

```bash
journalctl -u 911fiesta -n 50 --no-pager

# Common issues:
# - Port 8000 in use: ss -tlnp | grep 8000
# - Missing deps: /opt/911fiesta/.venv/bin/python -c "import fastapi"
# - Permissions: ls -la /opt/911fiesta
```

### "uvicorn: command not found"

The venv PATH may not be set. Check:
```bash
/opt/911fiesta/.venv/bin/uvicorn --version
```

If missing, reinstall:
```bash
sudo -u fiesta911 /opt/911fiesta/.venv/bin/pip install uvicorn
```

### Permission denied on /opt/911fiesta

```bash
sudo chown -R fiesta911:fiesta911 /opt/911fiesta
```

### git safe.directory error

```bash
sudo -u fiesta911 git config --global --add safe.directory /opt/911fiesta
```

---

## Files Reference

| File | Purpose |
|---|---|
| `api/main.py` | FastAPI server entrypoint |
| `systemd/911fiesta.service` | Systemd unit source |
| `systemd/911fiesta.env` | Environment overrides |
| `/etc/systemd/system/911fiesta.service` | Installed unit |
| `/etc/911fiesta/911fiesta.env` | Installed env file |
| `requirements/server.lock.txt` | Pinned server dependencies |

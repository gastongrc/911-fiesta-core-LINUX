# 911 Fiesta V7 - Camera Protocols Reference

## Overview

911 Fiesta supports two camera protocols, configured in `vision_config.json`:

| Protocol | Transport | Use case | Config fields |
|----------|-----------|----------|---------------|
| **MJPEG** | HTTP | Axis IP cameras, low-latency preview | `host`, `path`, `username`, `password` |
| **RTSP** | RTSP/UDP or TCP | Generic IP cameras, H.264/H.265 | `url_main`, `url_sub`, `preferred` |

The protocol is determined by the `type` field in each camera entry.

---

## Config Structure (`vision_config.json`)

### MJPEG Camera (current production config)

From the real `vision_config.json` in the repository:

```json
{
  "cameras": {
    "haze": {
      "type": "mjpeg",
      "enabled": true,
      "host": "192.168.1.110",
      "path": "/axis-cgi/mjpg/video.cgi?fps=10",
      "username": "root",
      "password": "root",
      "fps_target": 11,
      "timeout_s": 5.0,
      "reconnect_s": 2.0
    },
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
    },
    "artist": {
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

**URL construction** (from `core_vision/vision_config.py:489-512`):
```
http://{username}:{password}@{host}{path}
```

**Real example:**
```
http://root:root@192.168.1.110/axis-cgi/mjpg/video.cgi?fps=10
```

### RTSP Camera (supported, not in current config)

```json
{
  "cameras": {
    "front": {
      "type": "rtsp",
      "enabled": true,
      "url_main": "rtsp://admin:password@192.168.1.64:554/Streaming/Channels/101",
      "url_sub": "rtsp://admin:password@192.168.1.64:554/Streaming/Channels/102",
      "preferred": "sub",
      "fps_target": 10,
      "timeout_s": 5.0,
      "reconnect_s": 2.0,
      "transport": "udp",
      "low_latency": true
    }
  }
}
```

**RTSP fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `url_main` | Yes* | Primary stream (high res) |
| `url_sub` | Yes* | Sub-stream (low res, preferred for detection) |
| `url` | Alt | Single URL (alternative to main/sub) |
| `preferred` | No | `"sub"` (default) or `"main"` |
| `username` | No | Injected into URL if `@` not present |
| `password` | No | Injected into URL if `@` not present |
| `transport` | No | `"udp"` (default, lower latency) or `"tcp"` |
| `low_latency` | No | FFmpeg low-latency options (default: true) |

*At least one of `url`, `url_main`, or `url_sub` must be provided.

---

## Protocol Detection Logic

From `core_vision/camera_source.py:1516-1549`:

1. If `type` is explicitly `"rtsp"` or `"mjpeg"` → use that
2. If URL starts with `rtsp://` → RTSP
3. If URL starts with `http://` and contains `mjpg`, `mjpeg`, `video.cgi`, or `axis-cgi` → MJPEG
4. If URL starts with `http` → MJPEG (default)
5. If port is `:554` or `:8554` → RTSP
6. Fallback → MJPEG

---

## Camera Source Implementations

From `core_vision/camera_source.py`:

| Class | Protocol | Backend | Lines |
|-------|----------|---------|-------|
| `MJPEGSource` | HTTP MJPEG | `requests` (multipart) | 91-433 |
| `RTSPSource` | RTSP | `cv2.VideoCapture` | 555-809 |
| `RTSPSourcePyAV` | RTSP | `av` (FFmpeg/PyAV) | 1043-1299 |

**Selection priority:**
1. If RTSP and `av` (PyAV) is available → `RTSPSourcePyAV`
2. If RTSP and no PyAV → `RTSPSource` (OpenCV fallback)
3. If MJPEG → `MJPEGSource`

---

## Healthcheck Camera Validation

The `scripts/healthcheck_911fiesta.sh` tests cameras by:

1. **Parsing** `vision_config.json` using the same URL construction logic
   as `core_vision/vision_config.py`
2. **Ping** the camera host (2 second timeout)
3. **ffprobe** the constructed URL (5 second timeout)

The healthcheck respects the `type` field:
- `type: "mjpeg"` → builds `http://{user}:{pass}@{host}{path}`
- `type: "rtsp"` → uses `url` / `url_main` / `url_sub` directly

### Manual Camera Test Commands

```bash
# MJPEG camera (Axis)
ffprobe -v error -print_format json -show_streams \
  "http://root:root@192.168.1.110/axis-cgi/mjpg/video.cgi?fps=10"

# RTSP camera (generic)
ffprobe -v error -print_format json -show_streams \
  "rtsp://admin:password@192.168.1.64:554/Streaming/Channels/102"

# Quick connectivity check
ping -c 1 -W 2 192.168.1.110

# Test HTTP auth
curl -u root:root -s -o /dev/null -w "%{http_code}" \
  "http://192.168.1.110/axis-cgi/mjpg/video.cgi?fps=10"
```

---

## Troubleshooting

### Camera host not reachable

```
[FAIL] Camera 'haze': host 192.168.1.110 is NOT reachable.
```

- Camera powered off or disconnected
- Server not on the same VLAN (check `ip route get 192.168.1.110`)
- Firewall blocking ICMP

### ffprobe fails on MJPEG

```
[WARN] Camera 'dj': ffprobe could not open mjpeg stream.
```

- Camera uses digest auth (ffprobe only supports basic auth in URL)
- Wrong path in config (test with curl)
- Camera firmware doesn't serve MJPEG on that endpoint

### ffprobe fails on RTSP

```
[WARN] Camera 'front': ffprobe could not open rtsp stream.
```

- Port 554 blocked by firewall
- Wrong credentials or RTSP path
- Try TCP transport: add `"transport": "tcp"` to config
- Test manually: `ffplay "rtsp://admin:pass@IP:554/path"`

# 911 Fiesta V7 - Linux Dependencies Reference

## Python Version

**Target: Python 3.10.x** (Ubuntu 22.04 ships python3 3.10; the lock files are
tested with 3.10.x / 3.11.x).

The venv uses the system `python3` unless a specific version is required.

---

## System Packages (apt)

Installed by `scripts/bootstrap_linux.sh`. Source of truth: `infra/linux/apt-packages.txt`.

| Package | Category | Why |
|---------|----------|-----|
| `build-essential` | Build | C compiler for pip wheels (numpy, etc.) |
| `pkg-config` | Build | Locates system libraries for native builds |
| `git` | Build | Clone repo, track updates |
| `curl`, `wget` | Build | Download tools |
| `python3` | Runtime | Python interpreter |
| `python3-pip` | Runtime | Package installer |
| `python3-venv` | Runtime | Virtual environment support |
| `python3-dev` | Build | Python headers for C extensions |
| `libgl1` | Vision | OpenGL for OpenCV |
| `libglib2.0-0` | Vision | GLib for OpenCV |
| `libsm6`, `libxext6`, `libxrender1` | Vision | X11 libs for OpenCV |
| `libegl1`, `libxkbcommon0` | Qt | PySide6 headless rendering |
| `libdbus-1-3`, `libfontconfig1` | Qt | PySide6 system deps |
| `libxcb-xinerama0` | Qt | PySide6 XCB plugin |
| `ffmpeg` | Vision/Audio | Stream probe, camera test, PyAV backend |
| `libavformat-dev`, `libavcodec-dev` | Vision | Build PyAV from source |
| `libavdevice-dev`, `libavutil-dev` | Vision | Build PyAV from source |
| `libswscale-dev`, `libswresample-dev` | Vision | Build PyAV from source |
| `libportaudio2`, `portaudio19-dev` | Audio | PortAudio for sounddevice |
| `libsndfile1`, `libsndfile1-dev` | Audio | libsndfile for soundfile/librosa |
| `alsa-utils` | Audio | `arecord -l` for USB audio detection (Maono PS22) |
| `libhdf5-dev` | Vision | HDF5 for TensorFlow/Keras model loading |
| `net-tools`, `iputils-ping` | Network | Diagnostics and healthcheck |

---

## Python Dependencies by Profile

### Server Profile (`requirements/server.lock.txt`)

Headless API server. No GUI, no vision ML, no audio.

| Package | Version | Purpose |
|---------|---------|---------|
| `fastapi` | 0.115.5 | REST API framework |
| `uvicorn` | 0.32.1 | ASGI server |
| `starlette` | 0.41.3 | ASGI toolkit (FastAPI dep) |
| `pydantic` | 2.10.2 | Data validation |
| `pydantic-core` | 2.27.1 | Pydantic Rust core |
| `python-multipart` | 0.0.17 | Form data parsing |
| `httptools` | 0.6.4 | HTTP parser for uvicorn |
| `uvloop` | 0.21.0 | Fast event loop (Linux only) |
| `watchfiles` | 1.0.0 | File watching for uvicorn |
| `websockets` | 14.1 | WebSocket support |
| `httpcore` | 1.0.7 | HTTP client core |
| `httpx` | 0.28.1 | Async HTTP client |
| `numpy` | 1.26.4 | Numerical computing |
| `opencv-python-headless` | 4.10.0.84 | Computer vision (no GUI) |
| `requests` | 2.32.3 | HTTP client |
| `python-dotenv` | 1.0.1 | Env file loading |
| `email-validator` | 2.2.0 | Pydantic email validation |

Install:
```bash
pip install -r requirements/server.lock.txt
```

### Show Profile (`requirements/show.lock.txt`)

Full runtime with GUI, vision/ML, and audio. PyTorch installed separately.

| Package | Version | Purpose |
|---------|---------|---------|
| `PySide6` | 6.9.0 | Qt6 GUI framework |
| `pyqtgraph` | 0.13.7 | Real-time plotting |
| `numpy` | 1.26.4 | Numerical computing |
| `scipy` | 1.14.1 | Scientific computing |
| `sounddevice` | 0.5.1 | Audio capture |
| `librosa` | 0.10.2.post1 | Audio analysis |
| `soundfile` | 0.12.1 | Audio file I/O |
| `opencv-python` | 4.10.0.84 | Computer vision (with GUI) |
| `av` | 12.3.0 | PyAV for RTSP/video streams |
| `pillow` | 11.0.0 | Image processing |
| `ultralytics` | 8.3.50 | YOLO object detection |
| `Flask` | 3.0.3 | Vision API server |
| `flask-cors` | 5.0.0 | CORS for Flask |
| `psutil` | 6.1.0 | System monitoring |
| `matplotlib` | 3.9.2 | Plotting |
| `numba` | 0.60.0 | JIT compiler (librosa dep) |
| ... | ... | See full file for transitive deps |

Install:
```bash
# PyTorch first (GPU)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
# or (CPU only)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# Then the lock file
pip install -r requirements/show.lock.txt
```

---

## Regenerating Lock Files

The `.in` files are the unpinned source. The `.lock.txt` files are generated
from them using `pip-compile` (from `pip-tools`).

```bash
# Install pip-tools
pip install pip-tools

# Regenerate server lock
pip-compile requirements/server.in \
    -o requirements/server.lock.txt \
    --resolver=backtracking

# Regenerate show lock
pip-compile requirements/show.in \
    -o requirements/show.lock.txt \
    --resolver=backtracking
```

### Input Files

| File | Includes | Description |
|------|----------|-------------|
| `requirements/base.in` | - | Core deps (FastAPI, numpy, Flask, etc.) |
| `requirements/server.in` | - | Minimal server deps |
| `requirements/show.in` | - | Full show deps (Qt, audio, vision) |
| `requirements/audio.in` | `base.in` | Audio-specific deps |
| `requirements/vision.in` | `base.in` | Vision/ML deps |
| `requirements/dev.in` | - | Dev tools (pytest, ruff, mypy) |

---

## Conda / environment.yml

The repo includes `environment.yml` and `environment.lock.yml` from the original
Windows development environment. These are **reference only** and are NOT used
for Linux installation. The venv + pip approach is used for production.

---

## File Tree

```
requirements/
  base.in               # Unpinned: core dependencies
  server.in             # Unpinned: server-only dependencies
  show.in               # Unpinned: full show dependencies
  audio.in              # Unpinned: audio capture/analysis
  vision.in             # Unpinned: vision/ML pipeline
  dev.in                # Unpinned: development tools
  server.lock.txt       # PINNED: server profile (install target)
  show.lock.txt         # PINNED: show profile (install target)
```

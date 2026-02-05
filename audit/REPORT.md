# 911 Fiesta V7 — Dependency Audit Report

> Generated: 2026-02-05 21:14:34 UTC
> Python: 3.11.14 (`/usr/local/bin/python`)
> Platform: Linux-4.4.0-x86_64-with-glibc2.39
> GPU: Not detected

## Executive Summary

### Minimum for base (API server, headless)

- Python 3.10+ (3.11 recommended)
- FastAPI + uvicorn + pydantic
- numpy, scipy, requests, python-dotenv
- `apt`: python3, python3-pip, python3-venv, build-essential, git

### Required for vision (camera/detection)

- opencv-python-headless (+ libgl1, libglib2.0-0)
- torch + torchvision (CPU or CUDA)
- ultralytics (YOLO)
- pillow, scikit-image
- `apt`: ffmpeg, libgl1, libglib2.0-0

### Required for audio (BPM/analysis)

- librosa, soundfile, sounddevice, audioread, aubio
- torchaudio
- `apt`: ffmpeg, libportaudio2, portaudio19-dev, libsndfile1

### Required for cameras (RTSP/streaming)

- av (PyAV) — RTSP/stream decoding
- Flask + flask-cors (legacy vision API)
- `apt`: ffmpeg, libavformat-dev, libavcodec-dev, libswscale-dev

## Runtime Smoke Test Results

**Total: 35** — OK: 2 | FAIL: 31 | SKIPPED: 2

| Category | Name | Status | Version | Detail |
|----------|------|--------|---------|--------|
| core | numpy | **FAIL** |  | ImportError: No module named 'numpy' |
| core | scipy | **FAIL** |  | ImportError: No module named 'scipy' |
| core | pandas | **FAIL** |  | ImportError: No module named 'pandas' |
| core | requests | OK | 2.32.5 |  |
| core | python-dotenv | **FAIL** |  | ImportError: No module named 'dotenv' |
| core | typing_extensions | **FAIL** |  | ImportError: No module named 'typing_extensions' |
| core | pydantic | **FAIL** |  | ImportError: No module named 'pydantic' |
| core | PyYAML | OK | 6.0.1 |  |
| core | rich | **FAIL** |  | ImportError: No module named 'rich' |
| api | fastapi | **FAIL** |  | ImportError: No module named 'fastapi' |
| api | uvicorn | **FAIL** |  | ImportError: No module named 'uvicorn' |
| api | starlette | **FAIL** |  | ImportError: No module named 'starlette' |
| api | flask | **FAIL** |  | ImportError: No module named 'flask' |
| api | flask-cors | **FAIL** |  | ImportError: No module named 'flask_cors' |
| vision | opencv (cv2) | **FAIL** |  | ImportError: No module named 'cv2' |
| vision | torch | **FAIL** |  | ImportError: No module named 'torch' |
| vision | torchvision | **FAIL** |  | ImportError: No module named 'torchvision' |
| vision | ultralytics | **FAIL** |  | ImportError: No module named 'ultralytics' |
| vision | scikit-image | **FAIL** |  | ImportError: No module named 'skimage' |
| vision | pillow | **FAIL** |  | ImportError: No module named 'PIL' |
| audio | librosa | **FAIL** |  | ImportError: No module named 'librosa' |
| audio | soundfile | **FAIL** |  | ImportError: No module named 'soundfile' |
| audio | audioread | **FAIL** |  | ImportError: No module named 'audioread' |
| audio | sounddevice | **FAIL** |  | ImportError: No module named 'sounddevice' |
| audio | aubio | **FAIL** |  | ImportError: No module named 'aubio' |
| audio | torchaudio | **FAIL** |  | ImportError: No module named 'torchaudio' |
| network | pyartnet | **FAIL** |  | ImportError: No module named 'pyartnet' |
| network | python-artnet | **FAIL** |  | ImportError: No module named 'python_artnet' |
| network | sacn | **FAIL** |  | ImportError: No module named 'sacn' |
| system | ffmpeg | SKIP |  | binary not found in PATH |
| system | nvidia-smi | SKIP |  | binary not found (no NVIDIA GPU or drivers) |
| system | libportaudio | **FAIL** |  | FileNotFoundError: libportaudio not found |
| system | libsndfile | **FAIL** |  | FileNotFoundError: libsndfile not found |
| gpu | torch.cuda | **FAIL** |  | ImportError: No module named 'torch' |
| gpu | cuDNN | **FAIL** |  | ImportError: No module named 'torch' |

## Third-Party Dependency Table

*68 third-party packages detected via AST scan.*

| Import | pip package | Version | Tier | Refs | Used in |
|--------|-------------|---------|------|------|---------|
| `aubio` | aubio | — | audio | 1 | tools/audit/runtime_smoke_tests.py |
| `librosa` | librosa | — | audio | 2 | analyzers/bpm_detector.py, scripts/smoke_show.py |
| `sounddevice` | sounddevice | — | audio | 5 | engine_audio.py, main.py, scripts/smoke_show.py (+2 more) |
| `artist_detector` | artist_detector | — | base | 1 | core_vision/vision_manager.py |
| `auto_clock` | auto_clock | — | base | 2 | tempo/__init__.py, tempo/tap_bridge.py |
| `boot_manager` | boot_manager | — | base | 1 | core/__init__.py |
| `calendar_manager` | calendar_manager | — | base | 1 | core/calendar/__init__.py |
| `calendar_resolver` | calendar_resolver | — | base | 2 | core/calendar/__init__.py, core/calendar/calendar_manager.py |
| `calendar_rules` | calendar_rules | — | base | 2 | core/calendar/__init__.py, core/calendar/calendar_manager.py |
| `calendar_schedule_editor` | calendar_schedule_editor | — | base | 1 | ui/calendar_tab.py |
| `calendar_state` | calendar_state | — | base | 3 | core/calendar/__init__.py, core/calendar/calendar_manager.py, core/calendar/calendar_resolver.py |
| `camera_haze` | camera_haze | — | base | 3 | core_vision/__init__.py, core_vision/vision_manager.py, sensors/__init__.py |
| `camera_loop` | camera_loop | — | base | 2 | core_vision/__init__.py, core_vision/vision_manager.py |
| `camera_manager` | camera_manager | — | base | 1 | core/__init__.py |
| `camera_people` | camera_people | — | base | 1 | sensors/__init__.py |
| `camera_source` | camera_source | — | base | 2 | core_vision/camera_loop.py, core_vision/vision_manager.py |
| `camera_tracking` | camera_tracking | — | base | 2 | core_vision/__init__.py, sensors/__init__.py |
| `core_bpm` | core_bpm | — | base | 1 | tools/test_bpm_master.py |
| `cue_map` | cue_map | — | base | 2 | core/cues/__init__.py, core/cues/family_manager.py |
| `cues` | cues | — | base | 1 | core/system_bridge.py |
| `dj_detector` | dj_detector | — | base | 2 | core_vision/__init__.py, core_vision/vision_manager.py |
| `dotenv` | python-dotenv | — | base | 1 | scripts/smoke_show.py |
| `energy_detector` | energy_detector | — | base | 1 | main.py |
| `family_manager` | family_manager | — | base | 1 | core/cues/__init__.py |
| `fastapi` | fastapi | — | base | 16 | api/dependencies.py, api/main.py, api/routers/alerts.py (+8 more) |
| `flask` | flask | — | base | 2 | api_server.py, scripts/smoke_show.py |
| `flask_cors` | flask-cors | — | base | 2 | api_server.py, scripts/smoke_show.py |
| `httpx` | httpx | — | base | 5 | api/main.py, api/routers/calendar.py, api/routers/status.py |
| `layered_zone_editor` | layered_zone_editor | — | base | 3 | ui/__init__.py, ui/vision_artist_tab.py, ui/vision_dj_tab.py |
| `numpy` | numpy | — | base | 67 | analyzers/accent_catcher.py, analyzers/ambient_confirmator.py, analyzers/beat_steady.py (+64 more) |
| `psutil` | psutil | — | base | 3 | api/core_bridge.py, core/http_snapshot.py, main.py |
| `pulse_finder` | pulse_finder | — | base | 1 | analyzers/pulse_finder_wrapper.py |
| `pydantic` | pydantic | — | base | 4 | api/models.py, api/routers/alerts.py, scripts/smoke_server.py |
| `pytest` | pytest | — | base | 2 | tests/test_states.py, tests/test_v11.py |
| `requests` | requests | 2.32.5 | base | 9 | avolites_config.py, core/transport/titan_transport.py, core_vision/camera_source.py (+1 more) |
| `rhythm_tools` | rhythm_tools | — | base | 6 | analyzers/cadence_spotter.py, analyzers/dynamic_pulse.py, analyzers/flow_monitor.py (+3 more) |
| `runtime_smoke_tests` | runtime_smoke_tests | — | base | 1 | tools/audit/run_audit.py |
| `scipy` | scipy | — | base | 3 | analyzers/bpm_detector.py, analyzers/rhythm_highlighter.py, tempo/auto_clock.py |
| `smart_camera` | smart_camera | — | base | 1 | core/__init__.py |
| `starlette` | starlette | — | base | 1 | scripts/smoke_server.py |
| `static_import_scan` | static_import_scan | — | base | 1 | tools/audit/run_audit.py |
| `system_bridge` | system_bridge | — | base | 1 | core/__init__.py |
| `tap_bridge` | tap_bridge | — | base | 1 | tempo/__init__.py |
| `titan_queue` | titan_queue | — | base | 2 | core/transport/__init__.py, core/transport/titan_sync.py |
| `titan_sync` | titan_sync | — | base | 1 | core/transport/__init__.py |
| `titan_transport` | titan_transport | — | base | 3 | core/transport/__init__.py, core/transport/titan_queue.py, core/transport/titan_sync.py |
| `transport` | transport | — | base | 1 | core/__init__.py |
| `uvicorn` | uvicorn | — | base | 3 | api/main.py, scripts/smoke_server.py |
| `vision_artist_engine` | vision_artist_engine | — | base | 1 | core_vision/artist_detector.py |
| `vision_artist_tab` | vision_artist_tab | — | base | 1 | ui/__init__.py |
| `vision_config` | vision_config | — | base | 2 | core_vision/__init__.py, core_vision/vision_manager.py |
| `vision_config_widget` | vision_config_widget | — | base | 1 | ui/__init__.py |
| `vision_diagnostics` | vision_diagnostics | — | base | 1 | sensors/__init__.py |
| `vision_dj_engine` | vision_dj_engine | — | base | 2 | core_vision/__init__.py, core_vision/dj_detector.py |
| `vision_dj_tab` | vision_dj_tab | — | base | 1 | ui/__init__.py |
| `vision_haze_tab` | vision_haze_tab | — | base | 1 | ui/__init__.py |
| `vision_manager` | vision_manager | — | base | 1 | core_vision/__init__.py |
| `vision_router` | vision_router | — | base | 1 | core/__init__.py |
| `vision_state` | vision_state | — | base | 2 | core_vision/__init__.py, core_vision/vision_manager.py |
| `yolo_roi_detector` | yolo_roi_detector | — | base | 3 | core_vision/__init__.py, core_vision/artist_detector.py, core_vision/dj_detector.py |
| `python_artnet` | python_artnet | — | network | 1 | tools/audit/runtime_smoke_tests.py |
| `pyqtgraph` | pyqtgraph | — | ui | 3 | analyzers/super_analyzer.py, scripts/smoke_show.py, ui/bpm_master_tab.py |
| `PySide6` | PySide6 | — | ui | 63 | analyzers/super_analyzer.py, analyzers/waveform_widget.py, bpm_ui.py (+21 more) |
| `av` | av | — | vision | 2 | core_vision/camera_source.py, scripts/smoke_show.py |
| `cv2` | opencv-python-headless | — | vision | 19 | api_server.py, core/camera_manager.py, core/smart_camera.py (+16 more) |
| `PIL` | pillow | — | vision | 2 | tools/audit/runtime_smoke_tests.py |
| `torch` | torch | — | vision | 5 | core_vision/yolo_roi_detector.py, scripts/smoke_show.py, tools/audit/runtime_smoke_tests.py |
| `ultralytics` | ultralytics | — | vision | 4 | core_vision/yolo_roi_detector.py, scripts/smoke_show.py, tools/audit/runtime_smoke_tests.py |

## Python Version Recommendation

| Version | Status | Notes |
|---------|--------|-------|
| 3.10.x | Supported | Broadest CUDA/torch compatibility |
| **3.11.x** | **Recommended** | Good balance of speed + compatibility |
| 3.12.x | Experimental | Some packages may lack wheels |

## System (apt) Packages — Ubuntu/Debian

| Package | Reason |
|---------|--------|
| `build-essential` | compilation of native extensions |
| `ffmpeg` | audio/video processing (librosa, av, vision) |
| `git` | version control |
| `libaubio-dev` | required by aubio |
| `libavcodec-dev` | required by av |
| `libavdevice-dev` | required by av |
| `libavformat-dev` | required by av |
| `libavutil-dev` | required by av |
| `libdbus-1-3` | PySide6/Qt D-Bus |
| `libegl1` | PySide6/Qt EGL backend |
| `libgl1` | OpenCV / Qt headless rendering |
| `libglib2.0-0` | OpenCV / GLib dependency |
| `libportaudio2` | sounddevice / PyAudio |
| `libsndfile1` | soundfile |
| `libsndfile1-dev` | soundfile build |
| `libswresample-dev` | required by av |
| `libswscale-dev` | required by av |
| `libxkbcommon0` | PySide6/Qt keyboard |
| `pkg-config` | native lib detection |
| `portaudio19-dev` | sounddevice build |
| `python3` | Python interpreter |
| `python3-aubio` | required by aubio |
| `python3-flask` | required by flask |
| `python3-numpy` | required by numpy |
| `python3-opencv` | required by opencv-python-headless |
| `python3-pil` | required by pillow |
| `python3-pip` | pip package manager |
| `python3-psutil` | required by psutil |
| `python3-requests` | required by requests |
| `python3-scipy` | required by scipy |
| `python3-venv` | virtual environments |

## Risks and Notes

### CUDA / PyTorch

- PyTorch GPU builds require matching CUDA toolkit version.
- Install via the PyTorch selector: `pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121`
- CPU-only fallback: `--index-url https://download.pytorch.org/whl/cpu`
- TensorFlow is present in requirements.txt but may not be actively used in core — verify before including in production.

### OpenCV headless

- On headless Linux, use `opencv-python-headless` instead of `opencv-python` to avoid X11 dependencies.
- Both provide the same `cv2` API; headless omits `imshow`/`waitKey`.
- Requires `libgl1` and `libglib2.0-0` at minimum.

### Audio: PortAudio / sounddevice

- `sounddevice` wraps PortAudio — requires `libportaudio2` at runtime.
- On headless servers with no audio hardware, `sd.query_devices()` may return an empty list; the library still imports fine.
- `portaudio19-dev` is only needed if building from source.

### aubio

- The pip `aubio` package often requires compilation — needs `libaubio-dev` or pre-built wheel.
- Conda alternative: `conda install -c conda-forge aubio`.

### PySide6 / Qt on headless

- PySide6 is used for the desktop UI. On headless deploy, it can be omitted if only the API server is needed.
- If imported for any reason on headless, set `QT_QPA_PLATFORM=offscreen` or install `xvfb`.

### PyAV (av)

- Requires FFmpeg development libraries (`libavformat-dev`, `libavcodec-dev`, etc.).
- Or install the pre-built wheel: `pip install av` (includes bundled FFmpeg on many platforms).

## Static Import Scan Summary

- Files scanned: **158**
- Unique imports: **136**
  - stdlib: 39
  - internal: 29
  - third-party: 68

See `audit/artifacts/imports_used.json` for full details.

## Files Scanned

Total: 158 Python files.
See `audit/artifacts/files_scanned.txt` for the complete list.

---

*Report generated by `tools/audit/run_audit.py`*

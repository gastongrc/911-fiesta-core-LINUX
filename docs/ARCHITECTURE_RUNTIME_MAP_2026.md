# 911 Fiesta Core — Runtime Architecture Map 2026

> Generated from source on 2026-03-10. Reflects the current codebase exactly.
> Version: v4.12 (Setters Dinámicos + Engine Siempre Corre)

---

## Table of Contents

1. [Entrypoints](#1-entrypoints)
2. [Runtime Execution Chain](#2-runtime-execution-chain)
3. [Core Modules](#3-core-modules)
4. [Audio System](#4-audio-system)
5. [Vision System](#5-vision-system)
6. [Calendar Governance](#6-calendar-governance)
7. [Titan Transport Layer](#7-titan-transport-layer)
8. [Analyzer Modules](#8-analyzer-modules)
9. [API Endpoints](#9-api-endpoints)
10. [Cue Map](#10-cue-map)
11. [Runtime Dependency Graph](#11-runtime-dependency-graph)
12. [System Boot Sequence](#12-system-boot-sequence)
13. [Design Patterns](#13-design-patterns)

---

## 1. Entrypoints

### 1.1 GUI Mode — `main.py`

Primary runtime entrypoint. Launches the full PySide6 (Qt6) GUI application.

| Property | Value |
|---|---|
| Class | `Main(QMainWindow)` |
| Framework | PySide6 / Qt6 |
| Execution | `QApplication(sys.argv)` → `Main()` → `app.exec()` |
| Version banner | `911 Fiesta - v4.2 + BRAKE ANALYZER REAL + RED PANEL + HEALTH` |

Responsibilities:
- Initializes AudioEngine, StateManager, CueEngine, AvolitesController
- Starts CalendarManager, SystemBridge, BootManager, VisionManager
- Launches HTTP SnapshotServer (port 8010) and FastAPI (port 8000) in threads
- Runs Qt event loop with audio processing timers

Pre-import bootstrap:
- `_bootstrap_guard()` — configures Qt plugin paths for cross-machine portability
- OpenMP/BLAS thread protection (`KMP_DUPLICATE_LIB_OK`, `OMP_NUM_THREADS`)
- Conda DLL search path fix (Windows)
- `safe_import()` — graceful fallback for optional modules (MSE, Vision, etc.)

### 1.2 Headless API Mode — `api/main.py`

FastAPI REST server for remote control and web dashboard (no GUI).

| Property | Value |
|---|---|
| Framework | FastAPI + Uvicorn |
| Port | 8000 |
| CORS | All origins enabled |
| Static files | Vite SPA build (`webapp/dist/`) |

Launched either:
- From `main.py` via `start_api_server()` in a background thread (GUI mode)
- Standalone via systemd service (headless mode)

Proxies:
- Vision Flask API on port 5000 (frames, streams, status)
- Core HTTP SnapshotServer on port 8010 (authoritative state)

### 1.3 Vision Flask Server — `api_server.py`

Legacy Flask API for the vision subsystem.

| Property | Value |
|---|---|
| Framework | Flask + Flask-CORS |
| Port | 5000 |
| Components | CameraManager, VisionRouter, CameraPeopleSensor, CameraHazeSensor, CameraTrackingSensor, VisionDiagnostics |

### 1.4 Core HTTP Snapshot Server — `core/http_snapshot.py`

Minimal HTTP server running inside the GUI process. Single source of truth for all runtime state.

| Property | Value |
|---|---|
| Framework | `http.server.HTTPServer` (stdlib) |
| Port | 8010 (127.0.0.1 only) |
| Class | `SnapshotServer` (singleton) |
| Endpoint | `GET /core/snapshot` |

Exposes: state, energy, audio, avolites, cameras, calendar, system metrics.
Also handles calendar control commands (`POST /core/calendar/*`).

### 1.5 Systemd Services

**`systemd/911fiesta.service`** — Headless API server (no GUI)
```
User=fiesta911
WorkingDirectory=/opt/911fiesta
ExecStart=/opt/911fiesta/.venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000
Environment=QT_QPA_PLATFORM=offscreen
Restart=on-failure (5s delay)
LimitNOFILE=65536, LimitNPROC=4096
```

**`systemd/show-gui.service`** — GUI kiosk mode (Xorg + openbox)
```
User=fiesta911
ExecStart=/usr/bin/startx /opt/911fiesta/.xinitrc -- :0 vt7
TTYPath=/dev/tty7
PAMName=login
Conflicts=gdm.service, display-manager.service
```

---

## 2. Runtime Execution Chain

```
┌─────────────────────────────────────────────────────────────────┐
│                    AUDIO INPUT (sounddevice)                    │
│                  2-ch, 44100 Hz, float32                        │
└───────────────────────────┬─────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    AudioEngine (engine_audio.py)                │
│  DC Blocker → HP Filter → Notch Filter → Gate → Envelope       │
│  Ring buffer: 3 seconds                                        │
└───────────────────────────┬─────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│              Analyzer Pipeline (analyzers/*.py)                 │
│  4 groups: BAJADA | BASE_GOLPE | ATAQUE | BRAKE                │
│  Each analyzer: process(block, sr) → match score               │
│  Optional: MusicStructureEngine (MSE) parallel processing      │
└───────────────────────────┬─────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│              StateManager (state_manager.py)                    │
│  V13 Fast Baseline: EMA smoothing, stability buffer             │
│  Hysteresis matrix, ATAQUE override (≥80%), BRAKE thresholds   │
│  Output: state (BAJADA|BASE_GOLPE|ATAQUE|BRAKE) + energy       │
└───────────────────────────┬─────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│              CueEngine (cue_engine.py) v6.0                    │
│  DETERMINISTIC: reads state → OFF previous → ON new            │
│  7 specialist modules executed in strict order                  │
│  Calendar gating via _disabled_states                           │
└───────────────────────────┬─────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│              Titan Transport Layer                              │
│  TitanQueue → TitanTransport → Avolites Titan Console          │
│  Priority queue (KILL > FIRE > PING)                           │
│  TitanStateSync watchdog (2s polling)                          │
└───────────────────────────┬─────────────────────────────────────┘
                            ▼
                    ┌───────────────┐
                    │  DMX OUTPUT   │
                    │  (Avolites    │
                    │   Titan)      │
                    └───────────────┘
```

### Parallel Governance Overlay

```
CalendarManager ──► CalendarResolver (calendar.json)
       │                    │
       ▼                    ▼
 CalendarRules ◄─── ScheduleBlock (mode + actions)
       │
       ▼
 SystemBridge.apply_calendar_state()
       │
       ├──► AudioEngine.set_enabled()        (audio gating)
       ├──► CueEngine.set_disabled_states()  (state blocking)
       ├──► VisionManager.enable_module()    (vision control)
       └──► FamilyManager.activate_state()   (CLIMA cues C60-C63)
```

---

## 3. Core Modules

### 3.1 StateManager (`state_manager.py`)

Musical state machine with V13 Fast Baseline preset.

| Property | Value |
|---|---|
| States | BAJADA, BASE_GOLPE, ATAQUE, BRAKE |
| Presets | FAST (default): 0.8s hold, 0.2s cooldown, 120ms stability, EMA α=0.5 |
| | STABLE: 1.2s hold, 2.0s cooldown, 180ms stability, EMA α=0.3 |
| Input | Analyzer votes (per-state match scores) |
| Output | `get_state()`, `get_energy()` |

Key features:
- Hysteresis matrix prevents false transitions
- ATAQUE override: ≥80% score, 2 frames, ≥0.20s elapsed
- BRAKE logic: entry 0.52, sustained 0.48, exit 0.35 thresholds
- Calendar bridge: `_disabled_states` blocks specific states

### 3.2 CueEngine (`cue_engine.py`) v6.0

Modular cue orchestrator — fully deterministic.

| Module | Cue Range | Family |
|---|---|---|
| `ControlDimmerModule` | C41 | dimmer |
| `BreakModule` | C42–C44 | brake |
| `AtaqueModule` | C37–C39 | ataque |
| `BaseGolpeModule` | C1–C9, C51–C59 | base_golpe |
| `BajadaModule` | C10–C18 (colors), C19–C27 (positions) | bajada |
| `MovimientoModule` | C28–C36 | movimiento |
| `TimedSequenceModule` | C45–C50 | timed |

Execution order: dimmer → break → ataque → base_golpe → bajada → movimiento → timed.

Rules:
- A cue does NOT change unless: (1) state change, (2) explicit timer, (3) direct engine order
- No auto-advance, no implicit cycle_next, no heuristics

### 3.3 AuxStateManager (`aux_state_manager.py`)

Central state table — pure data, NO hardware control.

| Data | Purpose |
|---|---|
| C41 reasons | Table of reasons to keep dimmer OFF (FX_DIMMER, BREAK_C44) |
| C45–C50 index | Global timed sequence position |
| C44 flag | BREAK activation state |

Consumers: ControlDimmerModule, BreakModule, TimedSequenceModule (read state).
Producers: Same modules (call `request_c41_off()` / `release_c41_off()`).

### 3.4 UnionBridge (`union_bridge.py`)

Anti-repetition bridge for cue cycling.

- Tracks cue usage per energy level (BAJA, MEDIA, ALTA)
- After N complete cycles (default 2), bridges to neighbor energy
- Neighbor map: BAJA→MEDIA, MEDIA→ALTA, ALTA→MEDIA (circular)

### 3.5 BootManager (`core/boot_manager.py`)

Deterministic bootstrap sequence (AUTO LOAD SHOW). Singleton.

Boot steps:
1. Console baseline: KILL ALL + `CueEngine.silent_reset()`
2. Calendar resolve: Force `resolve(now)`, apply via SystemBridge
3. Vision sync: Sync haze/DJ/artist to calendar actions
4. CueEngine baseline: Fire C41 (dimmer ON)
5. Log READY with timestamps

Pending baseline pattern: if Titan offline during boot, retries on reconnect.

### 3.6 SystemBridge (`core/system_bridge.py`)

Calendar → System governance bridge (hard authority). Singleton.

Apply flow:
```
Calendar.go(mode) → SystemBridge.apply_calendar_state(mode, actions)
  → _apply_modules(dict)
    → VisionManager.enable_module()
    → AudioEngine.set_enabled()
    → CueEngine.set_disabled_states()
    → FamilyManager.activate_state()
```

Gating logic:
- Audio OFF → all CueEngine states blocked
- Audio ON (suave modes) → blocks ATAQUE, BRAKE only
- Audio ON (full) → all states allowed

Vision by actions:
- `vision_haze` → enable haze camera
- `vision_dj` / `dj_detection` → enable DJ detection
- `vision_artista` / `tracking_cam` → enable artist tracking
- DJ + Artist conflict → DJ wins

### 3.7 FamilyManager (`core/cues/family_manager.py`)

Exclusive cue family gating for extended cues (C60–C82).

- One cue active per family at a time
- Edge-trigger: no spam on redundant activations
- Uses CueEngine pipeline if connected, falls back to direct Avolites

### 3.8 HTTP SnapshotServer (`core/http_snapshot.py`)

Microserver exposing real CORE state. Singleton, runs in daemon thread.

| Endpoint | Method | Purpose |
|---|---|---|
| `/core/snapshot` | GET | Full state snapshot |
| `/core/calendar/week` | GET | Weekly schedule |
| `/core/calendar/go` | POST | Manual mode change |
| `/core/calendar/override` | POST | Temporary override |
| `/core/calendar/clear_override` | POST | Clear override |
| `/core/calendar/auto` | POST | Toggle auto mode |
| `/core/calendar/save` | POST | Save weekly schedule |
| `/core/calendar/control_mode` | POST | Set AUTO/MANUAL |
| `/core/calendar/force_block` | POST | Force specific block |
| `/core/calendar/force_manual` | POST | Force mode+actions |
| `/health` | GET | Health check |

---

## 4. Audio System

### 4.1 AudioEngine (`engine_audio.py`)

Stereo audio input pipeline with real-time processing.

Signal chain:
```
Input (2-ch, configurable SR) → DC Blocker (5Hz) → HP Filter (10Hz, 1st order)
  → Optional Notch (50/60Hz mains) → Gate (Schmitt trigger) → Envelope (attack/release)
  → Ring Buffer (3 seconds)
```

Gate logic:
- Open threshold: `noise_floor_rms × 2.5`
- Close threshold: `noise_floor_rms × 1.6`
- Min hold: 80ms (prevent chatter)
- Envelope: attack 12ms, release 180ms

### 4.2 DSP Utilities (`dsp_utils.py`)

Shared DSP helper functions for audio processing.

### 4.3 Timers (`timers.py`)

Qt timer management for audio processing callbacks.

### 4.4 AudioMonitor (`core/audio_monitor.py`)

Real-time audio level monitoring and silence/clipping detection.

### 4.5 Music Structure Engine (`core/music_structure_engine/`)

Optional advanced audio analysis replacing MIL-Lite.

| Sub-engine | Purpose |
|---|---|
| `BeatEngine` | Spectral flux + autocorrelation tempo detection |
| `EnergyEngine` | Multiband RMS + energy trend |
| `TransientEngine` | Transient density + spike detection |
| `PhraseEngine` | Phrase tracking (uses beat state) |
| `DropEngine` | Drop/buildup detection |
| `StateInference` | Produces `MusicStructureState` with probabilities |

Processing chain: `BeatEngine → EnergyEngine → TransientEngine → PhraseEngine → DropEngine → StateInference`

CPU target: < 12% total.

### 4.6 Tempo Subsystem (`tempo/`)

| Module | Purpose |
|---|---|
| `tap_bridge.py` | Bridge between tap tempo input and engine |
| `tap_sender.py` | Sends tap tempo events |
| `kick_detector.py` | Kick drum detection for BPM |
| `auto_clock.py` | Automatic BPM clock generation |

### 4.7 Music Intelligence Lite (`music_intelligence_lite/`)

Legacy music analysis system (predecessor to MSE).

| Module | Purpose |
|---|---|
| `mil_lite.py` | Core MIL-Lite engine |
| `weigher.py` | Analyzer weight computation |
| `profiler.py` | Performance profiling |
| `logger.py` | MIL-specific logging |

### 4.8 Waveform (`waveform_smooth.py`)

Smooth waveform visualization rendering.

---

## 5. Vision System

### 5.1 VisionManager (`core_vision/vision_manager.py`)

Central manager for Vision System PRO (Phase 6.14.1 + V9 Artist).

- Manages 3 independent camera loops (MJPEG IP only, USB removed)
- Watchdog monitoring: 5s interval, detects dead threads, stalls, zero FPS
- Calendar permission gating (fail-safe: permit if no calendar)
- Dancer zone detection via DJ detector person locations
- Lock-based thread-safe configuration

### 5.2 Camera Sources (`core_vision/camera_source.py`)

| Source | Protocol | Features |
|---|---|---|
| `MJPEGSource` | HTTP MJPEG | Axis cameras, reconnection, queue-based buffering |
| `RTSPSource` | RTSP via PyAV | VMS-grade low latency, serialized handshake, `_RTSP_CONNECT_LOCK` |

Both implement abstract `CameraSource` (start, stop, read, is_opened).

### 5.3 Camera Loop (`core_vision/camera_loop.py`)

Main capture loop orchestrating all detectors (Phase 6.14).

Pipeline per frame: `read frame → process haze → DJ → artist → callback`

Features: FPS measurement, frame timestamp for age-based skip, reconnection (max 3 attempts, 2s delay).

### 5.4 YOLO ROI Detector (`core_vision/yolo_roi_detector.py`)

YOLOv8n person detection with GPU optimization (V9.2).

- Multi-zone detection (1–10 zones)
- Device auto-detection: CUDA > MPS > CPU
- Normalized coordinates [0..1] with automatic pixel conversion
- FP16 on GPU, `torch.no_grad()` context
- Backoff on slow inference (>250ms)

### 5.5 Detection Engines

**Haze Detection (`core_vision/camera_haze.py`):**
- Contrast-based smoke density detection (LOW/MEDIUM/HIGH)
- EMA smoothing (factor=0.2), edge-trigger + refire modes
- States: READY → SHOOTING → COOLDOWN
- Fires C64–C66 via FamilyManager

**DJ Detection (`core_vision/dj_detector.py` + `vision_dj_engine.py`):**
- 1–5 zone state machine with disappear delay (2s grace)
- Non-blocking cue firing via event queue
- Per-zone activation: C67–C71
- Watchdog with degraded mode on consecutive errors

**Artist Detection (`core_vision/artist_detector.py` + `vision_artist_engine.py`):**
- 1–8 zone state machine (same architecture as DJ)
- Replaces legacy HOG-based ArtistTracker
- Per-zone activation: C72–C79

### 5.6 Configuration (`core_vision/vision_config.py`)

JSON-based configuration (`vision_config.json`). IP-only enforced. Supports MJPEG (host + path) and RTSP (url or url_main/url_sub).

### 5.7 Vision State (`core_vision/vision_state.py`)

Thread-safe state container (RLock). Tracks: haze level/state, DJ active zone (1–5), tracking zone (1–8). All modules start OFF (calendar governs).

### 5.8 Legacy Sensors (`sensors/`)

| Module | Purpose |
|---|---|
| `camera_people.py` | People counting sensor |
| `camera_haze.py` | Legacy haze sensor |
| `camera_tracking.py` | Legacy tracking sensor |
| `vision_diagnostics.py` | Vision system diagnostics |

### 5.9 Legacy Vision Core (`core/`)

| Module | Purpose |
|---|---|
| `vision_router.py` | Routes frames to registered sensors |
| `camera_manager.py` | Manages camera lifecycle |
| `smart_camera.py` | Smart camera abstraction |

---

## 6. Calendar Governance

### 6.1 CalendarManager (`core/calendar/calendar_manager.py`)

Calendar intelligence and governance — PASSIVE authority (decides modes/permissions, does NOT execute cues).

| Feature | Details |
|---|---|
| Polling | 60-second interval |
| Override types | NONE, TEMPORARY, PERMANENT, UNTIL_NEXT |
| Alert system | 5-minute pre-change alerts with reconfirmation |
| Callbacks | `on_mode_change(mode, source)`, `on_alert(alert_minutes, next_mode)` |
| Sources | MANUAL (user GO), AUTO (schedule), OVERRIDE |

### 6.2 CalendarResolver (`core/calendar/calendar_resolver.py`)

Reads `calendar.json` and resolves active mode.

- Locale-independent weekday resolution (v6.6 fix)
- Supports composite blocks: base_mode + 0–5 parallel actions
- Handles midnight-crossing time ranges
- Validates and detects overlapping blocks

### 6.3 CalendarRules (`core/calendar/calendar_rules.py`)

Permission matrices and canonical modes.

**Canonical Modules (8):**
`audio_engine`, `vision_haze`, `vision_dj`, `vision_artista`, `tracking_cam`, `dj_detection`, `cues_clima`, `system_idle`

**Canonical Modes (10):**

| Mode | audio_engine | vision_haze | vision_dj | vision_artista | tracking_cam | cues_clima |
|---|---|---|---|---|---|---|
| `clima_1` | - | - | - | - | - | ON |
| `clima_2` | - | - | - | - | - | ON |
| `clima_3` | - | - | - | - | - | ON |
| `clima_4` | - | - | - | - | - | ON |
| `teatro` | - | - | - | ON | ON | - |
| `artista` | - | - | - | ON | ON | - |
| `boliche_inicio` | ON | - | - | - | - | - |
| `boliche_desarrollo` | ON | ON | ON | - | - | - |
| `boliche_fin` | ON | - | - | - | - | - |
| `apagado` | - | - | - | - | - | - |

Actions always ENABLE (union), never disable.

### 6.4 CalendarState (`core/calendar/calendar_state.py`)

Data model for calendar state representation.

| Class | Purpose |
|---|---|
| `CalendarSource` (Enum) | MANUAL, AUTO, OVERRIDE |
| `ScheduleBlock` | from_time, to_time, mode, day, actions (0–5) |
| `PermissionState` | Derived permissions from current mode |
| `OverrideInfo` | Override metadata with expiration |
| `CalendarState` | Complete state with timeline, progress, alerts |

---

## 7. Titan Transport Layer

### 7.1 TitanTransport (`core/transport/titan_transport.py`)

HTTP transport to Avolites Titan console.

| Property | Value |
|---|---|
| Protocol | HTTP (legacy, no HTTPS) |
| Library | `requests` with connection pooling |
| Retry | Exponential backoff |
| Stats | fires/kills sent/ok/failed, latency tracking |

Methods: `send_fire(cue_id)`, `send_kill(cue_id)`, `ping()`, `get_active_playbacks()`

### 7.2 TitanQueue (`core/transport/titan_queue.py`)

Asynchronous priority queue for Titan commands.

| Property | Value |
|---|---|
| Priority | KILL (1) > FIRE (2) > PING (3) |
| Max queue | 512 |
| Rate limit | 60ms between requests |
| Dedup window | 50ms |
| Worker | Dedicated thread |

Key features:
- `fire_immediate()` — bypasses queue for critical cues (C41, C37–C39)
- `kill_immediate()` — direct KILL bypass
- `kill_pool()` — batch KILL operations
- Per-family threading locks (`FAMILY_RANGES`)
- Src-Trace (v1.4): caller info gated behind `TITAN_SRC_TRACE=1`

Family ranges:
| Family | Cues |
|---|---|
| BASE_GOLPE | C1–C9, C51–C59 |
| BAJADA_COLOR | C10–C18 |
| BAJADA_POS | C19–C27 |
| MOVIMIENTO | C28–C36 |
| ATAQUE | C37–C39 |
| BRAKE | C42–C44 |

### 7.3 TitanStateSync (`core/transport/titan_sync.py`)

State synchronization watchdog — detects and kills orphaned cues.

| Property | Value |
|---|---|
| Poll interval | 2 seconds |
| Orphan grace | 500ms |
| Max kills/cycle | 10 |
| Worker | Dedicated thread |

Flow: poll Titan → compare with local state → kill orphans with grace period → retry pending kills.

---

## 8. Analyzer Modules

All analyzers follow the pattern: `process(block, sr) → updates internal state → match score [0..100]`.
Located in `analyzers/`.

### 8.1 Energy & Dynamics

| Analyzer | File | Purpose |
|---|---|---|
| EnergyDetector | `energy_detector.py` | RMS energy level detection |
| DynamicPulse | `dynamic_pulse.py` | Dynamic energy pulsation tracking |
| DynamicFlattener | `dynamic_flattener.py` | Detects energy flattening (plateau) |
| EnergyCliff | `energy_cliff.py` | Sudden energy drop detection |
| RampUp | `ramp_up.py` | Energy buildup ramp detection |
| RampDown | `ramp_down.py` | Energy decay ramp detection |
| SoftPeaks | `soft_peaks.py` | Soft energy peak detection |

### 8.2 Rhythm & Beat

| Analyzer | File | Purpose |
|---|---|---|
| BPMDetector | `bpm_detector.py` | Tempo (BPM) detection |
| RhythmTracker | `rhythm_tracker.py` | Rhythm pattern tracking |
| RhythmHighlighter | `rhythm_highlighter.py` | Rhythm accent highlighting |
| RhythmVoid | `rhythm_void.py` | Rhythm absence detection |
| BeatSteady | `beat_steady.py` | Steady beat detection |
| GrooveKeeper | `groove_keeper.py` | Groove consistency monitoring |
| CadenceSpotter | `cadence_spotter.py` | Cadence pattern detection |
| PatternLock | `pattern_lock.py` | Auto-lock on repeating patterns |
| PreSteadyCoherence | `pre_steady_coherence.py` | Pre-steady state coherence analysis |

### 8.3 Percussion & Transients

| Analyzer | File | Purpose |
|---|---|---|
| PulseFinder | `pulse_finder.py` | Percussion pulse detection |
| PulseFinderWrapper | `pulse_finder_wrapper.py` | Legacy wrapper for PulseFinder |
| HiRoll | `hi_roll.py` | Hi-hat roll detection |
| SnareRoll | `snare_roll.py` | Snare roll detection |
| AccentCatcher | `accent_catcher.py` | Rhythmic accent detection |
| YesHits | `yes_hits.py` | Positive hit pattern detection |
| NoHits | `no_hits.py` | Hit absence detection |
| PercussiveBuild | `percussive_build.py` | Percussive buildup detection |

### 8.4 Spectral & Frequency

| Analyzer | File | Purpose |
|---|---|---|
| DeepListener | `deep_listener.py` | Low-frequency content analysis |
| MidRangeFinder | `mid_range_finder.py` | Mid-frequency content analysis |
| HFSwell | `hf_swell.py` | High-frequency swell detection |
| HighSilence | `high_silence.py` | High-frequency silence detection |
| WidebandBlackout | `wideband_blackout.py` | Full-spectrum silence detection |
| TextureCleaner | `texture_cleaner.py` | Spectral texture cleaning/analysis |

### 8.5 Structure & Flow

| Analyzer | File | Purpose |
|---|---|---|
| FlowMonitor | `flow_monitor.py` | Musical flow continuity monitoring |
| BreakSpotter | `break_spotter.py` | Musical break detection |
| Brake | `brake.py` | Brake condition analysis |
| LoopDissolver | `loop_dissolver.py` | Loop ending detection |
| AmbientConfirmator | `ambient_confirmator.py` | Ambient/pad confirmation |
| BurstSharpness | `burst_sharpness.py` | Burst attack sharpness measurement |
| BurstContinuity | `burst_continuity.py` | Burst sustain/continuity tracking |

### 8.6 Meta & Infrastructure

| Module | File | Purpose |
|---|---|---|
| SuperAnalyzer | `super_analyzer.py` | Aggregator / meta-analyzer |
| Placeholder | `placeholder.py` | No-op placeholder for disabled slots |
| ModuleConfig | `module_config.py` | Analyzer configuration management |
| RhythmTools | `rhythm_tools.py` | Shared rhythm analysis utilities |
| WaveformWidget | `waveform_widget.py` | Waveform visualization widget |

### 8.7 Legacy Analyzers (`legacy_analyzers/`)

| Analyzer | File | Purpose |
|---|---|---|
| BurstSharpness | `burst_sharpness.py` | Legacy burst sharpness |
| PulseFinder | `pulse_finder.py` | Legacy pulse finder |

---

## 9. API Endpoints

### 9.1 FastAPI Routers (port 8000)

#### Status (`api/routers/status.py`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/status` | Legacy system status (state, energy, audio, avolites, cue_engine) |
| GET | `/status/unified` | Forwards to CORE 8010 snapshot (Control Room V7) |
| GET | `/stream` | SSE stream of unified status (500ms interval) |

#### Cues (`api/routers/cues.py`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/cues` | Active cues + engine status |
| POST | `/cues/fire` | Fire cue (force flag bypasses READY) |
| DELETE | `/cues/kill` | Kill one or more cues |

#### Calendar (`api/routers/calendar.py`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/calendar/status` | Current mode, time remaining |
| POST | `/calendar/go` | Manual mode change |
| POST | `/calendar/override` | Temporary override |
| POST | `/calendar/extend` | Extend current block |
| POST | `/calendar/auto` | Toggle auto mode |
| POST | `/calendar/force_block` | Force specific schedule block |
| POST | `/calendar/force_manual` | Force mode+actions directly |
| GET | `/calendar/week` | Weekly schedule |
| POST | `/calendar/save` | Save and apply schedule |

All calendar requests forwarded to CORE 8010.

#### Analyzers (`api/routers/analyzers.py`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/analyzers` | All analyzers grouped by state |
| GET | `/analyzers/active` | Active analyzers only |
| GET | `/analyzers/matching` | Analyzers with match=True |

#### Presets (`api/routers/presets.py`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/presets` | List available presets |
| POST | `/save` | Capture current state |
| POST | `/load` | Apply preset (per-section) |

#### Config (`api/routers/config.py`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/config/{section}` | Read config (audio, avolites, state, modules) |
| POST | `/config/{section}` | Update config (avolites, modules only) |

#### System Health (`api/routers/system_health.py`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/status/system` | Real metrics (CPU, RAM, GPU, network, cameras) |
| GET | `/status/system/errors` | Ring buffer of last 50 errors |

#### Network (`api/routers/network.py`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/network/interfaces` | List network interfaces |
| POST | `/network/interface` | Set active interface |
| POST | `/network/console` | Set Avolites target IP:port |
| POST | `/network/ping` | Ping a host |

#### Alerts (`api/routers/alerts.py`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/alerts` | Audio monitor alert status |

### 9.2 API Infrastructure

| Module | Purpose |
|---|---|
| `api/dependencies.py` | FastAPI DI: `get_app_state()`, `get_preset_service()`, `get_analyzer_service()` |
| `api/models.py` | Pydantic models for all endpoints |
| `api/core_bridge.py` | Read-only bridge to CORE state (no state generation) |

### 9.3 Vision Proxy Routes (in `api/main.py`)

| Method | Path | Proxied To |
|---|---|---|
| GET | `/vision/frame/{cam}` | `localhost:5000` |
| GET | `/vision/stream/{cam}` | `localhost:5000` |
| GET | `/vision/status` | `localhost:5000` |

### 9.4 Core HTTP Snapshot Endpoints (port 8010)

| Method | Path | Purpose |
|---|---|---|
| GET | `/core/snapshot` | Full state snapshot |
| GET | `/core/calendar/week` | Weekly schedule |
| GET | `/health` | Health check |
| POST | `/core/calendar/go` | Mode change |
| POST | `/core/calendar/override` | Temporary override |
| POST | `/core/calendar/clear_override` | Clear override |
| POST | `/core/calendar/auto` | Toggle auto mode |
| POST | `/core/calendar/save` | Save schedule |
| POST | `/core/calendar/control_mode` | Set AUTO/MANUAL |
| POST | `/core/calendar/force_block` | Force block |
| POST | `/core/calendar/force_manual` | Force mode+actions |

---

## 10. Cue Map

### 10.1 CueEngine Module Cues (C1–C59)

| Range | Family | Module | Description |
|---|---|---|---|
| C1–C9 | `base_golpe` | BaseGolpeModule | Base golpe primary patterns |
| C10–C18 | `bajada_colores` | BajadaModule | Bajada color schemes |
| C19–C27 | `bajada_posiciones` | BajadaModule | Bajada position patterns |
| C28–C36 | `movimiento` | MovimientoModule | Movement patterns |
| C37–C39 | `ataque` | AtaqueModule | Attack cues |
| C41 | `dimmer` | ControlDimmerModule | Master dimmer control |
| C42–C44 | `brake` | BreakModule | Brake cues |
| C45–C50 | `timed` | TimedSequenceModule | Timed sequence cues |
| C51–C59 | `base_golpe` | BaseGolpeModule | Base golpe extended patterns |

### 10.2 Extended Cue Map — Canonical (C60–C82)

Source of truth: `core/cues/cue_map.py` v6.4

| Family | Range | States | Purpose |
|---|---|---|---|
| **CLIMA** | C60–C63 | clima_1, clima_2, clima_3, clima_4 | Climate/ambient lighting scenes |
| **HAZE** | C64–C66 | LOW, MID, HIGH | Smoke/haze intensity levels |
| **DJ** | C67–C71 | dj_1, dj_2, dj_3, dj_4, dj_5 | DJ booth zone lighting (5 zones) |
| **ARTIST** | C72–C79 | T1, T2, T3, T4, T5, T6, T7, T8 | Artist/stage zone lighting (8 zones) |
| **TRACKING** | C80–C82 | idle, follow, focus | Camera tracking behavior |

Semantics:
- One cue active per family at a time (exclusive)
- State change: kill previous → fire new
- Family disable: kill all in family

### 10.3 Full Cue Range Summary

```
C1  ─── C9   : BaseGolpe (primary)
C10 ─── C18  : Bajada Colors
C19 ─── C27  : Bajada Positions
C28 ─── C36  : Movimiento
C37 ─── C39  : Ataque
C41          : Control Dimmer
C42 ─── C44  : Brake
C45 ─── C50  : Timed Sequence
C51 ─── C59  : BaseGolpe (extended)
C60 ─── C63  : Clima
C64 ─── C66  : Haze
C67 ─── C71  : DJ Zones
C72 ─── C79  : Artist Zones
C80 ─── C82  : Tracking
```

---

## 11. Runtime Dependency Graph

```
                    ┌──────────────────┐
                    │    main.py       │
                    │  (QApplication)  │
                    └────────┬─────────┘
                             │ creates
          ┌──────────────────┼──────────────────────────┐
          │                  │                          │
          ▼                  ▼                          ▼
  ┌───────────────┐  ┌──────────────┐          ┌──────────────┐
  │  AudioEngine  │  │AvolitesCtrl  │          │   Threads    │
  │               │  │              │          │              │
  └───────┬───────┘  └──────┬───────┘          │ • API 8000   │
          │                 │                  │ • HTTP 8010  │
          │                 ▼                  │ • Calendar   │
          │         ┌──────────────┐           │ • TitanSync  │
          │         │ TitanQueue   │           └──────────────┘
          │         │              │
          │         └──────┬───────┘
          │                │
          │                ▼
          │         ┌──────────────┐
          │         │TitanTransport│───► Avolites Titan (HTTP)
          │         └──────────────┘
          │
          ▼
  ┌───────────────┐     ┌──────────────────┐
  │  Analyzers    │────►│  StateManager    │
  │  (35+ modules)│     │  (state machine) │
  └───────────────┘     └────────┬─────────┘
                                 │
          ┌──────────────────────┼──────────────────┐
          │                      │                  │
          ▼                      ▼                  ▼
  ┌───────────────┐     ┌──────────────┐    ┌──────────────┐
  │  CueEngine    │     │  UnionBridge │    │ EnergyDetect │
  │  (7 modules)  │     │              │    │              │
  └───────┬───────┘     └──────────────┘    └──────────────┘
          │
          ├──► AvolitesCtrl.fire_cue() / kill_cue()
          │
          ▼
  ┌───────────────┐
  │AuxStateManager│ (C41 reasons, C45-50 index)
  └───────────────┘

  ┌─────────────────────────────────────────────────────┐
  │                GOVERNANCE LAYER                      │
  │                                                      │
  │  CalendarManager ──► CalendarResolver (calendar.json)│
  │       │                                              │
  │       ▼                                              │
  │  SystemBridge ──┬──► AudioEngine (gating)            │
  │                 ├──► CueEngine (disabled states)     │
  │                 ├──► VisionManager (modules on/off)  │
  │                 └──► FamilyManager (CLIMA cues)      │
  │                                                      │
  │  BootManager (singleton) — startup orchestration     │
  └─────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────┐
  │                 VISION SYSTEM                        │
  │                                                      │
  │  VisionManager ──┬──► CameraLoop (haze)              │
  │                  ├──► CameraLoop (DJ)                │
  │                  └──► CameraLoop (artist)            │
  │                                                      │
  │  CameraLoop ──► CameraSource (MJPEG/RTSP)           │
  │       │                                              │
  │       ├──► HazeDetector ──► FamilyManager (C64-C66)  │
  │       ├──► DJDetector ───► FamilyManager (C67-C71)   │
  │       └──► ArtistDetector► FamilyManager (C72-C79)   │
  │                                                      │
  │  YoloRoiDetector (YOLOv8n) ◄── DJ/Artist detectors  │
  └─────────────────────────────────────────────────────┘
```

### Module Interaction Summary

| Source | Target | Relationship |
|---|---|---|
| AudioEngine | Analyzers | Provides audio blocks |
| Analyzers | StateManager | Provide match scores (votes) |
| StateManager | CueEngine | Provides state + energy |
| CueEngine | AvolitesCtrl | Fires/kills cues |
| AvolitesCtrl | TitanQueue | Enqueues commands |
| TitanQueue | TitanTransport | HTTP delivery |
| TitanStateSync | TitanTransport | Polls orphans |
| CalendarManager | SystemBridge | Provides mode + actions |
| SystemBridge | AudioEngine | Audio gating |
| SystemBridge | CueEngine | State disabling |
| SystemBridge | VisionManager | Module enable/disable |
| SystemBridge | FamilyManager | CLIMA cue activation |
| VisionManager | CameraLoop | Camera lifecycle |
| CameraLoop | Detectors | Frame processing |
| Detectors | FamilyManager | Cue fire/kill |
| BootManager | All singletons | Startup orchestration |
| SnapshotServer | All managers | State readout |
| FastAPI | SnapshotServer | Proxies to CORE |

---

## 12. System Boot Sequence

### 12.1 GUI Boot (`main.py`)

```
1. OpenMP/BLAS thread protection (environment variables)
2. Conda DLL path fix (Windows)
3. _bootstrap_guard() — Qt plugin path configuration
4. safe_import() — dynamic module loading with fallbacks
5. QApplication(sys.argv)
6. Main(QMainWindow).__init__():
   a. AudioEngine — initialize audio input
   b. StateManager — create state machine (FAST preset)
   c. AvolitesController — connect to Titan console
   d. CueEngine — create with 7 specialist modules
   e. EnergyDetector — energy level tracking
   f. CalendarManager — load calendar.json
   g. SystemBridge — connect calendar → system components
   h. VisionManager — initialize camera loops
   i. FamilyManager — connect to CueEngine
   j. BootManager.boot_autoload_show():
      i.   KILL ALL + CueEngine.silent_reset()
      ii.  Calendar.resolve(now) → SystemBridge.apply()
      iii. Vision sync to calendar actions
      iv.  Fire C41 (dimmer ON)
      v.   Log READY
   k. SnapshotServer — start HTTP on :8010
   l. start_api_server() — start FastAPI on :8000 (thread)
   m. Start Qt timers (audio processing, UI updates)
7. app.exec() — enter Qt event loop
```

### 12.2 Headless Boot (`systemd/911fiesta.service`)

```
1. systemd starts uvicorn with api.main:app
2. FastAPI app initialization
3. Routers registered (status, cues, calendar, analyzers, presets, config, network, alerts, system_health)
4. CORS middleware configured
5. Static files mounted (webapp/dist/)
6. Uvicorn serves on 0.0.0.0:8000
7. Proxies to CORE :8010 for authoritative state
```

### 12.3 Kiosk Boot (`systemd/show-gui.service`)

```
1. systemd allocates TTY7
2. startx launches .xinitrc on :0 vt7
3. .xinitrc starts openbox window manager
4. main.py launched inside X session
5. Full GUI boot sequence (see 12.1)
```

---

## 13. Design Patterns

### 13.1 Singleton Pattern

Used for global system components requiring single instances:
- `BootManager` (`get_boot_manager()` / `create_boot_manager()`)
- `SystemBridge` (`get_system_bridge()` / `reset_system_bridge()`)
- `AppState` (`get_app_state()`)
- `SnapshotServer` (`get_snapshot_server()`)
- `CalendarManager` (`get_calendar_manager()` / `set_calendar_manager()`)

### 13.2 Graceful Degradation

Optional modules use `safe_import()` with availability flags:
- `_MSE_AVAILABLE` — MusicStructureEngine
- `AVOLITES_AVAILABLE` — Avolites controller
- Missing modules replaced with no-op placeholder classes

### 13.3 Deterministic State Machine

```
Input (Analyzer votes) → StateManager (hysteresis) → CueEngine (OFF→ON)
```

No hidden state changes. Every transition is traceable.

### 13.4 Calendar Authority (Hard Gating)

Calendar is the single source of truth for system permissions. SystemBridge enforces:
- Audio ON/OFF
- State enabling/disabling
- Vision module activation
- Climate cue firing

### 13.5 Atomic Cue Transitions

CueEngine enforces KILL-first-then-FIRE for all state changes. No overlapping cues within the same family.

### 13.6 Edge-Trigger with Deduplication

FamilyManager and TitanQueue prevent duplicate commands:
- FamilyManager: no fire if already active
- TitanQueue: 50ms dedup window

### 13.7 Watchdog Pattern

Multiple watchdogs monitor system health:
- TitanStateSync: 2s Titan state polling, orphan detection
- VisionManager: 5s camera watchdog (dead threads, stalls, zero FPS)
- TitanQueue: pending kill retry

### 13.8 Priority Queue with Rate Limiting

TitanQueue implements:
- KILL > FIRE > PING priority
- 60ms rate limiting between requests
- Immediate bypass for critical cues (C41, C37–C39)
- Per-family threading locks

### 13.9 Proxy Architecture (API Layer)

```
Web Client → FastAPI (:8000) → SnapshotServer (:8010) → CORE State
                              → Vision Flask (:5000)  → Camera Frames
```

API never generates state — only reads from CORE.

### 13.10 Observer/Callback Pattern

- CalendarManager → on_mode_change callback → SystemBridge
- CueEngine modules → fire/kill callbacks → AvolitesController
- VisionManager → frame callbacks → UI

### 13.11 Producer/Consumer (AuxStateManager)

Modules produce state changes (request/release C41 OFF reasons), other modules consume them. No direct module-to-module coupling.

---

## File Index

```
911-fiesta-core-LINUX/
├── main.py                          # GUI entrypoint (QMainWindow)
├── state_manager.py                 # Musical state machine (V13)
├── cue_engine.py                    # Modular cue orchestrator (v6.0)
├── engine_audio.py                  # Audio input pipeline
├── aux_state_manager.py             # Central state table
├── union_bridge.py                  # Anti-repetition bridge
├── avolites_config.py               # Avolites controller + config
├── base_module.py                   # Base class for CueEngine modules
├── module_config.py                 # Module configuration
├── module_card.py                   # UI module card widget
├── dsp_utils.py                     # DSP helper functions
├── timers.py                        # Qt timer management
├── waveform_smooth.py               # Waveform visualization
├── flow_monitor.py                  # Flow monitoring (root level)
├── neon_styles.py                   # UI neon styling
├── bpm_ui.py / bpm_widget.py        # BPM display widgets
├── clock_widget.py                  # Clock display widget
├── cue_engine_debug_widget.py       # CueEngine debug panel
├── cues_monitor_tab.py              # Cues monitor UI tab
├── network_utils.py                 # Network utilities
├── api_server.py                    # Vision Flask API (port 5000)
│
├── mod_control_dimmer.py            # CueEngine: Dimmer (C41)
├── mod_break.py                     # CueEngine: Break (C42-44)
├── mod_ataque.py                    # CueEngine: Ataque (C37-39)
├── mod_basegolpe.py                 # CueEngine: BaseGolpe (C1-9, C51-59)
├── mod_bajada.py                    # CueEngine: Bajada (C10-27)
├── mod_movimiento.py                # CueEngine: Movimiento (C28-36)
├── mod_timed_sequence.py            # CueEngine: Timed (C45-50)
│
├── analyzers/                       # 35+ audio analyzers
│   ├── __init__.py
│   ├── energy_detector.py           # RMS energy
│   ├── bpm_detector.py              # BPM detection
│   ├── pulse_finder.py              # Percussion pulse
│   ├── rhythm_tracker.py            # Rhythm patterns
│   ├── beat_steady.py               # Steady beat
│   ├── ... (see Section 8)
│   └── super_analyzer.py            # Meta-analyzer
│
├── api/                             # FastAPI REST API
│   ├── main.py                      # FastAPI app (port 8000)
│   ├── core_bridge.py               # Read-only CORE bridge
│   ├── dependencies.py              # DI providers
│   ├── models.py                    # Pydantic models
│   └── routers/
│       ├── status.py                # System status + SSE
│       ├── cues.py                  # Cue fire/kill
│       ├── calendar.py              # Calendar control
│       ├── analyzers.py             # Analyzer state
│       ├── presets.py               # Preset save/load
│       ├── config.py                # Config management
│       ├── system_health.py         # System metrics
│       ├── network.py               # Network config
│       └── alerts.py                # Audio alerts
│
├── core/
│   ├── boot_manager.py              # Boot sequence
│   ├── system_bridge.py             # Calendar→System bridge
│   ├── http_snapshot.py             # CORE HTTP server (8010)
│   ├── audio_monitor.py             # Audio level monitor
│   ├── vision_router.py             # Legacy vision router
│   ├── camera_manager.py            # Legacy camera manager
│   ├── smart_camera.py              # Legacy smart camera
│   ├── cues/
│   │   ├── cue_map.py               # Canonical cue assignments (C60-C82)
│   │   └── family_manager.py        # Exclusive cue family gating
│   ├── transport/
│   │   ├── titan_transport.py       # HTTP transport to Titan
│   │   ├── titan_queue.py           # Priority command queue
│   │   └── titan_sync.py            # State sync watchdog
│   ├── calendar/
│   │   ├── calendar_manager.py      # Calendar intelligence
│   │   ├── calendar_resolver.py     # Schedule resolution
│   │   ├── calendar_rules.py        # Permission matrices
│   │   └── calendar_state.py        # State data model
│   └── music_structure_engine/
│       ├── music_structure_engine.py # MSE orchestrator
│       ├── beat_engine.py           # Beat analysis
│       ├── energy_engine.py         # Energy analysis
│       ├── transient_engine.py      # Transient analysis
│       ├── phrase_engine.py         # Phrase tracking
│       ├── drop_engine.py           # Drop detection
│       ├── state_inference.py       # State inference
│       ├── buffers.py               # Ring buffers
│       └── math_utils.py            # Math utilities
│
├── core_vision/                     # Vision System PRO
│   ├── vision_manager.py            # Central vision manager
│   ├── camera_source.py             # MJPEG/RTSP sources
│   ├── camera_loop.py               # Capture loop
│   ├── vision_config.py             # JSON config
│   ├── vision_state.py              # Thread-safe state
│   ├── yolo_roi_detector.py         # YOLOv8n detector
│   ├── camera_haze.py               # Haze detector
│   ├── haze_detector.py             # Legacy haze
│   ├── dj_detector.py               # DJ detection facade
│   ├── vision_dj_engine.py          # DJ zone state machine
│   ├── artist_detector.py           # Artist detection facade
│   ├── vision_artist_engine.py      # Artist zone state machine
│   ├── artist_tracker.py            # Legacy artist tracker
│   └── camera_tracking.py           # Legacy tracking
│
├── tempo/                           # Tempo subsystem
│   ├── tap_bridge.py
│   ├── tap_sender.py
│   ├── kick_detector.py
│   └── auto_clock.py
│
├── music_intelligence_lite/         # Legacy MIL
│   ├── mil_lite.py
│   ├── weigher.py
│   ├── profiler.py
│   └── logger.py
│
├── services/                        # Service layer
│   ├── app_state.py                 # Global app state singleton
│   ├── preset_service.py            # Preset management
│   └── analyzer_service.py          # Analyzer state service
│
├── sensors/                         # Legacy sensors
│   ├── camera_people.py
│   ├── camera_haze.py
│   ├── camera_tracking.py
│   └── vision_diagnostics.py
│
├── config/
│   └── mil_lite_config.py           # MIL-Lite configuration
│
├── ui/                              # UI tabs and widgets
│   ├── health_tab.py
│   ├── vision_tab.py
│   ├── vision_dj_tab.py
│   ├── vision_haze_tab.py
│   ├── vision_artist_tab.py
│   ├── vision_config_widget.py
│   ├── bpm_master_tab.py
│   ├── calendar_tab.py
│   ├── calendar_status_widget.py
│   ├── calendar_schedule_editor.py
│   └── layered_zone_editor.py
│
├── systemd/
│   ├── 911fiesta.service            # Headless API service
│   └── show-gui.service             # GUI kiosk service
│
├── tests/
│   ├── test_states.py
│   ├── test_titan_transport.py
│   └── test_v11.py
│
├── tools/
│   ├── taptempo_only.py
│   ├── test_bpm_master.py
│   ├── diag_boot.py
│   └── audit/
│       ├── run_audit.py
│       ├── static_import_scan.py
│       ├── runtime_smoke_tests.py
│       └── collect_runtime_probe.py
│
├── scripts/
│   ├── smoke_show.py
│   └── smoke_server.py
│
├── webapp/                          # Vite SPA (web dashboard)
├── legacy_analyzers/                # Deprecated analyzers
├── docs/                            # Documentation
└── requirements.txt                 # Python dependencies
```

---

*End of Architecture Runtime Map 2026.*

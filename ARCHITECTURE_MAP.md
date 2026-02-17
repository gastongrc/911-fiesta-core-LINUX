# 911 Fiesta Core LINUX — Mapa Técnico del Runtime
> Generado desde código fuente, branch `baseline/linux-foja-cero`
> Fecha: 2026-02-17

---

## 1. Entrypoints

| Entrypoint | Archivo | Tipo | Descripción |
|---|---|---|---|
| **GUI Principal** | `main.py` | `QMainWindow` (PySide6) | Aplicación completa con todos los subsistemas |
| **API Headless** | `api/main.py` | FastAPI / uvicorn | Servidor REST en puerto 8000 |
| **Vision Legacy** | `api_server.py` | Flask | API de visión legacy, puerto 5000 |
| **systemd service** | `systemd/911fiesta.service` | Unit | `uvicorn api.main:app --host 0.0.0.0 --port 8000` |
| **X11 Show** | `scripts/run_show.sh` + `scripts/xinitrc_show` | Shell | Lanzador GUI para X11 headless |

### Entrypoints secundarios (`if __name__ == "__main__"`)
- `module_config.py` — test de carga de analyzers
- `tools/taptempo_only.py` — tap tempo standalone
- `tools/test_bpm_master.py` — test BPM
- `tools/diag_boot.py` — diagnóstico de boot
- `tools/audit/run_audit.py` — auditoría estática
- `tools/audit/static_import_scan.py` — escaneo de imports
- `tools/audit/collect_runtime_probe.py` — recolección runtime
- `tools/audit/runtime_smoke_tests.py` — smoke tests
- `analyzers/dynamic_pulse.py` — test del módulo
- `tests/test_states.py`, `tests/test_titan_transport.py`, `tests/test_v11.py` — tests unitarios

---

## 2. Cadena de Ejecución (Runtime Principal)

### 2a. Modo GUI (`python main.py`)
```
main.py::Main(QMainWindow)
  ├─ AudioEngine            → captura audio, filtrado, ring buffer
  ├─ StateManager v13       → máquina de estados determinística
  ├─ AuxStateManager v3     → tabla de estado auxiliar (C41, C45-50)
  ├─ CueEngine v6.0         → orquesta 7 módulos en orden estricto
  │   ├─ ControlDimmerModule  (C41)
  │   ├─ BreakModule          (C42-44)
  │   ├─ AtaqueModule         (C37-39)
  │   ├─ BaseGolpeModule      (C1-9, C51-59)
  │   ├─ BajadaModule         (C10-27)
  │   ├─ MovimientoModule     (C28-36)
  │   └─ TimedSequenceModule  (C45-50)
  ├─ AvolitesController     → HTTP a consola Titan
  ├─ CalendarManager v6.4   → schedule → modos → governance
  ├─ SystemBridge v6.8      → puente calendario→módulos
  ├─ BootManager v1.0       → bootstrap determinístico
  ├─ VisionManager PRO      → cámaras, YOLO, detección
  ├─ UnionBridge v1         → anti-repetición con bridge
  ├─ Analyzers (45+)        → análisis musical en tiempo real
  └─ UI Tabs (PySide6)      → interfaz gráfica
```

### 2b. Modo Headless (`uvicorn api.main:app`)
```
api/main.py::FastAPI app
  ├─ Routers: status, analyzers, cues, network, presets,
  │           config, alerts, calendar, system_health
  ├─ AppState singleton     → estado compartido
  ├─ PresetService          → persistencia de presets
  ├─ AnalyzerService        → lifecycle de analyzers
  └─ Vision proxy           → redirige a Flask legacy (5000)
```

---

## 3. Módulos Principales

### 3a. Estado y Control

| Módulo | Archivo | Clase | Rol |
|---|---|---|---|
| State Manager | `state_manager.py` | `StateManager` | SSOT de estado musical (BAJADA/BASE_GOLPE/ATAQUE/BRAKE) |
| Aux State Manager | `aux_state_manager.py` | `AuxStateManager` | Tabla dimmer (C41) + secuencia aux (C45-50) |
| Cue Engine | `cue_engine.py` | `CueEngine` | Ejecución determinística de 7 módulos por tick |
| Union Bridge | `union_bridge.py` | `UnionBridge` | Anti-repetición por ciclos de energía |
| Cue Map | `core/cues/cue_map.py` | — | SSOT de asignación de cues (C1-C82) |
| Family Manager | `core/cues/family_manager.py` | `FamilyManager` | ON/OFF por familia, un cue activo por familia |

### 3b. Audio

| Módulo | Archivo | Clase | Rol |
|---|---|---|---|
| Audio Engine | `engine_audio.py` | `AudioEngine` | Captura → DC-Block → HP → Gate → Ring Buffer |
| Timers | `timers.py` | `setup_timers()` | Orquestación Qt con staggered startup |
| DSP Utils | `dsp_utils.py` | — | Utilidades de procesamiento |

### 3c. Hardware (Avolites Titan)

| Módulo | Archivo | Clase | Rol |
|---|---|---|---|
| Avolites Controller | `avolites_config.py` | `AvolitesController` | API HTTP a consola Titan |
| Titan Transport | `core/transport/titan_transport.py` | `TitanTransport` | HTTP send con reintentos |
| Titan Queue | `core/transport/titan_queue.py` | `TitanQueue` | Cola async, prioridad KILL > FIRE |
| Titan Sync | `core/transport/titan_sync.py` | `TitanStateSync` | Polling de estado de consola |
| Network Utils | `network_utils.py` | — | Detección de interfaces de red |

### 3d. Visión

| Módulo | Archivo | Clase | Rol |
|---|---|---|---|
| Vision Manager | `core_vision/vision_manager.py` | `VisionManager` | Gestión centralizada de visión |
| Camera Loop | `core_vision/camera_loop.py` | `CameraLoop` | Thread de captura de frames |
| Camera Source | `core_vision/camera_source.py` | `MJPEGSource`, `RTSPSource`, `RTSPSourcePyAV` | Protocolos MJPEG/RTSP |
| DJ Engine | `core_vision/vision_dj_engine.py` | `VisionDJEngine` | 5 zonas DJ (C67-71) YOLO |
| Artist Engine | `core_vision/vision_artist_engine.py` | `VisionArtistEngine` | 8 zonas artista (C72-79) YOLO |
| Haze Detector | `core_vision/haze_detector.py` | `HazeDetector` | Detección de humo (C64-66) |
| DJ Detector | `core_vision/dj_detector.py` | `DJDetector` | Detección DJ via YOLO |
| Artist Detector | `core_vision/artist_detector.py` | `ArtistDetector` | Detección artista via YOLO |
| Artist Tracker | `core_vision/artist_tracker.py` | `ArtistTracker` | Tracking de zonas |
| YOLO ROI | `core_vision/yolo_roi_detector.py` | `YoloRoiDetector` | Wrapper Ultralytics YOLOv8 |
| Vision Config | `core_vision/vision_config.py` | `VisionConfig` | Configuración persistente |
| Vision State | `core_vision/vision_state.py` | `VisionState` | Estado runtime de visión |

### 3e. Calendario y Governance

| Módulo | Archivo | Clase | Rol |
|---|---|---|---|
| Calendar Manager | `core/calendar/calendar_manager.py` | `CalendarManager` | Schedule → modos, polling 60s |
| Calendar State | `core/calendar/calendar_state.py` | `CalendarState`, `ScheduleBlock` | Estructuras de datos |
| Calendar Resolver | `core/calendar/calendar_resolver.py` | `CalendarResolver` | Resolución de bloque activo en tiempo T |
| Calendar Rules | `core/calendar/calendar_rules.py` | — | Permisos canónicos por modo |
| System Bridge | `core/system_bridge.py` | `SystemBridge` | Puente calendario → enable/disable módulos |
| Boot Manager | `core/boot_manager.py` | `BootManager` | Bootstrap determinístico (PENDING→BOOTING→READY) |

### 3f. Tempo y Beat

| Módulo | Archivo | Clase | Rol |
|---|---|---|---|
| Auto Clock | `tempo/auto_clock.py` | `AutoClock` | Tracking automático de tempo |
| Tap Bridge | `tempo/tap_bridge.py` | `TapBridge` | Input manual tap-tempo |
| Kick Detector | `tempo/kick_detector.py` | `KickPulseDetector` | Detección de kick desde audio |

### 3g. Sensores

| Módulo | Archivo | Clase | Rol |
|---|---|---|---|
| Camera People | `sensors/camera_people.py` | `CameraPeopleSensor` | Detección de personas |
| Camera Haze | `sensors/camera_haze.py` | `CameraHazeSensor` | Análisis de humo |
| Camera Tracking | `sensors/camera_tracking.py` | `CameraTrackingSensor` | Tracking |
| Vision Diagnostics | `sensors/vision_diagnostics.py` | `VisionDiagnostics` | Métricas de salud |

### 3h. Servicios

| Módulo | Archivo | Clase | Rol |
|---|---|---|---|
| Analyzer Service | `services/analyzer_service.py` | `AnalyzerService` | Lifecycle de analyzers |
| App State | `services/app_state.py` | `AppState` | Singleton estado compartido |
| Preset Service | `services/preset_service.py` | `PresetService` | Carga/guardado de presets |

---

## 4. Analyzers (45+ módulos en `/analyzers/`)

Todos heredan de `BaseModule` (`base_module.py`) con interfaz `process(block, sr)`.

| Categoría | Módulos clave | Uso |
|---|---|---|
| **Energía** | `energy_detector.py` | Clasificación BAJA/MEDIA/ALTA → StateManager |
| **BPM** | `bpm_detector.py` | Detección de tempo → lock de BPM |
| **BASE_GOLPE** | `dynamic_pulse.py`, `groove_keeper.py`, `rhythm_tracker.py`, `rhythm_highlighter.py` | Votación de kick para C1-9/C51-59 |
| **BAJADA** | `loop_dissolver.py`, `deep_listener.py` | Detección de loops, análisis sub-bass |
| **BRAKE** | `brake.py`, `energy_cliff.py` | Detección de brake y caída de energía |
| **ATAQUE** | `burst_sharpness.py` | Detección de ataque y sharpness |
| **Votación** | `no_hits.py`, `yes_hits.py` | Flags de votación hit/no-hit |
| **Debug** | `super_analyzer.py` | Vista consolidada de todos los analyzers |

---

## 5. API Endpoints (FastAPI)

Base: `http://localhost:8000`

| Router | Archivo | Prefijo | Funcionalidad |
|---|---|---|---|
| Status | `api/routers/status.py` | `/status` | Estado general del sistema |
| Analyzers | `api/routers/analyzers.py` | `/analyzers` | Estado y config de analyzers |
| Cues | `api/routers/cues.py` | `/cues` | Fire/kill cues |
| Network | `api/routers/network.py` | `/network` | Interfaces y consola |
| Presets | `api/routers/presets.py` | `/presets` | Save/load presets |
| Config | `api/routers/config.py` | `/config` | Configuración runtime |
| Alerts | `api/routers/alerts.py` | `/alerts` | Alertas del sistema |
| Calendar | `api/routers/calendar.py` | `/calendar` | Gestión de schedule |
| System Health | `api/routers/system_health.py` | `/system-health` | Recursos del sistema |

Modelos Pydantic: `api/models.py` (25+ modelos)

---

## 6. UI (PySide6 / Qt)

| Tab / Widget | Archivo | Clase |
|---|---|---|
| Vision Tab | `ui/vision_tab.py` | `VisionTab` |
| Calendar Tab | `ui/calendar_tab.py` | `CalendarTab` |
| Health Tab | `ui/health_tab.py` | `HealthMonitorWidget` |
| BPM Master Tab | `ui/bpm_master_tab.py` | `BpmMasterTab` |
| Vision Config | `ui/vision_config_widget.py` | `VisionConfigWidget` |
| Schedule Editor | `ui/calendar_schedule_editor.py` | `CalendarScheduleEditor` |
| Zone Editor | `ui/layered_zone_editor.py` | `LayeredZoneEditor` |
| DJ Tab | `ui/vision_dj_tab.py` | `VisionDJTab` |
| Artist Tab | `ui/vision_artist_tab.py` | `VisionArtistTab` |
| Haze Tab | `ui/vision_haze_tab.py` | `VisionHazeTab` |
| Calendar Status | `ui/calendar_status_widget.py` | `CalendarStatusWidget` |
| BPM Widget | `bpm_widget.py` | `BPMMonitorWidget` |
| Clock Widget | `clock_widget.py` | `ClockWidget` |
| Waveform | `waveform_smooth.py` | `SmoothWaveform` |
| Module Card | `module_card.py` | `ModuleCard` |
| Cues Monitor | `cues_monitor_tab.py` | `CuesMonitorTab` |
| CueEngine Debug | `cue_engine_debug_widget.py` | `CueEngineDebugWidget` |
| Flow Monitor | `flow_monitor.py` | `FlowMonitor` |
| BPM UI | `bpm_ui.py` | BPM interface |
| Neon Styles | `neon_styles.py` | Stylesheet system |

---

## 7. Mapa de Cues (SSOT: `core/cues/cue_map.py`)

| Familia | Rango | Uso |
|---|---|---|
| BASE_GOLPE FX_DIMMER | C1-3, C51-53 | Golpe dimmer |
| BASE_GOLPE FX_BEAM | C4-6, C54-56 | Golpe beam |
| BASE_GOLPE FX_COLOR | C7-9, C57-59 | Golpe color |
| BAJADA Colors | C10-18 | Colores BAJA/MEDIA/ALTA |
| BAJADA Positions | C19-27 | Posiciones BAJA/MEDIA/ALTA |
| MOVIMIENTO | C28-36 | Movimiento |
| ATAQUE | C37-39 | Ataque |
| DIMMER | C41 | Control dimmer |
| BRAKE | C42-44 | Brake effects |
| AUX Sequence | C45-50 | Secuencia temporizada |
| CLIMA | C60-63 | Clima 1-4 |
| HAZE | C64-66 | Humo LOW/MID/HIGH |
| DJ | C67-71 | Zonas DJ 1-5 |
| ARTIST | C72-79 | Zonas artista T1-T8 |
| TRACKING | C80-82 | Idle/follow/focus |

---

## 8. Infraestructura y Deploy

### systemd
- `911fiesta.service` — servicio principal (user: `fiesta911`, `/opt/911fiesta`)
- `911fiesta.env` — variables de entorno (CUDA, log level, puerto)
- `show.target` — target multi-user
- `show-getty-autologin.conf` — auto-login para show
- `911fiesta-show.desktop` — autostart XDG

### Scripts
- `scripts/bootstrap_linux.sh` — setup del sistema
- `scripts/install_911fiesta.sh` — instalación
- `scripts/update_911fiesta.sh` — actualización
- `scripts/healthcheck_911fiesta.sh` — health check
- `scripts/run_show.sh` — lanzador del show

### xorg
- `xorg/` — configuración X11 para entorno headless

---

## 9. Dependencias Principales

Desde `environment.yml` y `requirements.txt`:
- **UI:** PySide6
- **API:** FastAPI, Flask, uvicorn
- **Audio:** numpy, scipy, sounddevice
- **Vision:** opencv-python, ultralytics (YOLOv8), PyAV
- **ML:** torch (opcional, CUDA)
- **Networking:** requests, aiohttp

---

## 10. Patrones de Diseño Clave

1. **Máquina de estados determinística** — StateManager es SSOT, CueEngine solo lee y ejecuta
2. **Governance dura** — CalendarManager → SystemBridge → enable/disable módulos
3. **No auto-advance** — módulos no avanzan cues sin señal de StateManager
4. **Non-blocking vision** — frames se dropean bajo carga, maxsize=1
5. **Cola con prioridad** — TitanQueue: KILL > FIRE
6. **Bootstrap idempotente** — BootManager seguro en restart
7. **Thread safety** — todo acceso a estado detrás de locks
8. **Event-driven + Stateful** — BaseGolpe/Break son event-driven; Bajada/Movimiento son stateful
9. **SSOT múltiple** — cue_map.py (cues), StateManager (estado), calendar_rules.py (permisos)
10. **Dedup temporal** — ventana de 600ms para evitar fire/kill duplicados

---

## 11. Grafo de Dependencias (Simplificado)

```
                    ┌─────────────────────────────────────┐
                    │            main.py (GUI)             │
                    │         api/main.py (Headless)       │
                    └────┬────┬────┬────┬────┬────┬───────┘
                         │    │    │    │    │    │
              ┌──────────┘    │    │    │    │    └──────────┐
              ▼               ▼    │    ▼    ▼              ▼
        AudioEngine    StateManager│  CueEngine    VisionManager
              │           ▲   │    │    │  │              │
              │           │   ▼    │    │  ▼              ▼
              │        Analyzers   │    │ 7 Modules    CameraLoop
              │        (45+)       │    │    │         DJEngine
              │                    │    │    ▼         ArtistEngine
              │              CalendarManager           HazeDetector
              │                    │
              │                    ▼
              │              SystemBridge ──→ BootManager
              │                    │
              │                    ▼
              └──────────→ AvolitesController
                                   │
                                   ▼
                           TitanQueue → TitanTransport
                                          │
                                          ▼
                                   Consola Avolites
                                   (HTTP API)
```

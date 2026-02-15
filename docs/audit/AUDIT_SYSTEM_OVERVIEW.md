# AUDITORÍA 911 FIESTA — SYSTEM OVERVIEW

> Fecha: 2026-02-15
> Repo: `911-fiesta-core-LINUX`
> Rama: `claude/audit-911-fiesta-system-LvSAa`
> Alcance: Arquitectura, subsistemas, flujos de datos, riesgos, evidencia

---

## 1. ARQUITECTURA GENERAL

```
┌───────────────────────── SERVER LINUX (/opt/911fiesta) ────────────────────────┐
│                                                                                 │
│  ┌─────────────────── CORE (main.py, proceso principal) ──────────────────┐    │
│  │  PySide6 GUI  ─┬─ AudioEngine (sounddevice, ring buffer 3s)           │    │
│  │                 ├─ AvolitesController → TitanQueue → TitanTransport    │    │
│  │                 ├─ VisionManager → CameraLoop[] → CameraSource[]      │    │
│  │                 ├─ StateManager (BAJADA/BASE_GOLPE/ATAQUE/BRAKE)      │    │
│  │                 ├─ CueEngine (módulos por estado)                     │    │
│  │                 ├─ CalendarManager (schedule semanal)                  │    │
│  │                 ├─ EnergyDetector (BAJA/MEDIA/ALTA)                   │    │
│  │                 └─ AudioMonitor (silence/clipping/noise/stream_lost)   │    │
│  │                                                                        │    │
│  │  HTTP Snapshot Server ──► 127.0.0.1:8010 /core/snapshot               │    │
│  └────────────────────────────────────────────────────────────────────────┘    │
│          ↕ HTTP (localhost)                                                     │
│  ┌───────────────────── API (FastAPI/uvicorn, puerto 8000) ──────────────┐    │
│  │  /api/v1/status/unified ← forward 8010                               │    │
│  │  /api/v1/stream (SSE 2 updates/s)                                    │    │
│  │  /api/v1/cues/* /calendar/* /config/* /network/* /alerts/*           │    │
│  │  /api/v1/vision/* ← proxy a Flask 5000                               │    │
│  │  / → webapp/dist/index.html (React SPA)                              │    │
│  └───────────────────────────────────────────────────────────────────────┘    │
│          ↕ HTTP (localhost)                                                     │
│  ┌───────────────── Vision Flask (api_server.py, puerto 5000) ───────────┐    │
│  │  /vision/status  /vision/frame/{cam}  /vision/stream/{cam}            │    │
│  │  VisionManager → CameraLoop (haze, dj, artist)                       │    │
│  │  YoloRoiDetector (CUDA fp16 en GPU)                                   │    │
│  └───────────────────────────────────────────────────────────────────────┘    │
│                                                                                 │
│  ═══════════════════ HARDWARE / RED ═══════════════════════════════════════     │
│  GPU: NVIDIA GTX 1080 Ti (YOLO inference)                                      │
│  Audio: Maono PS22 USB (sounddevice → PortAudio → ALSA)                       │
│  Red LAN:  Avolites Titan (192.168.0.3:4430 HTTP)                              │
│            Cámaras IP Axis (192.168.1.110 MJPEG)                               │
│  systemd: 911fiesta.service (headless API en server)                            │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Puertos en uso

| Puerto | Proceso | Protocolo | Descripción |
|--------|---------|-----------|-------------|
| 8000 | uvicorn (FastAPI) | HTTP | API pública + SPA + SSE |
| 8010 | HTTPServer (stdlib) | HTTP | Snapshot CORE (solo 127.0.0.1) |
| 5000 | Flask | HTTP | Vision API (frames, detections) |
| 4430 | — (destino) | HTTP | Avolites Titan WebAPI |

**Evidencia:** `systemd/911fiesta.service:45` → `ExecStart=...uvicorn api.main:app --host 0.0.0.0 --port 8000`
**Evidencia:** `core/http_snapshot.py:516` → `HTTPServer(("127.0.0.1", 8010), Handler)`

---

## 2. SUBSISTEMAS

### 2.1 Avolites / Titan API

**Archivos clave:**
| Archivo | Responsabilidad |
|---------|----------------|
| `avolites_config.py` (1164 líneas) | AvolitesController — orquestador principal |
| `core/transport/titan_transport.py` (455 líneas) | HTTP client con retry (3 intentos, backoff 50/100/200ms) |
| `core/transport/titan_queue.py` (970 líneas) | Cola priorizada: KILL > FIRE, rate limit 60ms, dedup 300ms |
| `core/transport/titan_sync.py` (462 líneas) | Watchdog orphan cues (poll cada 2s) — **DESACTIVADO en legacy mode** |
| `avolites_config.json` | Config: IP=192.168.0.3, port=4430, offset=169 |

**Protocolo:** HTTP GET puro (sin auth, sin POST).
```
GET /titan/script/Playbacks/FirePlaybackAtLevel?userNumber={N}&level=1.0&bool=false
GET /titan/script/Playbacks/KillPlayback?userNumber={N}
GET /titan/get/System/SoftwareVersion  (ping)
```

**Timeouts:** connect=1.0s, read=2.0s (config), connect=1.2s, read=1.0s (transport default).

**Circuit breaker:** 5 fallos en 10s → bloqueo 5s → half-open → test.
**Evidencia:** `avolites_config.py:490-535`

**Reconexión:** El circuit breaker se resetea con `_mark_success()`. No hay reconexión automática de sesión HTTP — usa `requests.Session` con keep-alive y pool de conexiones (max=4). Si cambian IP/puerto, se recrea la sesión.
**Evidencia:** `avolites_config.py:538-560` (`_setup_session`)

**Estado reportado:** `get_status()` retorna dict con: connected, circuit_breaker, version, active_cues, last_error, latency_ms, queue_stats, sync_stats.
**Evidencia:** `avolites_config.py:1024-1054`

---

### 2.2 Vision / Cámaras IP

**Archivos clave:**
| Archivo | Responsabilidad |
|---------|----------------|
| `core_vision/camera_source.py` (1640 líneas) | MJPEGSource + RTSPSource + RTSPSourcePyAV |
| `core_vision/camera_loop.py` (354 líneas) | Loop de captura por cámara (1 thread cada una) |
| `core_vision/vision_manager.py` (913 líneas) | Coordinador: 3 camera loops (haze, dj, artist) |
| `core_vision/vision_config.py` (617 líneas) | Loader de vision_config.json |
| `core_vision/yolo_roi_detector.py` (874 líneas) | YOLO V8 inference per-zone (CUDA fp16) |
| `core_vision/dj_detector.py` / `artist_detector.py` | Wrappers de YOLO + state machine por zona |
| `core_vision/camera_haze.py` | Detector de haze por contraste |
| `api_server.py` (277 líneas) | Flask API vision puerto 5000 |
| `vision_config.json` | 3 cámaras: haze, dj, artist (Axis MJPEG 192.168.1.110) |

**Motor de captura:** Tres implementaciones disponibles:
1. **MJPEGSource** — `requests.Session` con streaming HTTP, decode JPEG manual (FFD8/FFD9 markers). Buffer max 1MB.
2. **RTSPSource** — `cv2.VideoCapture` con backend FFMPEG. Buffer=1 frame.
3. **RTSPSourcePyAV** — `av.open()` con FFmpeg bindings. Opciones low-latency (nobuffer, low_delay).

**Config actual:** Las 3 cámaras están en MJPEG apuntando a `192.168.1.110` (Axis).
**Evidencia:** `vision_config.json:56-88`

**Threading:** 1 thread daemon por cámara (CameraLoop). Frame queue maxsize=1 (latest-only, drop-old).
**Evidencia:** `camera_source.py:153` (lock), `camera_source.py:470` (queue put_nowait)

**Reconexión:** Exponential backoff: `reconnect_s * 1.5^min(count, 5)`, max 10s.
**Evidencia:** `camera_source.py:355-376`

**Stall detection:** Si `frame_age > timeout_s (5.0s)`, retorna `(False, None)`.
**Evidencia:** `camera_source.py:308-317`

**YOLO:** Modelo cargado en GPU CUDA con fp16. Rate limit 6 FPS. Skip frames > 250ms old. Backoff adaptativo si inference > 250ms.
**Evidencia:** `yolo_roi_detector.py:181-227` (load), `yolo_roi_detector.py:571-596` (inference)

**Memory:** Todas las fuentes retornan `frame.copy()` en `read()`. Frames son numpy arrays (BGR uint8).
**Evidencia:** `camera_source.py:317` (MJPEG), `camera_source.py:764` (RTSP)

---

### 2.3 Audio USB

**Archivos clave:**
| Archivo | Responsabilidad |
|---------|----------------|
| `engine_audio.py` (341 líneas) | AudioEngine — capture + filter chain + ring buffers |
| `core/audio_monitor.py` (83 líneas) | Anomaly detection: silence, clipping, noise, stream_lost |
| `waveform_smooth.py` (~150 líneas) | Display de forma de onda async |
| `tempo/auto_clock.py` (~80 líneas) | Beat detection PLL (BPM lock) |
| `config/audio_monitor.json` | Thresholds: silence_rms_min=0.005, clip=0.98 |

**Motor:** `sounddevice` (v0.4.6+) → PortAudio → ALSA.
**Evidencia:** `engine_audio.py:3` → `import sounddevice as sd`

**Device:** Maono PS22 USB. Seleccionable por index. Samplerate = device default (~48kHz).
**Evidencia:** `engine_audio.py:248-250`, `scripts/bootstrap_linux.sh:468-496`

**Buffer:** blocksize=1024 samples. Ring buffer=3 segundos (3 buffers paralelos: raw_filt, raw_clean, gated).
**Evidencia:** `engine_audio.py:37-38, 54-61`

**Threading:** Callback en real-time thread de sounddevice. Lock protege buffers. Main thread lee cada 33ms (30 FPS timer).
**Evidencia:** `engine_audio.py:61` (Lock), `main.py:3864` (frame tick)

**Signal chain:** DC block (5Hz) → HP filter (10Hz) → Notch opcional (50/60Hz) → Schmitt gate (2.5x/1.6x noise floor) → Envelope (12ms attack, 180ms release).
**Evidencia:** `engine_audio.py:64-76, 90-216`

**Device lost:** NO hay recovery automático en AudioEngine. AudioMonitor detecta `stream_lost` via `engine.is_running`. La app debe hacer stop/start manual.
**Evidencia:** `core/audio_monitor.py:34-37`

**xrun detection:** NO implementado. El parámetro `status` del callback se recibe pero no se procesa activamente.
**Evidencia:** `engine_audio.py:162` — `status` no se chequea.

---

### 2.4 Web / SSE / Frontend

**Backend:**
- FastAPI en puerto 8000 con 8 routers bajo `/api/v1/`.
- SSE stream en `/api/v1/stream` — emite snapshot cada 500ms.
- Forward: `/status/unified` → CORE 8010, `/vision/*` → Flask 5000.
- SPA catch-all: cualquier ruta no-API sirve `webapp/dist/index.html`.
**Evidencia:** `api/main.py:42-49` (routers), `api/routers/status.py:240-284` (SSE)

**Frontend:**
- React 18 + Vite 5 + Tailwind CSS + Zustand.
- `Home.jsx` usa hook `useUnifiedStatus()` — SSE primario, fallback a polling 1s.
- Dashboard muestra: CPU%, RAM%, Avolites status, Audio status, 3 cámaras.
**Evidencia:** `webapp/src/pages/Home.jsx:15-111` (SSE hook), `webapp/src/pages/Home.jsx:188-439` (cards)

**Cache:** Status router cachea snapshot 100ms para evitar spam a CORE.
**Evidencia:** `api/routers/status.py:34`

---

### 2.5 Scheduler / Calendar

**Archivos:** `core/calendar/calendar_manager.py`, `core/calendar/calendar_state.py`
- Schedule semanal con bloques horarios por modo (BAJADA, BASE_GOLPE, etc.)
- Override temporario con duración configurable.
- Source of truth en CORE (8010). API solo hace proxy.
**Evidencia:** `api/routers/calendar.py:23-41` (forward), `core/http_snapshot.py:269-410` (commands)

---

## 3. FLUJOS DE DATOS

### 3.1 Audio → Cues Avolites
```
Maono USB → ALSA → PortAudio → sounddevice callback (RT thread)
  → ring buffers (raw_filt, raw_clean, gated)
  → frame_tick cada 33ms lee 0.25s de audio
  → módulos de análisis (energía, BPM, thresholds)
  → CueEngine decide fire/kill
  → AvolitesController.fire_cue(N)
  → TitanQueue (prioridad, rate limit, dedup)
  → TitanTransport HTTP GET → Avolites Titan 192.168.0.3:4430
```

### 3.2 Cámaras → Detección → Cues
```
Cámara IP Axis 192.168.1.110 (MJPEG HTTP stream)
  → MJPEGSource (thread daemon, decode JPEG)
  → CameraLoop._read_frame() → frame queue (maxsize=1)
  → HazeDetector / DJDetector / ArtistDetector
  → YoloRoiDetector (CUDA fp16, per-zone ROI)
  → VisionEngine state machine (zone ON/OFF)
  → FamilyManager.fire(cue_id)
  → AvolitesController → Titan
```

### 3.3 Status → Frontend
```
CORE (main.py) → http_snapshot.get_snapshot()
  → agrupa: state, energy, audio, avolites, cameras, calendar, system
  → HTTPServer 127.0.0.1:8010 /core/snapshot

FastAPI status.py → _fetch_core_snapshot() via httpx
  → cache 100ms
  → SSE stream cada 500ms

React Home.jsx → EventSource(/api/v1/stream)
  → useUnifiedStatus() hook
  → render dashboard cards
```

---

## 4. RIESGOS Y PUNTOS DE FALLA POR SUBSISTEMA

### 4.1 Cámaras (RIESGO ALTO — falló ayer)

| Riesgo | Severidad | Evidencia |
|--------|-----------|-----------|
| **Thread blocking en read()** — Si MJPEG stream se congela, el thread queda bloqueado en `iter_content()`. Stall detection existe (5s) pero no mata el thread. | P0 | `camera_source.py:308-317` |
| **Sin watchdog de proceso** — No hay timer externo que verifique si el thread de cámara sigue vivo y produciendo frames. | P0 | Ausencia en `camera_loop.py` |
| **Reconexión sin límite** — El backoff es exponencial pero resetea después de `max_reconnect_attempts=3`. Puede generar cycles infinitos. | P1 | `camera_loop.py:199-232` |
| **Memory leak potencial** — Frame copy en cada `read()` genera nuevo numpy array. Si el consumer es lento, arrays se acumulan. | P1 | `camera_source.py:317` |
| **GPU starvation** — Si 3 YOLO inferences corren simultáneamente a 6 FPS cada una, la 1080 Ti puede saturarse. | P1 | `yolo_roi_detector.py:571-596` |
| **Todas las cámaras apuntan a la misma IP** — Si 192.168.1.110 cae, las 3 fallan juntas. | P1 | `vision_config.json:59,70,81` |

### 4.2 Avolites (RIESGO MEDIO)

| Riesgo | Severidad | Evidencia |
|--------|-----------|-----------|
| **Circuit breaker abierto = sin luces 5s** — En pico de fallos, 5 segundos sin poder enviar. | P1 | `avolites_config.py:490-520` |
| **Sin SSL verify** — `verify=False` en requests. Aceptable en LAN pero riesgo si la red es compartida. | P2 | `core/transport/titan_transport.py:131` |
| **TitanSync desactivado** — En legacy mode, no hay detección de orphan cues. Si un KILL falla, el cue queda activo en la consola. | P1 | `avolites_config.py:1064-1068` |
| **Queue full → FIRE dropped** — Si la cola se llena (512), los FIRE se dropean para hacer espacio a KILLs. | P2 | `core/transport/titan_queue.py:273-320` |

### 4.3 Audio (RIESGO BAJO-MEDIO)

| Riesgo | Severidad | Evidencia |
|--------|-----------|-----------|
| **Sin recovery automático de device** — Si el USB se desconecta, AudioEngine se para y no vuelve sin intervención manual. | P1 | `core/audio_monitor.py:34-37` |
| **xruns no detectados** — Dropouts de audio no se registran. | P2 | `engine_audio.py:162` |
| **Lock contention** — Si frame_tick tarda en procesar, el callback de audio espera el lock. Riesgo bajo pero real. | P2 | `engine_audio.py:61, 94, 220` |

### 4.4 Web / SSE (RIESGO BAJO)

| Riesgo | Severidad | Evidencia |
|--------|-----------|-----------|
| **SSE sin backpressure** — Si el cliente no consume, el generator sigue produciendo. Asyncio maneja esto bien, pero muchos clientes = mucha CPU. | P2 | `api/routers/status.py:240-261` |
| **CORS allow all origins** — Cualquier sitio puede hacer requests al API. Aceptable en LAN. | P2 | `api/main.py:33-39` |

### 4.5 Observabilidad (RIESGO ALTO)

| Riesgo | Severidad | Evidencia |
|--------|-----------|-----------|
| **Health endpoint trivial** — `/health` solo retorna `{"status":"ok"}`. No verifica nada real. | P0 | `api/main.py:130-147` |
| **System metrics incompletos** — Solo CPU% y RAM% via psutil. Falta: GPU temp/util/mem, disco, red, latencia. | P0 | `core/http_snapshot.py:206-212` |
| **Sin ring buffer de errores** — Los errores se imprimen a stdout/journal pero no hay buffer en memoria consultable vía API. | P1 | Ausencia general |
| **Sin métricas de cámaras individuales** — El snapshot muestra online/fps pero no: drops, reconnects, stalls, frame age, YOLO latency. | P1 | `core/http_snapshot.py:141-161` |
| **Sin métricas de red** — No hay tracking de latencia al gateway, interfaces activas, bytes in/out. | P1 | Ausencia en snapshot |

---

## 5. QUÉ MIDE HOY EL HEALTH Y QUÉ FALTA

### HOY mide:

| Métrica | Fuente | Endpoint |
|---------|--------|----------|
| CPU % | psutil | `/core/snapshot` → system.cpu |
| RAM % | psutil | `/core/snapshot` → system.ram |
| Audio running / level / silence / clipping | AudioEngine + AudioMonitor | `/core/snapshot` → audio |
| Avolites connected / IP / port / latency / last_error | AvolitesController.get_status() | `/core/snapshot` → avolites |
| Cámaras online / fps / IP (por handler) | VisionManager handlers | `/core/snapshot` → cameras |
| Calendar mode / next / override | CalendarManager | `/core/snapshot` → calendar |
| Core online | StateManager != None | `/core/snapshot` → core.online |

### FALTA (crítico):

| Métrica | Por qué importa |
|---------|-----------------|
| **GPU temp / utilization / memory** | La 1080 Ti corre YOLO. Throttling = cámaras freezan. |
| **GPU power draw** | Detectar si la GPU está en idle vs full load. |
| **Disk usage** | Logs pueden llenar disco. |
| **Network interfaces / latency** | Detectar si la red está caída antes de que todo falle. |
| **Audio device name real** | Saber si el Maono PS22 está conectado o si agarró otro device. |
| **Audio xruns / dropouts** | Glitches de audio que afectan detección de BPM. |
| **Camera drops / reconnects / stalls** | Diagnóstico de la falla de ayer. |
| **Camera YOLO inference time** | Saber si GPU está saturada. |
| **Avolites queue depth / drops** | Saber si hay backpressure en la cola de cues. |
| **Error ring buffer** | Ver últimos N errores sin ir a journalctl. |
| **Process uptime / restarts** | Saber si el servicio se reinició. |
| **Open file descriptors** | Leak de FDs = crash eventual. |

---

## 6. EVIDENCIA — ARCHIVOS CLAVE REFERENCIADOS

| Archivo | Líneas clave | Referenciado en |
|---------|--------------|-----------------|
| `systemd/911fiesta.service` | 45 (ExecStart) | Sección 1 |
| `core/http_snapshot.py` | 26-27, 63-234, 516 | Sección 1, 5 |
| `api/main.py` | 26-49, 56-119, 130-147 | Sección 2.4, 4.5 |
| `api/routers/status.py` | 29-60, 226-284 | Sección 2.4 |
| `avolites_config.py` | 202-289, 490-535, 538-560, 623-644, 840-984, 1024-1054 | Sección 2.1 |
| `core/transport/titan_transport.py` | 48-58, 154-218, 340-358 | Sección 2.1 |
| `core/transport/titan_queue.py` | 81-148, 324-555, 699-842 | Sección 2.1 |
| `core/transport/titan_sync.py` | 38-61, 176-355 | Sección 2.1 |
| `avolites_config.json` | 2-9 | Sección 2.1 |
| `core_vision/camera_source.py` | 91-530, 532-1017, 1019-1482, 1552-1641 | Sección 2.2 |
| `core_vision/camera_loop.py` | 24-355 | Sección 2.2 |
| `core_vision/vision_manager.py` | All | Sección 2.2 |
| `core_vision/yolo_roi_detector.py` | 181-227, 434-444, 571-596 | Sección 2.2 |
| `vision_config.json` | 56-88 | Sección 2.2 |
| `engine_audio.py` | 3, 37-38, 54-61, 64-76, 90-216, 248-250, 276-287 | Sección 2.3 |
| `core/audio_monitor.py` | 16-19, 28-74 | Sección 2.3 |
| `waveform_smooth.py` | 13, 52-68 | Sección 2.3 |
| `tempo/auto_clock.py` | 26-80 | Sección 2.3 |
| `config/audio_monitor.json` | All | Sección 2.3 |
| `webapp/src/pages/Home.jsx` | 15-111, 188-439 | Sección 2.4 |
| `webapp/src/store/useSystemStore.js` | All | Sección 2.4 |
| `scripts/healthcheck_911fiesta.sh` | All | Sección 5 |
| `scripts/bootstrap_linux.sh` | 131-150, 253-255, 468-496 | Sección 2.3 |

---

## 7. NOTA SOBRE ENTORNO DE AUDITORÍA

> **IMPORTANTE:** Esta auditoría de código fue realizada en un entorno de desarrollo
> (contenedor sin systemd, sin GPU, sin hardware real). Los datos de runtime
> (systemctl, nvidia-smi, journalctl, etc.) NO están disponibles aquí.
>
> Para obtener datos reales del server, ejecutar:
> - `tools/audit/collect_system_snapshot.sh`
> - `tools/audit/collect_runtime_probe.py`
>
> Ver: `docs/audit/RUNBOOK_AUDIT_RUNTIME.md`

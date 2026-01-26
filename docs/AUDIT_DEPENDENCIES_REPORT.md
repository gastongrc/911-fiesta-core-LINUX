# Mega Audit de Dependencias - 911 Fiesta V7

## Resumen Ejecutivo

**Fecha:** 2026-01-26
**Branch:** `claude/audit-dependencies-i8AJ7`

### Problemas Detectados en requirements.txt Original

| Problema | Severidad | Accion |
|----------|-----------|--------|
| Rutas `file:///` (aubio, PyYAML, pyqtgraph) | CRITICO | Eliminar - no reproducible |
| PyQt5 + PySide6 juntos | CRITICO | Eliminar PyQt5 - conflicto Qt |
| TensorFlow/Keras sin uso real | ALTO | Eliminar - no hay imports |
| customtkinter, dearpygui sin uso | MEDIO | Eliminar - no hay imports |
| Paquetes duplicados/legacy | MEDIO | Eliminar |

---

## A) Inventario Real de Dependencias

### Runtime SHOW (UI + Core + Vision + Audio)

| Paquete | Donde se usa | Motivo | Notas |
|---------|--------------|--------|-------|
| **PySide6** | ui/*.py, main.py, analyzers/waveform_widget.py | Framework UI Qt | UNICO framework Qt permitido |
| **numpy** | 60+ archivos (core, analyzers, vision, tempo) | Arrays/DSP | Core dependency |
| **opencv-python** | core_vision/*.py, sensors/*.py, ui/vision_*.py | Captura video | opencv-python-headless en server |
| **sounddevice** | engine_audio.py, main.py | Captura audio | Requiere PortAudio |
| **torch** | core_vision/yolo_roi_detector.py | Backend YOLO | GPU requerido para perf |
| **ultralytics** | core_vision/yolo_roi_detector.py | YOLOv8 detection | Descarga modelo auto |
| **pyqtgraph** | ui/bpm_master_tab.py, analyzers/super_analyzer.py | Graficos real-time | Requiere PyQt/PySide |
| **librosa** | analyzers/bpm_detector.py | Analisis audio | Carga diferida |
| **scipy** | analyzers/rhythm_highlighter.py, tempo/auto_clock.py | Signal processing | scipy.signal |
| **requests** | avolites_config.py, core/transport/titan_transport.py | HTTP Avolites | + urllib3 |
| **av** | core_vision/camera_source.py | Decode RTSP/streams | PyAV |
| **psutil** | main.py | Monitor sistema | Opcional |

### Runtime SERVER (FastAPI)

| Paquete | Donde se usa | Motivo |
|---------|--------------|--------|
| **fastapi** | api/main.py, api/routers/*.py | Framework API |
| **uvicorn** | api/main.py | ASGI server |
| **pydantic** | api/models.py, api/routers/alerts.py | Validacion datos |

### Desarrollo (DEV)

| Paquete | Motivo |
|---------|--------|
| **pytest** | Testing |
| **pip-tools** | Lock de dependencias |

---

## B) Lista Negra - Paquetes a ELIMINAR

### Conflictos Directos (ELIMINAR OBLIGATORIO)

| Paquete | Razon |
|---------|-------|
| PyQt5 | Conflicto con PySide6 |
| PyQt5-Qt5 | Conflicto con PySide6 |
| PyQt5-sip | Conflicto con PySide6 |
| pyqt5-plugins | Conflicto con PySide6 |
| pyqt5-tools | Conflicto con PySide6 |
| qt5-applications | Conflicto con PySide6 |
| qt5-tools | Conflicto con PySide6 |
| PyQtDarkTheme | Para PyQt5, no PySide6 |

### Sin Uso Real (NO HAY IMPORTS)

| Paquete | Evidencia |
|---------|-----------|
| tensorflow | 0 imports encontrados |
| tf_keras | 0 imports encontrados |
| keras | 0 imports encontrados |
| tensorboard | Solo TF |
| tensorboard-data-server | Solo TF |
| tensorflow-hub | Solo TF |
| tensorflow-io-gcs-filesystem | Solo TF |
| customtkinter | 0 imports encontrados |
| dearpygui | 0 imports encontrados |
| aubio | 0 imports + ruta file:/// |
| Js2Py | 0 imports encontrados |
| pyjsparser | Dependencia Js2Py |
| keyboard | 0 imports encontrados |
| sacn | 0 imports encontrados |
| pyartnet | 0 imports encontrados |
| python_artnet | 0 imports encontrados |
| numba | 0 imports encontrados |
| llvmlite | Dependencia numba |
| pandas | 0 imports encontrados |
| matplotlib | 0 imports encontrados |
| rich | 0 imports encontrados |
| scikit-learn | 0 imports encontrados |
| soundfile | 0 imports encontrados |
| colorama | 0 imports encontrados |
| beautifulsoup4 | 0 imports encontrados |
| soupsieve | Dependencia bs4 |
| pipwin | Tool Windows, no runtime |
| pySmartDL | 0 imports encontrados |
| PyPrind | 0 imports encontrados |
| docopt | 0 imports encontrados |

### Rutas Locales (NO REPRODUCIBLE)

| Paquete | Problema |
|---------|----------|
| aubio @ file:///D:/... | Ruta Windows local |
| PyYAML @ file:///D:/... | Ruta Windows local |
| pyqtgraph @ file:///home/... | Ruta Linux local |

---

## C) Arquitectura de Requirements

```
requirements/
  show.in          # Alto nivel, humano - SHOW runtime
  show.lock.txt    # Freeze exacto pip - SHOW
  server.in        # Alto nivel - SERVER runtime
  server.lock.txt  # Freeze exacto pip - SERVER
  dev.in           # Desarrollo/testing
```

### Comandos para Regenerar Locks

```bash
# Requiere pip-tools instalado
pip install pip-tools

# Generar show.lock.txt desde show.in
pip-compile requirements/show.in -o requirements/show.lock.txt --resolver=backtracking

# Generar server.lock.txt desde server.in
pip-compile requirements/server.in -o requirements/server.lock.txt --resolver=backtracking
```

---

## D) Separacion SHOW vs SERVER

### SHOW (UI Principal)
- PySide6 + pyqtgraph (UI)
- torch + ultralytics (YOLO GPU)
- opencv-python (video)
- sounddevice + librosa + scipy (audio)
- numpy, requests, av, psutil

### SERVER (API headless)
- fastapi + uvicorn + pydantic
- NO requiere Qt, torch, audio libs
- Puede correr en container Linux

### Compartidos
- numpy (ambos)
- requests (si server necesita llamar Titan)

---

## E) Notas de Compatibilidad

### Windows NVIDIA GPU
- torch debe instalarse desde index especial PyTorch
- Requiere CUDA toolkit compatible
- ultralytics descarga modelo yolov8n.pt automaticamente

### OpenCV
- `opencv-python` para SHOW (con GUI)
- `opencv-python-headless` para SERVER (sin GUI, mas liviano)

### PySide6 vs PyQt5
- SOLO PySide6 permitido
- pyqtgraph 0.13.7+ soporta PySide6
- No mezclar PyQt5 en el entorno

### Audio en Windows
- sounddevice requiere PortAudio
- Incluido en wheel de Windows

---

## F) Validacion

### Smoke Tests
- `scripts/smoke_show.py` - Valida SHOW runtime
- `scripts/smoke_server.py` - Valida SERVER runtime

### Criterios de Aceptacion
1. `pip install -r requirements/show.lock.txt` OK en env limpio
2. `python scripts/smoke_show.py` retorna OK
3. `pip install -r requirements/server.lock.txt` OK
4. `python scripts/smoke_server.py` retorna OK

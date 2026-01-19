# Auditoría: Remoción USB + Estabilización HAZE

## Fecha: 2026-01-10
## Branch: claude/add-ip-camera-support-hhD4w

---

## 1. INVENTARIO USB/LEGACY

### 1.1 Archivos con código USB activo (DEBE ELIMINARSE)

| Archivo | Líneas | Símbolos USB |
|---------|--------|--------------|
| `core_vision/camera_source.py` | 79-201 | `class USBSource`, `cv2.VideoCapture`, `CAP_DSHOW`, `device_index` |
| `core_vision/camera_loop.py` | 331-349 | USB fallback en `_open_camera()`, `CAP_DSHOW`, `camera_index` |
| `core_vision/vision_config.py` | 127-165, 470-497, 552-565 | `type: usb`, `device_index`, `_migrate_legacy_to_cameras()`, `_get_legacy_usb_config()` |
| `core_vision/vision_manager.py` | 85-88, 566-596, 411-479 | `camera_*_index`, `set_camera_*_index()`, `validate_camera_indices()`, `_fix_camera_index_collision()` |
| `core_vision/vision_state.py` | 31, 65-68, 190-193, 233 | `camera_index` state |

### 1.2 UI con controles USB legacy (DEBE ELIMINARSE)

| Archivo | Líneas | Controles USB |
|---------|--------|---------------|
| `ui/vision_haze_tab.py` | 439-467 | `camera_combo`, `camera_haze_index`, `set_camera_haze_index()` |
| `ui/vision_dj_tab.py` | 276-334 | `camera_combo`, `camera_dj_index`, `set_camera_dj_index()` |
| `ui/vision_artist_tab.py` | 324-367 | `camera_combo`, `camera_artist_index`, `set_camera_artist_index()` |
| `ui/vision_tab.py` | 1088-1102 | `camera_*_combo`, `set_camera_*_index()` |

### 1.3 Archivos de configuración

| Archivo | Keys USB |
|---------|----------|
| `vision_config.json` | `camera_dj_index: 1`, `camera_index: 2`, `camera_artist_index: 2` |

### 1.4 Factory function (DEBE MODIFICARSE)

```python
# core_vision/camera_source.py:571
source_type = config.get("type", "usb").lower()  # DEFAULT ES USB!

if source_type == "usb":
    return USBSource(...)  # ESTO DEBE ELIMINARSE
```

---

## 2. FLUJO ACTUAL (CON USB FALLBACK)

```
vision_config.json
       │
       ▼
VisionConfig._ensure_cameras_structure()
       │
       ├─ ip_only=true? → crear MJPEG defaults (host=0.0.0.0)
       │
       └─ ip_only=false? → _migrate_legacy_to_cameras() → type="usb"
              │
              ▼
VisionManager._create_camera_source()
       │
       ├─ config.get_camera_source_config()
       │      │
       │      └─ cam_type == "usb"? → return USB config
       │
       ├─ create_source_from_config()
       │      │
       │      └─ source_type == "usb"? → return USBSource()  ← PROBLEMA
       │
       └─ source_type == "usb" && ip_only? → BLOCKED (pero ya creó!)

CameraLoop._open_camera()
       │
       ├─ self.source existe? → source.start()
       │
       └─ self.source = None?
              │
              ├─ ip_only=true? → BLOCKED, return False
              │
              └─ ip_only=false? → cv2.VideoCapture(index, CAP_DSHOW)  ← USB FALLBACK
```

**PROBLEMA IDENTIFICADO**: Aunque `ip_only=true`, el código aún:
1. Tiene rutas que crean USBSource
2. Tiene fallback USB en CameraLoop
3. Mantiene `camera_*_index` en config que pueden activarse

---

## 3. ANÁLISIS DEL CRASH HAZE

### 3.1 Stack del crash

```
Fatal Python error: Aborted
Thread MJPEGSource bloqueado en socket.readinto -> urllib3/requests stream
Archivo: core_vision/camera_source.py
  _capture_loop (line ~346)
  _connect_and_stream (line ~392)

QThreadStorage: entry destroyed before end of thread
Windows fatal exception: access violation
```

### 3.2 Causa raíz #1: numpy.std() desde thread

**Ubicación**: `core_vision/camera_haze.py:103`

```python
contrast = float(np.std(gray.astype(np.float32)))
```

**Problema**:
- `np.std()` en arrays grandes puede activar BLAS/LAPACK multithreading
- Cuando se llama desde un thread de cámara junto con Qt, causa conflictos de memoria
- El `gray.astype(np.float32)` crea una copia que añade presión de memoria

**También en**: `core_vision/haze_detector.py:94`

### 3.3 Causa raíz #2: UI update desde thread

**Ubicación**: `core_vision/camera_loop.py:263`

```python
if self.frame_callback:
    self.frame_callback(frame)  # Llamado desde thread de cámara!
```

**Problema**:
- El callback llama directamente a métodos UI (QPixmap, setPixmap)
- Qt widgets solo pueden modificarse desde main thread
- Causa "access violation" y "QThreadStorage destroyed"

### 3.4 Causa raíz #3: MJPEG threads no se detienen

**Problema**: `iter_content()` puede bloquear indefinidamente
- Cuando se cierra la app, los threads MJPEG siguen vivos
- Qt intenta destruir objetos mientras threads aún los usan

---

## 4. PLAN DE CORRECCIÓN

### FASE 1: Eliminar USB completamente

1. **camera_source.py**:
   - Eliminar clase `USBSource` (líneas 79-201)
   - Factory solo acepta "mjpeg", raise error si otro tipo

2. **camera_loop.py**:
   - Eliminar USB fallback en `_open_camera()` (líneas 326-349)
   - Eliminar `camera_index`, `set_camera_index()`
   - Si no hay source → log + return False (sin intentar USB)

3. **vision_config.py**:
   - Eliminar `_migrate_legacy_to_cameras()`
   - Eliminar `_get_legacy_usb_config()`
   - Eliminar referencias a `camera_*_index`
   - Defaults: solo MJPEG con host=0.0.0.0, enabled=false

4. **vision_manager.py**:
   - Eliminar `set_camera_*_index()` métodos
   - Eliminar `validate_camera_indices()`, `_fix_camera_index_collision()`
   - Eliminar lectura de `camera_*_index` de config

5. **UI tabs**:
   - Eliminar camera_combo en vision_haze_tab, vision_dj_tab, vision_artist_tab
   - Eliminar `_on_camera_changed()` métodos

6. **vision_config.json**:
   - Eliminar `camera_index`, `camera_dj_index`, `camera_artist_index`

### FASE 2: Fix crash HAZE

1. **camera_haze.py:103** y **haze_detector.py:94**:
   ```python
   # ANTES (peligroso):
   contrast = float(np.std(gray.astype(np.float32)))

   # DESPUÉS (thread-safe):
   _, stddev = cv2.meanStdDev(gray)
   contrast = float(stddev[0][0])
   ```

2. **vision_haze_tab.py**: Ya tiene thread-safe frame buffer (implementado)

3. **MJPEGSource.stop()**: Ya tiene timeout robusto (implementado)

### FASE 3: Shutdown determinístico

1. Conectar `app.aboutToQuit` a `vision_manager.shutdown()`
2. `shutdown()` debe: stop() + join() todos los threads
3. Verificar que al cambiar tabs NO recrea sources

---

## 5. CHECKLIST DE VERIFICACIÓN POST-FIX

- [ ] `grep -r "USBSource" core_vision/` → 0 resultados
- [ ] `grep -r "CAP_DSHOW" core_vision/` → 0 resultados
- [ ] `grep -r "VideoCapture(" core_vision/` → 0 resultados
- [ ] `grep -r "camera_index" core_vision/` → 0 resultados (excepto comments)
- [ ] `grep -r "device_index" core_vision/` → 0 resultados
- [ ] `grep -r "np.std" core_vision/` → 0 resultados
- [ ] Entrar/salir HAZE 50x sin crash
- [ ] Apply config 20x sin leak threads
- [ ] Cerrar app sin warnings QThreadStorage

---

## 6. ESTRUCTURA OBJETIVO (POST-FIX)

```
vision_config.json
       │
       ▼
VisionConfig (ip_only siempre true)
       │
       └─ cameras:
            haze: {type: mjpeg, host: X, enabled: bool}
            dj: {type: mjpeg, host: X, enabled: bool}
            artist: {type: mjpeg, host: X, enabled: bool}
              │
              ▼
VisionManager._create_camera_source()
       │
       ├─ host válido + enabled? → MJPEGSource
       │
       └─ no válido/disabled? → None (skip, log)
              │
              ▼
CameraLoop
       │
       ├─ source != None? → start capture
       │
       └─ source == None? → NOT STARTED (no USB, no fallback)
```

**ZERO USB CODE PATHS**

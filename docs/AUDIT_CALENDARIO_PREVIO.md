# AUDITORÍA PREVIA — CALENDARIO / MODOS / TIMERS

**Fecha:** 2025-12-16
**Branch:** claude/musical-analysis-audit-6WtQD
**Objetivo:** Detectar código existente relacionado con calendario antes de crear CalendarManager

---

## 1. ARCHIVOS ENCONTRADOS

### 1.1 Archivos con nombre relacionado

| Archivo | Propósito | Importado | Ejecutado | Clasificación |
|---------|-----------|-----------|-----------|---------------|
| `timers.py` | QTimers de UI (VU, scope, etc.) | ✅ Sí (main.py) | ✅ Sí | ✔️ **ÚTIL** — No relacionado con calendario |
| `api/models.py` | Modelos Pydantic API | ✅ Sí | ✅ Sí | ✔️ **ÚTIL** — Contiene "mode" en nombre pero no de calendario |

### 1.2 Código que menciona "calendar"

| Archivo | Líneas | Contenido | Clasificación |
|---------|--------|-----------|---------------|
| `core_vision/vision_manager.py` | 109-113, 541-558 | `mode_calendar`, `set_calendar_mode()`, `get_calendar_mode()` | ⚠️ **STUB** — Esperando integración |
| `core_vision/camera_tracking.py` | 90-92, 112-113, 249-257 | `mode_show_artist` flag | ⚠️ **STUB** — Depende de VisionManager |
| `core_vision/haze_detector.py` | 203-206 | `disable_by_mode()` | ⚠️ **STUB** — Depende de calendar mode |
| `ui/vision_tab.py` | 811, 1294-1304 | ComboBox calendario manual | ✔️ **UI MANUAL** — Control manual |
| `ui/vision_artist_tab.py` | 225, 370-373 | ComboBox calendario manual | ✔️ **UI MANUAL** — Control manual |

---

## 2. MODOS YA DEFINIDOS (STRINGS QUEMADOS)

En `core_vision/vision_manager.py` L111, L376, L546:

```python
# Valores actualmente usados:
"OFF"       # Default
"ARTISTA"   # Activa tracking de artista
"TEATRO"    # Desactiva haze detector
"BOLICHE"   # Modo boliche (no implementado)
"ESCENA"    # Desactiva haze detector
"CLIMA"     # Desactiva haze detector
```

**⚠️ RIESGO:** Estos strings están hardcodeados. Un CalendarManager debería usar los MISMOS valores o habrá inconsistencia.

---

## 3. LÓGICA DE MODO ACTUAL (SIN CALENDARIO)

### Flujo actual (MANUAL):

```
┌─────────────────────────────────────────────────────────────┐
│ UI (vision_tab.py / vision_artist_tab.py)                   │
│   ComboBox: ["OFF", "ARTISTA", "TEATRO", "BOLICHE"]         │
│   Usuario selecciona manualmente                            │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ VisionManager.set_calendar_mode(mode: str)                  │
│   self.mode_calendar = mode                                 │
│   self.mode_show_artist = (mode == "ARTISTA")               │
│   self.artist_tracker.set_mode_show_artist(...)             │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ ArtistTracker / HazeDetector                                │
│   Respetan mode_show_artist flag                            │
│   HazeDetector.disable_by_mode() si modo restrictivo        │
└─────────────────────────────────────────────────────────────┘
```

### Lo que FALTA (CalendarManager):

```
┌─────────────────────────────────────────────────────────────┐
│ CalendarManager (NO EXISTE)                                 │
│   - Leer hora actual                                        │
│   - Comparar con schedule definido                          │
│   - Llamar VisionManager.set_calendar_mode() automáticamente│
│   - NO EXISTE NINGÚN CÓDIGO QUE HAGA ESTO                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. FLAGS Y VARIABLES RELACIONADAS

### 4.1 En VisionManager (`core_vision/vision_manager.py`)

| Variable | Línea | Default | Propósito |
|----------|-------|---------|-----------|
| `mode_calendar` | 112 | `"OFF"` | Modo actual (string) |
| `mode_show_artist` | 113 | `False` | Flag derivado (True si ARTISTA) |

### 4.2 En VisionState (`core_vision/vision_state.py`)

| Variable | Línea | Default | Propósito |
|----------|-------|---------|-----------|
| `system_enabled` | 30 | `False` | Enable/disable de cámaras |

**Nota:** `system_enabled` es para el sistema de visión, NO para el sistema global de 911 Fiesta.

### 4.3 En ArtistTracker (`core_vision/camera_tracking.py`)

| Variable | Línea | Default | Propósito |
|----------|-------|---------|-----------|
| `mode_show_artist` | 92 | `False` | Copia del flag de VisionManager |

---

## 5. CÓDIGO HUÉRFANO / LEGACY

| Hallazgo | Ubicación | Detalle |
|----------|-----------|---------|
| ✅ **NO hay imports huérfanos** | - | No hay `import calendar_manager` ni similar |
| ✅ **NO hay archivos abandonados** | - | No hay `calendar*.py` olvidados |
| ✅ **NO hay timers de horario** | - | `timers.py` es solo para UI refresh |
| ⚠️ **Stubs esperando integración** | core_vision | `set_calendar_mode()` existe pero nadie lo llama automáticamente |

---

## 6. REFERENCIAS EN DOCUMENTACIÓN

### ROADMAP.md (línea 52)

```markdown
- [ ] Pestañas:
  - Estado general
  - Configuración de red
  - Analizadores / calibración
  - Backup & Licencia
  - Calendario / programación  ← MENCIONADO COMO UI, NO BACKEND
```

**Observación:** El ROADMAP menciona "Calendario / programación" como parte de la WebApp (Fase 3), pero como UI, no como lógica de backend. No hay diseño previo de CalendarManager.

---

## 7. NOMBRES "QUEMADOS" — NO REUTILIZAR

Para evitar colisiones, estos nombres YA están en uso:

| Nombre | Dónde | Usar para CalendarManager? |
|--------|-------|---------------------------|
| `mode_calendar` | VisionManager | ❌ NO — Ya existe como string |
| `set_calendar_mode()` | VisionManager | ✅ SÍ — Interfaz existente |
| `get_calendar_mode()` | VisionManager | ✅ SÍ — Interfaz existente |
| `mode_show_artist` | VisionManager, ArtistTracker | ❌ NO — Flag derivado |
| `system_enabled` | VisionState | ❌ NO — Es de visión, no global |
| `timers.py` | Root | ❌ NO — Ya existe para QTimers |

### Nombres SEGUROS para usar:

```
CalendarManager       ← ✅ LIBRE
calendar_manager.py   ← ✅ LIBRE
ShowSchedule          ← ✅ LIBRE
TimeSlot              ← ✅ LIBRE
show_schedule.json    ← ✅ LIBRE
set_show_mode()       ← ✅ LIBRE (si es para algo diferente)
global_enable         ← ✅ LIBRE (no existe)
master_mode           ← ✅ LIBRE
```

---

## 8. RIESGOS DE COLISIÓN

### 8.1 Riesgo BAJO — Colisión de nombres

El código existente usa `set_calendar_mode(mode: str)` que espera strings específicos. Un nuevo CalendarManager debería:
- ✅ Usar la misma interfaz `set_calendar_mode()`
- ✅ Usar los mismos strings de modo ("OFF", "ARTISTA", "TEATRO", "BOLICHE")
- ❌ NO crear nueva interfaz paralela

### 8.2 Riesgo BAJO — Conflicto de archivos

No hay archivo `calendar_manager.py` ni similar. Crear uno nuevo es seguro.

### 8.3 Riesgo MEDIO — Inconsistencia de modos

Los modos están hardcodeados como strings en múltiples lugares:
- `vision_manager.py` L111, L376, L546
- `vision_tab.py` L811
- `vision_artist_tab.py` L225

**Recomendación:** Definir modos como `Enum` en un solo lugar.

---

## 9. CONCLUSIÓN Y RECOMENDACIONES

### ✅ SE PUEDE CREAR CalendarManager

No hay código previo de CalendarManager. Solo existen:
- Stubs en VisionManager esperando ser llamados
- UI manual que usa los mismos stubs

### 📋 ANTES DE IMPLEMENTAR

1. **Definir modos como Enum** (evitar strings sueltos)
   ```python
   # Crear: calendar_modes.py
   class CalendarMode(str, Enum):
       OFF = "OFF"
       ARTISTA = "ARTISTA"
       TEATRO = "TEATRO"
       BOLICHE = "BOLICHE"
       ESCENA = "ESCENA"
       CLIMA = "CLIMA"
   ```

2. **Reutilizar interfaz existente**
   - CalendarManager debe llamar a `VisionManager.set_calendar_mode()`
   - NO crear interfaz paralela

3. **Archivo nuevo seguro**
   - `calendar_manager.py` en root o en `services/`

4. **NO tocar**
   - `timers.py` — No tiene nada que ver con calendario
   - `mode_show_artist` — Es flag derivado, no fuente

### 📊 RESUMEN

| Aspecto | Estado |
|---------|--------|
| CalendarManager existente | ❌ NO EXISTE |
| Archivos de calendario | ❌ NO EXISTEN |
| Código muerto/legacy | ❌ NO HAY |
| Stubs esperando integración | ✅ SÍ (VisionManager) |
| Riesgo de colisión | 🟡 BAJO (usar misma interfaz) |
| Nombres bloqueados | `mode_calendar`, `set_calendar_mode` (ya usados) |
| Nombres seguros | `CalendarManager`, `calendar_manager.py`, `ShowSchedule` |

---

*Auditoría completada — Campo libre para CalendarManager*

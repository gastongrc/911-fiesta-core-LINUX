# Auditoría v6.4 — Estado Real + Plan de Cierre

**Fecha:** 2025-12-28
**Rama:** `claude/calendar-multi-action-editor-uV2nz`

---

## 1. Contrato Calendario — Confirmado ✅

### Ubicación: `core/calendar/calendar_rules.py`

```python
CANONICAL_MODULES = [
    "audio_engine", "vision_haze", "vision_dj", "vision_artista",
    "tracking_cam", "dj_detection", "cues_clima", "system_idle"
]

CALENDAR_RULES = {
    "clima_1": {..., "cues_clima": True, ...},
    "boliche_inicio": {"audio_engine": False, ...},  # TODO: audio suave?
    "boliche_desarrollo": {"audio_engine": True, "vision_haze": True, ...},
    ...
}
```

### Consumo Real del Contrato

| Archivo | Línea | Uso |
|---------|-------|-----|
| `core/system_bridge.py` | 172-173 | `get_permissions()` + `merge_permissions_with_actions()` |
| `core/system_bridge.py` | 197-239 | `_apply_modules()` — habilita/deshabilita componentes |
| `core/calendar/calendar_manager.py` | 335 | `get_permissions()` para estado actual |
| `ui/calendar_tab.py` | 1034-1035 | UI muestra módulos por modo |
| `core_vision/vision_manager.py` | 161 | Lee permisos del calendario |

### ¿Se usa `merge_permissions_with_actions()`?

**SÍ.** En `core/system_bridge.py:173`:
```python
base_modules = get_permissions(base_mode)
modules = merge_permissions_with_actions(base_modules, actions)
```

Esto permite que acciones (ej: `vision_dj`) se sumen al modo base.

### Gap: `boliche_inicio` — ¿Audio suave o OFF total?

**Estado actual:** `audio_engine: False` (todo OFF)

**Opciones:**
1. **Mantener OFF** — "boliche vacío" = silencio total. ✅ Válido.
2. **Audio suave** — Solo bajada/basegolpe, sin ataque/brake.

**Propuesta:** Agregar `audio_profile` opcional sin romper contrato booleano:

```python
# NO cambiar audio_engine: False/True
# Agregar metadata por modo (sin afectar lógica existente)
MODE_METADATA = {
    "boliche_inicio": {
        "energy_cap": "low",  # Limita a BAJA (opcional)
        "allowed_states": ["BAJADA", "BASE_GOLPE"],  # Si audio ON
    },
    ...
}
```

**Decisión requerida:** ¿`boliche_inicio` debe tener audio suave o silencio?

---

## 2. Wiring Real — Confirmado ✅

### Flujo de Permisos

```
CalendarManager.get_permissions()
        ↓
SystemBridge.apply_mode(mode, actions)
        ↓
merge_permissions_with_actions(base, actions)
        ↓
_apply_modules(modules)
        ↓
├── AudioEngine.set_enabled(bool)
├── CueEngine.set_disabled_states([])
├── VisionManager.enable_module("haze", bool)
├── VisionManager.enable_module("dj_cues", bool)
├── VisionManager.enable_module("artista_cues", bool)
├── VisionManager.enable_module("tracking", bool)
└── FamilyManager → CLIMA cues (C60-C63)
```

### Evidencia de Aplicación Real

`core/system_bridge.py:197-239`:
```python
def _apply_modules(self, modules: Dict[str, bool]) -> None:
    # Audio Engine
    audio_on = modules.get("audio_engine", False)
    if self._audio_engine:
        self._audio_engine.set_enabled(audio_on)

    # CueEngine gating
    if self._cue_engine:
        if audio_on:
            self._cue_engine.set_disabled_states([])
        else:
            self._cue_engine.set_disabled_states(["ALL"])

    # Vision Manager
    if self._vision_manager:
        vm.enable_module("haze", modules.get("vision_haze", False))
        vm.enable_module("dj_cues", modules.get("vision_dj", False))
        ...
```

**Conclusión:** El calendario SÍ controla los módulos en runtime via SystemBridge.

---

## 3. API Faltante

### Routers Existentes

| Router | Prefix | Estado |
|--------|--------|--------|
| status | `/api/v1` | ✅ |
| analyzers | `/api/v1` | ✅ |
| cues | `/api/v1` | ✅ |
| network | `/api/v1` | ✅ |
| presets | `/api/v1` | ✅ |
| config | `/api/v1` | ✅ |
| alerts | `/api/v1` | ✅ |
| **calendar** | — | ❌ MISSING |
| **vision** | — | ❌ MISSING |

### Plan: `api/routers/calendar.py`

```python
# Endpoints requeridos
GET  /api/v1/calendar/state      # Modo actual, permisos, timeline
GET  /api/v1/calendar/events     # Schedule de la semana
GET  /api/v1/calendar/active     # Bloque activo actual
GET  /api/v1/calendar/next       # Próximo cambio
POST /api/v1/calendar/go         # Forzar modo (GO manual)
POST /api/v1/calendar/save       # Guardar schedule
POST /api/v1/calendar/now        # Override temporal

# Todas llaman CalendarManager (CORE), sin lógica en API
```

### Plan: `api/routers/vision.py`

```python
# Endpoints requeridos
GET  /api/v1/vision/state        # Estado de todos los detectores
GET  /api/v1/vision/config       # Configuración actual
POST /api/v1/vision/config       # Actualizar config
GET  /api/v1/vision/haze         # Estado haze detector
GET  /api/v1/vision/dj           # Estado DJ detector
GET  /api/v1/vision/tracking     # Estado artist tracker

# Todas llaman VisionManager (CORE)
```

### Integración en `api/main.py`

```python
from api.routers import calendar, vision

app.include_router(calendar.router, prefix="/api/v1", tags=["calendar"])
app.include_router(vision.router, prefix="/api/v1", tags=["vision"])
```

---

## 4. WebApp UX Mandatoria

### 4.1 Popup "Cues Manuales Activos"

**Ubicación:** `webapp/src/components/Layout.jsx`

**Implementación:**
```jsx
// En Layout.jsx, agregar:
import { useEffect, useState } from 'react';
import useSystemStore from '../store/useSystemStore';

export function Layout({ children }) {
  const { cues } = useSystemStore();
  const [showCueAlert, setShowCueAlert] = useState(false);

  // Mostrar alerta si hay cues activos al navegar
  useEffect(() => {
    if (cues?.active_cues?.length > 0) {
      setShowCueAlert(true);
    }
  }, [location.pathname]);

  return (
    <>
      {showCueAlert && (
        <ActiveCuesPopup
          cues={cues.active_cues}
          onDismiss={() => setShowCueAlert(false)}
        />
      )}
      ...
    </>
  );
}
```

**Archivos a modificar:**
- `webapp/src/components/Layout.jsx` — agregar popup global
- `webapp/src/components/ActiveCuesPopup.jsx` — nuevo componente
- `webapp/src/store/useSystemStore.js` — ya tiene `cues.active_cues`

### 4.2 Dirty State + SAVE Verde

**Ubicación:** `webapp/src/pages/Config.jsx`, `webapp/src/pages/Network.jsx`

**Implementación:**
```jsx
// En Config.jsx
const [initialConfig, setInitialConfig] = useState(null);
const [currentConfig, setCurrentConfig] = useState(null);

const isDirty = useMemo(() => {
  return JSON.stringify(initialConfig) !== JSON.stringify(currentConfig);
}, [initialConfig, currentConfig]);

// Botón SAVE
<Button
  className={cn(
    isDirty ? "bg-green-600 hover:bg-green-700" : ""
  )}
  disabled={!isDirty}
  onClick={handleSave}
>
  {isDirty ? "Guardar Cambios" : "Sin Cambios"}
</Button>

// beforeunload
useEffect(() => {
  const handleBeforeUnload = (e) => {
    if (isDirty) {
      e.preventDefault();
      e.returnValue = '';
    }
  };
  window.addEventListener('beforeunload', handleBeforeUnload);
  return () => window.removeEventListener('beforeunload', handleBeforeUnload);
}, [isDirty]);
```

**Archivos a modificar:**
- `webapp/src/pages/Config.jsx` — dirty tracking
- `webapp/src/pages/Network.jsx` — dirty tracking
- `webapp/src/hooks/useDirtyState.js` — nuevo hook reutilizable

---

## 5. mod_bajada No-Repeat — YA IMPLEMENTADO ✅

**CORRECCIÓN:** El audit anterior era INCORRECTO.

### Evidencia: `mod_bajada.py:118-119, 166-167`

```python
# Color no-repeat (L118-119)
if len(candidates) > 1 and self._last_col_used in candidates:
    candidates = [c for c in candidates if c != self._last_col_used] or candidates

# Position no-repeat (L166-167)
if len(candidates) > 1 and self._last_pos_used in candidates:
    candidates = [c for c in candidates if c != self._last_pos_used] or candidates
```

**Lógica:**
1. Si hay múltiples candidatos con el mismo usage count
2. Y el último usado está entre ellos
3. Filtrarlo para no repetir

**Persistencia:**
- `config/bajada_color_usage.json` — guarda `last` color
- `config/bajada_pos_usage.json` — guarda `last` position

**Conclusión:** mod_bajada tiene no-repeat robusto con fair rotation + persistencia.

---

## Resumen DONE / PARTIAL / MISSING

| Item | Estado | Evidencia |
|------|--------|-----------|
| Contrato calendario | ✅ DONE | `calendar_rules.py` completo |
| `get_permissions()` consumido | ✅ DONE | `system_bridge.py:172` |
| `merge_permissions_with_actions()` usado | ✅ DONE | `system_bridge.py:173` |
| Runtime enable/disable | ✅ DONE | `_apply_modules()` L197-239 |
| API /calendar | ❌ MISSING | Router no existe |
| API /vision | ❌ MISSING | Router no existe |
| Popup cues activos | ❌ MISSING | No existe en Layout |
| Dirty state | ❌ MISSING | Config/Network no lo tienen |
| mod_bajada no-repeat | ✅ DONE | L118-119, L166-167 |
| audio_profile por modo | ⚠️ PARTIAL | Solo booleano, sin metadata |

---

## 5 Próximos Commits

### Commit 1: API Calendar Router
```
Branch: claude/calendar-multi-action-editor-uV2nz
Commit: feat(api): add /calendar router with state/events/go/save

Files:
- api/routers/calendar.py (NEW)
- api/main.py (add include_router)
```

### Commit 2: API Vision Router
```
Branch: claude/calendar-multi-action-editor-uV2nz
Commit: feat(api): add /vision router with state/config/haze/dj/tracking

Files:
- api/routers/vision.py (NEW)
- api/main.py (add include_router)
```

### Commit 3: WebApp Active Cues Popup
```
Branch: claude/calendar-multi-action-editor-uV2nz
Commit: feat(webapp): add global popup for active manual cues

Files:
- webapp/src/components/ActiveCuesPopup.jsx (NEW)
- webapp/src/components/Layout.jsx (integrate popup)
```

### Commit 4: WebApp Dirty State Hook
```
Branch: claude/calendar-multi-action-editor-uV2nz
Commit: feat(webapp): add dirty state tracking with SAVE button

Files:
- webapp/src/hooks/useDirtyState.js (NEW)
- webapp/src/pages/Config.jsx (use hook)
- webapp/src/pages/Network.jsx (use hook)
```

### Commit 5: Calendar audio_profile Metadata (Opcional)
```
Branch: claude/calendar-multi-action-editor-uV2nz
Commit: feat(calendar): add MODE_METADATA for energy caps and state restrictions

Files:
- core/calendar/calendar_rules.py (add MODE_METADATA)
- core/system_bridge.py (read energy_cap if present)

NOTA: Solo implementar si se confirma que boliche_inicio necesita audio suave.
```

---

## Decisiones Pendientes

1. **¿boliche_inicio debe tener audio suave?**
   - Si SÍ → Commit 5 agrega `audio_profile`
   - Si NO → Mantener `audio_engine: False`

2. **¿WebApp debe tener páginas Vision/Calendar?**
   - API routers son necesarios para control remoto
   - Páginas UI son opcionales (ya hay UI en main.py PySide)

---

## Archivos Clave por Feature

```
API Calendar:
├── api/routers/calendar.py     # NEW
├── api/main.py                 # Agregar router
└── core/calendar/calendar_manager.py  # Ya existe, API lo llama

API Vision:
├── api/routers/vision.py       # NEW
├── api/main.py                 # Agregar router
└── core_vision/vision_manager.py  # Ya existe, API lo llama

WebApp Popup:
├── webapp/src/components/ActiveCuesPopup.jsx  # NEW
├── webapp/src/components/Layout.jsx           # Integrar
└── webapp/src/store/useSystemStore.js         # Ya tiene cues

WebApp Dirty:
├── webapp/src/hooks/useDirtyState.js  # NEW
├── webapp/src/pages/Config.jsx        # Usar hook
└── webapp/src/pages/Network.jsx       # Usar hook
```

# Auditoría ROADMAP v6.4 — Repo vs Especificación

**Fecha:** 2025-12-28
**Rama:** `claude/calendar-multi-action-editor-uV2nz`
**Tipo:** Auditoría estática (sin implementación)

---

## Tabla Principal: Roadmap Item → Estado

| Fase | Item | Estado | Evidencia |
|------|------|--------|-----------|
| **CRÍTICA** | cue_offset en config | **DONE** | `avolites_config.py:128` → `user_number_offset: 169` |
| **CRÍTICA** | fire_cue_logical() | **PARTIAL** | NO existe. `fire_cue()` aplica offset internamente via `_map_cue()` |
| **CRÍTICA** | kill_cue_logical() | **PARTIAL** | NO existe. `kill_cue()` aplica offset internamente |
| **CRÍTICA** | Offset unificado | **DONE** | `titan_transport.py:152` → `_map_cue(cue_id) = cue_id + offset` |
| **1** | state_manager.confirmed_state | **DONE** | `state_manager.py:717` → `self.current_state` |
| **1** | state_manager.previous_state | **DONE** | `state_manager.py:124` |
| **1** | state_manager.stability | **DONE** | `state_manager.py:22,135` → `STABILITY_WINDOW_MS`, `stability_buffer` |
| **1** | state_manager.cooldown | **DONE** | `state_manager.py:72,130` → `cooldown_seconds`, `cooldown_remaining` |
| **1** | state_manager.hysteresis | **DONE** | `state_manager.py:71,82` → `hysteresis_margin`, `_hysteresis_matrix` |
| **1** | mod_break activa/mata | **DONE** | `mod_break.py:138,209` → `_kill_snapshot()`, `_take_snapshot()` |
| **1** | mod_ataque 3 cues | **DONE** | `mod_ataque.py:41` → `CUE_SET = [37, 38, 39]` |
| **1** | mod_basegolpe bandas | **DONE** | `mod_basegolpe.py:40-42` → `FX_DIMMER (ALTA)`, `FX_BEAM (MEDIA)`, `FX_COLOR (BAJA)` |
| **1** | mod_bajada no-repeat | **MISSING** | No hay lógica de `last_cue` / `no_repeat` |
| **1** | mod_movimiento sin cambio falso | **DONE** | `mod_movimiento.py:8` → "Rota SOLO en cambio de estado global" |
| **2** | API /cues | **DONE** | `api/routers/cues.py:19,63,101` |
| **2** | API /config | **DONE** | `api/routers/config.py:150,191` |
| **2** | API /network | **DONE** | `api/routers/network.py:19,60,90,126` |
| **2** | API /analyzers | **DONE** | `api/routers/analyzers.py:12,90,98` |
| **2** | API /presets | **DONE** | `api/routers/presets.py:20,53,104` |
| **2** | API /vision | **MISSING** | No existe router de vision |
| **2** | API /calendar | **MISSING** | No existe router de calendar |
| **3** | WebApp estructura | **DONE** | 6 rutas en `webapp/src/router.jsx` |
| **3** | Manual cue popup | **MISSING** | No hay popup persistente al navegar |
| **3** | Dirty state + SAVE | **MISSING** | No hay tracking de cambios |
| **6** | VisionManager | **DONE** | `core_vision/vision_manager.py:16-100` |
| **6** | FamilyManager wiring | **DONE** | `core_vision/vision_manager.py:136-145` → `set_family_manager()` |
| **6** | Familias separadas | **DONE** | `core/cues/cue_map.py:177` → CLIMA, HAZE, DJ, ARTIST, TRACKING |
| **6** | HAZE OFF explícito | **DONE** | `core_vision/camera_haze.py:205` via `deactivate_family()` |
| **MEGA** | calendar_manager.py | **DONE** | `core/calendar/calendar_manager.py` |
| **MEGA** | calendar_rules.py | **DONE** | `core/calendar/calendar_rules.py` con 10 modos |
| **MEGA** | calendar_state.py | **DONE** | `core/calendar/calendar_state.py` |
| **MEGA** | calendar.json format | **PARTIAL** | Config existe pero no verificado JSON completo |

---

## FASE CRÍTICA — Offset Global

### Resultado: **OFFSET UNIFICADO = SÍ** (via `_map_cue()`)

#### Arquitectura actual:
```
Módulo → av.fire_cue(42) → _titan_queue.fire(42) → TitanTransport._map_cue(42)
                                                         ↓
                                               42 + 169 = 211 (real Titan)
```

#### Evidencia:
```python
# core/transport/titan_transport.py:150-152
def _map_cue(self, cue_id: int) -> int:
    """Aplica offset de mapeo al cue_id."""
    return cue_id + self.config.user_number_offset
```

#### ¿Existe `fire_cue_logical()`?
**NO.** Pero no es necesario. El offset se aplica automáticamente en la capa de transporte.

#### Llamadas directas a fire_cue (TODAS pasan por offset):

| Archivo | Línea | Llamada |
|---------|-------|---------|
| mod_movimiento.py | 103,177,226,234,247,256 | `self.av.fire_cue(c)` ✅ |
| mod_ataque.py | 112,142 | `self.av.fire_cue(target)` ✅ |
| mod_basegolpe.py | 245 | `self.av.fire_cue(cue)` ✅ |
| mod_break.py | 140,164,198,287 | `self.av.fire_cue(target/c)` ✅ |
| mod_bajada.py | 240,246 | `self.av.fire_cue(pos/col)` ✅ |
| mod_control_dimmer.py | 87,118 | `self.av.fire_cue(41)` ✅ |
| mod_timed_sequence.py | 171 | `self.av.fire_cue(cue_num)` ✅ |
| cue_engine.py | 524 | `self.av.fire_cue(41)` ✅ |
| family_manager.py | 99 | `self._av.fire_cue(new_cue)` ✅ |
| api/routers/cues.py | 84,87 | `fire_cue_manual()` / `fire_cue()` ✅ |

**Conclusión:** Todas las llamadas pasan por `AvolitesController.fire_cue()` que aplica offset en `TitanTransport`.

---

## FASE 1 — Lógica Musical

### StateManager (state_manager.py)

| Atributo | Estado | Línea | Valor Default |
|----------|--------|-------|---------------|
| `previous_state` | ✅ DONE | 124 | `None` |
| `cooldown_remaining` | ✅ DONE | 130 | `0.0` |
| `stability_buffer` | ✅ DONE | 135 | `[]` |
| `STABILITY_WINDOW_MS` | ✅ DONE | 60 | `0` (fast preset) |
| `cooldown_seconds` | ✅ DONE | 72 | `0.2` |
| `hysteresis_margin` | ✅ DONE | 71 | `0.04` |
| `_hysteresis_matrix` | ✅ DONE | 82 | Dict por estado |

### Módulos (mod_*.py)

| Módulo | Requerimiento | Estado | Evidencia |
|--------|---------------|--------|-----------|
| **mod_break** | Activar y matar snapshot | ✅ DONE | `_take_snapshot()` L134, `_kill_snapshot()` L238 |
| **mod_break** | ENTRY/RUN/EXIT | ✅ DONE | L92-155 |
| **mod_ataque** | Usar 3 cues | ✅ DONE | `CUE_SET = [37, 38, 39]` L41 |
| **mod_basegolpe** | Usar bandas baja/media/alta | ✅ DONE | `FX_DIMMER` (ALTA), `FX_BEAM` (MEDIA), `FX_COLOR` (BAJA) L40-42 |
| **mod_bajada** | No repetir cue seguido | ❌ MISSING | No hay `last_cue` tracking |
| **mod_movimiento** | No rotar sin transición | ✅ DONE | "Rota SOLO en cambio de estado global" L8, `last_state_seen` L63 |

### Frágil/Falta:
- **mod_bajada:** No tiene lógica de no-repetición de cues consecutivos

---

## FASE 2 — API Endpoints

### Endpoints Actuales (reales):

| Ruta | Método | Router | Línea |
|------|--------|--------|-------|
| `/api/v1/status` | GET | status.py | 12 |
| `/api/v1/cues` | GET | cues.py | 19 |
| `/api/v1/cues/fire` | POST | cues.py | 63 |
| `/api/v1/cues/kill` | DELETE | cues.py | 101 |
| `/api/v1/analyzers` | GET | analyzers.py | 12 |
| `/api/v1/analyzers/active` | GET | analyzers.py | 90 |
| `/api/v1/analyzers/matching` | GET | analyzers.py | 98 |
| `/api/v1/config/{section}` | GET | config.py | 150 |
| `/api/v1/config/{section}` | POST | config.py | 191 |
| `/api/v1/network/interfaces` | GET | network.py | 19 |
| `/api/v1/network/interface` | POST | network.py | 60 |
| `/api/v1/network/console` | POST | network.py | 90 |
| `/api/v1/network/ping` | POST | network.py | 126 |
| `/api/v1/presets` | GET | presets.py | 20 |
| `/api/v1/save` | POST | presets.py | 53 |
| `/api/v1/load` | POST | presets.py | 104 |
| `/api/v1/alerts` | GET | alerts.py | 12 |

### Comparación vs Roadmap:

| Requerido | Estado |
|-----------|--------|
| `/cues/*` | ✅ DONE |
| `/config/*` | ✅ DONE |
| `/network/*` | ✅ DONE |
| `/vision/*` | ❌ MISSING |
| `/calendar/*` | ❌ MISSING |

---

## FASE 3 — WebApp

**Referencia:** `docs/frontend_audit_phase3.md` (ya auditado)

### Resumen:

| Sección | Estado |
|---------|--------|
| Estado general (Dashboard) | ✅ DONE |
| Cámaras | ❌ MISSING (componentes existen pero no en router) |
| Estados de humo | ❌ MISSING |
| Detección DJ | ❌ MISSING |
| Tracking | ❌ MISSING |
| Manual cues | ✅ DONE |
| Artist cues | ❌ MISSING |
| Configuración | ✅ PARTIAL |
| Calendario | ❌ MISSING |
| API | ✅ DONE |
| Red | ✅ DONE |
| Licencia | ❌ MISSING |

### UX Mandatoria:

| Requerimiento | Estado | Ubicación |
|---------------|--------|-----------|
| Popup si manual cue activo | ❌ MISSING | Debería estar en `Layout.jsx` o global |
| Dirty state tracking | ❌ MISSING | `Config.jsx`, `Network.jsx` |
| SAVE verde si dirty | ❌ MISSING | Botones siempre habilitados |

---

## FASE 6 — Cámaras

### VisionManager → FamilyManager Wiring

```python
# core_vision/vision_manager.py:136-145
def set_family_manager(self, family_manager):
    self.haze_detector.set_family_manager(family_manager)
    self.dj_detector.set_family_manager(family_manager)
    self.artist_tracker.set_family_manager(family_manager)
    print("[VisionManager] FamilyManager conectado a todos los detectores")
```

**Estado:** ✅ DONE

### Familias Separadas (core/cues/cue_map.py)

| Familia | Cues | Estado |
|---------|------|--------|
| CLIMA | C60-C63 | ✅ Separada |
| HAZE | C64-C66 | ✅ Separada |
| DJ | C67-C71 | ✅ Separada |
| ARTIST | C72-C79 | ✅ Separada |
| TRACKING | C80-C82 | ✅ Separada |

**CLIMA no se mezcla con HAZE/DJ/ARTIST:** ✅ Confirmado (familias distintas, cues distintos)

### HAZE OFF Explícito

```python
# core_vision/camera_people.py:185-188
if self._family_manager:
    self._family_manager.deactivate_family(FAMILIA_DJ)
```

**Estado:** ✅ DONE via `deactivate_family()`

### ON/OFF por Familia

```python
# core/cues/family_manager.py:54-100
def activate_state(self, family: str, state, force: bool = False) -> bool:
    # Kill todos excepto nuevo, fire nuevo

def deactivate_family(self, family: str) -> bool:
    # Kill todos los cues de la familia
```

**Estado:** ✅ DONE

---

## FASE MEGA — Calendario Inteligente

### Archivos Existentes:

| Archivo | Estado | Path |
|---------|--------|------|
| calendar_manager.py | ✅ EXISTS | `core/calendar/calendar_manager.py` |
| calendar_state.py | ✅ EXISTS | `core/calendar/calendar_state.py` |
| calendar_rules.py | ✅ EXISTS | `core/calendar/calendar_rules.py` |
| calendar_resolver.py | ✅ EXISTS | `core/calendar/calendar_resolver.py` |
| config/calendar.json | ⚠️ NOT VERIFIED | |

### Modos Canónicos (calendar_rules.py:42-53):

```python
CANONICAL_MODES = [
    "clima_1", "clima_2", "clima_3", "clima_4",
    "teatro", "artista",
    "boliche_inicio", "boliche_desarrollo", "boliche_fin",
    "apagado",
]
```

**10/10 modos definidos:** ✅

### Reglas por Modo (CALENDAR_RULES):

| Modo | audio_engine | vision_haze | vision_dj | tracking_cam | dj_detection | cues_clima |
|------|--------------|-------------|-----------|--------------|--------------|------------|
| clima_1-4 | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| teatro | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ |
| artista | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |
| boliche_inicio | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| boliche_desarrollo | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| boliche_fin | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ |
| apagado | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

**Estado:** ✅ Coincide con Roadmap v6.4

---

## Resumen de Gaps

### Críticos (bloquean funcionalidad):
1. **API /vision**: No existe router
2. **API /calendar**: No existe router
3. **WebApp Vision**: Componentes existen pero no integrados en router
4. **WebApp Calendar**: No existe página

### Importantes (UX/completitud):
5. **mod_bajada no-repeat**: Falta lógica de no repetir cues
6. **Popup manual cue**: Falta en webapp
7. **Dirty state tracking**: Falta en webapp

### Menores (naming):
8. `fire_cue_logical()` no existe como tal (pero offset funciona via `_map_cue()`)

---

## Archivos Relevantes por Fase

```
FASE CRÍTICA:
├── avolites_config.py:815-837      # set_cue_offset()
├── core/transport/titan_transport.py:150-152  # _map_cue()
└── core/transport/titan_queue.py   # fire() → transport

FASE 1:
├── state_manager.py               # V13 FAST BASELINE
├── mod_break.py                   # STATEFUL canonical
├── mod_ataque.py                  # 3 cues [37,38,39]
├── mod_basegolpe.py               # Bandas ALTA/MEDIA/BAJA
├── mod_bajada.py                  # ⚠️ Falta no-repeat
└── mod_movimiento.py              # STATEFUL canonical

FASE 2:
├── api/routers/cues.py
├── api/routers/config.py
├── api/routers/network.py
├── api/routers/analyzers.py
├── api/routers/presets.py
├── api/routers/status.py
└── api/routers/alerts.py

FASE 3:
└── webapp/src/                    # Ver frontend_audit_phase3.md

FASE 6:
├── core_vision/vision_manager.py
├── core_vision/camera_haze.py
├── core_vision/camera_people.py
├── core_vision/camera_tracking.py
├── core/cues/family_manager.py
└── core/cues/cue_map.py

FASE MEGA:
├── core/calendar/calendar_manager.py
├── core/calendar/calendar_state.py
├── core/calendar/calendar_rules.py
└── core/calendar/calendar_resolver.py
```

# 911 BIBLIA CANÓNICA

**Sistema de Control de Iluminación — 911 Fiesta**

Versión: 1.0
Fecha: 2025-12-15
Estado: FROZEN (no modificar sin consenso)

---

## ÍNDICE

1. [Arquitectura General](#1-arquitectura-general)
2. [Mapa de Cues](#2-mapa-de-cues)
3. [Módulos Canónicos](#3-módulos-canónicos)
4. [Patrones de Implementación](#4-patrones-de-implementación)
5. [Matriz de Interacciones](#5-matriz-de-interacciones)
6. [Prohibiciones Absolutas](#6-prohibiciones-absolutas)
7. [Glosario](#7-glosario)

---

## 1. ARQUITECTURA GENERAL

### 1.1 Flujo de Control

```
StateManager → CueEngine → Módulos → Avolites/Titan
     ↓              ↓           ↓
  (estado)    (orquestación)  (fire/kill)
```

### 1.2 Principios Fundamentales

| Principio | Descripción |
|-----------|-------------|
| **Determinismo** | Mismo input → mismo output, siempre |
| **Single Source of Truth** | StateManager decide estado, módulos ejecutan |
| **Fire Once** | Disparar una vez en ENTRY, no reassert |
| **Kill Deferred** | Fire primero, kill después (siguiente tick) |
| **Offline Safe** | No depender de is_active() para decisiones |

### 1.3 Jerarquía de Prioridad

```
BRAKE > ATAQUE > BASE_GOLPE > BAJADA > MOVIMIENTO > AUX
```

BRAKE puede matar todo. AUX coexiste con todos.

---

## 2. MAPA DE CUES

### 2.1 Rangos por Familia

| Familia | Cues | Módulo | Notas |
|---------|------|--------|-------|
| **FX_DIMMER** | C1, C2, C3, C51, C52, C53 | BASE_GOLPE | Energía ALTA, toca C41 |
| **FX_BEAM** | C4, C5, C6, C54, C55, C56 | BASE_GOLPE | Energía MEDIA |
| **FX_COLOR** | C7, C8, C9, C57, C58, C59 | BASE_GOLPE | Energía BAJA |
| **COLORES** | C10-C18 | BAJADA | 3 grupos por energía |
| **POSICIONES** | C19-C27 | BAJADA | 3 grupos por energía |
| **MOVIMIENTO** | C28-C36 | MOVIMIENTO | 3 grupos por energía |
| **ATAQUE** | C37, C38, C39 | ATAQUE | Mapeo fijo por energía |
| **DIMMER** | C41 | CONTROL_DIMMER | Solo FX_DIMMER y BRAKE_C44 |
| **BRAKE** | C42, C43, C44 | BRAKE | FREEZE/RESTORE |
| **AUX** | C45-C50 | TimedSequence | Secuencia temporal |

### 2.2 Mapeo Energía → Cue

#### BASE_GOLPE
| Energía | Familia | Cues |
|---------|---------|------|
| ALTA | FX_DIMMER | C1, C2, C3, C51, C52, C53 |
| MEDIA | FX_BEAM | C4, C5, C6, C54, C55, C56 |
| BAJA | FX_COLOR | C7, C8, C9, C57, C58, C59 |

#### BAJADA
| Energía | Colores | Posiciones |
|---------|---------|------------|
| BAJA | C10, C11, C12 | C19, C20, C21 |
| MEDIA | C13, C14, C15 | C22, C23, C24 |
| ALTA | C16, C17, C18 | C25, C26, C27 |

#### MOVIMIENTO
| Energía | Cues |
|---------|------|
| BAJA | C28, C29, C30 |
| MEDIA | C31, C32, C33 |
| ALTA | C34, C35, C36 |

#### ATAQUE (mapeo fijo)
| Energía | Cue |
|---------|-----|
| BAJA | C37 |
| MEDIA | C38 |
| ALTA | C39 |

#### BRAKE (mapeo fijo)
| Energía | Cue | Función |
|---------|-----|---------|
| BAJA | C42 | FREEZE |
| MEDIA | C43 | FREEZE |
| ALTA | C44 | RESTORE + dim_off |

---

## 3. MÓDULOS CANÓNICOS

### 3.1 BASE_GOLPE

**Naturaleza:** EVENT-DRIVEN

| Aspecto | Comportamiento |
|---------|----------------|
| ENTRY | Fire 1 cue según energía (timestamp-based) |
| RUN | NO-OP |
| EXIT | Solo release_dim_off(REASON_FX_DIMMER) |
| C41 | Solo FX_DIMMER solicita dim_off |
| Selección | `int(time.time() * 10) % len(cues)` |

**Estado interno:**
```python
self.last_state_seen: Optional[str]
self._dimmer_requested: bool
```

**Prohibido:** Reassert, timers, is_active(), RR con memoria.

---

### 3.2 ATAQUE

**Naturaleza:** STATEFUL con HOLD (2.0s)

| Aspecto | Comportamiento |
|---------|----------------|
| ENTRY | Fire cue fijo por energía + HOLD 2.0s |
| RUN | Cambiar solo si energía cambió Y HOLD expiró |
| EXIT | Kill current_cue + reset |
| Cambio energía | Fire nuevo → kill anterior → reset HOLD |

**Estado interno:**
```python
self.current_cue: Optional[int]
self.current_energy: Optional[str]
self.hold_until: float
self.last_state_seen: Optional[str]
```

**Prohibido:** Reassert, matar otras familias, tocar C41.

---

### 3.3 BRAKE

**Naturaleza:** STATEFUL con HOLD (2.0s)

| Aspecto | Comportamiento |
|---------|----------------|
| ENTRY | Snapshot + kill all + fire cue + HOLD |
| RUN | Cambiar solo si energía cambió Y HOLD expiró |
| EXIT | Restore snapshot + kill C42-44 + release dimmer |
| C44 | request_dim_off("BREAK_C44") |
| Snapshot | is_active() PERMITIDO (excepción única) |

**Estado interno:**
```python
self.current_cue: Optional[int]
self.current_energy: Optional[str]
self.hold_until: float
self.last_state_seen: Optional[str]
self.freeze_snapshot: Optional[List[int]]
self._dimmer_requested: bool
```

**Snapshot excluye:** C41, C42, C43, C44

---

### 3.4 MOVIMIENTO

**Naturaleza:** STATEFUL con PIN (30s)

| Aspecto | Comportamiento |
|---------|----------------|
| Fire inicial | Si current_cue is None → fire desde RR |
| Rotación | Solo en cambio de estado global Y PIN expiró |
| PIN | Bloquea rotación, no bloquea fire inicial ni restore |
| UNION V1 | Puente a subgrupo vecino tras 2 ciclos |
| Pausa | BAJADA llama pause_for_positions() |
| Restore | BAJADA llama restore_from_positions() |

**Estado interno:**
```python
self.current_cue: Optional[int]
self.pin_until: float
self.paused_by_positions: bool
self.paused_cue: Optional[int]
self.idx: Dict[str, int]  # RR por energía (persiste)
self.last_state_seen: Optional[str]
self._cycle_due: bool
# UNION V1
self._cycle_count, self._rr_used, self._bridge_due
self._pending_kills: List[int]
```

**Prohibido:** Cambiar por energía, cambiar por tiempo, is_active() para decisiones.

---

### 3.5 BAJADA

**Naturaleza:** STATEFUL (latch en ENTRY)

| Aspecto | Comportamiento |
|---------|----------------|
| ENTRY | pause_for_positions() + fire pos + fire col |
| RUN | NO-OP (latch) |
| EXIT | restore_from_positions() + reset latches |
| Fair RR | Persistente en JSON para colores y posiciones |

**Estado interno:**
```python
self.in_bajada: bool
self.latched_pos: Optional[int]
self.latched_col: Optional[int]
self.last_state_seen: Optional[str]
self.movement  # referencia
# Fair RR (JSON)
self._color_usage, self._last_col_used
self._pos_usage, self._last_pos_used
```

**Prohibido:** Matar MOVIMIENTO directamente, reassert, is_active().

---

### 3.6 AUX (TimedSequence)

**Naturaleza:** STATEFUL (secuencia temporal)

| Aspecto | Comportamiento |
|---------|----------------|
| Dwell-based | Fires basados en tiempo en estado (start_after + interval) |
| State change | force_exit() en CADA cambio de estado |
| force_exit() | Kill C45-50 + reset timer + reset state machine |
| Kill confirm | is_active() PERMITIDO para confirmar kills |

**Estado interno:**
```python
self._state: str  # idle, fire_candidate, hold, kill_pending
self.last_fired_cue: Optional[int]
self.global_index: int
self.last_slot_index_seen: int
self.last_state_seen: Optional[str]
```

**Coexiste con:** Todos los módulos.

---

### 3.7 CONTROL_DIMMER

**Naturaleza:** PASIVO (responde a requests)

| Caller | Reason | Acción |
|--------|--------|--------|
| BASE_GOLPE (FX_DIMMER) | REASON_FX_DIMMER | dim_off |
| BRAKE (C44) | BREAK_C44 | dim_off |

**API:**
```python
request_dim_off(reason: str)
release_dim_off(reason: str)
```

---

## 4. PATRONES DE IMPLEMENTACIÓN

### 4.1 Detección de Transiciones (OBLIGATORIO)

```python
prev_state = self.last_state_seen
self.last_state_seen = state

is_entry = (prev_state != "ESTADO" and state == "ESTADO")
is_exit = (prev_state == "ESTADO" and state != "ESTADO")
```

### 4.2 Estructura de run() (OBLIGATORIO)

```python
def run(self, state: str, energy: str) -> Optional[int]:
    state = (state or "").upper()
    energy = (energy or "MEDIA").upper()

    # Normalizar energía
    energy = {"LOW": "BAJA", "MEDIUM": "MEDIA", "HIGH": "ALTA"}.get(energy, energy)

    # Detección de transiciones
    prev_state = self.last_state_seen
    self.last_state_seen = state
    is_entry = (prev_state != "MI_ESTADO" and state == "MI_ESTADO")
    is_exit = (prev_state == "MI_ESTADO" and state != "MI_ESTADO")

    # EXIT
    if is_exit:
        # cleanup
        return None

    # Not in state
    if state != "MI_ESTADO":
        return None

    # ENTRY
    if is_entry:
        # fire cues
        return cue

    # RUN (inside state)
    # ... lógica específica o NO-OP
    return self.current_cue
```

### 4.3 Fire-First, Kill-Deferred

```python
# En fire
self._pending_kills = [c for c in POOL if c != target]
self.av.fire_cue(target)

# En siguiente tick
if self._pending_kills:
    for c in self._pending_kills:
        self.av.kill_cue(c)
    self._pending_kills.clear()
```

### 4.4 HOLD Pattern

```python
# En ENTRY o cambio
self.hold_until = time.time() + HOLD_DURATION_S

# En RUN
if time.time() < self.hold_until:
    return self.current_cue  # NO-OP
```

---

## 5. MATRIZ DE INTERACCIONES

### 5.1 Quién Mata a Quién

| Killer | Target | Mecanismo |
|--------|--------|-----------|
| CueEngine | Familia saliente | off_now_for_state() |
| BRAKE | Todo (snapshot) | Snapshot + kill |
| ATAQUE | BASE_GOLPE | CueEngine (implícito) |
| BAJADA | MOVIMIENTO | pause_for_positions() (NO kill) |

### 5.2 Coexistencia

| Módulo A | Módulo B | Relación |
|----------|----------|----------|
| BASE_GOLPE | MOVIMIENTO | Coexisten |
| BASE_GOLPE | AUX | Coexisten |
| ATAQUE | MOVIMIENTO | Coexisten |
| ATAQUE | AUX | Coexisten |
| BAJADA | MOVIMIENTO | BAJADA pausa MOVIMIENTO |
| MOVIMIENTO | AUX | Coexisten |

### 5.3 C41 (Dimmer Master)

| Quién puede tocarlo | Cómo |
|---------------------|------|
| BASE_GOLPE (FX_DIMMER) | request/release_dim_off(REASON_FX_DIMMER) |
| BRAKE (C44) | request/release_dim_off("BREAK_C44") |
| Nadie más | — |

---

## 6. PROHIBICIONES ABSOLUTAS

### 6.1 En TODOS los módulos

| Prohibición | Razón |
|-------------|-------|
| `is_active()` para decidir fire | No determinista, depende de timing |
| Reassert si cue "no está activo" | Viola fire-once |
| Matar familias ajenas | Solo CueEngine o BRAKE |
| Auto-advance sin timer documentado | Viola determinismo |
| Heurísticas de comportamiento | Viola determinismo |

### 6.2 Excepciones Documentadas

| Módulo | Excepción | Razón |
|--------|-----------|-------|
| BRAKE | is_active() para snapshot | Necesario para FREEZE/RESTORE |
| AUX | is_active() para confirmar kill | Necesario para secuencia |
| MOVIMIENTO | is_active() en get_active_cues() | Solo telemetría |

---

## 7. GLOSARIO

| Término | Definición |
|---------|------------|
| **ENTRY** | Transición de otro estado → este estado |
| **EXIT** | Transición de este estado → otro estado |
| **RUN** | Tick dentro del estado (después de ENTRY) |
| **HOLD** | Período donde cambios están bloqueados |
| **PIN** | HOLD específico de MOVIMIENTO (30s) |
| **Latch** | Cue fijo durante todo el estado |
| **Fair RR** | Round-robin que evita repeticiones |
| **UNION V1** | Puente a subgrupo vecino tras N ciclos |
| **Fire-first** | Disparar antes de matar |
| **Kill-deferred** | Matar en el siguiente tick |
| **Snapshot** | Lista de cues activos para restore |
| **Offline Safe** | Funciona sin conexión a consola |

---

## HISTORIAL DE CAMBIOS

| Fecha | Versión | Cambios |
|-------|---------|---------|
| 2025-12-15 | 1.0 | Versión inicial - Auditoría forense completa |

---

## COMMITS CANÓNICOS

| Módulo | Commit | Mensaje |
|--------|--------|---------|
| BASE_GOLPE | `7871aa9` | feat(base_golpe): canonical event-driven implementation |
| ATAQUE | `4aa4028` | refactor(ataque): canonical stateful implementation per 911 Bible |
| BRAKE | `7b97fbc` | refactor(brake): canonical stateful implementation per 911 Bible |
| MOVIMIENTO | `65d2e2a` | refactor(movimiento): remove dead code, canonical cleanup |
| BAJADA | `641e267` | refactor(bajada): canonical implementation per 911 Bible |
| AUX | — | Ya canónico (no modificado) |

---

**FIN DEL DOCUMENTO**

Este documento es la fuente de verdad para el sistema 911 Fiesta.
Cualquier cambio requiere consenso y actualización de este documento.

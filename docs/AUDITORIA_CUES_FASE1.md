# AUDITORÍA COMPLETA — SISTEMA DE CUES 911 FIESTA

## FASE 1: IDENTIFICACIÓN DE MÓDULOS Y ANÁLISIS

---

## 1. INVENTARIO DE MÓDULOS

### 1.1 CueEngine (`cue_engine.py`) — **ORQUESTADOR PRINCIPAL**

| Campo | Descripción |
|-------|-------------|
| **Responsabilidad** | Orquestar 7 módulos especializados, gestionar cambios de estado, coordinar OFF→ON en transiciones |
| **Inputs** | `state_manager.get_state()`, `state_manager.get_energy()` |
| **Outputs** | Llamadas a `module.run(state, energy)` para cada módulo |
| **Afecta** | Todos los módulos especializados |
| **Versión** | v5.1 (SIN GATE READY + AUX-V2) |

**Flujo de ejecución:**
```
update() cada 200ms →
  1. Lee estado/energía de StateManager
  2. Si cambió estado: off_now_for_state(estado_anterior)
  3. Ejecuta módulos en orden:
     control_dimmer → break → ataque → base_golpe → bajada → movimiento → timed
```

---

### 1.2 BaseGolpeModule (`mod_basegolpe.py`) — **FAMILIA FX**

| Campo | Descripción |
|-------|-------------|
| **Responsabilidad** | Mapear energía→familia (FX_DIMMER/FX_BEAM/FX_COLOR), alternar 6 cues (3+3), gestionar C41 |
| **Inputs** | `state`, `energy` desde CueEngine |
| **Outputs** | `fire_cue()`, `kill_cue()` vía avolites, `request_dim_off()` vía ControlDimmer |
| **Afecta** | ControlDimmer (C41), Colores Fijos (C10-18 si FX_COLOR) |
| **Cues** | C1-9 (ALTA), C51-56 (fallback ALTA), C13-18 (MEDIA), C10-12,19-21 (BAJA) |

**Lógica de entrada:**
```python
if state == "BASE_GOLPE":
    if not in_bg:  # ENTRADA
        familia = ENERGY_TO_FAMILY[energy]  # ALTA→FX_DIMMER, MEDIA→FX_BEAM, BAJA→FX_COLOR
        cue = _select_next_cue(energy, cues)  # alternancia 3+3
        kill_except(cue, all_bg_cues)
        fire_cue(cue)
        if familia == "FX_DIMMER": request_dim_off()
        if familia == "FX_COLOR": kill_colores_fijos()
        in_bg = True
    else:  # DENTRO
        re-assert si apagado
else:  # SALIDA
    _deactivate_all()
```

**UNION V1:** Cada 2 ciclos completos en la misma familia, dispara 1 cue de familia vecina ("puente").

---

### 1.3 BajadaModule (`mod_bajada.py`) — **POSICIONES + COLORES**

| Campo | Descripción |
|-------|-------------|
| **Responsabilidad** | Activar Posiciones (C19-27) y Colores (C10-18) al entrar, pausar Movimiento |
| **Inputs** | `state`, `energy` desde CueEngine |
| **Outputs** | `fire_cue()`, `kill_cue()`, `movement.pause_for_positions()` |
| **Afecta** | MovimientoModule (pausa/restore) |
| **Cues** | C10-27 |

**Lógica:**
```python
if state == "BAJADA":
    if not in_bajada:  # ENTRADA
        kill_pool(C28-36)  # kill-seguro de Movimiento
        movement.pause_for_positions()
        pos = _choose_pos_fair()  # RR justo C19-27
        col = _choose_color_fair()  # RR justo C10-18
        fire(pos), fire(col)
        in_bajada = True
    else:  # DENTRO
        re-assert latches
else:  # SALIDA
    kill_pool(C10-27)
    kill_pool(C28-36)  # kill-seguro
    movement.restore_from_positions()
```

---

### 1.4 MovimientoModule (`mod_movimiento.py`) — **MOVIMIENTO CONTINUO**

| Campo | Descripción |
|-------|-------------|
| **Responsabilidad** | Mantener 1 cue activo (C28-36), rotar SOLO en cambio de estado global |
| **Inputs** | `state`, `energy` desde CueEngine, `paused_by_positions` desde Bajada |
| **Outputs** | `fire_cue()`, `kill_cue()` |
| **Afecta** | Solo a sí mismo |
| **Cues** | C28-36 |

**Lógica:**
```python
if paused_by_positions: return None

if state cambió: _cycle_due = True

if current_cue is None:
    choice = _next_rr(energy)  # RR por energía
    _ensure_fire(choice)  # pin 30s
elif _cycle_due and not _pin_active():
    choice = _next_rr(energy)
    if choice != current_cue: _ensure_fire(choice)
    _cycle_due = False
else:
    re-assert si apagado
```

**UNION V1:** Cada 2 ciclos completos, dispara 1 cue de subgrupo vecino ("puente").

---

### 1.5 AtaqueModule (`mod_ataque.py`) — **ATAQUE EXCLUSIVO**

| Campo | Descripción |
|-------|-------------|
| **Responsabilidad** | Mapear energía→cue (BAJA→C37, MEDIA→C38, ALTA→C39), exclusividad estricta |
| **Inputs** | `state`, `energy` desde CueEngine |
| **Outputs** | `fire_cue()`, `kill_cue()` |
| **Afecta** | Solo al set exclusivo C37-39 |
| **Cues** | C37, C38, C39 |

**Lógica:**
```python
if state != "ATAQUE":
    _deactivate_all()
    return None

if not _in_ataque:  # ENTRADA
    target = ENERGY_TO_CUE[energy]
    _ensure_exclusive(target)  # kill C37-39 excepto target
    fire_cue(target)
    _in_ataque = True
else:  # DENTRO
    if energy cambió: _handle_energy_change(energy)
    re-assert si apagado
```

---

### 1.6 BreakModule (`mod_break.py`) — **FREEZE/RESTORE**

| Campo | Descripción |
|-------|-------------|
| **Responsabilidad** | FREEZE (C42/C43) toma snapshot y congela, RESTORE (C44) restaura |
| **Inputs** | `state`, `energy` desde CueEngine |
| **Outputs** | `fire_cue()`, `kill_cue()`, snapshot de cues activos |
| **Afecta** | Cues 1-50 (snapshot), ControlDimmer (C41 via request_dim_off) |
| **Cues** | C42, C43, C44 |

**Lógica:**
```python
if state != "BRAKE":
    if _in_brake: _deactivate_all()
    return None

if not _in_brake:  # ENTRADA
    target = MAP[energy]  # BAJA→42, MEDIA→43, ALTA→44
    if target == 44:
        _handle_restore()  # restore snapshot + C44
    else:
        _handle_freeze()  # snapshot + kill + fire freeze
    _in_brake = True
else:  # DENTRO
    re-assert o cambiar por energía
```

**KILL-DUAL:** Doble kill para garantizar 100% efectividad.

---

### 1.7 ControlDimmerModule (`mod_control_dimmer.py`) — **C41 CONTROL**

| Campo | Descripción |
|-------|-------------|
| **Responsabilidad** | Mantener C41 ON por defecto, OFF solo si hay razones activas |
| **Inputs** | Razones de otros módulos (`FX_DIMMER`, `BREAK_C44`) |
| **Outputs** | `fire_cue(41)`, `kill_cue(41)` |
| **Afecta** | Solo C41 |
| **Cues** | C41 |

**Lógica:**
```python
run():
    _check_autounset()  # si no hay razones >250ms → forzar ON
    if _has_reasons():
        _ensure_off()
    else:
        _ensure_on()
```

**AUTO-UNSET:** Si no hay razones activas por ≥250ms, fuerza C41 ON.

---

### 1.8 TimedSequenceModule (`mod_timed_sequence.py`) — **SECUENCIA AUXILIAR**

| Campo | Descripción |
|-------|-------------|
| **Responsabilidad** | Disparar C45-C50 secuencialmente por tiempo de permanencia |
| **Inputs** | `state`, `energy`, `state_manager.state_start_time` |
| **Outputs** | `fire_cue()`, `kill_cue()` |
| **Afecta** | Solo C45-50 |
| **Cues** | C45, C46, C47, C48, C49, C50 |

**Máquina de estados V3:**
```
STATE_IDLE → STATE_FIRE_CANDIDATE → STATE_HOLD → STATE_KILL_PENDING → STATE_IDLE
```

**Parámetros:**
- `start_after`: 20s (espera antes de empezar)
- `interval`: 10s (tiempo entre fires)
- `duration`: 10s (hold del cue)
- `kill_on_state_change`: True
- `persist_index_across_states`: True

---

### 1.9 AuxStateManager (`aux_state_manager.py`) — **TABLA DE ESTADO**

| Campo | Descripción |
|-------|-------------|
| **Responsabilidad** | Mantener tabla de razones para C41, flag de C44, índice de secuencia auxiliar |
| **Inputs** | Razones de ControlDimmer, Break, TimedSequence |
| **Outputs** | Consultas de estado (has_c41_reasons, is_c44_active, get_aux_index) |
| **Afecta** | Ningún hardware — solo tabla de estado |

**IMPORTANTE:** NO hace fire/kill. Solo mantiene estado.

---

### 1.10 StateManager (`state_manager.py`) — **MÁQUINA DE ESTADOS GLOBAL**

| Campo | Descripción |
|-------|-------------|
| **Responsabilidad** | Determinar estado global (BAJADA/BASE_GOLPE/ATAQUE/BRAKE) por votación |
| **Inputs** | Módulos analizadores de audio (modules_bajada, modules_golpe, modules_ataque, modules_brake) |
| **Outputs** | `get_state()`, `get_energy()` |
| **Afecta** | CueEngine (via get_state/get_energy) |

**Estados:** BAJADA, BASE_GOLPE, ATAQUE, BRAKE

**V12 Features:**
- Override ATAQUE ≥80% (2 frames, elapsed≥0.20s)
- BASE_GOLPE requiere 4/10 votos (40%)
- Stability window 180ms
- Histéresis adaptativa

---

## 2. DIAGRAMA DE DEPENDENCIAS

```
┌─────────────────────────────────────────────────────────────────────┐
│                         StateManager (V12)                          │
│                    get_state() / get_energy()                       │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          CueEngine (V5.1)                           │
│         update() cada 200ms → ejecuta 7 módulos en orden            │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
        ▼                       ▼                       ▼
┌───────────────┐       ┌───────────────┐       ┌───────────────┐
│ControlDimmer │       │    Break      │       │    Ataque     │
│    (C41)     │◄──────│  (C42-44)     │       │   (C37-39)    │
└───────────────┘       └───────────────┘       └───────────────┘
        ▲
        │ request_dim_off()
        │
┌───────────────┐       ┌───────────────┐       ┌───────────────┐
│   BaseGolpe  │       │    Bajada     │──────►│  Movimiento   │
│   (C1-9,51-59)│       │   (C10-27)    │pause  │   (C28-36)    │
└───────────────┘       └───────────────┘       └───────────────┘

┌───────────────┐       ┌───────────────────────────────────────┐
│TimedSequence │◄──────│           AuxStateManager             │
│   (C45-50)   │ index │     (tabla de estado, sin hardware)   │
└───────────────┘       └───────────────────────────────────────┘
```

---

## 3. CANDIDATOS A FANTASMA

### 3.1 EN CueEngine (`cue_engine.py`)

| Línea | Código | Análisis | Veredicto |
|-------|--------|----------|-----------|
| 73 | `self.ed = energy_detector` | Se guarda pero **no se usa** — comentario dice "Mantener por compatibilidad, no usar" | **FANTASMA** |
| 139-141 | `_brake_pulse_start`, `_brake_no_event_timeout` | Variables inicializadas pero **nunca usadas** en el código | **FANTASMA** |
| 144-146 | `transport_quiet_ms`, `_last_pool_send`, `_sent_this_tick` | Rate limiting de transporte — **pero** `_can_send_transport()` y `_mark_sent()` **nunca se llaman** | **FANTASMA** |
| 257-272 | `_can_send_transport()`, `_mark_sent()` | Métodos definidos pero **nunca invocados** | **FANTASMA** |
| 274-280 | `_check_family_cooldown()`, `_mark_family_change()` | Métodos definidos pero **nunca invocados** | **FANTASMA** |
| 733-761 | `quantize_to_beat()` | Método definido pero **nunca invocado** — comentario dice "gancho opcional" | **FANTASMA** |
| 421-440 | Timer automático de BAJADA | Usa `cycle_next_cue()` pero BajadaModule **no tiene ese método** → **código muerto** | **FANTASMA** |

### 3.2 EN BaseGolpeModule (`mod_basegolpe.py`)

| Línea | Código | Análisis | Veredicto |
|-------|--------|----------|-----------|
| 88-101 | `self.flags` (10 flags de analizadores) | Se inicializan y actualizan pero **nunca se usan para tomar decisiones** | **CANDIDATO FANTASMA** (potencialmente útil para debug) |
| 456-543 | `set_modules_golpe()`, `update_analyzer_flags()`, `get_analyzer_flags()`, `get_votes()` | Conectan analizadores pero **los valores no influyen en disparo de cues** | **CANDIDATO FANTASMA** |

### 3.3 EN BajadaModule (`mod_bajada.py`)

| Línea | Código | Análisis | Veredicto |
|-------|--------|----------|-----------|
| 126-127 | `pos_idx`, `col_idx` | Round-robin por energía inicializado pero **no se usa** — en su lugar se usa `_choose_pos_fair()` y `_choose_color_fair()` que tienen su propia lógica | **FANTASMA** |
| 174-182 | `_next_rr()` | Método definido pero **nunca invocado** — reemplazado por `_choose_*_fair()` | **FANTASMA** |

### 3.4 EN MovimientoModule (`mod_movimiento.py`)

| Línea | Código | Análisis | Veredicto |
|-------|--------|----------|-----------|
| Ninguno | — | Código limpio, todo se usa | **OK** |

### 3.5 EN AtaqueModule (`mod_ataque.py`)

| Línea | Código | Análisis | Veredicto |
|-------|--------|----------|-----------|
| 44-48 | `locked_until` (dict de hold) | Se setea en `_fire_target()` pero `_en_hold()` **nunca bloquea nada** (run() no hace nada con el resultado) | **LÓGICA INCOMPLETA** |

### 3.6 EN BreakModule (`mod_break.py`)

| Línea | Código | Análisis | Veredicto |
|-------|--------|----------|-----------|
| Ninguno | — | Código limpio, todo se usa | **OK** |

### 3.7 EN ControlDimmerModule (`mod_control_dimmer.py`)

| Línea | Código | Análisis | Veredicto |
|-------|--------|----------|-----------|
| Ninguno | — | Código limpio, todo se usa | **OK** |

### 3.8 EN TimedSequenceModule (`mod_timed_sequence.py`)

| Línea | Código | Análisis | Veredicto |
|-------|--------|----------|-----------|
| 53 | `self.duration` | Se guarda pero **nunca se usa** — el hold es controlado por intervalo, no por duration | **FANTASMA** |

### 3.9 EN AuxStateManager (`aux_state_manager.py`)

| Línea | Código | Análisis | Veredicto |
|-------|--------|----------|-----------|
| 100-128 | `activate_c44()`, `deactivate_c44()`, `is_c44_active()` | Métodos definidos pero **nunca invocados** por ningún módulo | **FANTASMA** |

---

## 4. PROBLEMAS DETECTADOS

### 4.1 PROBLEMAS CRÍTICOS

#### P1: Timer BAJADA llama método inexistente
**Ubicación:** `cue_engine.py:421-436`
```python
if hasattr(self.m_bajada, 'cycle_next_cue'):
    self.m_bajada.cycle_next_cue()
```
**Problema:** BajadaModule **NO tiene** método `cycle_next_cue()`. El `hasattr` pasa False y no hace nada.
**Impacto:** Timer de 10s completamente inútil.

#### P2: Energy Detector pasado pero no usado
**Ubicación:** `cue_engine.py:73`
**Problema:** `energy_detector` se recibe en constructor pero nunca se usa — el energy viene de StateManager.
**Impacto:** Parámetro confuso en API.

#### P3: Rate limiting definido pero no aplicado
**Ubicación:** `cue_engine.py:144-146, 257-280`
**Problema:** Sistema de rate limiting (`_can_send_transport`, `_mark_sent`, `transport_quiet_ms`) completamente implementado pero **nunca invocado**.
**Impacto:** Código muerto que confunde mantenimiento.

### 4.2 PROBLEMAS DE DISEÑO

#### D1: Doble sistema de RR en Bajada
**Ubicación:** `mod_bajada.py`
**Problema:** Tiene `pos_idx`, `col_idx` (RR simple) Y `_choose_pos_fair()`, `_choose_color_fair()` (RR justo con persistencia).
Solo se usa el segundo, el primero es código muerto.

#### D2: Flags de analizadores sin uso
**Ubicación:** `mod_basegolpe.py:88-101`
**Problema:** Sistema completo de 10 flags de votación que no influye en ninguna decisión de disparo.

#### D3: Duration sin uso en TimedSequence
**Ubicación:** `mod_timed_sequence.py:53`
**Problema:** `duration` se configura (10s) pero el ciclo se basa en `interval`, no en duration.

#### D4: C44 flags en AuxStateManager sin uso
**Ubicación:** `aux_state_manager.py:100-128`
**Problema:** `activate_c44()`, `deactivate_c44()`, `is_c44_active()` nunca se llaman desde ningún módulo.

### 4.3 PROBLEMAS DE CONSISTENCIA

#### C1: Hold en Ataque no bloquea
**Ubicación:** `mod_ataque.py:44-48`
**Problema:** `_en_hold()` retorna True/False pero `run()` no usa ese valor para bloquear cambios de energía.
El hold existe pero no tiene efecto real.

#### C2: UNION V1 inconsistente
**Ubicación:** `mod_basegolpe.py`, `mod_movimiento.py`
**Problema:** Ambos tienen lógica de "puente" tras 2 ciclos, pero con implementaciones ligeramente diferentes.
Debería ser un patrón único reutilizable.

---

## 5. RELACIONES MASTER/SLAVE

| Master | Slave | Mecanismo | Estado |
|--------|-------|-----------|--------|
| StateManager | CueEngine | `get_state()`, `get_energy()` | **OK** |
| CueEngine | Todos los módulos | `module.run(state, energy)` | **OK** |
| Bajada | Movimiento | `pause_for_positions()`, `restore_from_positions()` | **OK** |
| BaseGolpe | ControlDimmer | `request_dim_off()`, `release_dim_off()` | **OK** |
| Break | ControlDimmer | `request_dim_off()`, `release_dim_off()` | **OK** |
| AuxStateManager | TimedSequence | `get_aux_index()`, `increment_aux_index()` | **OK** |
| AuxStateManager | ControlDimmer | `has_c41_reasons()` | **OK** |

---

## 6. TIMERS INTERNOS

| Timer | Ubicación | Intervalo | Propósito | Estado |
|-------|-----------|-----------|-----------|--------|
| CueEngine.update | `cue_engine.py:483-494` | 200ms | Loop principal de orquestación | **OK** |
| BAJADA auto-cycle | `cue_engine.py:421-440` | 10s | Ciclar siguiente cue de Bajada | **ROTO** (método inexistente) |
| TimedSequence | `mod_timed_sequence.py` | start_after=20s, interval=10s | Secuencia auxiliar C45-50 | **OK** |
| Movimiento PIN | `mod_movimiento.py:10` | 30s | Estabilidad post-fire | **OK** |
| ControlDimmer autounset | `mod_control_dimmer.py:37` | 250ms | Forzar C41 ON si no hay razones | **OK** |
| Ataque HOLD | `mod_ataque.py:6` | 2s | Hold corto para respuesta | **INEFECTIVO** |
| Break HOLD | `mod_break.py:7` | 1.5s | Hold corto | **OK** |

---

## 7. AUTO-ADVANCE / AUTO-NEXT

| Módulo | Mecanismo | Trigger | Estado |
|--------|-----------|---------|--------|
| CueEngine | BAJADA auto-cycle | Timer 10s | **ROTO** |
| TimedSequence | Secuencia temporal | Dwell time > slot*interval | **OK** |
| Movimiento | Rotación por cambio de estado | `_cycle_due` flag | **OK** |
| BaseGolpe | UNION V1 puente | 2 ciclos completos | **OK** |

---

## 8. RESUMEN DE FANTASMAS

### CÓDIGO MUERTO (eliminar)
1. `cue_engine.py:73` — `energy_detector` no usado
2. `cue_engine.py:139-141` — `_brake_pulse_*` no usados
3. `cue_engine.py:144-146, 257-280` — rate limiting no aplicado
4. `cue_engine.py:274-280` — `_check_family_cooldown()` no invocado
5. `cue_engine.py:421-440` — timer BAJADA llama método inexistente
6. `cue_engine.py:733-761` — `quantize_to_beat()` nunca invocado
7. `mod_bajada.py:126-127, 174-182` — RR viejo no usado
8. `mod_timed_sequence.py:53` — `duration` no usado
9. `aux_state_manager.py:100-128` — C44 flags nunca invocados

### LÓGICA INCOMPLETA (revisar)
1. `mod_ataque.py:44-48` — hold existe pero no bloquea
2. `mod_basegolpe.py:88-101` — flags de analizadores sin efecto

### DUPLICACIÓN (unificar)
1. UNION V1 en BaseGolpe y Movimiento — mismo patrón, implementaciones diferentes

---

## 9. CONCLUSIONES FASE 1

El sistema tiene:
- **7 módulos especializados** funcionando correctamente en su lógica core
- **~150 líneas de código fantasma** que deben eliminarse
- **2 sistemas de lógica incompleta** que deben decidirse si implementar o eliminar
- **1 patrón duplicado** (UNION V1) que debería unificarse

La arquitectura general es sólida (orquestador + módulos especializados + máquina de estados), pero tiene acumulación de código heredado de versiones anteriores que nunca se limpió.

**RECOMENDACIÓN:** Proceder a FASE 2 definiendo la lógica correcta antes de refactorizar.

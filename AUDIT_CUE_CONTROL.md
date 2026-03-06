# AUDITORÍA COMPLETA: Pipeline de Control de Cues
## 911 Fiesta Core — Sistema de Control Avolites Titan
### Fecha: 2026-03-06

---

## 1. DIAGRAMA DEL PIPELINE DE CONTROL

```
 ┌─────────────┐    ┌──────────────────┐    ┌──────────────────┐
 │  AUDIO IN   │───▶│   43 Analyzers   │───▶│  Voting System   │
 │  (PyAudio)  │    │  (energy, beat,  │    │  (% modules ON)  │
 └─────────────┘    │   rhythm, etc.)  │    └────────┬─────────┘
                    └──────────────────┘             │
                                                     ▼
 ┌─────────────┐    ┌──────────────────┐    ┌──────────────────┐
 │     MSE     │───▶│  State Inference │───▶│  Score Blending  │
 │ (beat,drop, │    │  (probabilities) │    │  65% Ana + 35%   │
 │  phrase)    │    └──────────────────┘    │      MSE         │
 └─────────────┘                           └────────┬─────────┘
                                                     │
                                                     ▼
                                            ┌──────────────────┐
 ┌─────────────┐                            │  StateManager    │
 │  Calendar   │──── disabled_states ──────▶│  V13 FAST        │
 │  Manager    │                            │                  │
 └──────┬──────┘                            │  EMA α=0.5      │
        │                                   │  Stability 120ms │
        │                                   │  Hold 0.32-0.96s │
        │                                   └────────┬─────────┘
        │                                            │
        │                                    get_state() / get_energy()
        │                                            │
        │                                            ▼
        │                                   ┌──────────────────┐
        ├── apply_calendar_state() ────────▶│   CueEngine v6   │
        │     (via SystemBridge)            │  DETERMINÍSTICO   │
        │                                   │                  │
        │                                   │  1. State change?│
        │                                   │     → OFF familia│
        │                                   │  2. Run modules  │
        │                                   │     in order     │
        │                                   └────────┬─────────┘
        │                                            │
        │                          ┌─────────────────┼──────────────────┐
        │                          │                 │                  │
        │                          ▼                 ▼                  ▼
        │                   ┌────────────┐   ┌────────────┐   ┌──────────────┐
        │                   │BreakModule │   │AtaqueModule│   │BaseGolpeModule│
        │                   │ C42-44     │   │ C37-39     │   │ C1-9,C51-59  │
        │                   └─────┬──────┘   └─────┬──────┘   └──────┬───────┘
        │                         │                │                  │
        │                         ▼                ▼                  ▼
        │                   ┌────────────┐   ┌────────────┐   ┌──────────────┐
        │                   │BajadaModule│   │Movimiento  │   │TimedSequence │
        │                   │ C10-27     │   │ C28-36     │   │ C45-50 (AUX) │
        │                   └─────┬──────┘   └─────┬──────┘   └──────┬───────┘
        │                         │                │                  │
        │                         └────────┬───────┘──────────────────┘
        │                                  │
        │                                  ▼
        │                         ┌──────────────────┐
        │                         │ ControlDimmer    │
        │                         │ C41 (PASIVO)     │
        │                         └────────┬─────────┘
        │                                  │
        │                                  ▼
        │                         ┌──────────────────┐
        │                         │ AvolitesController│
        │                         │ v5.1 LEGACY      │
        │                         └────────┬─────────┘
        │                                  │
        ├── Vision modules ──────────┐     │
        │   (HAZE/DJ/ARTIST)         │     │
        │   C60-C82 via              │     ▼
        │   FamilyManager       ┌────┴────────────────┐
        │                       │   TitanQueue v1.4   │
        │                       │   KILL > FIRE       │
        │                       │   Rate: 60ms        │
        │                       │   Dedup: 300ms      │
        │                       └────────┬────────────┘
        │                                │
        │                                ▼
        │                       ┌─────────────────────┐
        │                       │  TitanTransport     │
        │                       │  HTTP GET/POST      │
        └───────────────────────┤  FirePlaybackAtLevel│
                                │  KillPlayback       │
                                └────────┬────────────┘
                                         │
                                         ▼
                                ┌─────────────────────┐
                                │  AVOLITES TITAN     │
                                │  Console (Hardware) │
                                └─────────────────────┘
```

### Pipeline de BPM/Tempo (paralelo):

```
 Audio IN → KickDetector (40-120Hz) → AutoClock (PLL)
                                          │
                                    LOCKED? ──▶ TapSender
                                                    │
                                          3x TAP burst (interval_ms spacing)
                                                    │
                                                    ▼
                                          Titan HTTP: /titan/script/2/Macros/Run
                                              ?macroId=Avolites.Macros.TapBPM1
```

---

## 2. MAPA DE ACTIVACIÓN / DESACTIVACIÓN DE CUES

### 2.1 Tabla por familia

| Familia | Cues | Quién ACTIVA | Función que FIRE | Quién DESACTIVA | Función que KILL |
|---------|------|--------------|------------------|-----------------|------------------|
| **Dimmer** | C41 | `ControlDimmerModule.release_dim_off()` | `av.fire_cue(41)` — `mod_control_dimmer.py:87` | `ControlDimmerModule.request_dim_off()` | `av.kill_cue(41)` — `mod_control_dimmer.py:69` |
| **Base Golpe** | C1-9, C51-59 | `BaseGolpeModule.run()` en ENTRY | `av.fire_cue(cue)` — `mod_basegolpe.py:254` | `CueEngine.off_now_for_state()` | `av.kill_pool()` — `cue_engine.py:530` |
| **Bajada** | C10-27 | `BajadaModule.run()` en ENTRY | `av.fire_cue(pos)` + `av.fire_cue(col)` — `mod_bajada.py:241-245` | `CueEngine.off_now_for_state()` | `av.kill_pool()` — `cue_engine.py:530` |
| **Movimiento** | C28-36 | `MovimientoModule._fire_cue()` | `av.fire_cue(choice)` — `mod_movimiento.py:177` | `MovimientoModule._fire_cue()` (mata otros en mismo tick) | `av.kill_cue()` — `mod_movimiento.py:183-189` |
| **Ataque** | C37-39 | `AtaqueModule.run()` en ENTRY | `av.fire_cue(target)` — `mod_ataque.py:115` | `AtaqueModule._handle_exit()` | `av.kill_cue()` — `mod_ataque.py:95` |
| **Brake** | C42-44 | `BreakModule._handle_entry()` | `av.fire_cue(cue)` — `mod_break.py:151` | `BreakModule._handle_exit()` | `av.kill_pool([42,43,44])` — `mod_break.py:212` |
| **Auxiliar** | C45-50 | `TimedSequenceModule._do_fire()` | `av.fire_cue(cue_id)` — `mod_timed_sequence.py:188` | `TimedSequenceModule._do_kill()` o `force_exit()` | `av.kill_cue()` — `mod_timed_sequence.py:208` |
| **Clima** | C60-63 | `FamilyManager.activate_state()` via SystemBridge | `av.fire_cue()` — `family_manager.py` | `FamilyManager.deactivate_family()` | `av.kill_cue()` — `family_manager.py` |
| **Vision** | C64-82 | `FamilyManager` via VisionManager | `CueEngine.fire()` — `cue_engine.py:252` | `FamilyManager` | `CueEngine.kill()` — `cue_engine.py:273` |

### 2.2 Boot Sequence (activación inicial)

```
BootManager.boot()
  ├── PASO 1: kill_all_cues() → limpia consola
  ├── PASO 2: CalendarManager.resolve() → determina modo
  ├── PASO 3: VisionManager sync → según actions del calendario
  └── PASO 4: fire_cue(41) → C41 ON (dimmer master)

CueEngine.start_auto_update()
  └── fire_cue(41) → C41 ON (DUPLICADO - segundo fire)
```

---

## 3. IDENTIFICACIÓN DE FALLAS — PROBLEMAS REPORTADOS

---

### PROBLEMA 1: Delay al desactivar cues

**Causa exacta:** Múltiples capas de latencia acumulada entre la decisión de cambio de estado y el envío del comando OFF a Titan.

**Desglose de latencia:**

| Capa | Latencia | Archivo:Línea |
|------|----------|---------------|
| EMA smoothing (α=0.5) | 1-3 frames (~40-120ms) | `state_manager.py:448` |
| Stability window | 120ms obligatorio | `state_manager.py:648` |
| Hold time mínimo | 320-960ms según estado | `state_manager.py:817-829` |
| Cooldown post-ATAQUE/BRAKE | 200ms | `state_manager.py:831-836` |
| CueEngine update interval | 200ms (polling) | `cue_engine.py:176` |
| TitanQueue rate limit | 60ms entre requests | `titan_queue.py:121` |
| TitanQueue dedup window | 300ms (puede bloquear re-KILL) | `titan_queue.py:124` |
| HTTP round-trip | ~5-50ms | `titan_transport.py` |

**Latencia TOTAL worst-case para desactivación:**
- Estado sale de ATAQUE: 960ms hold + 200ms cooldown + 120ms stability + 200ms polling + 60ms rate + 50ms HTTP = **~1590ms**
- Estado sale de BAJADA: 320ms hold + 120ms stability + 200ms polling + 60ms rate + 50ms HTTP = **~750ms**

**Hallazgo clave:** La ventana de dedup de 300ms en TitanQueue (`titan_queue.py:124`) puede bloquear un KILL legítimo si el mismo cue fue matado recientemente. Esto es problemático cuando el CueEngine envía off_now_for_state() seguido de un KILL individual del módulo.

**Archivos afectados:**
- `state_manager.py:817-836` — Hold times y cooldowns
- `cue_engine.py:176` — Intervalo de polling 200ms
- `core/transport/titan_queue.py:124` — Dedup window 300ms
- `avolites_config.py:50` — DEDUP_WINDOW_MS = 600ms (config nivel alto)

---

### PROBLEMA 2: Tap tempo operativo incorrecto

**Causa exacta:** No existe mecanismo de escalado de BPM. El sistema envía el BPM detectado directamente a Titan sin ningún factor de conversión.

**Flujo actual:**
```
KickDetector → AutoClock.register_kick()
                    → interval_ms calculado
                    → EMA smoothing (α=0.12)
                    → BPM = 60000 / interval_ms    ← SIN ESCALA
                    → TapSender recibe interval_ms
                    → Envía TAPs espaciados a interval_ms
```

**Archivos y líneas exactas:**

1. **Cálculo de BPM sin escala:**
   - `tempo/auto_clock.py:579-583` — `get_bpm()` retorna `60000.0 / self.interval_ms` directamente
   - No hay parámetro `scale_factor` ni `divisor`

2. **Envío de TAPs sin escala:**
   - `tempo/tap_sender.py:196-206` — `_start_burst()` usa `interval_ms` directamente
   - El intervalo entre TAPs enviados a Titan ES el intervalo detectado
   - No hay transformación `interval_ms * 2` para enviar mitad de tempo

3. **Config sin campo de escala:**
   - `tempo/tap_sender.py:23-45` — `TapSenderConfig` no tiene campo `bpm_scale` ni `tempo_divisor`

4. **Endpoint Titan fijo:**
   - `avolites_config.py:1112-1113` — `send_tap()` usa `/titan/script/Playback/TapTempo`
   - `tempo/tap_sender.py:105-107` — TAP macro: `Avolites.Macros.TapBPM1`

**Requisito no implementado:** Si BPM detectado = 100, enviar BPM = 50 a consola requiere `interval_ms * 2` en el punto de envío.

---

### PROBLEMA 3: Cues auxiliares no se desactivan siempre

**Causa exacta:** `TimedSequenceModule` mata cues en `force_exit()` al cambiar estado, PERO tiene una ventana de 150ms de gracia (`_defer_until`) durante la cual puede re-disparar un cue auxiliar si el módulo `run()` se ejecuta antes de que expire el defer.

**Flujo problemático:**

```
1. Estado = BAJADA, cue C46 activo (auxiliar)
2. Estado cambia a ATAQUE
3. CueEngine detecta cambio → off_now_for_state("BAJADA")
4. CueEngine ejecuta módulos en orden:
   ... módulos 1-6 ejecutan ...
   7. TimedSequenceModule.run() → detecta state_changed
      → force_exit() → kill C46  ✓
      → _defer_until = now + 0.15s
5. PRÓXIMO TICK (200ms después):
   TimedSequenceModule.run() → estado=ATAQUE
   → state_machine es "idle" (fue reseteado por force_exit)
   → SI dwell >= start_after Y slot_index cambió
   → PUEDE DISPARAR NUEVO AUXILIAR  ← ¡PROBLEMA!
```

**Archivos y líneas:**

1. **force_exit() resetea a idle pero NO bloquea redisparo:**
   - `mod_timed_sequence.py:316-325` — `force_exit()` mata cue, resetea state a "idle", pero `_defer_until` es solo 150ms
   - Tras 150ms el módulo está listo para disparar de nuevo

2. **No hay bloqueo por cambio de estado:**
   - `mod_timed_sequence.py:277-299` — `run()` solo verifica `state != last_state_seen` para llamar `force_exit()`
   - NO verifica si el estado cambió RECIENTEMENTE — solo si cambió AHORA

3. **kill_pending puede quedarse colgado:**
   - `mod_timed_sequence.py:207-213` — Si `is_active(cue)` sigue retornando True después del kill, el módulo queda en `kill_pending` indefinidamente sin timeout

**Requisito no implementado:** Cuando cambia el estado musical, toda la familia auxiliar debe apagarse Y no puede volver a activarse hasta que expire `start_after` (20s) completo desde el nuevo estado.

---

### PROBLEMA 4: C41 no siempre se activa al iniciar

**Causa exacta:** C41 se dispara en DOS lugares diferentes del boot, pero ambos dependen de que la conexión HTTP a Titan esté activa. Si Titan no responde durante el boot, C41 queda pendiente y puede no resolverse.

**Secuencia de boot actual:**

```
1. BootManager.boot()
   └── PASO 4 (line 390): avolites.fire_cue(41)
       → Si falla: _pending_boot_baseline = True
       → Pero NO hay retry automático inmediato

2. CueEngine.start_auto_update() (line 677-681)
   └── Dispara fire_cue(41) ANTES del loop
       → Si falla: solo print, NO retry
       → Loop comienza SIN C41
```

**Archivos y líneas:**

1. **Boot C41 — BootManager:**
   - `core/boot_manager.py:378-398` — PASO 4 dispara C41
   - Si Titan offline: marca `_pending_boot_baseline = True` (line 395)
   - `core/boot_manager.py:450-485` — `apply_pending_baseline()` se llama cuando Titan reconecta
   - PERO: `apply_pending_baseline()` hace `kill_all + fire_cue(41)` — podría matar cues ya activos

2. **Boot C41 — CueEngine:**
   - `cue_engine.py:677-681` — Fire C41 en `start_auto_update()`
   - No retry, no verificación de éxito

3. **Orden del boot problemático:**
   - BootManager dispara C41 en PASO 4 (después de calendar/vision)
   - CueEngine dispara C41 al iniciar su loop
   - Si BootManager falla Y CueEngine falla → C41 nunca se enciende
   - No hay health-check periódico de C41

4. **ControlDimmerModule es PASIVO:**
   - `mod_control_dimmer.py:43-52` — NO dispara C41 en init
   - Solo responde a `request_dim_off()` / `release_dim_off()`
   - Si nadie solicita dim_off, C41 debería estar ON, pero el módulo NO lo garantiza

---

### PROBLEMA 5: Calendario debe apagar todo

**Causa exacta:** Cuando el calendario cambia de modo, SystemBridge propaga `set_disabled_states()` al CueEngine, pero esto solo afecta NUEVAS decisiones del StateManager — NO apaga cues ya activos de la familia saliente. Solo cuando se pasa `"ALL"` se hace un kill general.

**Flujo actual en cambio de calendario:**

```
CalendarManager detecta cambio de modo
  → SystemBridge.apply_calendar_state(new_mode, actions)
    → get_permissions(new_mode)
    → _apply_modules(modules)
      → CueEngine.set_disabled_states(disabled_list)
        → StateManager.set_disabled_states(disabled_list)
        → Solo si "ALL": off_now_for_family() para todas las familias
```

**Archivos y líneas:**

1. **SystemBridge solo deshabilita estados futuros:**
   - `core/system_bridge.py:252-264` — `_apply_modules()` llama `set_disabled_states()`
   - Solo modo "boliche_inicio/fin" deshabilita ATAQUE+BRAKE
   - Cambio entre climas NO deshabilita nada (audio_engine=False → "ALL")
   - Pero si `audio_engine=False` → sí manda "ALL"

2. **CueEngine.set_disabled_states() no mata cues existentes:**
   - `cue_engine.py:421-458` — Solo cuando `"ALL"` está en la lista ejecuta `off_now_for_family()` para todas las familias
   - Para cambios parciales (ej: deshabilitar solo ATAQUE), los cues de ATAQUE YA ACTIVOS no se matan inmediatamente

3. **No hay "kill all except new mode":**
   - No existe un método que haga: "mata todo y solo deja activos los cues del nuevo clima"
   - El cambio es gradual: el StateManager deja de elegir estados deshabilitados, y los cues activos se apagan solo cuando el CueEngine detecta el cambio de estado en su siguiente `update()`

4. **Vision modules permanecen:**
   - `core/system_bridge.py:269-300` — Vision se gobierna solo por actions
   - Si el calendario cambia de clima pero mantiene las mismas actions, Vision no se toca
   - Esto es correcto según el diseño, pero puede confundir al operador

---

### PROBLEMA 6: Grupos de energía

**Causa exacta:** La energía NO funciona como "gating" (bloqueo) de grupos. La energía solo modula la SELECCIÓN de cue dentro de cada familia. No existe un mecanismo que apague cues de un nivel de energía cuando el nivel cambia.

**Cómo funciona actualmente:**

```
StateManager.get_energy() → "BAJA" | "MEDIA" | "ALTA"
  ↓
CueEngine.update() pasa energy a cada módulo
  ↓
Cada módulo selecciona cue según energía:
  - AtaqueModule: BAJA→C37, MEDIA→C38, ALTA→C39
  - BreakModule:  BAJA→C42, MEDIA→C43, ALTA→C44
  - BaseGolpe:    BAJA→FX_COLOR, MEDIA→FX_BEAM, ALTA→FX_DIMMER
```

**El problema:**
1. Si energía cambia de ALTA a BAJA:
   - El cue de ALTA (ej C39) sigue activo hasta el PRÓXIMO cambio de estado
   - Dentro del mismo estado, los módulos Ataque/Brake solo reaccionan a energía DESPUÉS del hold time (2.0s)
   - BaseGolpeModule NO reacciona a cambios de energía dentro del mismo estado — solo dispara en ENTRY

2. **No hay "energy gating" a nivel de CueEngine:**
   - `cue_engine.py` NO tiene lógica para: "si energía cambió, matar cues del nivel anterior"
   - Los módulos son responsables individualmente, y solo Ataque/Brake lo manejan (con 2s de hold)

**Archivos y líneas:**
- `cue_engine.py:616` — `energy_changed` se trackea pero NO dispara acciones
- `mod_ataque.py:127-154` — Maneja cambio de energía con hold de 2s
- `mod_break.py:118-190` — Maneja cambio de energía con hold de 2s
- `mod_basegolpe.py:220-254` — Solo dispara en ENTRY, ignora cambios de energía
- `mod_bajada.py` — No usa energía para selección de cues
- `mod_movimiento.py` — Usa energía para RR pero no reacciona a cambios de energía

---

### PROBLEMA 7: Repetición de cues

**Causa exacta:** No existe un sistema de anti-repetición a nivel de CUE individual. Solo hay anti-repetición a nivel de ESTADO (recent_picks, hold times).

**Mecanismos actuales:**

| Nivel | Mecanismo | Ubicación | Efectividad |
|-------|-----------|-----------|-------------|
| Estado | `recent_picks` deque(3) | `state_manager.py:606-630` | Parcial — solo 3 estados |
| Estado | Hold times (0.32-0.96s) | `state_manager.py:817-829` | Buena para anti-jitter |
| Estado | Stability window 120ms | `state_manager.py:648` | Buena para anti-jitter |
| Cue (Bajada) | Fair rotation JSON | `mod_bajada.py:108-125` | Buena dentro de BAJADA |
| Cue (Movimiento) | Round-robin + PIN 30s | `mod_movimiento.py:142-166` | Buena dentro de Movimiento |
| Cue (BaseGolpe) | `idx = time.time()*10 % len` | `mod_basegolpe.py:149` | MALA — pseudo-random, no anti-repetición |
| Cue (Ataque) | Selección por energía fija | `mod_ataque.py:110-119` | NULA — siempre mismo cue por energía |
| Cue (Brake) | Selección por energía fija | `mod_break.py:131-155` | NULA — siempre mismo cue por energía |
| Cue (TimedSeq) | Round-robin global_index | `mod_timed_sequence.py` | Buena dentro de auxiliares |
| Transport | Dedup 300ms | `titan_queue.py:124` | Previene spam, no anti-repetición |

**Escenario problemático:**
```
1. Estado = ATAQUE, energía = ALTA → C39
2. Estado cambia a BAJADA
3. Estado vuelve a ATAQUE, energía = ALTA → C39 de nuevo  ← REPETICIÓN
4. No hay cooldown por cue individual
5. No hay historial de "C39 ya se usó hace 5 segundos"
```

**Archivos clave:**
- `cue_engine.py:236-241` — `_fire_history` es solo para monitoreo, NO para gating
- `mod_ataque.py:110-119` — Mapeo fijo energía→cue sin variación
- `mod_break.py:131-155` — Mapeo fijo energía→cue sin variación
- `mod_basegolpe.py:149` — Selección timestamp-based, no tiene memoria

---

## 4. RIESGOS ESTRUCTURALES

### 4.1 Cues sin control de estado

| Riesgo | Descripción | Severidad |
|--------|-------------|-----------|
| **BaseGolpe no mata sus cues** | El módulo solo dispara en ENTRY. La desactivación depende 100% de `CueEngine.off_now_for_state()`. Si CueEngine falla, los cues quedan activos indefinidamente. | ALTA |
| **Bajada no mata sus cues** | Igual que BaseGolpe — depende de CueEngine para cleanup. | ALTA |
| **ControlDimmer estado lógico desincronizado** | `_is_dim_off` puede diferir del estado real de C41 en Titan si fire/kill falla silenciosamente. No hay polling ni verificación. | MEDIA |
| **active_cues set en AvolitesController es solo lógico** | `_active_cues` en `avolites_config.py:213` se mantiene en memoria pero NO se verifica contra Titan (TitanSync está desactivado). | MEDIA |

### 4.2 Timers que no se cancelan

| Riesgo | Descripción | Severidad |
|--------|-------------|-----------|
| **TimedSequence kill_pending sin timeout** | Si `is_active(cue)` sigue retornando True después del kill, el módulo queda atascado en `kill_pending` sin escape. No hay timeout máximo. | ALTA |
| **Break hold_until no se resetea en emergency_stop** | `silent_reset()` pone `hold_until=0.0` pero `emergency_stop()` llama `reset()` que reinicia módulos — podrían quedar holds residuales si reset falla parcialmente. | MEDIA |
| **PIN de Movimiento persiste en pausa** | Cuando Bajada pausa Movimiento, el PIN timer sigue contando. Al restaurar, si el PIN ya expiró, no se extiende — el cue puede rotar inmediatamente al primer state change. | BAJA |

### 4.3 Módulos que no limpian su estado

| Riesgo | Descripción | Severidad |
|--------|-------------|-----------|
| **Break snapshot restore puede reactivar cues muertos** | Al salir de BRAKE, `_handle_exit()` restaura TODOS los cues del snapshot sin verificar si deben seguir activos. Si otro módulo los mató legítimamente, se reactivan incorrectamente. | ALTA |
| **AuxStateManager.reset() no notifica módulos** | `aux_state_manager.py:179-184` — reset() limpia la tabla pero no notifica a ControlDimmerModule ni TimedSequenceModule. Los módulos pueden operar con estado stale. | MEDIA |
| **Bajada fair rotation JSON nunca se resetea** | Los contadores de uso en `bajada_colors_rr.json` y `bajada_positions_rr.json` crecen indefinidamente. Tras meses de uso, todos los contadores son altos y la "fairness" se vuelve irrelevante. | BAJA |

### 4.4 Race conditions

| Riesgo | Descripción | Severidad |
|--------|-------------|-----------|
| **CueEngine update en thread vs UI thread** | CueEngine corre en daemon thread (`cue_engine.py:693`) pero los módulos acceden a `av.fire_cue()/kill_cue()` que interactúan con TitanQueue (thread-safe) y `_active_cues` (con lock). Sin embargo, `active_by_family` NO tiene lock. | MEDIA |
| **Calendar polling vs state change** | CalendarManager hace polling cada 60s en su propio ciclo. Si el calendario cambia entre polls, los cues del modo anterior siguen activos hasta el próximo poll. | MEDIA |
| **Dedup window puede comer KILLs legítimos** | Si CueEngine envía kill_pool() y luego un módulo envía kill_cue() individual para el mismo cue dentro de 300ms, el segundo KILL se dropea como duplicado. | MEDIA |

---

## 5. PLAN DE CORRECCIÓN

### 5.1 Apagado determinístico de cues

**Propuesta: "Kill-All-Then-Fire" en cambio de calendario**

```python
# En SystemBridge._apply_modules():
def _apply_modules(self, modules):
    # NUEVO: Si el modo cambió, kill ALL cues primero
    if mode_changed:
        cue_engine.emergency_kill_all_families()  # Nuevo método
        # Esperar confirmación de TitanQueue (flush)
        titan_queue.flush(timeout_ms=500)

    # Luego aplicar nuevo estado
    cue_engine.set_disabled_states(disabled_list)
```

**Nuevo método en CueEngine:**
```python
def emergency_kill_all_families(self):
    """Kill ALL families except dimmer (C41)."""
    for family in FAMILY_CUE_RANGES:
        if family != "control_dimmer":
            self.off_now_for_family(family)
```

### 5.2 Control de familias por energía

**Propuesta: Energy gating en CueEngine.update()**

```python
# En CueEngine.update(), después de detectar energy_changed:
if energy_changed and self.last_energy is not None:
    # Kill cues del nivel de energía anterior
    self._kill_energy_group(self.last_energy)

def _kill_energy_group(self, energy: str):
    """Kill cues asociados al nivel de energía saliente."""
    energy_cue_map = {
        "ALTA": [39, 44, 1, 2, 3, 51, 52, 53, 34, 35, 36],
        "MEDIA": [38, 43, 4, 5, 6, 54, 55, 56, 31, 32, 33],
        "BAJA": [37, 42, 7, 8, 9, 57, 58, 59, 28, 29, 30],
    }
    ids = energy_cue_map.get(energy, [])
    active_ids = [c for c in ids if self.av.is_active(c)]
    if active_ids:
        self.av.kill_pool(active_ids)
```

### 5.3 Control de repetición (anti-repetición por cue)

**Propuesta: Cooldown registry en CueEngine**

```python
class CueCooldownRegistry:
    def __init__(self, cooldown_activations: int = 3, cooldown_seconds: float = 30.0):
        self._history: deque = deque(maxlen=50)  # últimos 50 fires
        self._cooldown_n = cooldown_activations
        self._cooldown_s = cooldown_seconds

    def can_fire(self, cue_id: int) -> bool:
        """Retorna True si el cue puede dispararse (no está en cooldown)."""
        now = time.time()
        recent = [h for h in self._history
                  if h["cue"] == cue_id and (now - h["ts"]) < self._cooldown_s]
        return len(recent) < self._cooldown_n

    def record_fire(self, cue_id: int):
        self._history.append({"cue": cue_id, "ts": time.time()})

    def suggest_alternative(self, cue_id: int, candidates: list) -> int:
        """Si cue está en cooldown, sugiere alternativa de los candidatos."""
        if self.can_fire(cue_id):
            return cue_id
        for alt in candidates:
            if self.can_fire(alt):
                return alt
        return cue_id  # fallback
```

**Integración:**
- Cada módulo consulta `cooldown_registry.can_fire(cue)` antes de disparar
- Si no puede, pide `suggest_alternative(cue, family_candidates)`
- Los parámetros `cooldown_activations` y `cooldown_seconds` son configurables por familia

### 5.4 Control de tempo operativo (BPM escalado)

**Propuesta: Agregar `bpm_scale_factor` al pipeline de tempo**

```python
# En TapSenderConfig (tap_sender.py):
@dataclass
class TapSenderConfig:
    taps_per_burst: int = 3
    diff_ms: float = 12.0
    diff_ratio: float = 0.03
    bpm_scale_factor: float = 1.0  # NUEVO: 0.5 = mitad de tempo

# En TapSender._start_burst():
def _start_burst(self, interval_ms: float, reason: str):
    scaled_interval = interval_ms / self._cfg.bpm_scale_factor
    # Enviar TAPs con scaled_interval
    self._pending_interval_ms = scaled_interval
```

**Alternativa más simple (sin tocar TapSender):**
```python
# En AutoClock:
def get_bpm_scaled(self, factor: float = 1.0) -> float:
    raw = self.get_bpm()
    return raw * factor

# Uso: auto_clock.get_bpm_scaled(0.5) → BPM/2
```

### 5.5 Auxiliares determinísticos en cambio de estado

**Propuesta: Bloqueo completo de auxiliares tras cambio de estado**

```python
# En TimedSequenceModule:
def force_exit(self):
    # Kill actual
    self._do_kill()
    self._state = "idle"
    # NUEVO: Bloqueo completo por start_after
    self._blocked_until = self._now() + self.start_after  # 20s

def run(self, state, energy):
    # NUEVO: Verificar bloqueo
    if self._now() < self._blocked_until:
        return  # Bloqueado
    # ... resto de lógica
```

### 5.6 C41 garantizado en boot

**Propuesta: Health-check periódico de C41**

```python
# En ControlDimmerModule:
def ensure_dimmer_on(self):
    """Garantiza C41 ON si no hay razones para OFF."""
    if not self.has_c41_reasons() and not self.av.is_active(41):
        self.av.fire_cue(41)
        print("[DIMMER] C41 restored (health-check)")

# Llamar desde CueEngine.update() cada N ticks:
if self.stats["updates"] % 50 == 0:  # Cada ~10 segundos
    self.m_control.ensure_dimmer_on()
```

**Boot fix:**
```python
# En BootManager.boot():
# Mover C41 a PASO 1 (inmediatamente después de kill_all)
def boot(self):
    # PASO 1: Kill all + C41 ON (baseline)
    self.avolites.kill_all_cues()
    self.avolites.fire_cue(41)  # ← PRIMERO
    # PASO 2: Calendar
    # PASO 3: Vision
    # PASO 4: Verificar C41 sigue ON
```

---

## 6. RESUMEN DE PRIORIDADES

| # | Problema | Severidad | Esfuerzo | Prioridad |
|---|----------|-----------|----------|-----------|
| 1 | BPM escalado (tempo operativo) | ALTA | BAJO | P0 — Agregar `bpm_scale_factor` |
| 2 | C41 boot garantizado | ALTA | BAJO | P0 — Health-check + reorder boot |
| 3 | Auxiliares no se desactivan | ALTA | MEDIO | P1 — Bloqueo por `start_after` |
| 4 | Delay desactivación | MEDIA | MEDIO | P1 — Reducir dedup window, fast-path OFF |
| 5 | Calendario kill-all | MEDIA | MEDIO | P1 — Kill-all-then-fire en cambio de modo |
| 6 | Energy gating | MEDIA | MEDIO | P2 — Implementar energy kill groups |
| 7 | Repetición de cues | MEDIA | ALTO | P2 — CueCooldownRegistry |

---

## 7. ARCHIVOS AUDITADOS

| Archivo | Líneas | Auditoría |
|---------|--------|-----------|
| `cue_engine.py` | 1028 | Completa |
| `state_manager.py` | 1425 | Completa |
| `avolites_config.py` | 1163 | Completa |
| `aux_state_manager.py` | 185 | Completa |
| `timers.py` | 69 | Completa |
| `mod_control_dimmer.py` | ~125 | Completa |
| `mod_break.py` | ~309 | Completa |
| `mod_ataque.py` | ~191 | Completa |
| `mod_basegolpe.py` | ~434 | Completa |
| `mod_bajada.py` | ~299 | Completa |
| `mod_movimiento.py` | ~310 | Completa |
| `mod_timed_sequence.py` | ~424 | Completa |
| `core/transport/titan_queue.py` | 969 | Parcial (headers + config) |
| `core/transport/titan_transport.py` | 454 | Via subagente |
| `core/transport/titan_sync.py` | 462 | Via subagente (desactivado) |
| `core/system_bridge.py` | 476 | Completa |
| `core/boot_manager.py` | 560 | Via subagente |
| `core/calendar/calendar_manager.py` | 1352 | Via subagente |
| `core/calendar/calendar_rules.py` | 319 | Via subagente |
| `core/calendar/calendar_state.py` | 280 | Via subagente |
| `core/cues/family_manager.py` | 327 | Via subagente |
| `core/cues/cue_map.py` | 266 | Via subagente |
| `tempo/auto_clock.py` | ~500 | Via subagente |
| `tempo/tap_sender.py` | 296 | Via subagente |
| `tempo/tap_bridge.py` | ~230 | Via subagente |

**Total: 25 archivos auditados, ~10,600+ líneas de código revisadas**

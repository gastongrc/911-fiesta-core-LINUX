# LÓGICA CORRECTA — SISTEMA DE CUES 911 FIESTA

## FASE 2: DEFINICIÓN DE REGLAS

**Este documento es LEY. No es sugerencia.**

---

## 1. REGLA DE ORO

> **Un cue NO cambia a otro cue SALVO:**
> 1. Orden explícita del StateManager (cambio de estado)
> 2. Timer explícito y documentado
> 3. Cambio de energía dentro del mismo estado (donde aplique)

**PROHIBIDO:**
- Cues que "deciden" cambiar solos
- Lógica de auto-advance sin timer documentado
- Transiciones basadas en heurísticas o interpretación de audio
- Módulos paralelos que dupliquen decisiones

---

## 2. JERARQUÍA DE AUTORIDAD

```
┌─────────────────────────────────────────────────┐
│              FUENTE ÚNICA DE VERDAD             │
│                  StateManager                   │
│      get_state() → BAJADA|BASE_GOLPE|ATAQUE|BRAKE      │
│      get_energy() → BAJA|MEDIA|ALTA             │
└─────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────┐
│                   ORQUESTADOR                   │
│                    CueEngine                    │
│   - Lee estado/energía de StateManager          │
│   - Ejecuta módulos en orden estricto           │
│   - Gestiona OFF→ON en transiciones             │
└─────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────┐
│                    MÓDULOS                      │
│   - Reciben (state, energy) de CueEngine        │
│   - NUNCA consultan StateManager directo        │
│   - NUNCA deciden estados por sí mismos         │
│   - Solo disparan/matan cues de SU familia      │
└─────────────────────────────────────────────────┘
```

**REGLA:** Ningún módulo ignora el estado. Ningún módulo decide estados.

---

## 3. ESTADOS Y SUS FAMILIAS

### 3.1 BAJADA

| Propiedad | Valor |
|-----------|-------|
| **Cues activos** | Colores (C10-18) + Posiciones (C19-27) |
| **Comportamiento** | Elige 1 Color + 1 Posición al entrar, mantiene hasta salir |
| **Interacción** | PAUSA Movimiento (C28-36) |
| **Cambio interno** | NO cambia por energía ni por tiempo |
| **Al salir** | Kill C10-27, Kill C28-36 (safety), Restore Movimiento |

**REGLA:** Bajada NO tiene timer de auto-cycle. El cue se mantiene fijo.

### 3.2 BASE_GOLPE

| Propiedad | Valor |
|-----------|-------|
| **Cues activos** | FX según energía (C1-9 ó C51-56 ó C10-21) |
| **Comportamiento** | Elige 1 cue de la familia según energía, mantiene hasta salir |
| **Mapeo energía** | ALTA→FX_DIMMER, MEDIA→FX_BEAM, BAJA→FX_COLOR |
| **Interacción** | Si FX_DIMMER: solicita C41 OFF. Si FX_COLOR: kill Colores Fijos |
| **Cambio interno** | NO cambia por energía (latch en entrada) |
| **Al salir** | Kill familia activa, liberar C41 si FX_DIMMER |

**REGLA:** La energía solo importa en el momento de ENTRADA. Dentro del estado, no cambia.

### 3.3 ATAQUE

| Propiedad | Valor |
|-----------|-------|
| **Cues activos** | C37 ó C38 ó C39 (exclusivos) |
| **Comportamiento** | Mapea energía→cue, exclusividad estricta |
| **Mapeo energía** | BAJA→C37, MEDIA→C38, ALTA→C39 |
| **Cambio interno** | SÍ cambia por energía (responde a cambios) |
| **Al salir** | Kill C37-39 |

**REGLA:** Ataque SÍ responde a cambios de energía dentro del estado.

### 3.4 BRAKE

| Propiedad | Valor |
|-----------|-------|
| **Cues activos** | C42 ó C43 ó C44 (exclusivos) |
| **Comportamiento** | FREEZE (C42/C43) toma snapshot, RESTORE (C44) restaura |
| **Mapeo energía** | BAJA→C42, MEDIA→C43, ALTA→C44 |
| **Cambio interno** | SÍ cambia por energía |
| **Al salir** | Restaurar snapshot si había freeze, Kill C42-44 |

**REGLA:** Brake maneja snapshot de cues activos.

---

## 4. REGLAS DE FAMILIAS

### 4.1 Definición de Familias

| Familia | Cues | Estado Válido | Exclusividad |
|---------|------|---------------|--------------|
| COLORES_FIJOS | C10-18 | BAJADA | Múltiple (1 activo) |
| POSICIONES_FIJAS | C19-27 | BAJADA | Múltiple (1 activo) |
| MOVIMIENTO | C28-36 | !BAJADA | Exclusivo (1 activo) |
| FX_DIMMER | C1-3, C51-53 | BASE_GOLPE ALTA | Exclusivo (1 activo) |
| FX_BEAM | C4-6, C54-56 | BASE_GOLPE MEDIA | Exclusivo (1 activo) |
| FX_COLOR | C7-9, C57-59 | BASE_GOLPE BAJA | Exclusivo (1 activo) |
| ATAQUE | C37-39 | ATAQUE | Exclusivo (1 activo) |
| BRAKE | C42-44 | BRAKE | Exclusivo (1 activo) |
| CONTROL | C41 | SIEMPRE | ON por defecto |
| AUXILIAR | C45-50 | SIEMPRE | Secuencial (1 activo) |

### 4.2 Reglas de Exclusividad

1. **Dentro de una familia exclusiva:** Solo 1 cue activo a la vez
2. **Kill antes de Fire:** SIEMPRE kill otros de la familia ANTES de fire nuevo
3. **Kill incondicional:** NO confiar en `is_active()` — siempre kill_cue()
4. **Verificar kill:** Usar doble kill si es crítico (BRAKE)

### 4.3 Reglas de Convivencia

| Familia A | Familia B | Relación |
|-----------|-----------|----------|
| POSICIONES | MOVIMIENTO | EXCLUSIÓN (Posiciones pausa Movimiento) |
| FX_COLOR | COLORES_FIJOS | EXCLUSIÓN (FX_COLOR mata Colores) |
| FX_DIMMER | CONTROL (C41) | DEPENDENCIA (FX_DIMMER → C41 OFF) |
| BRAKE_C44 | CONTROL (C41) | DEPENDENCIA (C44 → C41 OFF) |

---

## 5. REGLAS MASTER/SLAVE

### 5.1 Definiciones

| Rol | Significado |
|-----|-------------|
| **MASTER** | Puede ordenar kill/fire a otros |
| **SLAVE** | Obedece órdenes del master |
| **TABLA** | Solo mantiene estado, no ordena |

### 5.2 Relaciones Definidas

```
StateManager [MASTER GLOBAL]
    └── CueEngine [ORQUESTADOR]
            ├── ControlDimmer [SLAVE de BaseGolpe, Brake]
            ├── Break [INDEPENDIENTE]
            ├── Ataque [INDEPENDIENTE]
            ├── BaseGolpe [MASTER de ControlDimmer]
            ├── Bajada [MASTER de Movimiento]
            │       └── Movimiento [SLAVE de Bajada]
            └── TimedSequence [CONSUMIDOR de AuxStateManager]
                    └── AuxStateManager [TABLA]
```

### 5.3 Reglas de Comunicación

1. **Bajada → Movimiento:**
   - `pause_for_positions()`: Bajada ordena pausa
   - `restore_from_positions()`: Bajada ordena restore
   - Movimiento NO decide cuándo pausar/restaurar

2. **BaseGolpe → ControlDimmer:**
   - `request_dim_off(REASON_FX_DIMMER)`: Solicita C41 OFF
   - `release_dim_off(REASON_FX_DIMMER)`: Libera solicitud
   - ControlDimmer decide estado final basado en todas las razones

3. **Brake → ControlDimmer:**
   - `request_dim_off(REASON_BREAK_C44)`: Solicita C41 OFF
   - `release_dim_off(REASON_BREAK_C44)`: Libera solicitud

4. **TimedSequence → AuxStateManager:**
   - `get_aux_index()`: Consulta índice
   - `increment_aux_index()`: Incrementa índice
   - AuxStateManager NO dispara cues, solo mantiene contador

---

## 6. TIMERS AUTORIZADOS

| Timer | Módulo | Intervalo | Propósito | Autorizado |
|-------|--------|-----------|-----------|------------|
| CueEngine loop | CueEngine | 200ms | Ejecutar módulos | **SÍ** |
| PIN estabilidad | Movimiento | 30s | Evitar cambios rápidos | **SÍ** |
| Secuencia auxiliar | TimedSequence | start:20s, interval:10s | Ciclar C45-50 | **SÍ** |
| Auto-unset C41 | ControlDimmer | 250ms | Forzar C41 ON si no hay razones | **SÍ** |
| HOLD ataque | Ataque | 2s | Evitar cambios rápidos | **SÍ** (pero debe implementarse) |
| HOLD brake | Brake | 1.5s | Evitar cambios rápidos | **SÍ** |

**TIMERS PROHIBIDOS:**
- BAJADA auto-cycle (eliminado — no existe en diseño original)
- Cualquier timer no listado arriba

---

## 7. CUES AUXILIARES (C45-50)

### 7.1 Reglas

1. **Escuchar TODOS los estados:** Funcionan en cualquier estado global
2. **Respetar prioridades:** Si estado cambia, kill cue actual
3. **No quedar pegados:** Máquina de estados garantiza kill antes de avanzar
4. **Secuencia global:** El índice persiste entre estados
5. **Independencia:** No interfieren con otras familias

### 7.2 Máquina de Estados

```
IDLE → (slot avanza) → FIRE_CANDIDATE → (fire ok) → HOLD
                                ↑                      │
                                │                      │
                        KILL_PENDING ← (slot avanza o estado cambia)
                                │
                                └── (kill confirmado) → IDLE
```

**REGLA CRÍTICA:** NUNCA avanzar sin confirmar kill del anterior.

---

## 8. CONTROL DIMMER (C41)

### 8.1 Reglas

1. **Estado por defecto:** C41 ON
2. **OFF solo por razones:** FX_DIMMER ó BREAK_C44
3. **Contador de razones:** Si hay ≥1 razón activa → OFF, sino → ON
4. **Auto-unset:** Si 0 razones por >250ms → forzar ON
5. **No decide:** Solo responde a requests de otros módulos

### 8.2 Flujo

```
BaseGolpe ENTRA con ALTA:
    → request_dim_off(FX_DIMMER)
    → ControlDimmer.run() → detecta razón → kill_cue(41)

BaseGolpe SALE:
    → release_dim_off(FX_DIMMER)
    → ControlDimmer.run() → 0 razones → fire_cue(41)
```

---

## 9. TRANSICIONES DE ESTADO

### 9.1 Protocolo de Cambio

```
CueEngine.update():
    if state_changed:
        1. OFF familia saliente: off_now_for_state(old_state)
        2. Actualizar estado interno
        3. En siguiente tick: módulos disparan familia entrante
```

### 9.2 Orden de Ejecución

```
1. control_dimmer.run()  — C41 primero (puede afectar a otros)
2. break.run()           — BRAKE tiene prioridad
3. ataque.run()          — ATAQUE segunda prioridad
4. base_golpe.run()      — BASE_GOLPE
5. bajada.run()          — BAJADA
6. movimiento.run()      — MOVIMIENTO (depende de Bajada)
7. timed.run()           — Secuencia auxiliar (independiente)
```

### 9.3 Orden OFF→ON

**REGLA:** Siempre OFF primero, luego ON.

```
Transición BAJADA → BASE_GOLPE:
    1. off_now_for_state("BAJADA") → kill C10-27
    2. Bajada.run() → detecta state != "BAJADA" → kill adicionales
    3. BaseGolpe.run() → detecta state == "BASE_GOLPE" → fire nuevo cue
```

---

## 10. PROHIBICIONES EXPLÍCITAS

### 10.1 PROHIBIDO en módulos

1. ❌ Consultar StateManager directamente (solo vía CueEngine)
2. ❌ Crear timers propios no documentados
3. ❌ Disparar cues de otra familia
4. ❌ Matar cues de otra familia (excepto exclusiones definidas)
5. ❌ Ignorar el estado recibido
6. ❌ Decidir cambios de estado
7. ❌ Implementar lógica de "interpretación musical"
8. ❌ Crear heurísticas de comportamiento

### 10.2 PROHIBIDO en CueEngine

1. ❌ Saltar módulos en la ejecución
2. ❌ Ejecutar módulos fuera de orden
3. ❌ Crear lógica paralela a los módulos
4. ❌ Guardar estado de energía/audio propio

### 10.3 PROHIBIDO en general

1. ❌ Código que "simula" o "emula" comportamiento
2. ❌ Lógica de fallback que crea comportamiento alternativo
3. ❌ Optimizaciones creativas no solicitadas
4. ❌ Módulos paralelos o duplicados

---

## 11. CONTRATO DE CADA MÓDULO

### 11.1 Método run(state, energy)

**Debe:**
- Recibir state y energy como parámetros
- Actuar SOLO si state corresponde a su familia
- Desactivar familia completa si state NO corresponde
- Re-asegurar cue activo si fue matado externamente
- Retornar cue activo o None

**No debe:**
- Consultar StateManager
- Crear timers internos no documentados
- Afectar cues de otras familias

### 11.2 Método get_active_cues()

**Debe:**
- Retornar lista de cues activos de SU familia
- Consultar driver para estado real
- Retornar lista vacía si no hay activos

### 11.3 Método get_status()

**Debe:**
- Retornar dict con estado interno para telemetría
- Incluir cues activos, índices, flags
- NO modificar estado al consultar

### 11.4 Método reset()

**Debe:**
- Desactivar todos los cues de su familia
- Limpiar estado interno
- Volver a estado inicial
- NO afectar otros módulos

---

## 12. RESUMEN EJECUTIVO

| Principio | Regla |
|-----------|-------|
| **Fuente de verdad** | StateManager es la ÚNICA fuente de estado |
| **Ejecución** | CueEngine ejecuta módulos en orden estricto |
| **Decisiones** | Módulos NO deciden, solo ejecutan |
| **Familias** | Cada módulo maneja SU familia exclusivamente |
| **Transiciones** | OFF primero, ON después |
| **Timers** | Solo los documentados en sección 6 |
| **Auxiliares** | Funcionan en todos los estados, secuencia global |
| **C41** | ON por defecto, OFF solo por razones |

**Este documento es CONTRATO. La refactorización debe cumplirlo al 100%.**

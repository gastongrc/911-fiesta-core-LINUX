# ANÁLISIS FORENSE: BRAKE INTERMITENTE / TARDÍO

**Fecha:** 2025-12-16
**Branch:** claude/musical-analysis-audit-6WtQD
**Alcance:** Diagnóstico de por qué BRAKE a veces entra y a veces no, y por qué entra tarde

---

## TAREA 1 — TODAS LAS CONDICIONES NECESARIAS PARA BRAKE

### Árbol Completo de Condiciones

Para que `BrakeAnalyzer._on = True`, TODAS estas condiciones deben cumplirse en cadena:

```
┌─────────────────────────────────────────────────────────────────────────┐
│ CONDICIÓN 1: ok_drop = True                                              │
│   Línea 200-201                                                          │
│   drop_db = 10*log10(eL/eS) >= 12.0                                      │
│   Requiere: EMA larga > EMA corta por 12dB                               │
│   Dependencias: win_short (0.14s), win_long (1.2s)                       │
└─────────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ CONDICIÓN 2: ok_quiet = True                                             │
│   Línea 204                                                              │
│   rms <= 0.35 * baseline_rms                                             │
│   Requiere: RMS actual sea < 35% del baseline adaptativo                 │
│   Dependencias: baseline_tau (10.0s de adaptación)                       │
└─────────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ CONDICIÓN 3: ok_flux = True                                              │
│   Línea 207-208                                                          │
│   flux <= flux_max (0.12)                                                │
│   Requiere: Spectral flux bajo (sin cambios espectrales)                 │
│   Dependencias: FFT + comparación de magnitudes                          │
└─────────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ CONDICIÓN 4: ok_time = True                      ⏱️ BLOQUEANTE TEMPORAL │
│   Línea 215-216                                                          │
│   since_onset = self._t - self._last_onset_t >= void_s (1.2s)            │
│   Requiere: 1.2 SEGUNDOS sin ningún onset detectado                      │
│   Dependencias: _detect_onsets() no debe encontrar transitorios          │
└─────────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ CONDICIÓN 5: all_ok OR v_raw > 0.7               (para acumular _ok_time)│
│   Línea 227-228                                                          │
│   all_ok = ok_drop AND ok_quiet AND ok_flux AND ok_time                  │
│   Requiere: Las 4 condiciones simultáneas, O score > 0.7                 │
│   Efecto: _ok_time += dt (acumula confirmación)                          │
└─────────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ CONDICIÓN 6: v_confirm >= 1.0                    (confirmar durante 1s) │
│   Línea 234                                                              │
│   v_confirm = _ok_time / confirm_s (1.0s)                                │
│   Requiere: Acumular 1.0 segundos con condiciones mantenidas             │
│   Efecto: v_confirm pesa 40% del score final                             │
└─────────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ CONDICIÓN 7: v (suavizado) >= thr_on (0.60)                              │
│   Línea 278                                                              │
│   v = EMA(v_raw * 0.6 + v_confirm * 0.4)                                 │
│   Requiere: Score final suavizado supere umbral 0.60                     │
│   Dependencias: smooth (0.50), tau_ms (120-200ms)                        │
└─────────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ CONDICIÓN 8: _t_on >= hold_on_s (550ms)          ⏱️ HOLD TEMPORAL       │
│   Línea 279-282                                                          │
│   Requiere: v >= thr_on MANTENIDO durante 550ms consecutivos             │
│   Efecto: Finalmente _on = True                                          │
└─────────────────────────────────────────────────────────────────────────┘
           │
           ▼
        _on = True
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ CONDICIÓN 9: StateManager score >= BRAKE_THRESHOLD (0.65)                │
│   state_manager.py L422                                                  │
│   scores["brake"] = active_analyzers / total_analyzers                   │
│   Requiere: Suficientes analizadores de BRAKE activos                    │
└─────────────────────────────────────────────────────────────────────────┘
           │
           ▼
        STATE_BRAKE
```

### Tabla Resumen de 9 Condiciones

| # | Condición | Línea | Valor Requerido | Tiempo Mínimo |
|---|-----------|-------|-----------------|---------------|
| 1 | ok_drop | L201 | drop_db >= 12dB | ~140ms (win_short) |
| 2 | ok_quiet | L204 | rms <= 35% baseline | Instantáneo |
| 3 | ok_flux | L208 | flux <= 0.12 | ~20ms (1 frame) |
| 4 | ok_time | L216 | since_onset >= 1.2s | **1200ms** |
| 5 | all_ok / v_raw>0.7 | L227-228 | 4 condiciones OR score | Depende de 1-4 |
| 6 | v_confirm | L234 | _ok_time >= 1.0s | **+1000ms** |
| 7 | v >= thr_on | L278 | score >= 0.60 | ~150ms (smooth) |
| 8 | _t_on >= hold | L281 | 550ms consecutivos | **+550ms** |
| 9 | StateManager | SM:L422 | scores >= 0.65 | ~20ms |

**TOTAL MÍNIMO SECUENCIAL: ~2.9 segundos**

---

## TAREA 2 — CONDICIONES FRÁGILES QUE CAUSAN INTERMITENCIA

### 2.1 `_detect_onsets()` — LA MÁS FRÁGIL

**Ubicación:** `brake.py` L89-126

```python
# L106: Umbral adaptativo
thr = float(np.median(dpos) + 2.2 * 1.4826 * _mad(dpos))

# L109: Candidatos
cand = np.where(dpos > thr)[0]
```

**Por qué es frágil:**

| Aspecto | Problema |
|---------|----------|
| **Umbral MAD-based** | Adaptativo por frame → varía con cada bloque de audio |
| **Mediana + 2.2σ** | Detecta CUALQUIER transitorio, no solo golpes musicales |
| **Sin filtro de frecuencia** | Voz con consonantes duras = onset detectado |
| **Refractario corto** | 120ms permite múltiples onsets por segundo |

**Qué puede disparar un onset falso y resetear `_last_onset_t`:**
- Consonante plosiva en la voz (P, T, K)
- Respiración audible del cantante
- Reverberación con picos
- Ruido de fondo con variación
- Artefactos del audio comprimido

**Consecuencia:** Cada onset detectado **RESETEA** el contador `since_onset`, reiniciando los 1.2s de espera.

### 2.2 `baseline_rms` — ADAPTACIÓN LENTA

**Ubicación:** `brake.py` L194-197

```python
baseline_tau = 10.0  # 10 segundos de adaptación
aB = np.exp(-dt / baseline_tau)
self._baseline_rms = (1.0 - aB) * max(rms, 0.001) + aB * self._baseline_rms
```

**Por qué es frágil:**

| Escenario | Efecto en baseline_rms | Efecto en ok_quiet |
|-----------|------------------------|-------------------|
| Canción con intro suave → pico energético | baseline bajo | ok_quiet = True fácil |
| Canción energética desde inicio | baseline alto | ok_quiet difícil de alcanzar |
| Secuencia de BRAKEs cortos | baseline no recupera | ok_quiet progresivamente más difícil |
| Cambio de canción | 10s para adaptarse | Comportamiento impredecible |

**Consecuencia:** `ok_quiet` depende del **historial de 10 segundos**, no solo del momento actual.

### 2.3 `_ok_time` Acumulador — DECAY ASIMÉTRICO

**Ubicación:** `brake.py` L227-231

```python
if all_ok or v_raw > 0.7:
    self._ok_time = min(10.0, self._ok_time + dt)  # Crece lento
else:
    self._ok_time = max(0.0, self._ok_time - 2*dt)  # Decrece 2x más rápido
```

**Por qué es frágil:**

| Situación | Efecto |
|-----------|--------|
| 1 frame con onset = ok_time=False | _ok_time -= 2*dt (pierde el doble) |
| Onset en medio de acumulación | Resetea progreso |
| Oscilación rápida de condiciones | _ok_time nunca acumula suficiente |

**Consecuencia:** Un **SOLO frame** con onset puede costar **40-80ms de progreso** en confirmación.

### 2.4 Histéresis `_t_on` — SIN MEMORIA

**Ubicación:** `brake.py` L278-284

```python
if v >= thr_on:
    self._t_on += dt
else:
    self._t_on = 0.0  # RESET COMPLETO
```

**Por qué es frágil:**

Si el score `v` cae **UN SOLO FRAME** por debajo de 0.60 (por onset o fluctuación), `_t_on` vuelve a 0.0, perdiendo todo el progreso hacia los 550ms.

**Consecuencia:** Requiere **550ms CONSECUTIVOS** sin ninguna interrupción.

---

## TAREA 3 — FUENTE DE ENTRADA TARDE

### Cadena Temporal del Retraso

```
EVENTO MUSICAL: Golpe desaparece (T=0)
    │
    ├──► win_short detecta caída de energía: +140ms
    │
    ├──► drop_db alcanza 12dB: +100ms adicionales ≈ T=240ms
    │       └──► ok_drop = True ✓
    │
    ├──► rms cae bajo 35% baseline: ~inmediato
    │       └──► ok_quiet = True ✓
    │
    ├──► flux cae bajo 0.12: ~inmediato
    │       └──► ok_flux = True ✓
    │
    ├──► PERO _detect_onsets() detecta residuos:
    │       └──► Voz con consonante → onset → reset _last_onset_t
    │       └──► Reverb decay → onset → reset _last_onset_t
    │       └──► ok_time = False ✗
    │
    ├──► Esperar void_s = 1.2s SIN ONSETS: +1200ms
    │       └──► ok_time = True ✓ (finalmente)
    │
    ├──► all_ok = True, _ok_time empieza a acumular: T ≈ 1.4s
    │
    ├──► _ok_time alcanza confirm_s = 1.0s: +1000ms ≈ T=2.4s
    │       └──► v_confirm ≈ 1.0
    │
    ├──► v_raw * 0.6 + v_confirm * 0.4 ≈ 0.64
    │       └──► Suavizado: +150ms ≈ T=2.55s
    │       └──► v >= thr_on (0.60) ✓
    │
    ├──► hold_on acumula 550ms: +550ms ≈ T=3.1s
    │       └──► _t_on >= 550ms
    │       └──► _on = True ✓
    │
    └──► StateManager detecta y cambia estado: +20ms ≈ T=3.12s
            └──► STATE_BRAKE ✓
```

### Contribución de Cada Condición al Retraso

| Condición | Tiempo Contribuido | % del Total | Evitable? |
|-----------|-------------------|-------------|-----------|
| void_s (1.2s sin onsets) | **1200ms** | **38%** | Dominante |
| confirm_s (acumulador) | **1000ms** | **32%** | Segundo lugar |
| hold_on (histéresis) | **550ms** | **17%** | Tercero |
| smooth (suavizado VU) | ~150ms | 5% | Menor |
| win_short + respuesta | ~240ms | 8% | Necesario |
| **TOTAL** | **~3140ms** | 100% | |

### El Punto Exacto de Entrada Tarde

**Línea L216:** `ok_time = (since_onset >= void_s)`

Esta línea es la **puerta cerrada** durante los primeros 1.2 segundos, independientemente de cuán claro sea el BRAKE musical.

---

## TAREA 4 — EXPLICACIÓN DE VARIABILIDAD

### ¿Por qué el mismo evento musical a veces dispara BRAKE y a veces no?

#### Escenario A: BRAKE Entra (Raro)

```
Condiciones que se alinean:
1. Canción con baseline_rms alto (canción energética previa)
   → El corte baja rms fácilmente al 35% del baseline

2. BRAKE musical limpio sin voz
   → Sin consonantes plosivas
   → Sin reverberación residual significativa
   → _detect_onsets() NO encuentra transitorios

3. Silencio prolongado natural > 1.2s
   → void_s se cumple naturalmente

4. Sin fluctuaciones durante acumulación
   → _ok_time acumula los 1.0s completos
   → _t_on acumula los 550ms sin interrupciones

Resultado: BRAKE entra ~3s después del evento
```

#### Escenario B: BRAKE NO Entra (Común)

```
Causas típicas:
1. Voz continúa durante el BRAKE (la gente canta)
   → _detect_onsets() detecta consonantes como onsets
   → since_onset se resetea constantemente
   → ok_time NUNCA es True

2. Reverberación/eco residual
   → Picos de energía durante el decay
   → _detect_onsets() detecta como transitorios
   → void_s nunca se cumple

3. Ruido de fondo con variación
   → Cualquier variación > median + 2.2*MAD
   → Se interpreta como onset

4. baseline_rms adaptado a nivel bajo
   → Si la sección anterior era suave
   → rms del BRAKE puede ser > 35% del baseline
   → ok_quiet = False

5. Spectral flux residual
   → Si hay cambios en el espectro (voz modulando)
   → flux > 0.12
   → ok_flux = False

Resultado: BRAKE nunca entra, o entra muy tarde
```

#### Escenario C: BRAKE Entra Tarde (Frecuente)

```
Secuencia típica:
T=0:     BRAKE musical ocurre
T=0-1s:  Voz con consonantes detectadas como onsets
         → since_onset se resetea múltiples veces

T=1.0s:  Voz hace pausa para tomar aire
T=1.0-2.2s: void_s empieza a acumularse
         → ok_time = True en T=2.2s

T=2.2-3.2s: _ok_time acumula hasta 1.0s
         → v_confirm sube
         → v cruza thr_on

T=3.2-3.75s: _t_on acumula 550ms
         → _on = True

T=3.8s:  BRAKE finalmente entra
         → 3.8 segundos después del evento musical
         → La audiencia ya está cantando desde hace 3 segundos
```

### Diagrama de Estados Posibles

```
                    ┌─────────────────────────────┐
                    │     BRAKE MUSICAL OCURRE    │
                    └─────────────────────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
              ▼                  ▼                  ▼
    ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
    │ Voz continúa    │ │ Silencio limpio │ │ Reverb residual │
    │ con consonantes │ │ (raro)          │ │ o ruido         │
    └─────────────────┘ └─────────────────┘ └─────────────────┘
              │                  │                  │
              ▼                  ▼                  ▼
    ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
    │ onsets          │ │ ok_time = True  │ │ onsets          │
    │ detectados      │ │ tras 1.2s       │ │ esporádicos     │
    │ constantemente  │ │                 │ │                 │
    └─────────────────┘ └─────────────────┘ └─────────────────┘
              │                  │                  │
              ▼                  ▼                  ▼
    ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
    │ BRAKE           │ │ BRAKE entra     │ │ BRAKE entra     │
    │ NUNCA ENTRA     │ │ ~3.1s tarde     │ │ ~4-6s tarde     │
    │                 │ │                 │ │ (intermitente)  │
    └─────────────────┘ └─────────────────┘ └─────────────────┘
```

### Resumen de Fuentes de Variabilidad

| Factor Variable | Efecto en BRAKE | Previsibilidad |
|-----------------|-----------------|----------------|
| **Contenido de voz** | Consonantes = onsets falsos | IMPREDECIBLE |
| **Reverberación** | Picos = onsets falsos | Depende de mezcla |
| **baseline_rms** | Determina ok_quiet | Depende de últimos 10s |
| **Ruido ambiente** | Variaciones = onsets | Depende de grabación |
| **Spectral content** | Modulación = flux alto | Depende de arreglo |

---

## CONCLUSIÓN FORENSE

### Diagnóstico Principal

**BRAKE falla intermitentemente porque:**

1. **`_detect_onsets()` es demasiado sensible** (L89-126)
   - Detecta consonantes de voz como golpes musicales
   - Detecta reverberación como transitorios
   - Cada detección resetea el contador de void_s

2. **`void_s = 1.2s` es el cuello de botella** (L216)
   - Requiere 1.2 segundos COMPLETOS sin ningún onset
   - Casi imposible cuando hay voz o efectos

3. **El acumulador `_ok_time` es frágil** (L227-231)
   - Decrece 2x más rápido de lo que crece
   - Un solo frame malo causa pérdida doble

4. **La histéresis `_t_on` no tiene memoria** (L278-284)
   - Requiere 550ms consecutivos sin interrupción
   - Un solo frame bajo umbral = reset total

### Por Qué Entra Tarde

La latencia de ~3 segundos es **estructural**, no un bug:
- void_s (1.2s) + confirm_s (1.0s) + hold_on (550ms) = 2.75s mínimo
- Con onsets intermedios, puede ser 4-6+ segundos

### Por Qué A Veces No Entra

El detector de onsets (`_detect_onsets`) interpreta contenido frecuente de audio (voz con consonantes, reverberación, ruido variable) como "golpes", reseteando continuamente el contador y previniendo que `ok_time` sea True.

---

*Análisis forense completado — Solo diagnóstico, sin propuestas de cambio*

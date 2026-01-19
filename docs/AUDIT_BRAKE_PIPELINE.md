# AUDITORÍA ESPECÍFICA: PIPELINE DE BRAKE

**Fecha:** 2025-12-16
**Branch:** claude/musical-analysis-audit-6WtQD
**Alcance:** Solo diagnóstico del pipeline BRAKE — Sin propuestas de cambio

---

## DEFINICIÓN MUSICAL CANÓNICA (Referencia)

> **BRAKE** = La música **pierde el golpe abruptamente**, la energía rítmica cae, la voz queda en primer plano, el DJ baja la música de golpe para que la gente cante.
>
> **BRAKE debe entrar rápido.** Una entrada tarde es peor que un falso positivo corto.

---

## TAREA 1 — ANALIZADORES DE BRAKE

### 1.1 BrakeAnalyzer (DAS) — `analyzers/brake.py`

#### Qué señal musical detecta REALMENTE

| Señal | Línea | Cómo funciona | Qué detecta |
|-------|-------|---------------|-------------|
| **Drop dB** | L200-201 | `drop_db = 10.0 * log10(eL/eS)` | Caída de energía (EMA larga vs corta) |
| **Silencio relativo** | L204 | `rms <= 0.35 * baseline_rms` | Nivel bajo vs baseline adaptativo |
| **Flux bajo** | L207-208 | `flux <= 0.12` | Ausencia de cambios espectrales |
| **Tiempo sin onsets** | L215-216 | `since_onset >= void_s` | **1.2 segundos sin ningún golpe** |

**Resultado:** BrakeAnalyzer detecta **SILENCIO PROLONGADO** + **AUSENCIA DE GOLPES POR 1.2s**, NO "pérdida abrupta del golpe".

#### Ventanas Temporales

| Componente | Valor Default | Propósito | Línea |
|------------|---------------|-----------|-------|
| `win_short` | **0.14s (140ms)** | EMA corta para energía instantánea | L43 |
| `win_long` | **1.20s** | EMA larga para baseline de comparación | L44 |
| `baseline_tau` | **10.0s** | Baseline adaptativo (muy lento) | L194 |
| `void_s` | **1.2s** | Tiempo mínimo SIN onsets | L46 |
| `confirm_s` | **1.0s** | Acumulador de confirmación | L48 |
| `smooth tau` | **120-200ms** | Suavizado del score VU | L238 |
| `hold_on` | **550ms** | Hold para transición OFF→ON | L50 |
| `hold_off` | **700ms** | Hold para transición ON→OFF | L51 |
| `thr_on` | **0.60** | Umbral de score para entrar | L54 |

#### Latencia Introducida (BrakeAnalyzer)

| Escenario | Latencia | Desglose |
|-----------|----------|----------|
| **Mínima teórica** | **~690ms** | win_short (140ms) + hold_on (550ms) |
| **Típica** | **~1.8s** | void_s (1.2s) + smooth (150ms) + hold_on (550ms) |
| **Máxima** | **~2.8s** | void_s (1.2s) + confirm_s (1.0s) + smooth + hold_on |

**Dominante:** `void_s = 1.2s` es el cuello de botella absoluto.

---

### 1.2 BreakSpotter — `analyzers/break_spotter.py`

#### Qué señal musical detecta REALMENTE

| Señal | Línea | Cómo funciona | Qué detecta |
|-------|-------|---------------|-------------|
| **Gap/Microcorte** | L170 | `gmin <= gap_ms <= gmax` | Silencio breve (80-240ms) |
| **Umbral dBFS** | L231-233 | `level < 10^(thdb/20)` | Nivel bajo con histéresis |

**Resultado:** BreakSpotter detecta **GAPS TERMINADOS** (retrospectivo, no predictivo).

#### Ventanas Temporales

| Componente | Valor Default | Propósito | Línea |
|------------|---------------|-----------|-------|
| `gmin` | **80ms** | Gap mínimo a detectar | L52 |
| `gmax` | **240ms** | Gap máximo a detectar | L53 |
| `thdb` | **-45 dBFS** | Umbral de silencio | L54 |
| `env_ms` | **10ms** | Ventana RMS | L55 |
| `hold` | **200ms** | Hold del evento | L56 |
| `smooth tau` | **~95ms** | Suavizado (smooth=0.25) | L262 |

#### Latencia Introducida (BreakSpotter)

| Escenario | Latencia | Desglose |
|-----------|----------|----------|
| **Mínima** | **~175ms** | gmin (80ms) + smooth (95ms) |
| **Típica** | **~340ms** | gmax/2 (120ms) + hold (200ms) |
| **Máxima** | **~540ms** | gmax (240ms) + hold (200ms) + smooth |

**Limitante:** El gap debe **TERMINAR** para detectarse (L164-178). No detecta el inicio del gap.

---

## TAREA 2 — MAPEO VS DEFINICIÓN MUSICAL

### Clasificación de Componentes

| Componente | Valor | Clasificación | Justificación |
|------------|-------|---------------|---------------|
| **BrakeAnalyzer.win_short** | 140ms | ✔️ **APORTA** | Detecta caída instantánea de energía |
| **BrakeAnalyzer.drop_db_req** | 12dB | ✔️ **APORTA** | Umbral de caída razonable |
| **BrakeAnalyzer.win_long** | 1.2s | ⚠️ **RETRASA** | Baseline lento para comparación |
| **BrakeAnalyzer.void_s** | **1.2s** | ❌ **CONTRADICE** | Espera 1.2s sin golpes = **pierde el momento** |
| **BrakeAnalyzer.confirm_s** | **1.0s** | ❌ **CONTRADICE** | Acumulador post-detección = **entrada tarde** |
| **BrakeAnalyzer.hold_on** | **550ms** | ❌ **EXCESIVO** | Medio segundo adicional post-score |
| **BrakeAnalyzer.smooth** | 120-200ms | ⚠️ **RETRASA** | Suavizado visual, pero agrega latencia |
| **BrakeAnalyzer.baseline_tau** | 10.0s | ⚠️ **HERENCIA** | Adaptación muy lenta, irrelevante para BRAKE rápido |
| **BrakeAnalyzer.thr_on** | 0.60 | ⚠️ **CONSERVADOR** | Requiere 60% de score antes de considerar |
| **BreakSpotter.gmin** | 80ms | ✔️ **APORTA** | Detecta gaps cortos |
| **BreakSpotter.gmax** | 240ms | ⚠️ **LIMITANTE** | Ignora gaps >240ms (típicos de BRAKE largo) |
| **BreakSpotter.hold** | 200ms | ✔️ **APORTA** | Mantiene el evento activo |

### Resumen de Clasificación

| Categoría | Componentes |
|-----------|-------------|
| ✔️ **Necesarios** | win_short, drop_db_req, gmin, hold (BreakSpotter) |
| ⚠️ **Excesivos/Retrasan** | win_long, smooth, baseline_tau, thr_on, gmax |
| ❌ **Contradictorios** | **void_s (1.2s)**, **confirm_s (1.0s)**, **hold_on (550ms)** |

---

## TAREA 3 — PUNTO EXACTO DE ENTRADA TARDE

### Secuencia Temporal del Pipeline

```
T=0ms     │ QUIEBRE MUSICAL OCURRE (golpe desaparece)
          │
T=0-140ms │ win_short detecta caída de energía ✓
          │ drop_db sube ✓
          │ ok_quiet puede ser True ✓
          │
T=140ms   │ ⚠️ PERO void_s BLOQUEA
          │ since_onset = 140ms
          │ void_s = 1200ms
          │ ok_time = FALSE ← L216
          │
T=140ms-  │ BrakeAnalyzer calcula v_raw
1200ms    │ v_raw = max(0.6*(drop+quiet), 0.6*ok_time, 0.5*flux)
          │ v_raw ≈ 0.6 máximo (sin ok_time)
          │
T=1200ms  │ ok_time = TRUE (por fin)
          │ v_raw sube
          │
T=1200ms- │ confirm_s acumula _ok_time ← L227-231
2200ms    │ _ok_time += dt cada frame
          │ v_confirm = _ok_time / 1.0s
          │
T=2200ms  │ v_confirm ≈ 1.0
          │ v_raw = 0.6*v_raw + 0.4*v_confirm ← L235
          │ v_raw ≈ 0.76
          │
T=2200ms- │ EMA suaviza _vu ← L239-240
2400ms    │ tau_ms = 120-200ms
          │ _vu crece lentamente hacia v_raw
          │
T=2400ms  │ _vu >= thr_on (0.60)
          │ Histéresis inicia ← L278-284
          │ _t_on += dt
          │
T=2400ms- │ hold_on acumula ← L281
2950ms    │ Espera _t_on >= 550ms
          │
T=2950ms  │ _on = TRUE ← L282
          │ BrakeAnalyzer reporta BRAKE
          │
T=2950ms+ │ StateManager procesa
          │ scores["brake"] = 0.5 o 1.0
          │ (si ambos analizadores ON)
          │
```

### Líneas Exactas del Bloqueo

| Línea | Archivo | Código | Efecto |
|-------|---------|--------|--------|
| **L216** | brake.py | `ok_time = (since_onset >= void_s)` | **Bloquea hasta 1.2s sin onsets** |
| **L227** | brake.py | `all_ok = ok_drop and ok_quiet and ok_flux and ok_time` | ok_time domina |
| **L229** | brake.py | `self._ok_time = min(10.0, self._ok_time + dt)` | Acumula solo si all_ok |
| **L234** | brake.py | `v_confirm = _ok_time / confirm_s` | Escala con confirm_s=1.0s |
| **L235** | brake.py | `v_raw = v_raw * 0.6 + v_confirm * 0.4` | confirm pesa 40% |
| **L281** | brake.py | `if self._t_on >= hold_on_s` | Espera 550ms adicionales |

### El Primer Instante Donde BRAKE Podría Entrar

**T = ~140-200ms** después del quiebre, cuando:
- `drop_db >= 12dB` ✓
- `ok_quiet = True` ✓
- `ok_flux = True` ✓

Pero **no entra** porque `ok_time = False` (void_s=1.2s no cumplido).

### Confirmación Que Ocurre DESPUÉS del Quiebre

| Confirmación | Tiempo Después del Quiebre | Propósito Declarado |
|--------------|---------------------------|---------------------|
| void_s | 1.2s | "Esperar que no haya onsets" |
| confirm_s | +1.0s (acumulado) | "Confirmar que se mantiene" |
| hold_on | +550ms | "Histéresis para evitar falsos positivos" |
| **TOTAL** | **~2.75s** | — |

---

## TAREA 4 — ROL DEL STATE_MANAGER

### Privilegios de BRAKE en StateManager

| Privilegio | Línea | Código | Efecto |
|------------|-------|--------|--------|
| Bypass cooldown | L473-474 | `if new_state != self.STATE_BRAKE: return False` | BRAKE ignora cooldown inter-estado |
| Bypass stability | L478 | `if new_state != self.STATE_BRAKE` | BRAKE ignora ventana de 180ms |
| Prioridad máxima | L422-423 | Evaluado primero en `_determine_next_state_responsive` | BRAKE > ATAQUE > GOLPE > BAJADA |
| Hold post-entrada | L68 | `"BRAKE": {"hard": 1.5, "priority": set()}` | Una vez en BRAKE, hold de 1.5s |

### Latencia Adicional del StateManager

| Componente | Valor | Aplica a BRAKE? |
|------------|-------|-----------------|
| `STABILITY_WINDOW_MS` | 180ms | ❌ NO (bypass L478) |
| `INTER_STATE_COOLDOWN_MS` | 0ms (V12.1) | ❌ NO (bypass L474) |
| `_ema_alpha` | 0.3 | ✓ SÍ (suaviza scores) |
| `BRAKE_THRESHOLD` | 0.65 | ✓ SÍ (umbral de score) |

### El Problema NO Está en StateManager

```python
# state_manager.py L422-423
if scores["brake"] >= BRAKE_THRESHOLD:  # 0.65
    return self.STATE_BRAKE
```

StateManager está **preparado** para BRAKE rápido:
- Bypass de cooldown ✓
- Bypass de stability window ✓
- Prioridad máxima ✓

**PERO** el `scores["brake"]` viene de los analizadores. Si:
- `BrakeAnalyzer._on = False` (por void_s)
- `BreakSpotter.card.is_on() = False` (gap no terminado)

Entonces `scores["brake"] = 0.0` y StateManager **no puede hacer nada**.

### Flujo de Score

```
BrakeAnalyzer._on ──┐
                    ├──► state_manager._calculate_scores_responsive()
BreakSpotter.is_on()─┘           │
                                 ▼
                    scores["brake"] = active / total
                                 │
                                 ▼
                    _scores_smooth["brake"] = EMA(scores["brake"], α=0.3)
                                 │
                                 ▼
                    if scores["brake"] >= 0.65: STATE_BRAKE
```

El cuello de botella está en `BrakeAnalyzer._on`, que depende de `void_s=1.2s`.

---

## RESUMEN EJECUTIVO

### Partes del Pipeline de BRAKE

| Componente | Necesario | Excesivo | Contradice Definición |
|------------|-----------|----------|----------------------|
| win_short (140ms) | ✔️ | | |
| drop_db_req (12dB) | ✔️ | | |
| win_long (1.2s) | | ⚠️ | |
| **void_s (1.2s)** | | | ❌ **PRINCIPAL** |
| **confirm_s (1.0s)** | | | ❌ |
| **hold_on (550ms)** | | ❌ | |
| smooth (120-200ms) | | ⚠️ | |
| thr_on (0.60) | | ⚠️ | |
| gmin (80ms) | ✔️ | | |
| gmax (240ms) | | ⚠️ | |

### Diagnóstico Final

**El pipeline actual de BRAKE detecta:**
> "Silencio prolongado de al menos 1.2 segundos sin ningún golpe, confirmado durante 1 segundo adicional, con histéresis de 550ms"

**La definición musical de BRAKE es:**
> "Pérdida abrupta del golpe donde la voz queda en primer plano"

**Contradicción fundamental:**
- La definición requiere **entrada rápida** (~100-300ms)
- El pipeline actual tiene **latencia mínima de ~2s**
- `void_s=1.2s` **garantiza** que BRAKE llegue tarde al momento musical

### Punto de Falla Principal

| Archivo | Línea | Código | Impacto |
|---------|-------|--------|---------|
| `brake.py` | **L216** | `ok_time = (since_onset >= void_s)` | Bloquea hasta void_s=1.2s |
| `brake.py` | **L46** | `void_s` default = 1.2 | Valor del parámetro |
| `brake.py` | **L227-235** | Acumulador confirm_s | +1.0s adicional |
| `brake.py` | **L281** | hold_on check | +550ms adicional |

---

*Auditoría generada automáticamente — Solo diagnóstico, sin propuestas de cambio*

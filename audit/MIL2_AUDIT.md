# AUDITORIA — Integracion MIL-2 (Music Intelligence Layer v2)

**Fecha:** 2026-03-01
**Branch base:** baseline/linux-foja-cero
**Modo:** SOLO AUDITORIA. Sin modificacion de codigo.
**Scope:** Analisis estructural completo del sistema 911-Fiesta-Core para integracion segura de MIL-2.

---

## 1. Punto optimo de insercion

### 1.1 Opciones evaluadas

| Opcion | Ubicacion | Viabilidad | Riesgo | Latencia |
|--------|-----------|------------|--------|----------|
| A | Dentro de AudioEngine (`engine_audio.py`) | BAJA | ALTO — callback de sounddevice es critico, no tolera carga extra | +15-40ms por bloque |
| B | Como nuevo modulo en AnalyzerService (junto a `analyzers/`) | MEDIA | MEDIO — se mezcla con analyzers que votan, MIL no vota | +0ms (corre en paralelo) |
| C | **Entre analyzers y StateManager** | **ALTA** | **BAJO** — punto de intercepcion limpio sin tocar ningun extremo | **+2-5ms** |
| D | Dentro de StateManager (`state_manager.py`) | MEDIA | MEDIO — contamina la maquina de estados con logica de ML | +3-8ms |
| E | Como wrapper previo a CueEngine | BAJA | ALTO — tarde en el pipeline, los scores ya estan decididos | +0ms pero inutil |

### 1.2 Recomendacion: Opcion C — Entre analyzers y StateManager

**Punto exacto de insercion en el pipeline:**

```
_process_modules_limited()  (main.py:3902)
    |
    v
[1] Todos los analyzers ejecutan process(block, sr)  (lineas 3924-3935)
    |
    v
[2] >>> MIL-2 SE INSERTA AQUI <<<
    |   - Lee los valores actuales de todos los module.card
    |   - Ejecuta feature_extractor → context_model → adaptive_engine
    |   - Modifica parametros del StateManager ANTES de su update()
    |
    v
[3] state_manager.update(modules_bajada, ..., modules_brake)  (linea 3952)
    |
    v
[4] CueEngine.update() lee get_state()/get_energy()
```

**Justificacion tecnica:**

1. **Minimo acoplamiento:** MIL no necesita modificar ningun analyzer ni el StateManager internamente. Solo necesita:
   - LEER: valores de `module.card` de cada analyzer (ya disponibles tras process())
   - ESCRIBIR: parametros del StateManager via setters publicos (nuevos, no existentes)

2. **Thread-safety preservada:** Todo corre en el hilo principal del QTimer `t_mod` (40ms). No se introduce ningun hilo nuevo para la ejecucion critica. El modelo LightGBM ejecuta inferencia en <2ms para vectores de 7 features.

3. **Latencia minima:** El overhead es la inferencia del modelo (~1-2ms) + smoothing (~0.1ms). El budget del tick de 40ms tiene margen suficiente.

4. **Determinismo garantizado:** LightGBM es determinista para la misma entrada. No hay randomness ni estado oculto.

### 1.3 Riesgo por thread-safety

| Aspecto | Riesgo | Mitigacion |
|---------|--------|------------|
| Lectura de module.card en hilo principal | NULO — ya se hace hoy | Mismo patron existente |
| Escritura a StateManager params | BAJO — single-threaded | Setters atomicos con clamp |
| Inferencia LightGBM | NULO — CPU-bound, sin I/O | Budget de 2ms < 40ms tick |
| StateMonitorWidget lee concurrentemente | BAJO — ya existe hoy sin locks | MIL no cambia esta dinamica |
| CueEngine thread lee get_state() | BAJO — ya existe race teorica | MIL no agrava; si se quiere proteger, Lock en get_state() |

### 1.4 Impacto en latencia

**Pipeline actual (sin MIL):**
```
Audio callback → Ring buffer:           23ms (blocksize 1024 @ 44.1kHz)
Ring buffer → Analyzers (get_recent):   0-5ms
Analyzers process():                    5-15ms (40+ analyzers)
StateManager.update():                  1-3ms
StateManager → CueEngine:              0-200ms (poll interval)
CueEngine → Avolites:                  60-500ms (queue + network)
TOTAL:                                  ~90-750ms
```

**Pipeline con MIL (+2-5ms):**
```
Audio callback → Ring buffer:           23ms
Ring buffer → Analyzers:                0-5ms
Analyzers process():                    5-15ms
>>> MIL-2 inferencia + adapt:          2-5ms <<<
StateManager.update():                  1-3ms
StateManager → CueEngine:              0-200ms
CueEngine → Avolites:                  60-500ms
TOTAL:                                  ~92-755ms (+0.7% worst case)
```

**Conclusion:** Impacto despreciable. El cuello de botella es CueEngine poll (200ms) y red Avolites, no el procesamiento.

---

## 2. Cambios necesarios (archivo por archivo)

### 2.1 Archivos NUEVOS a crear

| Archivo | Funcion | Dependencias |
|---------|---------|-------------|
| `music_intelligence/__init__.py` | Package init, kill-switch check | `os.environ` |
| `music_intelligence/feature_extractor.py` | Extrae features de analyzers → vector 7D | Lectura de `module.card` |
| `music_intelligence/context_model.py` | Wrapper LightGBM, predice contexto 7D | `lightgbm`, `numpy` |
| `music_intelligence/adaptive_engine.py` | Traduce vector contexto → ajustes SM | `state_manager` (setters) |
| `music_intelligence/mil_config.py` | Constantes: clamps, smoothing, defaults | Ninguna |
| `music_intelligence/mil_logger.py` | Logging comparativo (shadow mode) | `logging`, `json` |

### 2.2 Archivos EXISTENTES a modificar (cambios minimos)

#### `main.py` (3 cambios puntuales)

**Cambio 1 — Import condicional (cerca de linea 151):**
```python
# Despues de: from state_manager import StateManager
ENABLE_MIL = int(os.environ.get("ENABLE_MIL", "0"))
if ENABLE_MIL:
    from music_intelligence import MusicIntelligenceLayer
```

**Cambio 2 — Instanciacion condicional (cerca de linea 557):**
```python
# Despues de: self.state_manager = StateManager(...)
self.mil = None
if ENABLE_MIL:
    try:
        self.mil = MusicIntelligenceLayer(self.state_manager)
        print("[MIL] Music Intelligence Layer v2 ACTIVADO")
    except Exception as e:
        print(f"[MIL] FALLO al inicializar: {e} — sistema continua sin MIL")
        self.mil = None
```

**Cambio 3 — Invocacion en pipeline (main.py:3949, ANTES de state_manager.update):**
```python
# Despues de todos los module.process(block, sr)
# ANTES de state_manager.update()
if self.mil is not None:
    try:
        self.mil.tick(
            modules_bajada=self._get_active_modules(self.modules_bajada),
            modules_golpe=self._get_active_modules(self.modules_golpe),
            modules_ataque=self._get_active_modules(self.modules_ataque),
            modules_brake=self._get_active_modules(self.modules_brake),
            kick_detector=getattr(self, 'kick_detector', None),
            energy_detector=self.energy_detector,
            bpm_detector=getattr(self, 'bpm_detector', None),
        )
    except Exception as e:
        print(f"[MIL] Error en tick: {e}")
```

#### `state_manager.py` (1 cambio: agregar setters con clamp)

Agregar metodos publicos para adaptar parametros. **NO modificar logica interna.**

```python
# Nuevos metodos en StateManager (al final de la clase):
def set_adaptive_params(self, params: dict):
    """
    MIL-2: Recibe parametros adaptativos con clamp de seguridad.
    Si MIL esta desactivado, este metodo nunca se llama.
    Todos los valores se clamean al rango seguro.
    """
    # Ejemplo de parametros aceptados:
    # hold_factor: 0.5..2.0 (multiplica min_hold_seconds base)
    # stability_factor: 0.5..2.0 (multiplica STABILITY_WINDOW_MS base)
    # hysteresis_factor: 0.5..2.0 (multiplica hysteresis_margin base)
    pass  # Implementacion en fase 2
```

#### `module_config.py` (0 cambios)

No requiere modificacion. MIL lee pero no escribe MODULE_CONFIG.

#### `requirements.txt` (1 linea)

```
lightgbm>=4.0.0
```

### 2.3 Archivos que NO se tocan

| Archivo | Razon |
|---------|-------|
| `engine_audio.py` | MIL no interfiere con captura de audio |
| `cue_engine.py` | MIL no modifica como se ejecutan cues |
| `avolites_config.py` | MIL no toca transporte |
| `timers.py` | MIL no agrega timers, usa el tick existente |
| `union_bridge.py` | MIL no modifica anti-repeticion |
| `analyzers/*` | NINGUN analyzer se modifica |
| `mod_*.py` | NINGUN modulo de cue se modifica |
| `tempo/kick_detector.py` | MIL solo lee, no escribe |

---

## 3. Riesgos tecnicos

### 3.1 Oscilacion de parametros

**Riesgo: ALTO si no se mitiga.**

Si MIL ajusta `hold_duration` cada 40ms sin smoothing, puede causar:
- Ciclos de acortar hold → transicion prematura → alargar hold → transicion bloqueada → acortar...
- Resonancia con la hysteresis matrix del StateManager

**Mitigacion obligatoria:**
1. **EMA con alpha bajo (0.05-0.15)** en TODOS los parametros adaptativos. Esto limita la velocidad de cambio a ~1-3 segundos de convergencia.
2. **Rate limiting:** Maximo 1 cambio efectivo por segundo (aunque MIL corra cada 40ms, solo aplica si delta > epsilon).
3. **Clamp absoluto:** Cada parametro tiene min/max fijo. Ejemplo:
   ```
   hold_factor:      [0.6, 1.8]  (nunca <60% ni >180% del valor base)
   stability_factor: [0.5, 2.0]
   hysteresis_factor:[0.7, 1.5]
   ```
4. **Derivada maxima:** `|param(t) - param(t-1)| < max_delta` por tick.

### 3.2 Interaccion con dedup 600ms

**Riesgo: MEDIO.**

Si MIL reduce `hold_duration` demasiado, el StateManager puede intentar cambiar de estado mas rapido que el dedup window de 600ms del TitanQueue. Esto causaria:
- CueEngine intenta FIRE cue → TitanQueue lo deduplica → cue no se dispara
- Estado cambia pero iluminacion no responde

**Mitigacion:**
- `hold_duration_min` NUNCA puede ser menor a `DEDUP_WINDOW_MS + CueEngine.interval = 600+200 = 800ms`
- MIL DEBE respetar este floor en adaptive_engine.py

### 3.3 Conflicto con hold actual

**Riesgo: MEDIO.**

El StateManager tiene `_hold_config` hardcodeado:
```python
"BAJADA":     {"hard": 0.3, "priority": {"ATAQUE", "BRAKE"}}
"BASE_GOLPE": {"hard": 0.6, "priority": {"ATAQUE", "BRAKE"}}
"ATAQUE":     {"hard": 0.8, "priority": {"BRAKE"}}
"BRAKE":      {"hard": 1.5, "priority": set()}
```

Si MIL modifica `min_hold_seconds` pero no coordina con `_hold_config["hard"]`, se producen inconsistencias.

**Mitigacion:**
- MIL SOLO modifica `min_hold_seconds` (que es la base).
- `_hold_config` se recalcula como `base * factor` internamente.
- BRAKE hard hold NUNCA se reduce por debajo de 1.0s (safety floor).

### 3.4 Inconsistencias entre GUI y headless

**Riesgo: BAJO.**

El sistema actual no tiene un modo headless formal (todo corre via PySide6/QTimer). Sin embargo:
- La API REST (`api_server.py`) expone estado via endpoints
- Si MIL adapta parametros, la API deberia reflejar los nuevos valores

**Mitigacion:**
- Agregar endpoint `/api/mil/status` que exponga:
  - Ultimo vector de contexto predicho
  - Parametros adaptativos actuales
  - Estado del kill-switch
- StateMonitorWidget ya lee via get_status() — los parametros adaptados se reflejaran automaticamente si se agregan al dict de status.

### 3.5 Impacto en rendimiento CPU

**Riesgo: BAJO.**

Mediciones esperadas de MIL por tick:
| Componente | CPU time | Notas |
|-----------|----------|-------|
| Feature extraction | 0.3-0.8ms | Lee ~40 module.card values, calcula estadisticas |
| LightGBM predict | 0.5-1.5ms | 1 prediccion, 7 features → 7 outputs |
| Adaptive engine | 0.1-0.3ms | Clamp + smoothing + apply |
| **Total MIL** | **1-2.5ms** | **Budget tick: 40ms → 6% overhead** |

**Peor caso con CPU cargada:**
- 40+ analyzers: ~15ms
- MIL: ~3ms (pessimistic)
- StateManager: ~3ms
- Total: ~21ms / 40ms = 52.5% utilization → margen seguro

**Mitigacion adicional:**
- Si tick excede 35ms, MIL skip (cooldown 1 tick).
- Metrica de self-monitoring: `mil_tick_ms` exportada en stats.

### 3.6 Fallo de carga del modelo LightGBM

**Riesgo: MEDIO (en deployment).**

Si el archivo .pkl/.txt del modelo no existe, esta corrupto, o LightGBM no esta instalado:

**Mitigacion (ya cubierta por diseno):**
- `ENABLE_MIL=0` por defecto → sistema nunca intenta cargar
- Import con try/except → fallo silencioso con log
- `self.mil = None` → todos los `if self.mil is not None:` se saltan
- Resultado: **sistema se comporta IDENTICO al actual si MIL falla**

### 3.7 Modelo desactualizado o con drift

**Riesgo: BAJO (operacional, no tecnico).**

Si el modelo fue entrenado con datos de genero X pero se usa en genero Y.

**Mitigacion:**
- Shadow mode (Fase 1) detecta drift midiendo divergencia entre predicciones y comportamiento real
- Clamp absoluto limita dano incluso si las predicciones son erroneas
- Kill-switch instantaneo via `ENABLE_MIL=0`

---

## 4. Arquitectura propuesta

### 4.1 Estructura de directorios

```
music_intelligence/
    __init__.py              # Package + kill-switch gate
    feature_extractor.py     # Analyzers → feature vector 7D
    context_model.py         # LightGBM wrapper (predict only)
    adaptive_engine.py       # Context vector → SM param adjustments
    mil_config.py            # Constantes, clamps, defaults
    mil_logger.py            # Shadow-mode logging comparativo
    models/
        context_v1.txt       # Modelo LightGBM serializado
```

### 4.2 Flujo de datos MIL

```
                    ┌─────────────────┐
                    │ ANALYZERS (40+) │
                    │ ya ejecutados   │
                    └────────┬────────┘
                             │ module.card values
                             v
                    ┌─────────────────┐
                    │ FEATURE         │
                    │ EXTRACTOR       │
                    │                 │
                    │ Extrae:         │
                    │  - kick_strength│    ┌───────────┐
                    │  - rhy_density  │───>│ CONTEXT   │
                    │  - regularity   │    │ MODEL     │
                    │  - spec_balance │    │ (LightGBM)│
                    │  - energy_trend │    │           │
                    │  - breakdown_p  │    │ predict() │
                    │  - buildup_p    │    └─────┬─────┘
                    └─────────────────┘          │ context vector 7D
                                                 v
                                        ┌─────────────────┐
                                        │ ADAPTIVE        │
                                        │ ENGINE          │
                                        │                 │
                                        │ Traduce vector  │
                                        │ a ajustes:      │
                                        │  - hold_factor  │
                                        │  - stab_factor  │
                                        │  - hyst_factor  │
                                        │  - basegolpe_m  │
                                        │                 │
                                        │ Aplica:         │
                                        │  - EMA smoothing│
                                        │  - Clamp ranges │
                                        │  - Rate limit   │
                                        └────────┬────────┘
                                                 │ clamped params
                                                 v
                                        ┌─────────────────┐
                                        │ STATE MANAGER   │
                                        │ set_adaptive_   │
                                        │ params()        │
                                        │                 │
                                        │ (logica interna │
                                        │  NO cambia)     │
                                        └─────────────────┘
```

### 4.3 Feature Extractor — Mapeo desde analyzers existentes

| Feature MIL | Source analyzer(s) | Extraccion |
|-------------|-------------------|------------|
| `kick_strength` | KickDetector (tempo/) | `last_energy / last_threshold` ratio |
| `rhythmic_density` | YesHits + AccentCatcher | `(yes_hits.card.value + accent.card.value) / 2` |
| `regularity` | PatternLock + GrooveKeeper | `pattern_lock.card.value * groove.card.value` |
| `spectral_balance` | DeepListener + HighSilence | `deep.card.value - high_silence.card.value` → [-1,1] |
| `energy_trend` | EnergyDetector | `delta(energy_rms, window=10 frames)` → [-1,1] |
| `breakdown_prob` | BreakSpotter + RampDown + WidebandBlackout | `max(break.card.value, ramp.card.value, wbb.card.value)` |
| `buildup_prob` | RampUp + PercussiveBuild + BurstContinuity | `max(ramp_up.card.value, perc.card.value, burst.card.value)` |

### 4.4 Adaptive Engine — Mapeo de parametros

| Parametro SM | Context features usados | Logica de adaptacion |
|-------------|------------------------|---------------------|
| `min_hold_seconds` | regularity, breakdown_prob | Alta regularidad → hold corto (musica estable). Alto breakdown → hold largo (proteger transicion) |
| `STABILITY_WINDOW_MS` | rhythmic_density, regularity | Alta densidad + alta regularidad → window corto (respuesta rapida). Baja regularidad → window largo (evitar falsos) |
| `hysteresis_margin` | energy_trend, spectral_balance | Trend ascendente → hysteresis baja (facilitar subida). Trend descendente → hysteresis alta (resistir bajada prematura) |
| `basegolpe_mode` | kick_strength, rhythmic_density | kick_strength > 0.7 → modo kick. Sino → modo density |

### 4.5 Kill-switch y fallback

```python
# music_intelligence/__init__.py
import os

ENABLE_MIL = int(os.environ.get("ENABLE_MIL", "0"))

if ENABLE_MIL:
    try:
        from .feature_extractor import FeatureExtractor
        from .context_model import ContextModel
        from .adaptive_engine import AdaptiveEngine

        class MusicIntelligenceLayer:
            def __init__(self, state_manager):
                self.fe = FeatureExtractor()
                self.cm = ContextModel()
                self.ae = AdaptiveEngine(state_manager)
                self._enabled = True

            def tick(self, **kwargs):
                if not self._enabled:
                    return
                try:
                    features = self.fe.extract(**kwargs)
                    context = self.cm.predict(features)
                    self.ae.apply(context)
                except Exception as e:
                    print(f"[MIL] tick error: {e}")
                    # NO desactivar — puede ser error transitorio

            def disable(self):
                self._enabled = False
                self.ae.restore_defaults()  # restaurar params originales

    except ImportError as e:
        print(f"[MIL] Cannot import: {e} — MIL disabled")
        MusicIntelligenceLayer = None
else:
    MusicIntelligenceLayer = None
```

---

## 5. Plan de implementacion faseado

### Fase 0 — Preparacion (sin cambios funcionales)

**Objetivo:** Infraestructura y validacion de que el punto de insercion funciona.

**Tareas:**
1. Crear directorio `music_intelligence/` con `__init__.py` vacio
2. Agregar `ENABLE_MIL=0` a documentacion de env vars
3. Crear test unitario que verifique que el sistema arranca identico con y sin `ENABLE_MIL`
4. Crear benchmark de latencia del tick de 40ms actual (baseline)

**Archivos tocados:** Ninguno en produccion. Solo tests/ y docs/.
**Riesgo:** CERO.

### Fase 1 — Shadow Mode (logging sin efecto)

**Objetivo:** MIL corre, predice, loguea, pero NO modifica ningun parametro.

**Tareas:**
1. Implementar `feature_extractor.py` — lee module.card, genera vector 7D
2. Implementar `context_model.py` — carga modelo LightGBM, predice
3. Implementar `mil_logger.py` — escribe CSV con:
   - timestamp, features[7], predictions[7], state_actual, energy_actual
4. Agregar los 3 cambios a main.py (import, init, tick)
5. `adaptive_engine.py` en modo SHADOW: calcula ajustes pero NO los aplica
6. Validar que con `ENABLE_MIL=1`:
   - El sistema se comporta IDENTICO
   - El CSV se genera correctamente
   - La latencia del tick no supera 5ms adicionales

**Archivos tocados:** main.py (3 cambios minimos), music_intelligence/* (nuevos).
**Riesgo:** BAJO — MIL corre pero es no-operativo.

### Fase 2 — Aplicacion gradual (un parametro)

**Objetivo:** Activar adaptacion de UN solo parametro con blend conservador.

**Tareas:**
1. Implementar `set_adaptive_params()` en state_manager.py
2. Activar adaptive_engine para `min_hold_seconds` SOLAMENTE
3. Blend: `effective = 0.8 * default + 0.2 * mil_suggested`
4. Logging comparativo: parametro default vs parametro MIL vs parametro effective
5. Validar que las metricas de transicion (transitions, blocked_by_hold, etc.) se mantienen en rango razonable

**Archivos tocados:** state_manager.py (1 metodo nuevo), adaptive_engine.py.
**Riesgo:** BAJO — un solo parametro con 80% del valor default.

### Fase 3 — Expansion controlada

**Objetivo:** Activar todos los parametros adaptativos con blend incremental.

**Tareas:**
1. Activar `STABILITY_WINDOW_MS` adaptativo
2. Activar `hysteresis_margin` adaptativo
3. Activar `basegolpe_mode` adaptativo
4. Incrementar blend gradualmente: 0.2 → 0.4 → 0.6 → 0.8
5. En cada incremento, validar con musica real (3 generos: techno, house, ambient)
6. Monitorear CPU, latencia, transition quality

**Archivos tocados:** adaptive_engine.py, mil_config.py.
**Riesgo:** MEDIO — multiples parametros cambian simultaneamente.

### Fase 4 — Produccion

**Objetivo:** MIL activo por defecto con monitoring.

**Tareas:**
1. Cambiar default `ENABLE_MIL=1`
2. Agregar endpoint API `/api/mil/status`
3. Agregar widget MIL a StateMonitorWidget
4. Documentar procedimiento de rollback (ENABLE_MIL=0)
5. Agregar alertas si MIL tick excede budget

**Archivos tocados:** main.py (default), api/, ui/.
**Riesgo:** Controlado — kill-switch siempre disponible.

---

## 6. Plan de validacion

### 6.1 Simulacion offline

**Objetivo:** Validar MIL contra grabaciones de audio sin sistema en vivo.

**Metodo:**
1. Capturar 10+ minutos de audio real (techno, house, ambient, dnb) con el sistema actual
2. Almacenar snapshots de module.card values cada 40ms (CSV)
3. Replay offline: alimentar feature_extractor con snapshots → generar predicciones
4. Comparar predicciones con estados reales observados
5. Metricas:
   - Accuracy de breakdown_prob vs BAJADA entries reales
   - Accuracy de buildup_prob vs ATAQUE entries reales
   - Correlacion kick_strength vs KickDetector real

**Criterio de exito:** Correlacion > 0.7 en features principales.

### 6.2 Logging comparativo (A/B Shadow)

**Objetivo:** Demostrar que MIL en shadow mode no degrada nada.

**Metodo:**
1. Correr sistema 30 minutos con `ENABLE_MIL=0` (control)
2. Correr sistema 30 minutos con `ENABLE_MIL=1` en shadow (tratamiento)
3. Comparar:
   - Distribucion de transiciones por estado
   - Frecuencia de blocked_by_hold / blocked_by_cooldown
   - Latencia tick (p50, p95, p99)
   - CPU usage

**Criterio de exito:** Diferencia <5% en todas las metricas.

### 6.3 Metricas de transicion (Fase 2+)

**Objetivo:** Validar que la adaptacion mejora la calidad de transiciones.

**Metricas:**
| Metrica | Definicion | Rango aceptable |
|---------|-----------|-----------------|
| transition_rate | Cambios de estado / minuto | 8-25 (actual: 10-20) |
| false_positive_rate | ATAQUE entries sin transiente real | <15% |
| hold_utilization | % tiempo en hold efectivo | 30-60% |
| adaptation_range | Rango real de parametros MIL | Dentro de clamps |
| mil_tick_ms_p95 | Latencia p95 del tick MIL | <3ms |

### 6.4 Kill-switch testing

**Objetivo:** Verificar que el kill-switch funciona instantaneamente.

**Test plan:**
1. **Test A — Boot con MIL off:**
   - `ENABLE_MIL=0` → sistema arranca normal → verificar MIL=None
2. **Test B — Boot con MIL on:**
   - `ENABLE_MIL=1` → sistema arranca → verificar MIL activo
3. **Test C — Runtime disable:**
   - `ENABLE_MIL=1` → sistema corriendo → llamar `mil.disable()` → verificar params restaurados
4. **Test D — Fallo de modelo:**
   - Renombrar archivo de modelo → `ENABLE_MIL=1` → sistema arranca sin MIL
5. **Test E — Fallo de libreria:**
   - Desinstalar lightgbm → `ENABLE_MIL=1` → ImportError capturado → sistema normal
6. **Test F — Fallo en tick:**
   - Inyectar excepcion en context_model.predict() → verificar que state_manager.update() sigue ejecutandose normalmente

**Criterio de exito:** TODOS los tests pasan. El sistema es IDENTICO al actual en todos los modos de fallo.

### 6.5 Stress testing

**Objetivo:** Verificar estabilidad bajo carga extrema.

**Escenarios:**
1. **CPU saturada:** Correr con 100% CPU artificial → verificar que MIL skip funciona
2. **Audio extremo:** Señal de ruido blanco a full volume → verificar que features no explotan
3. **Silence prolongado:** 5 minutos sin audio → verificar que MIL no oscila
4. **Transiciones rapidas:** Musica con cambios cada 2s → verificar que clamp/smoothing previene oscilacion

---

## Apendice A — Resumen de constantes criticas

| Constante | Valor actual | Rango MIL permitido | Floor/Ceiling absoluto |
|-----------|-------------|---------------------|----------------------|
| min_hold_seconds | 0.8s (FAST) | 0.5s - 1.4s | 0.5s / 2.0s |
| STABILITY_WINDOW_MS | 120ms | 60ms - 240ms | 60ms / 300ms |
| hysteresis_margin | 0.04 | 0.02 - 0.08 | 0.02 / 0.10 |
| cooldown_seconds | 0.2s | NO adaptativo | Fijo |
| ATAQUE_MARGIN_MIN | 0.12 | NO adaptativo | Fijo |
| BRAKE_ENTRY_THRESHOLD | 0.52 | NO adaptativo | Fijo |
| ema_alpha | 0.5 | 0.3 - 0.7 | 0.2 / 0.8 |
| DEDUP_WINDOW_MS | 600ms | NO adaptativo | Fijo |

**Principio:** MIL NUNCA adapta parametros de seguridad (BRAKE, ATAQUE margin, cooldown, dedup).

## Apendice B — Mapa de threads actual

```
[THREAD: Main / Qt Event Loop]
  ├── QTimer t_mod (40ms) → _frame_tick() → analyzers.process() → [MIL.tick()] → SM.update()
  ├── QTimer t_vu (50ms) → VU meters
  ├── QTimer t_scope (80ms) → waveform display
  ├── QTimer t_energy (200ms) → energy_detector.process()
  ├── QTimer t_bpm (250ms) → BPM display update
  ├── QTimer t_groups (300ms) → group UI update
  └── QTimer t_status (400ms) → status display

[THREAD: sounddevice callback]
  └── engine_audio._callback() → ring buffers (lock-protected)

[THREAD: CueEngine daemon]
  └── _loop() → CueEngine.update() cada 200ms → lee SM.get_state()

[THREAD: BPMDetector daemon]
  └── analysis_loop() → BPM analysis (independent)

[THREAD: TitanQueue worker]
  └── Queue consumer → HTTP to Avolites console

MIL CORRE EN: Thread Main (QTimer t_mod) — NO introduce threads nuevos.
```

## Apendice C — Flags de entorno necesarios

| Variable | Default | Descripcion |
|----------|---------|-------------|
| `ENABLE_MIL` | `0` | Kill-switch global. 0=desactivado, 1=activado |
| `MIL_SHADOW` | `1` | Cuando MIL activo: 1=solo logging (no aplica), 0=aplica ajustes |
| `MIL_BLEND` | `0.2` | Factor de blend: 0.0=100% default, 1.0=100% MIL |
| `MIL_LOG_PATH` | `""` | Path para CSV de shadow logging. Vacio=no loguear |
| `MIL_MODEL_PATH` | `music_intelligence/models/context_v1.txt` | Path al modelo LightGBM |
| `MIL_MAX_TICK_MS` | `5` | Budget maximo por tick. Si excede, skip siguiente tick |

---

*Fin de auditoria. Documento generado por analisis estatico del codebase sin modificacion de archivos.*

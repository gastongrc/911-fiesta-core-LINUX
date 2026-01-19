# AUDITORÍA MUSICAL — 911 FIESTA CORE

**Fecha:** 2025-12-16
**Branch:** claude/musical-analysis-audit-6WtQD
**Baseline:** main (post-limpieza)

---

## 1. LISTADO COMPLETO DE ANALIZADORES MUSICALES ACTIVOS

### 1.1 MOTOR REAL (Votan en StateManager)

| Archivo | Clase/Función | Qué Mide | Ventana Temporal | Estado Destino |
|---------|---------------|----------|------------------|----------------|
| `analyzers/yes_hits.py:7` | `YesHits` | Transitorios via RMS + derivada | 250ms bloque, EMA smooth 0.18, hold 50ms, refractario 15ms | BASE_GOLPE |
| `analyzers/dynamic_pulse.py:36` | `DynamicPulse` | Variación MAD/mediana de picos | 2.0s ventana, smooth 80-600ms, hold 120ms | BASE_GOLPE |
| `analyzers/flow_monitor.py:138` | `FlowMonitor` | Densidad de onsets + gaps | 3.0s ventana, smooth 80-400ms, hold 120ms | BASE_GOLPE |
| `analyzers/no_hits.py:30` | `NoHits` | Ausencia de transitorios (calma) | 250ms bloque, refractario 40ms, tau 60-800ms | BAJADA |
| `analyzers/deep_listener.py:58` | `DeepListener` | Calma en graves 30-220Hz | FFT 512, buffer ~10ms, AGC 200 frames, tau 20-600ms | BAJADA |
| `analyzers/break_spotter.py:30` | `BreakSpotter` | Microcortes (gaps 20-2000ms) | env_ms 10ms, hold 200ms, smooth 80-600ms | BRAKE |
| `analyzers/brake.py:33` | `BrakeAnalyzer` | Dead air + drop dB + flux + onsets | win_short 0.14s, win_long 1.2s, confirm 1.0s, baseline 10s | BRAKE |

### 1.2 MÓDULOS LEGACY (Solo UI, NO votan)

| Archivo | Clase | Propósito | Destino Nominal |
|---------|-------|-----------|-----------------|
| `analyzers/high_silence.py` | `HighSilence` | Silencio alta frecuencia | BAJADA_LEGACY |
| `analyzers/soft_peaks.py` | `SoftPeaks` | Picos suaves | BAJADA_LEGACY |
| `analyzers/rhythm_void.py` | `RhythmVoid` | Vacío rítmico | BAJADA_LEGACY |
| `analyzers/hf_swell.py` | `HfSwell` | Hinchazón HF | ATAQUE_LEGACY |
| `analyzers/hi_roll.py` | `HiRoll` | Detección hi-hat/roll | ATAQUE_LEGACY |
| `analyzers/snare_roll.py` | `SnareRoll` | Redoble snare | ATAQUE_LEGACY |

---

## 2. ANALIZADORES QUE IMPACTAN DECISIONES

### 2.1 Pipeline de Votación BASE_GOLPE

**Punto de consumo:** `main.py:2412-2416` → `state_manager.update()`

```
modules_golpe activos (V12):
  └── YesHits.detected (flag_name="YES_HITS")
  └── DynamicPulse._on (flag_name="DYNAMIC_PULSE")
  └── FlowMonitor._on (flag_name="FLOW_MONITOR")
```

**Variable consumida:** `module.card.is_on()` o atributo `.detected`

**Umbral:** `state_manager.py` → `GOLPE_THRESHOLD = 0.30` (3/10 votos mínimo)

### 2.2 Pipeline de Votación BAJADA

**Punto de consumo:** `main.py:2412-2416` → `state_manager.update()`

```
modules_bajada activos (V12):
  └── NoHits.card.is_on()
  └── DeepListener.is_on
```

**Umbral:** `state_manager.py` → `BAJADA_THRESHOLD = 0.50`

### 2.3 Pipeline de Votación BRAKE

**Punto de consumo:** `main.py:2391-2395` (procesamiento separado)

```
modules_brake:
  └── BrakeAnalyzer._on
  └── BreakSpotter.card.is_on()
```

**Umbrales:**
- `BRAKE_ENTRY = 0.52`
- `BRAKE_SUSTAINED = 0.48`
- `BRAKE_EXIT = 0.35`

### 2.4 StateManager — Punto de Decisión Final

**Archivo:** `state_manager.py`

**Método clave:** `_determine_next_state_responsive(scores)`

**Scores consumidos:**
```python
_scores_smooth = {
    "bajada": float,      # Agregación modules_bajada
    "base_golpe": float,  # Agregación modules_golpe
    "ataque": float,      # Agregación modules_ataque (si existe)
    "brake": float        # Agregación modules_brake
}
```

**Prioridad de estados (implícita):**
1. BRAKE (dominante)
2. ATAQUE
3. BASE_GOLPE
4. BAJADA (default)

---

## 3. CÓDIGO FANTASMA

### 3.1 Analizadores Cuyos Resultados NO Se Usan

| Archivo | Clase | Evidencia |
|---------|-------|-----------|
| `analyzers/rhythm_tracker.py` | `RhythmTracker` | No está en modules_* de main.py |
| `analyzers/rhythm_highlighter.py` | `RhythmHighlighter` | No instanciado en main.py |
| `analyzers/beat_steady.py` | `BeatSteady` | No instanciado en main.py |
| `analyzers/accent_catcher.py` | `AccentCatcher` | No instanciado en main.py |
| `analyzers/pulse_finder.py` | `PulseFinder` | Solo wrapper usado |
| `analyzers/pulse_finder_wrapper.py` | `PulseFinderAnalyzer` | No en modules_golpe activos |
| `analyzers/energy_cliff.py` | `EnergyCliff` | No instanciado |
| `analyzers/ramp_down.py` | `RampDown` | No instanciado |
| `analyzers/ramp_up.py` | `RampUp` | No instanciado |
| `analyzers/loop_dissolver.py` | `LoopDissolver` | No instanciado |
| `analyzers/ambient_confirmator.py` | `AmbientConfirmator` | No instanciado |
| `analyzers/texture_cleaner.py` | `TextureCleaner` | No instanciado |
| `analyzers/cadence_spotter.py` | `CadenceSpotter` | No instanciado |
| `analyzers/pre_steady_coherence.py` | - | No instanciado |
| `analyzers/pattern_lock.py` | `PatternLock` | No instanciado |
| `analyzers/percussive_build.py` | `PercussiveBuild` | No instanciado |
| `analyzers/groove_keeper.py` | `GrooveKeeper` | No instanciado |
| `analyzers/mid_range_finder.py` | `MidRangeFinder` | No instanciado |
| `analyzers/wideband_blackout.py` | `WidebandBlackout` | No instanciado |
| `analyzers/burst_sharpness.py` | `BurstSharpness` | No instanciado (legacy) |
| `analyzers/burst_continuity.py` | `BurstContinuity` | No instanciado |
| `analyzers/dynamic_flattener.py` | `DynamicFlattener` | No instanciado |
| `analyzers/bpm_detector.py` | `BPMDetector` | No conectado a decisión de estado |
| `analyzers/super_analyzer.py` | `SuperAnalyzer` | No conectado a decisión de estado |

### 3.2 Analizadores Calculados Pero Puenteados

| Archivo | Clase | Situación |
|---------|-------|-----------|
| `analyzers/high_silence.py` | `HighSilence` | En `modules_bajada_legacy`, se procesa pero NO se pasa a `state_manager.update()` |
| `analyzers/soft_peaks.py` | `SoftPeaks` | En `modules_bajada_legacy`, procesado para UI solamente |
| `analyzers/rhythm_void.py` | `RhythmVoid` | En `modules_bajada_legacy`, procesado para UI solamente |
| `analyzers/hf_swell.py` | `HfSwell` | En `modules_ataque_legacy`, procesado para UI solamente |
| `analyzers/hi_roll.py` | `HiRoll` | En `modules_ataque_legacy`, procesado para UI solamente |
| `analyzers/snare_roll.py` | `SnareRoll` | En `modules_ataque_legacy`, procesado para UI solamente |

**Evidencia en código (`main.py:2397-2408`):**
```python
# V12: Process legacy modules (for UI display only, not for voting)
legacy_modules = [
    *self._get_active_modules(self.modules_bajada_legacy),
    *self._get_active_modules(self.modules_golpe_legacy),
    *self._get_active_modules(self.modules_ataque_legacy),
    *self._get_active_modules(self.modules_brake_legacy)
]
for module in legacy_modules:
    module.process(block, sr)  # ← Solo procesamiento, NO votación
```

---

## 4. PIPELINE REAL DE DECISIÓN MUSICAL

### 4.1 Diagrama de Flujo

```
                         ┌─────────────────────────┐
                         │   ENTRADA DE AUDIO      │
                         │   (sounddevice stream)  │
                         └───────────┬─────────────┘
                                     │
                         ┌───────────▼─────────────┐
                         │    engine_audio.py      │
                         │    AudioEngine          │
                         │  • DC-Block             │
                         │  • HP 30Hz              │
                         │  • Notch 50/60Hz        │
                         │  • Gate Schmitt         │
                         │  Buffer: 10s circular   │
                         └───────────┬─────────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    │                │                │
            ┌───────▼───────┐ ┌──────▼───────┐ ┌─────▼──────┐
            │ 250ms bloque  │ │ 50ms scope   │ │ 50ms ener. │
            │ (módulos)     │ │ (waveform)   │ │ (energy)   │
            └───────┬───────┘ └──────────────┘ └─────┬──────┘
                    │                                │
    ┌───────────────┼───────────────┐               │
    │               │               │               │
┌───▼────┐    ┌─────▼─────┐   ┌─────▼─────┐   ┌─────▼─────┐
│ BAJADA │    │BASE_GOLPE │   │  BRAKE    │   │  ENERGY   │
│modules │    │ modules   │   │ modules   │   │ DETECTOR  │
├────────┤    ├───────────┤   ├───────────┤   ├───────────┤
│NoHits  │    │YesHits    │   │Brake      │   │RMS+AGC    │
│Deep    │    │DynPulse   │   │AnalyzerDAS│   │EMA        │
│Listener│    │FlowMon    │   │BreakSpot  │   │Percentil  │
└───┬────┘    └─────┬─────┘   └─────┬─────┘   └─────┬─────┘
    │               │               │               │
    │    ┌──────────┴───────────────┴───────┐      │
    │    │                                  │      │
    └────►      STATE_MANAGER.update()      ◄──────┘
              state_manager.py:L~200
         ┌──────────────────────────────────┐
         │  _calculate_scores_responsive()  │
         │                                  │
         │  ┌─────────────────────────────┐ │
         │  │ scores = {                  │ │
         │  │   "bajada": 0.0-1.0,        │ │
         │  │   "base_golpe": 0.0-1.0,    │ │
         │  │   "ataque": 0.0-1.0,        │ │
         │  │   "brake": 0.0-1.0          │ │
         │  │ }                           │ │
         │  └──────────────┬──────────────┘ │
         │                 │                │
         │  _apply_light_smoothing()        │
         │  EMA alpha = 0.3                 │
         │                 │                │
         │  ┌──────────────▼──────────────┐ │
         │  │_determine_next_state_       │ │
         │  │responsive(scores)           │ │
         │  │                             │ │
         │  │ if brake >= 0.52: BRAKE     │ │
         │  │ elif ataque >= 0.52: ATAQUE │ │
         │  │ elif golpe >= 0.30: GOLPE   │ │
         │  │ elif bajada >= 0.50: BAJADA │ │
         │  └──────────────┬──────────────┘ │
         │                 │                │
         │  _can_change_state_responsive()  │
         │  • Stability window: 180ms       │
         │  • Hysteresis matrix             │
         └─────────────────┬────────────────┘
                           │
               ┌───────────▼───────────┐
               │      CUE_ENGINE       │
               │   cue_engine.py       │
               │                       │
               │ state = sm.get_state()│
               │ energy = sm.get_energy│
               │                       │
               │ → m_break.run()       │
               │ → m_ataque.run()      │
               │ → m_bg.run()          │
               │ → m_bajada.run()      │
               │ → m_move.run()        │
               └───────────┬───────────┘
                           │
               ┌───────────▼───────────┐
               │    AVOLITES TITAN     │
               │    fire_cue()/kill_cue│
               └───────────────────────┘
```

### 4.2 Cadencias de Procesamiento

**Definidas en `main.py:~100`:**

| Componente | Cadencia | Bloque Audio |
|------------|----------|--------------|
| `modules` | ~20ms | 250ms (0.25s) |
| `scope` (waveform) | ~20ms | 50ms (0.05s) |
| `energy` | ~20ms | 50ms |
| `cues` | ~20ms | N/A |
| `vu` | ~50ms | N/A |
| `status` | ~100ms | N/A |

---

## 5. LATENCIAS ACUMULADAS

### 5.1 Desglose por Etapa

| Etapa | Latencia | Buffer/Ventana | Fuente |
|-------|----------|----------------|--------|
| **AudioEngine buffer** | ~5ms | BLOCKSIZE callback | `engine_audio.py` |
| **DC-Block + HP 30Hz** | <1ms | IIR | `engine_audio.py` |
| **Gate envelope** | 12ms attack / 180ms release | Schmitt | `engine_audio.py:~80` |
| **get_recent(0.25)** | 250ms | Buffer history | `main.py:2305` |
| **YesHits EMA smooth** | ~18% factor | EMA | `yes_hits.py:18` |
| **YesHits hold** | 50ms | Timer | `yes_hits.py:20` |
| **YesHits refractario** | 15ms | Timer | `yes_hits.py:17` |
| **DynamicPulse window** | 2000ms | Analysis | `dynamic_pulse.py:95` |
| **DynamicPulse smooth** | 80-600ms tau | EMA | `dynamic_pulse.py:337-342` |
| **DynamicPulse hold** | 120ms | Timer | `dynamic_pulse.py:101` |
| **FlowMonitor window** | 3000ms | Analysis | `flow_monitor.py:172` |
| **FlowMonitor smooth** | 80-400ms tau | EMA | `flow_monitor.py:319` |
| **FlowMonitor hold** | 120ms | Timer | `flow_monitor.py:178` |
| **NoHits tau smooth** | 60-800ms | EMA | `no_hits.py:161` |
| **DeepListener FFT** | 512 samples (~10ms @ 48kHz) | Buffer | `deep_listener.py:88` |
| **DeepListener AGC** | 200 frames (~4s) | History | `deep_listener.py:104` |
| **DeepListener tau** | 20-600ms | EMA | `deep_listener.py:366` |
| **BrakeAnalyzer win_short** | 140ms | EMA | `brake.py:43` |
| **BrakeAnalyzer win_long** | 1200ms | EMA | `brake.py:44` |
| **BrakeAnalyzer baseline** | 10000ms | EMA | `brake.py:196` |
| **BrakeAnalyzer confirm** | 1000ms | Acumulador | `brake.py:48` |
| **BrakeAnalyzer hold ON** | 550ms | Timer | `brake.py:50` |
| **BrakeAnalyzer hold OFF** | 700ms | Timer | `brake.py:51` |
| **StateManager EMA** | α=0.3 (~70ms equiv) | Score smooth | `state_manager.py` |
| **StateManager stability** | 180ms | Timer | `state_manager.py` |
| **CueEngine interval** | 120-200ms | Loop | `cue_engine.py:168` |

### 5.2 Latencias Totales por Estado (Estimadas)

| Transición | Latencia Mínima | Latencia Típica | Latencia Máxima |
|------------|-----------------|-----------------|-----------------|
| **→ BASE_GOLPE** | ~270ms | ~400ms | ~700ms |
| **→ BAJADA** | ~350ms | ~600ms | ~1200ms |
| **→ BRAKE** | ~450ms | ~800ms | ~2000ms |
| **BRAKE →** (salida) | ~700ms | ~1000ms | ~1500ms |

### 5.3 Buffers Circulares Activos

| Componente | Tamaño | Propósito |
|------------|--------|-----------|
| `AudioEngine._buffer_raw` | 10s | Historia cruda |
| `AudioEngine._buffer_gated` | 10s | Historia gateada |
| `BrakeAnalyzer._flux_history` | 150 frames (~3s) | Spectral flux |
| `DeepListener._agc_hist` | 200 frames (~4s) | AGC normalización |
| `DeepListener._env_hist` | 32 frames | Crest factor |
| `NoHits._hits_history` | 10 samples | Suavizado temporal |

---

## 6. RESUMEN EJECUTIVO

### Analizadores Activos (7)
- **BASE_GOLPE:** YesHits, DynamicPulse, FlowMonitor
- **BAJADA:** NoHits, DeepListener
- **BRAKE:** BrakeAnalyzer, BreakSpotter

### Analizadores Legacy (6) — Procesados pero NO votan
- HighSilence, SoftPeaks, RhythmVoid (BAJADA)
- HfSwell, HiRoll, SnareRoll (ATAQUE)

### Código Fantasma (23 archivos)
- 23 analizadores definidos en `analyzers/` pero nunca instanciados
- BPMDetector y SuperAnalyzer no conectados a decisión de estado

### Latencia Total del Pipeline
- **Mínima:** ~250-450ms (audio → estado)
- **Típica:** ~400-800ms
- **Máxima:** ~1000-2000ms (especialmente BRAKE)

### Punto de Decisión Final
`state_manager.py` → `_determine_next_state_responsive()` usando scores suavizados por EMA con umbrales:
- BRAKE: 0.52
- ATAQUE: 0.52
- BASE_GOLPE: 0.30
- BAJADA: 0.50

---

*Auditoría generada automáticamente - Solo diagnóstico, sin propuestas de cambio*

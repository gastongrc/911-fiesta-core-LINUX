# MUSIC STRUCTURE ENGINE - Plan de reemplazo
## Arquitectura, flujo de datos e integracion

**Fecha**: 2026-03-05
**Reemplaza**: MIL-Lite (music_intelligence_lite/)

---

## 1. Que se elimina

| Componente | Accion |
|------------|--------|
| `music_intelligence_lite/` (directorio completo) | ELIMINAR |
| `config/mil_lite.json` | ELIMINAR |
| `config/mil_lite_config.py` | ELIMINAR |
| Imports MIL-Lite en `main.py` | REEMPLAZAR con imports MSE |
| `_mil_*` atributos en `state_manager.py` | REEMPLAZAR con `_mse_*` |
| Widget MUSIC INTELLIGENCE en Monitor | REEMPLAZAR con MUSIC STRUCTURE |

## 2. Que se mantiene

| Componente | Razon |
|------------|-------|
| `engine_audio.py` | Sin cambios. MSE usa `get_recent()` existente |
| Todos los analyzers en `analyzers/` | Sin cambios. Siguen votando como siempre |
| `state_manager.py` estructura | Se modifica minimamente, no se reescribe |
| `_process_modules_limited()` | Se modifica para agregar tick MSE |
| Cadencia de 33ms para modules | MSE opera en la misma cadencia |

---

## 3. Arquitectura nueva

```
                          engine_audio.py
                               |
                    get_recent(0.25) -> stereo float32 (N,2)
                               |
                    sanitize_audio() -> mono float32 (N,)
                               |
            +------------------+-------------------+
            |                                      |
     [Analyzers existentes]              [MusicStructureEngine]
     module.process(block, sr)           mse.process(block, sr)
            |                                      |
     card.is_on() votos                  MusicStructureState
            |                                      |
            +------------------+-------------------+
                               |
                    state_manager.update(
                        modules_bajada, modules_golpe,
                        modules_ataque, modules_brake
                    )
                               |
                    score_final = 0.65 * analyzer_score
                                + 0.35 * mse_probability
                    (solo si mse.confidence >= 0.4)
```

## 4. Modulo nuevo: `core/music_structure_engine/`

```
core/music_structure_engine/
    __init__.py
    music_structure_engine.py    # Clase principal MusicStructureEngine
    beat_engine.py               # Tempo, beat phase, beat confidence
    energy_engine.py             # Energia multibanda + tendencia
    transient_engine.py          # Densidad de transientes
    phrase_engine.py             # Frase musical (bar, phrase, position)
    drop_engine.py               # Prediccion de drops (build/pre-drop/drop)
    state_inference.py           # Combinacion final -> probabilidades de estado
    buffers.py                   # Ring buffers circulares para memoria temporal
    math_utils.py                # Funciones DSP compartidas
```

## 5. Flujo de datos interno

```
audio_block (mono float32, ~11025 samples, sr=44100)
    |
    +-> BeatEngine.process(block, sr)
    |       -> tempo, beat_phase, beat_confidence, beat_index
    |
    +-> EnergyEngine.process(block, sr)
    |       -> energy_level, energy_trend, low/mid/high energy
    |
    +-> TransientEngine.process(block, sr)
    |       -> transient_density, transient_spike
    |
    +-> PhraseEngine.update(beat_engine_state)
    |       -> bar_index, phrase_index, phrase_position, phrase_boundary_prob
    |
    +-> DropEngine.update(energy_state, transient_state, phrase_state)
    |       -> drop_state (NONE/BUILD/PRE_DROP/DROP)
    |
    +-> StateInference.infer(beat, energy, transient, phrase, drop)
            -> P_bajada, P_base, P_ataque, P_brake
            -> suggested_state, confidence
```

## 6. Memoria temporal (buffers circulares)

| Buffer | Ventana | Tick ~40ms | Capacidad |
|--------|---------|------------|-----------|
| beat_memory | 16 s | ~400 slots | Onset envelope + autocorrelation |
| energy_memory | 8 s | ~200 slots | RMS + bandas |
| transient_memory | 2 s | ~50 slots | Picos transientes |
| spectral_memory | 8 s | ~200 slots | Spectral flux |

## 7. Integracion con StateManager

### 7.1 Nuevo metodo en StateManager

```python
def update_music_structure(self, music_state):
    """Recibe MusicStructureState del MSE."""
    self._mse_state = music_state
```

### 7.2 Blend de scores

En `_calculate_scores_responsive()`, reemplazar la multiplicacion MIL-Lite con:

```python
# Reemplaza: scores[k] *= self._mil_weights.get(k, 1.0)
if self._mse_state and self._mse_state.confidence >= 0.4:
    mse_probs = {
        "bajada": self._mse_state.P_bajada,
        "base_golpe": self._mse_state.P_base,
        "ataque": self._mse_state.P_ataque,
        "brake": self._mse_state.P_brake,
    }
    for k in scores:
        scores[k] = 0.65 * scores[k] + 0.35 * mse_probs.get(k, 0.0)
```

### 7.3 Integracion en main.py

En `_process_modules_limited()`:

```python
# Reemplaza: self.mil_lite.tick(...)
if self.music_structure_engine is not None:
    self.music_structure_engine.process(block, sr)
    mse_state = self.music_structure_engine.get_state()
    if hasattr(self.state_manager, 'update_music_structure'):
        self.state_manager.update_music_structure(mse_state)
```

## 8. Monitor UI

Reemplazar widget MUSIC INTELLIGENCE por MUSIC STRUCTURE:

```
+-----------------------------------+
| MUSIC STRUCTURE                   |
+-----------------------------------+
| Tempo     128.0 BPM               |
| Beat      3/4  phase=0.72         |
| Phrase    2/4  pos=0.45            |
| Energy    0.65  trend=RISING       |
| Transient 0.42  density            |
| State     BASE_GOLPE  conf=0.78   |
| Drop      BUILD                    |
+-----------------------------------+
```

## 9. Performance

| Componente | CPU estimado |
|------------|-------------|
| BeatEngine (FFT + autocorr) | < 4% |
| EnergyEngine (RMS + bandas) | < 2% |
| TransientEngine (onset) | < 2% |
| PhraseEngine (contadores) | < 0.5% |
| DropEngine (reglas) | < 0.5% |
| StateInference (aritmetica) | < 0.5% |
| **Total** | **< 10%** |

Objetivo: < 12% CPU total.

## 10. Por que resuelve el problema

| Problema actual | Como lo resuelve MSE |
|----------------|---------------------|
| Kick debil | EnergyEngine analiza multibanda, no depende del kick |
| Groove mid/high | BeatEngine usa spectral flux full-band |
| Sincopas | BeatEngine con phase tracking sigue el groove real |
| Transiciones suaves | EnergyEngine.trend detecta rampas graduales |
| Sin anticipacion | DropEngine + PhraseEngine predicen cambios estructurales |
| Sin memoria | Buffers de 2-16s dan contexto temporal real |
| Sin ritmo | BeatEngine calcula tempo + fase + confianza |

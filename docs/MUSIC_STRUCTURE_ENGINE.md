# Music Structure Engine (MSE) — Technical Documentation

## Overview

The Music Structure Engine (MSE) is a deterministic audio analysis module that replaces
the MIL-Lite system. It processes raw audio to extract musical structure information:
tempo, beat phase, energy profiles, transient density, phrase position, and drop prediction.

It uses only DSP and statistical methods. No machine learning, no trained models, no
heavy dependencies. Only numpy + standard Python.

**Location**: `core/music_structure_engine/`

---

## Architecture

```
audio_block (mono float32, ~11025 samples @ 44100 Hz)
    |
    +-> BeatEngine        -> tempo, beat_phase, beat_confidence, beat_index
    +-> EnergyEngine      -> energy_level, energy_trend, low/mid/high
    +-> TransientEngine   -> transient_density, transient_spike
    |
    +-> PhraseEngine      -> bar_index, phrase_index, phrase_position, boundary_prob
    |       (uses BeatEngine output)
    |
    +-> DropEngine        -> drop_state (NONE/BUILD/PRE_DROP/DROP)
    |       (uses EnergyEngine + TransientEngine + PhraseEngine output)
    |
    +-> StateInference    -> P_bajada, P_base, P_ataque, P_brake
            (combines all engines)
            -> suggested_state, confidence
```

All engines are stateful with circular buffers providing temporal memory.

---

## Modules

### buffers.py

Ring buffers for temporal memory.

- **RingBuffer**: Fixed-capacity circular buffer for float scalars. O(1) push, O(n) read.
- **RingBuffer2D**: Same but stores float vectors (rows).

Used by all engines to maintain sliding windows of past analysis results.

### math_utils.py

Shared DSP functions:

- `rms(x)`: Root mean square of array
- `spectral_flux(prev_mag, curr_mag)`: Half-wave rectified spectral flux (only positive changes)
- `onset_envelope_frame(block, sr, hop)`: Compute onset strength envelope via spectral flux. Uses 1024-sample Hann-windowed FFT with 512-sample hop.
- `autocorrelate(x, max_lag)`: Normalized autocorrelation via FFT (zero-padded)
- `bandpass_energy(block, sr, lo_hz, hi_hz)`: Energy in a frequency band using FFT magnitude
- `ema(prev, curr, alpha)`: Single-step exponential moving average

### beat_engine.py — Tempo + Beat Tracking

**Strategy**: Full-band spectral flux onset detection + autocorrelation.

1. Compute onset envelope via spectral flux (1024 FFT, 512 hop) — works with ALL
   frequency content, not just kick drum
2. Store onsets in 16-second ring buffer (~1400 frames at ~86 Hz onset rate)
3. Every 8 ticks (~320ms), autocorrelate onset buffer to find dominant period
4. Convert lag to BPM with octave correction (prefer 85-165 BPM range)
5. Track beat phase via sample counting

**BPM range**: 70-180 BPM (search range), octave-corrected to 85-165.

**Why it works with weak kick**: Spectral flux is computed over the FULL spectrum.
A hi-hat pattern, snare rhythm, or synth stab all produce onset energy. The
autocorrelation finds the dominant periodicity regardless of which frequency band
carries the beat.

**Output**: `tempo`, `beat_phase` [0,1), `beat_confidence` [0,1], `beat_index` (int)

### energy_engine.py — Multiband Energy + Trend

Three frequency bands:
- Low: 20-250 Hz (bass, kick)
- Mid: 250-4000 Hz (vocals, snare, most instruments)
- High: 4000-16000 Hz (hi-hats, cymbals, air)

Plus overall RMS energy.

**Trend detection**: Compares mean energy of recent first-half vs second-half over a
50-tick window (~2s). If the difference exceeds a threshold, reports RISING or FALLING.

**Memory**: 8 seconds (200 ticks).

**Output**: `energy_level`, `energy_trend` (RISING/FALLING/STABLE), `low_energy`,
`mid_energy`, `high_energy`

### transient_engine.py — Transient Density + Spikes

- **Density**: Counts threshold crossings (|sample| > 0.15) per second, averaged over
  2-second buffer
- **Spike**: Detects sudden RMS jumps (current/previous > 3x)

**Memory**: 2 seconds (50 ticks).

**Output**: `transient_density`, `transient_spike` (bool)

### phrase_engine.py — Musical Phrase Tracking

Assumes standard dance music structure:
- 4 beats per bar
- 4 bars per phrase (16 beats per phrase)

Tracks beat increments from BeatEngine and maintains:
- `bar_index` [0..3]: beat within current bar
- `phrase_index` [0..3]: bar within current phrase
- `phrase_position` [0, 1): smooth position within phrase

**Phrase boundary probability**: Gaussian-like function that peaks when `phrase_position`
is near 0.0 or 1.0 (within ~2.4 beats of a phrase boundary).

**Memory**: 64 beats of energy history at beat boundaries.

**Output**: `beat_index`, `bar_index`, `phrase_index`, `phrase_position`,
`phrase_boundary_probability`

### drop_engine.py — Drop Prediction

State machine with 4 states:

```
NONE -> BUILD -> PRE_DROP -> DROP -> NONE
```

Transitions:
- **NONE -> BUILD**: energy rising + transient density > 5 + energy > 0.05
- **BUILD -> PRE_DROP**: build sustained > 1s + near phrase boundary + energy grew > 30%
- **BUILD -> DROP**: transient spike during build (direct drop without pre-drop)
- **PRE_DROP -> DROP**: transient spike OR phrase boundary crossed
- **DROP -> NONE**: after 2s hold time

**Output**: `drop_state`, `drop_confidence` [0,1]

### state_inference.py — Final State Probabilities

Combines all engine outputs into probabilities for the 4 system states:

| State | Key indicators |
|-------|---------------|
| BAJADA | Low energy, falling trend, few transients, no clear beat |
| BASE_GOLPE | Moderate energy, beat present, stable trend |
| ATAQUE | High energy, rising trend, many transients, drop context |
| BRAKE | Falling energy above minimum, phrase boundary, low transients |

Probabilities are normalized to sum to 1.0.

**Confidence**: Margin between top-2 probabilities + beat confidence factor.

**Output**: `MusicStructureState` dataclass with all fields.

---

## Integration with StateManager

### Score blending

In `_calculate_scores_responsive()`:

```python
score_final[k] = 0.65 * analyzer_score[k] + 0.35 * mse_probability[k]
```

Only active when `mse_state.confidence >= 0.4`. Below that threshold, analyzers
operate alone (100% weight).

### Data flow

```
main.py _process_modules_limited():
    1. audio block -> analyzers (as before)
    2. audio block -> MusicStructureEngine.process(block, sr)
    3. MSE state -> state_manager.update_music_structure(mse_state)
    4. state_manager.update(modules...) — now blends MSE probabilities
```

### Monitor UI

The MUSIC STRUCTURE widget in Monitor tab shows:
- Tempo (BPM)
- Beat (bar position + phase + confidence)
- Phrase (phrase position)
- Energy (level + trend with color coding)
- Transient density
- Suggested state (color-coded) + confidence
- Drop prediction (color-coded state)

---

## Why This Solves the Musical Problem

### Problem: Kick-dependent detection

**Before**: Analyzers relied on low-frequency transients (kick). Weak kick = no detection.

**After**: BeatEngine uses full-band spectral flux. A hi-hat pattern at 8kHz produces
onset energy just like a kick at 80Hz. The autocorrelation finds the dominant period
regardless of frequency content.

### Problem: No memory

**Before**: Each analyzer tick was independent. 250ms window with no context.

**After**: Ring buffers provide 2-16 seconds of history. Energy trends are computed over
2 seconds. Tempo estimation uses 16 seconds of onset data. Phrase tracking maintains
position across hundreds of beats.

### Problem: No anticipation

**Before**: System could only react to events after they happened.

**After**: DropEngine predicts drops by detecting builds (energy rising + transient
increase). PhraseEngine tracks position within 16-beat phrases, enabling anticipation
of structural boundaries. The phrase_boundary_probability signal rises BEFORE the
boundary arrives.

### Problem: Latin/syncopated rhythms

**Before**: Rigid detection windows missed off-beat patterns.

**After**: BeatEngine's autocorrelation naturally finds the dominant periodicity even
with syncopation. The onset envelope captures ALL rhythmic activity, not just
on-beat events. Phase tracking follows the actual groove.

---

## Performance

| Component | Estimated CPU |
|-----------|--------------|
| BeatEngine (FFT + autocorrelation every 8 ticks) | < 4% |
| EnergyEngine (RMS + 3 band FFTs) | < 2% |
| TransientEngine (threshold counting) | < 2% |
| PhraseEngine (integer arithmetic) | < 0.5% |
| DropEngine (state machine rules) | < 0.5% |
| StateInference (arithmetic) | < 0.5% |
| **Total** | **< 10%** |

Key optimizations:
- BeatEngine only recomputes tempo every 8 ticks (~320ms), not every tick
- Ring buffers use numpy arrays with O(1) push
- FFT sizes are power-of-2 (1024 for onset, auto-padded for autocorrelation)
- No memory allocation in hot path (pre-allocated buffers)

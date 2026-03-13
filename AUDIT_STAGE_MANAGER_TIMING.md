# AUDIO SYSTEM AUDIT — Stage / Structure Decision Pipeline

## Date: 2026-03-13
## Scope: Why the Stage Manager anticipates musical transitions

---

## 1. Full Audio Decision Pipeline

```
Audio Input (sounddevice, 44100 Hz, block=1024)
       │
       ▼
┌─────────────────────────────────────┐
│  AudioEngine (engine_audio.py)      │
│  DC Block → HP 10Hz → Gate          │
│  Ring buffer: 3s raw + 3s gated     │
│  Gate: Schmitt trigger (hysteresis) │
└──────────────┬──────────────────────┘
               │
       ▼ _frame_tick() (~33ms)
               │
    ┌──────────┴──────────┐
    │                     │
    ▼                     ▼
Kick Detection       _process_modules_limited()
(mod_basegolpe)       (250ms audio window)
    │                     │
    │           ┌─────────┴─────────┐
    │           │                   │
    │           ▼                   ▼
    │   Analyzer Modules     MusicStructureEngine
    │   (vote per state)     (MSE probabilities)
    │           │                   │
    │           └─────────┬─────────┘
    │                     │
    │                     ▼
    │            StateManager.update()
    │            ┌────────────────────────────────┐
    │            │ 1. Calculate scores             │
    │            │    (45% analyzer + 55% MSE)     │
    │            │ 2. EMA smooth (alpha=0.5)       │
    │            │ 3. Light stability buffer (2f)  │
    │            │ 4. Determine candidate          │
    │            │ 5. Validate (hold/cooldown/     │
    │            │    hysteresis/stability window)  │
    │            │ 6. Change state → dispatch       │
    │            └────────────────────────────────┘
    │                     │
    └──────────┬──────────┘
               │
               ▼
    Module Dispatch (CueEngine)
    ATAQUE  → C37/C38/C39
    BAJADA  → C10-27 (position+color)
    BASE_GOLPE → FX family cues
    BRAKE   → (handled by analyzer)
```

---

## 2. Role of Stage vs Structure Analysis

### Stage Analysis = Analyzer Modules (vote-based)

The analyzer modules are threshold-based detectors that each produce a binary ON/OFF vote:
- **Bajada modules**: Detect low energy / calm passages
- **Golpe modules** (10 flags): Detect rhythmic hits — YES_HITS, ACCENT_CATCHER, GROOVE_KEEPER, PATTERN_LOCK, CADENCE_SPOTTER, FLOW_MONITOR, DYNAMIC_PULSE, PULSE_FINDER, RHYTHM_HIGHLIGHTER, BURST_SHARPNESS
- **Ataque modules**: Detect high energy / attack passages
- **Brake modules** (DeadAirSentinel): Detect dead air / sudden drops

Score = `active_modules / total_modules` (ratio 0.0–1.0)

### Structure Analysis = Music Structure Engine (MSE, probability-based)

The MSE runs five sub-engines on each audio block:

| Sub-engine | Output | Purpose |
|---|---|---|
| BeatEngine | tempo, beat_phase, beat_confidence | Rhythmic tracking |
| EnergyEngine | energy_level, energy_trend, 3-band | Energy profile |
| TransientEngine | transient_density, transient_spike | Hit detection |
| PhraseEngine | phrase_position, phrase_boundary_probability | Musical phrasing |
| DropEngine | drop_state (NONE/BUILD/PRE_DROP/DROP) | Drop detection |

These feed into `StateInference` which produces `P_bajada, P_base, P_ataque, P_brake` (normalized probabilities).

### Which Has Priority?

**MSE dominates at 55% weight** when its confidence ≥ 0.4:
```python
effective_score = 0.45 * analyzer_score + 0.55 * mse_probability
```

This is a critical finding. The MSE uses **predictive features** (energy trends, transient spikes, drop state, phrase boundaries) that inherently look forward. The analyzer modules are more reactive (threshold crossings on current values). By giving MSE 55% weight, the system is biased toward anticipation.

---

## 3. State Machine of Stage Manager

### States
```
BAJADA       — Low energy, calm (default/initial)
BASE_GOLPE   — Moderate energy, groove, rhythmic
ATAQUE       — High energy, attack
BRAKE        — Dead air / sudden energy drop
```

### Priority Order (hardcoded in `_determine_next_state_responsive`)
```
BRAKE > ATAQUE > BASE_GOLPE > BAJADA
```

### Decision Flow
```
1. If currently ATAQUE and persistence ≥ 2/3 → stay ATAQUE
2. If brake_score ≥ 0.65 → BRAKE
3. If ataque_score ≥ 0.68 AND (clean_rise OR already ATAQUE) → ATAQUE
4. If base_golpe_score ≥ 0.30 AND persistence ≥ 2/3 → BASE_GOLPE
5. If bajada_score ≥ 0.35 AND sustained_drop ≥ 2/3 → BAJADA
6. Tie-breaker within 0.03 margin → least-used state
7. Otherwise → keep current state
```

---

## 4. Transition Conditions

### ATAQUE → BAJADA
1. ATAQUE persistence drops below 2/3 frames
2. BAJADA score ≥ 0.35 with sustained drop ≥ 2/3 frames
3. Must pass: hold_remaining = 0 (min_hold × 1.2 = **0.96s**)
4. Must pass: cooldown_remaining = 0 (0.2s after leaving ATAQUE)
5. Must pass: hysteresis (bajada must exceed ataque + margin)
6. Must pass: stability window (120ms pending)

**Anticipation risk**: BAJADA threshold is only 0.35 and requires just 2 frames (~66ms). If energy starts declining while still clearly in ATAQUE territory, the MSE's "FALLING" trend detection can push P_bajada high enough within 2 frames.

### ATAQUE → BASE_GOLPE
1. ATAQUE persistence drops below 2/3
2. BASE_GOLPE score ≥ 0.30 with persistence ≥ 2/3
3. Same hold/cooldown/hysteresis/stability checks
4. Peak lock (0.18s) must expire

**Anticipation risk**: BASE_GOLPE threshold is extremely low (0.30 = 3/10 votes). With MSE blending at 55%, even moderate P_base values can push the effective score above 0.30.

### BASE_GOLPE → BAJADA
1. BASE_GOLPE score drops below thresholds
2. BAJADA score ≥ 0.35 with sustained drop 2/3
3. Hold: min_hold × 0.6 = **0.48s**
4. No cooldown (only ATAQUE/BRAKE exits trigger cooldown)

**Anticipation risk**: BASE_GOLPE hold is only 0.48s — very short. Energy trend going to "FALLING" immediately boosts P_bajada by +0.25, which after normalization and MSE blending can exceed 0.35 within 1-2 frames of energy decline starting.

### BASE_GOLPE → BRAKE
1. Brake score ≥ 0.65
2. BRAKE bypasses stability window
3. BRAKE bypasses inter-state cooldown
4. Hold: min_hold × 0.6 = 0.48s must expire

**Anticipation risk**: DeadAirSentinel has its own 1.0s confirmation accumulator, so BRAKE itself is actually well-guarded. However, MSE's P_brake can spike when it detects FALLING trend + low transient density, contributing 55% toward the brake score even before the actual dead air condition is confirmed.

---

## 5. Timing and Confirmation Mechanisms

### What EXISTS:

| Mechanism | Value | Where |
|---|---|---|
| EMA smoothing | alpha=0.5 | `state_manager.py:336` |
| Stability buffer | 2 frames (~66ms) | `state_manager.py:430-446` |
| Stability window | 120ms | `state_manager.py:647-658` |
| ATAQUE persistence | 3-frame deque | `state_manager.py:101,338-340` |
| BASE_GOLPE persistence | 3-frame deque, ≥2 required | `state_manager.py:108,348,598-600` |
| BAJADA sustained drop | 3-frame deque, ≥2 required | `state_manager.py:109,349,601-603` |
| Hold times | ATAQUE: 0.96s, BRAKE: 0.96s, GOLPE: 0.48s, BAJADA: 0.32s | `state_manager.py:818-829` |
| Cooldown after ATAQUE/BRAKE | 0.2s | `state_manager.py:72` |
| Hysteresis margin | 0.04 (flat) | `state_manager.py:738-740` |
| ATAQUE margin check | 0.12 over second score | `state_manager.py:660-671` |
| ATAQUE peak lock | 0.18s | `state_manager.py:822` |
| Global lock | 0.12s | `state_manager.py:815` |
| Kick debounce | 150ms | `mod_basegolpe.py` |
| DeadAirSentinel confirm | 1.0s accumulation | `analyzers/brake.py` |

### What is MISSING or INSUFFICIENT:

| Missing Mechanism | Impact |
|---|---|
| **No minimum state duration** | BAJADA hold is only 0.32s, BASE_GOLPE only 0.48s — states can change extremely fast |
| **No confirmation window for MSE trend changes** | EnergyEngine trend flips on a slope threshold of 0.03 over 50 ticks — single trend change immediately affects all scores |
| **Ultra Stability Layer DISABLED** | Sprint 6 global stability checks are commented out (lines 708-722) due to causing "false BAJADA retention" |
| **Inter-state cooldown = 0ms** | No cooldown between any state transitions (set to 0 for "musical flow") |
| **EMA alpha too fast** | 0.5 means each new sample is 50% of the smoothed value — barely any smoothing |
| **Persistence windows too short** | 3-frame deques at ~33ms cadence = only ~100ms of history |
| **No phrase-aware gating** | Transitions happen mid-phrase without waiting for phrase boundaries |

### Where Transitions Occur Immediately:

1. **`_determine_next_state_responsive` line 591**: BRAKE check has no persistence requirement — a single frame with brake score ≥ 0.65 is enough to select BRAKE as candidate
2. **`_determine_next_state_responsive` line 586-588**: ATAQUE persistence check keeps ATAQUE alive, but once persistence drops to 1/3, ATAQUE is immediately eligible to change
3. **`_can_change_state_responsive` line 648**: BRAKE bypasses stability window entirely — goes straight to state change

---

## 6. Root Cause Analysis: Why the System Anticipates Transitions

### Cause 1: MSE Energy Trend is Predictive (PRIMARY)

`energy_engine.py:67-86`: Trend detection uses a 50-tick (~2s) window, comparing the mean of the first half vs second half. A slope > 0.03 = RISING, < -0.03 = FALLING.

**Problem**: This detects the *beginning* of a trend, not its completion. When music starts to build toward a peak, the trend flips to RISING almost immediately. The energy level is still low (still in BASE_GOLPE territory), but P_ataque gets +0.20 from `RISING` trend. Combined with even modest transient activity, P_ataque can reach 0.40-0.50, which after MSE blending (55%) pushes the effective ataque score above 0.68.

**Same problem in reverse**: When a peak starts to decline, trend flips to FALLING, boosting P_bajada by +0.25 even though energy is still high.

### Cause 2: MSE Dominates at 55% (AMPLIFIER)

`state_manager.py:425-426`:
```python
scores[k] = 0.45 * scores[k] + 0.55 * mse_probs.get(k, 0.0)
```

The MSE probabilities are derived from **instantaneous features** (energy level, trend, transient density, spike detection) that react to micro-changes. By weighting MSE at 55%, these micro-changes dominate over the more conservative analyzer vote ratios.

### Cause 3: State Inference Uses Normalized Probabilities (DISTORTION)

`state_inference.py:119-124`: Raw probabilities are normalized to sum to 1.0. This means if one probability rises slightly, all others drop proportionally, creating a **zero-sum competition** that exaggerates small changes.

Example: If P_ataque rises from 0.30 to 0.45 due to a transient spike, the normalization pushes P_base and P_bajada down proportionally, making it look like a clear ATAQUE signal even though the absolute evidence is modest.

### Cause 4: Insufficient Hold Times (ENABLER)

- **BAJADA hold: 0.32s** — After entering BAJADA, the system can leave in just 320ms
- **BASE_GOLPE hold: 0.48s** — Less than half a second
- These are far too short for musical phrases that typically last 4-8 seconds

### Cause 5: EMA Alpha Too Aggressive (ENABLER)

`state_manager.py:79`: `_ema_alpha = 0.5`

With alpha=0.5, the smoothed score is 50% new value + 50% old value. This provides minimal damping. A sudden score spike propagates to 50% of its magnitude in a single frame (~33ms) and to 75% within two frames (~66ms).

### Cause 6: Persistence Windows Too Short (ENABLER)

3-frame deques at ~33ms cadence = ~100ms of history. Requiring 2/3 frames means a state only needs to be dominant for ~66ms to pass the persistence check. Musical transitions happen over seconds, not milliseconds.

### Cause 7: Stability Window Too Short (ENABLER)

`STABILITY_WINDOW_MS = 120` — A pending state only needs 120ms of consistency to be accepted. Combined with the fast EMA and short persistence, this means the entire pipeline from first signal change to state transition can complete in ~200-250ms.

### Cause 8: Drop Engine Feeds Into ATAQUE Prematurely

`state_inference.py:99-100`:
```python
if drop_state in ("BUILD", "PRE_DROP", "DROP"):
    p_ataque += 0.2
```

The DROP engine enters BUILD state when it detects rising energy + transient density > 5. This adds +0.20 to P_ataque during the BUILD phase, which is precisely the "still building" phase where the music hasn't actually reached ATAQUE yet.

---

## 7. Recommendations

### R1: Increase Minimum State Durations (HIGH PRIORITY)

Current vs proposed minimum hold times:

| State | Current | Proposed | Rationale |
|---|---|---|---|
| BAJADA | 0.32s | 1.5s | Calm sections last multiple phrases |
| BASE_GOLPE | 0.48s | 1.2s | Groove needs time to establish |
| ATAQUE | 0.96s | 2.0s | Attack peaks should sustain |
| BRAKE | 0.96s | 1.5s | Dead air is deliberate, respect it |

Implementation: Change multipliers in `_change_state` (lines 818-829).

### R2: Add Confirmation Window for State Transitions (HIGH PRIORITY)

Replace the 120ms stability window with a proper confirmation window that requires the candidate state to be dominant for a musically meaningful duration:

```python
CONFIRMATION_WINDOW_MS = {
    "BAJADA": 800,      # Must show calm for 800ms
    "BASE_GOLPE": 500,  # Must show groove for 500ms
    "ATAQUE": 400,      # Attack can be faster (still 400ms)
    "BRAKE": 200,       # Emergency, keep fast
}
```

Implementation location: `_can_change_state_responsive` (line 647-658), replace the flat `STABILITY_WINDOW_MS` with per-state values.

### R3: Reduce MSE Weight or Add MSE Trend Confirmation (HIGH PRIORITY)

Option A — Reduce MSE weight:
```python
scores[k] = 0.60 * scores[k] + 0.40 * mse_probs.get(k, 0.0)
```

Option B — Add trend confirmation delay in EnergyEngine:
```python
# Only flip trend after N consecutive frames in same direction
_TREND_CONFIRM_TICKS = 15  # ~600ms at 40ms/tick
```

Option C (recommended) — Both: reduce MSE to 40% AND require trend confirmation. This prevents the MSE from predicting transitions before the music actually changes.

### R4: Increase EMA Damping (MEDIUM PRIORITY)

Change from alpha=0.5 to alpha=0.25 (or use the STABLE preset's 0.3):
```python
self._ema_alpha = 0.25  # More smoothing, less reactivity
```

This makes scores change more gradually. A spike needs to persist for 4-5 frames instead of 1-2 to fully propagate.

### R5: Extend Persistence Windows (MEDIUM PRIORITY)

Increase deque sizes from 3 to 6-8 frames and require higher ratios:

```python
self._atk_persistence = deque(maxlen=8)   # was 3
self._golpe_persistence = deque(maxlen=6)  # was 3
self._bajada_persistence = deque(maxlen=6) # was 3

# Require 5/8 for ATAQUE, 4/6 for others
```

This ensures a state must be consistently dominant over ~200-250ms of history instead of ~66ms.

### R6: Add State Hysteresis with Asymmetric Entry/Exit (MEDIUM PRIORITY)

Use different thresholds for entering vs leaving a state:

```python
THRESHOLDS = {
    "ATAQUE":     {"enter": 0.72, "exit": 0.55},  # Must score 0.72 to enter, drops below 0.55 to leave
    "BASE_GOLPE": {"enter": 0.40, "exit": 0.25},
    "BAJADA":     {"enter": 0.45, "exit": 0.28},
    "BRAKE":      {"enter": 0.65, "exit": 0.45},
}
```

This creates a dead zone where the system holds its current state, preventing oscillation at threshold boundaries.

### R7: Don't Count DROP BUILD Phase as ATAQUE Evidence (MEDIUM PRIORITY)

In `state_inference.py`, only count DROP (not BUILD/PRE_DROP) as ATAQUE evidence:

```python
# Current (line 99-100):
if drop_state in ("BUILD", "PRE_DROP", "DROP"):
    p_ataque += 0.2

# Proposed:
if drop_state == "DROP":
    p_ataque += 0.2
elif drop_state == "PRE_DROP":
    p_ataque += 0.10  # partial credit only at PRE_DROP
# BUILD gives no ATAQUE credit
```

### R8: Phrase-Aware Transition Gating (LOW PRIORITY, HIGH IMPACT)

Use PhraseEngine's `phrase_boundary_probability` to prefer transitions at musical boundaries:

```python
def _can_change_state_responsive(self, new_state, scores):
    # ... existing checks ...

    # Phrase-aware gating: prefer transitions near phrase boundaries
    if self._mse_state and hasattr(self._mse_state, 'phrase_boundary_probability'):
        boundary_prob = self._mse_state.phrase_boundary_probability
        # Allow transition if near phrase boundary OR if score is overwhelming
        max_score = max(scores.values())
        if boundary_prob < 0.3 and max_score < 0.85:
            return False  # Wait for phrase boundary unless very strong signal
```

This makes the system wait for natural musical boundaries before transitioning, which is how human lighting operators work.

### R9: Re-enable Ultra Stability Layer with Fixes (LOW PRIORITY)

Sprint 6's global stability checks (lines 708-722) were disabled because they caused false BAJADA retention. The fix: exempt transitions where the score differential is large:

```python
if len(self._global_state_buffer) == 4:
    count = self._global_state_buffer.count(new_state)
    score_diff = new_score - current_score
    if count < 2 and new_state != self.STATE_BRAKE and score_diff < 0.25:
        return False
```

---

## Summary: Priority Implementation Order

1. **R2** — Per-state confirmation windows (replaces flat 120ms)
2. **R1** — Increase minimum hold times
3. **R3** — Reduce MSE weight + add trend confirmation
4. **R6** — Asymmetric entry/exit thresholds (hysteresis)
5. **R5** — Extend persistence windows
6. **R4** — Lower EMA alpha to 0.25
7. **R7** — Fix DROP BUILD→ATAQUE leak
8. **R8** — Phrase-aware gating
9. **R9** — Re-enable Ultra Stability with score-differential exemption

Implementing R1+R2+R3 alone should dramatically reduce premature transitions. R6 adds robustness. R8 makes transitions feel musically natural.

---

## Files Referenced

| File | Line(s) | Relevance |
|---|---|---|
| `state_manager.py` | 59-60 | Stability window & cooldown constants |
| `state_manager.py` | 334-336 | EMA smoothing |
| `state_manager.py` | 415-426 | MSE blending (45/55 split) |
| `state_manager.py` | 430-446 | Light stability buffer |
| `state_manager.py` | 545-631 | State candidate selection |
| `state_manager.py` | 633-745 | Validation checks |
| `state_manager.py` | 818-829 | Hold time assignments |
| `state_inference.py` | 55-124 | Probability calculation |
| `energy_engine.py` | 67-86 | Trend detection (anticipation source) |
| `drop_engine.py` | — | BUILD→ATAQUE leak |
| `analyzers/brake.py` | — | DeadAirSentinel (well-guarded) |

# FULL SYSTEM AUDIT: Musical Analysis & Cue Triggering Pipeline

**Date:** 2026-03-18
**Baseline:** stable-dmx-cues-v1
**Status:** AUDIT ONLY — NO MODIFICATIONS

---

## PART 1 — FULL PIPELINE TRACE

### 1.1 Pipeline Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AUDIO INPUT (engine_audio.py)                        │
│  sounddevice InputStream → DC-Block → HP 10Hz → [Notch 50/60Hz] → RAW      │
│  RAW × Schmitt Gate (80ms min-open/close) → GATED                          │
│  Ring buffer: 3s stereo float32 @ 44100Hz, blocksize=1024                  │
└───────────────┬──────────────────────────────────────────┬──────────────────┘
                │                                          │
     get_recent(0.25s)                          read_new_for_kick()
                │                                          │
┌───────────────▼──────────────────────┐   ┌───────────────▼──────────────────┐
│  LAYER 1: 45+ ANALYZER MODULES       │   │  KICK PULSE DETECTOR             │
│  (analyzers/*.py)                    │   │  (mod_basegolpe.py:391-464)      │
│                                      │   │  Low-band energy + adaptive      │
│  Each: process(block, sr) → card._on │   │  threshold + 150ms debounce      │
│                                      │   │  → get_kick_pulse() one-shot     │
│  Groups:                             │   └───────────────┬──────────────────┘
│   BAJADA:  5 modules                 │                   │
│   GOLPE:  10 modules                 │                   ▼
│   ATAQUE:  3 modules                 │        ┌──────────────────────┐
│   BRAKE:  3-4 modules                │        │  AutoClock / TapBridge│
│                                      │        │  (tempo/auto_clock.py)│
│  Output: card.is_on() → bool vote    │        └──────────────────────┘
└───────────────┬──────────────────────┘
                │
    ┌───────────▼───────────────────────────────────────────────────────────┐
    │  MUSIC STRUCTURE ENGINE (MSE)                                         │
    │  core/music_structure_engine/music_structure_engine.py                 │
    │                                                                       │
    │  BeatEngine → EnergyEngine → TransientEngine → PhraseEngine           │
    │       → DropEngine → StateInference                                   │
    │                                                                       │
    │  Output: MusicStructureState                                          │
    │    P_bajada, P_base, P_ataque, P_brake, confidence, suggested_state   │
    │    tempo, beat_phase, energy_level, energy_trend, drop_state          │
    │    phrase_position, phrase_boundary_probability                        │
    └───────────┬───────────────────────────────────────────────────────────┘
                │ (blended at 70/30 if confidence >= 0.4)
                │
    ┌───────────▼───────────────────────────────────────────────────────────┐
    │  STAGE MANAGER (state_manager.py) — SINGLE SOURCE OF TRUTH            │
    │                                                                       │
    │  Phase 1: Score Calculation                                           │
    │    raw_score = active_modules / total_modules_in_group                │
    │    if MSE.confidence >= 0.4: score = 0.70×analyzer + 0.30×MSE        │
    │                                                                       │
    │  Phase 2: Light Smoothing (buffer_size=2 avg)                         │
    │  Phase 3: EMA Smoothing (alpha=0.5)                                   │
    │  Phase 4: Persistence tracking (3-frame buffers per state)            │
    │  Phase 5: State Decision (priority: BRAKE>ATAQUE>GOLPE>BAJADA)        │
    │  Phase 6: Validation (_can_change_state_responsive)                   │
    │    - Inter-state cooldown (0ms, BRAKE bypasses)                       │
    │    - Stability window (120ms, BRAKE bypasses)                         │
    │    - ATAQUE margin check (12% over second score)                      │
    │    - ATAQUE override ≥80% (2 frames + 0.20s elapsed)                 │
    │    - ATAQUE persistence lock (2/3 frames → can't exit except BRAKE)  │
    │    - Peak lock post-ATAQUE (0.18s anti-bounce)                        │
    │    - Hold timer (state-specific durations)                            │
    │    - Cooldown timer (0.2s post-ATAQUE/BRAKE)                         │
    │    - Hysteresis (new > current + margin)                             │
    │    - Min confidence (0.50)                                            │
    │                                                                       │
    │  Output: get_state(), get_energy()                                    │
    └───────────┬───────────────────────────────────────────────────────────┘
                │
    ┌───────────▼───────────────────────────────────────────────────────────┐
    │  CUE ENGINE (cue_engine.py) — DETERMINISTIC ORCHESTRATOR              │
    │                                                                       │
    │  Every 50ms tick:                                                     │
    │    1. Read state/energy from StateManager                             │
    │    2. If state changed → off_now_for_state(old) [KILL before FIRE]   │
    │    3. Execute 7 modules in strict order:                              │
    │       ① ControlDimmer (C41)                                          │
    │       ② Break/BRAKE (C42-44)                                         │
    │       ③ Ataque (C37-39)                                              │
    │       ④ BaseGolpe (C1-9, C51-59)                                     │
    │       ⑤ Bajada (C10-18 colors, C19-27 positions)                     │
    │       ⑥ Movimiento (C28-36)                                          │
    │       ⑦ TimedSequence (C45-50)                                       │
    │    4. Family exclusivity sanity check (every ~1s)                     │
    └───────────┬───────────────────────────────────────────────────────────┘
                │
    ┌───────────▼───────────────────────────────────────────────────────────┐
    │  FAMILIES (mod_*.py) — MODULE-LEVEL CUE LOGIC                         │
    │  (see Section 1.3 for detailed family analysis)                       │
    └───────────┬───────────────────────────────────────────────────────────┘
                │ av.fire_cue() / av.kill_cue()
                │
    ┌───────────▼───────────────────────────────────────────────────────────┐
    │  AVOLITES CONTROLLER (avolites_config.py) — TRANSPORT ROUTER          │
    │                                                                       │
    │  Routes to active transport:                                          │
    │    HTTP mode → TitanQueue → TitanTransport → HTTP GET to console      │
    │    ArtNet mode → CueOutputAdapter → DmxState → ArtNetEngine → UDP    │
    │    sACN mode → CueOutputAdapter → DmxState → SacnEngine → UDP mcast │
    │                                                                       │
    │  Toggle-safe: skip fire if already active, skip kill if inactive      │
    │  Critical fast-path: C41, C37-39 bypass queue (fire_immediate)        │
    └───────────┬───────────────────────────────────────────────────────────┘
                │
    ┌───────────▼───────────────────────────────────────────────────────────┐
    │  DMX/sACN TRANSPORT                                                   │
    │                                                                       │
    │  DmxState (dmx_state.py):                                            │
    │    fire()/kill() → identical 2-frame pulse (ch=255 for 2 frames)      │
    │    Both toggle the Titan cue — fire and kill are the SAME signal      │
    │    Pulse queue: multiple rapid events spread across consecutive frames│
    │                                                                       │
    │  SacnEngine (sacn_engine.py):                                        │
    │    40fps continuous sender → E1.31 multicast UDP                      │
    │    snapshot() every 25ms → decrement pulse counters                   │
    │                                                                       │
    │  ArtNetEngine (artnet_engine.py):                                    │
    │    40fps continuous sender → Art-Net unicast UDP                       │
    │    ArtPoll responder on port 6454                                     │
    │                                                                       │
    │  Pulse timing: 2 frames × 25ms = 50ms per fire/kill event            │
    └───────────────────────────────────────────────────────────────────────┘
```

---

### 1.2 Audio Input Detail

**File:** `engine_audio.py`

| Parameter | Value | Notes |
|-----------|-------|-------|
| Sample rate | 44100 Hz (default) | Auto-detected from device |
| Block size | 1024 samples | ~23ms per callback |
| Channels | 2 (stereo) | Converted via `to_stereo_f32()` |
| Ring buffer | 3.0 seconds | Three separate rings: raw_filt, raw_clean, gated |
| DC-block | 5 Hz cutoff | 1st-order IIR |
| High-pass | 10 Hz cutoff | 1st-order IIR (originally 30Hz, lowered for BPM) |
| Notch | Optional 50/60 Hz | Q=12, disabled by default |
| Gate | Schmitt trigger | open_ratio=2.5, close_ratio=1.6 × noise_floor |
| Gate hold | 80ms min-open/close | Prevents gate chatter |
| Envelope | attack=12ms, release=180ms | Smooth gate transitions |
| Noise calibration | 1.5s, percentile 85 | Clamped to [1e-6, 0.1] |

**Critical path for kick detection:** `read_new_for_kick()` returns only NEW samples since last read (incremental cursor), capped at 0.25s to avoid stale backlog. Provides `block_start_ts` from `time.monotonic()` for accurate timing.

---

### 1.3 Family Detail

#### FAMILY: BAJADA (mod_bajada.py)

| Aspect | Detail |
|--------|--------|
| **Nature** | STATEFUL — only active during BAJADA state |
| **Cues** | Colors C10-18, Positions C19-27 (3 energy tiers × 3 per tier) |
| **Entry condition** | `prev_state != "BAJADA" and state == "BAJADA"` (line 201) |
| **Entry action** | 1. `movement.pause_for_positions()` 2. Fire 1 position (fair RR) 3. Fire 1 color (fair RR) |
| **Exit condition** | `prev_state == "BAJADA" and state != "BAJADA"` (line 202) |
| **Exit action** | 1. Kill latched pos/col explicitly 2. `movement.restore_from_positions()` 3. Reset latches |
| **Internal state** | `latched_pos`, `latched_col` (int or None), `in_bajada` (bool) |
| **Re-trigger** | NONE — RUN is NO-OP, re-fires only on full exit + re-entry |
| **Timers/cooldowns** | None in module. StateManager hold = 0.32s (0.8 × 0.4) |
| **Fair rotation** | Persistent JSON (bajada_colors_rr.json, bajada_positions_rr.json). Priority G3>G2>G1. Anti-repetition: skip last used if alternatives exist |
| **Cleanup dependency** | Module does explicit kill on EXIT; CueEngine `off_now_for_state` is safety net |

#### FAMILY: BASE_GOLPE (mod_basegolpe.py)

| Aspect | Detail |
|--------|--------|
| **Nature** | EVENT-DRIVEN — fires once at ENTRY, no state held |
| **Cues** | FX_DIMMER (ALTA): C1-3, C51-53 / FX_BEAM (MEDIA): C4-6, C54-56 / FX_COLOR (BAJA): C7-9, C57-59 |
| **Entry condition** | `prev_state != "BASE_GOLPE" and state == "BASE_GOLPE"` (line 228) |
| **Entry action** | 1. Map energy→subfamily 2. Select cue via round-robin per energy 3. Fire cue 4. If FX_DIMMER: `dim.request_dim_off()` |
| **Exit condition** | `prev_state == "BASE_GOLPE" and state != "BASE_GOLPE"` (line 229) |
| **Exit action** | 1. Kill fired cue explicitly 2. Release dimmer if requested |
| **Internal state** | `_fired_cue`, `_fire_ts`, `_dimmer_requested`, `_rr_index` per energy |
| **Re-trigger** | NONE — RUN returns None, no reassert |
| **Timers/cooldowns** | None in module. StateManager hold = 0.48s (0.8 × 0.6) |
| **V11 Voting** | 10 analyzer flags (hits, accent, groove, pattern, cadence, flow, dynamic, pulse, rhythm, burst) fed to AutoClock |
| **V12 Kick Pulse** | Low-band energy + adaptive threshold + 150ms debounce. One-shot consumed by `get_kick_pulse()` |
| **Cleanup dependency** | Module does explicit kill on EXIT; CueEngine `off_now_for_state` is safety net |

#### FAMILY: BRAKE (mod_break.py)

| Aspect | Detail |
|--------|--------|
| **Nature** | STATEFUL with HOLD and SNAPSHOT |
| **Cues** | BAJA→C42, MEDIA→C43, ALTA→C44 (fixed mapping) |
| **Entry condition** | `prev_state != "BRAKE" and state == "BRAKE"` (line 94) |
| **Entry action** | 1. Take snapshot (all active C1-50 except C41, C42-44, C28-36) 2. Kill snapshot cues 3. Fire target cue 4. Set HOLD = 2.0s 5. If C44: `dim.request_dim_off("BREAK_C44")` |
| **Exit condition** | `prev_state == "BRAKE" and state != "BRAKE"` (line 95) |
| **Exit action** | 1. Restore snapshot (re-fire all) 2. Kill current brake cue 3. Release dimmer |
| **Internal state** | `current_cue`, `current_energy`, `hold_until`, `freeze_snapshot`, `_dimmer_requested` |
| **Re-trigger** | Energy change while in BRAKE AND hold expired → fire new, kill old, reset hold |
| **Timers** | Module HOLD = 2.0s. StateManager hold = 0.96s (0.8 × 1.2) |
| **SNAPSHOT exception** | ONLY module allowed to call `is_active()` to build snapshot |
| **Cleanup dependency** | Module does explicit kill on EXIT + restore |

#### FAMILY: ATAQUE (mod_ataque.py)

| Aspect | Detail |
|--------|--------|
| **Nature** | STATEFUL with HOLD |
| **Cues** | BAJA→C37, MEDIA→C38, ALTA→C39 |
| **Entry condition** | `prev_state != "ATAQUE" and state == "ATAQUE"` |
| **Entry action** | Map energy→cue, fire, set HOLD = 2.0s |
| **Exit action** | Kill current cue, reset state |
| **Re-trigger** | Energy change while in ATAQUE AND hold expired |
| **Timers** | Module HOLD = 2.0s. StateManager hold = 0.96s. Peak lock = 0.18s post-exit |

#### FAMILY: AUX / Timed Sequence (mod_timed_sequence.py)

| Aspect | Detail |
|--------|--------|
| **Cues** | C45-C50 (6 steps) |
| **Activation** | After 20s dwell in any state, advances every 10s |
| **State machine** | idle → fire_candidate → hold → kill_pending → idle |
| **Kill confirmation** | Retries kill every 150ms, checks `is_active()` for confirmation |

#### Extended Families (core/cues/family_manager.py)

| Family | Cues | Notes |
|--------|------|-------|
| CLIMA | C60-63 | 4 climate states, one active per family |
| HAZE | C64-66 | LOW/MID/HIGH |
| DJ | C67-71 | 5 zones, multi-zone support (no kill-before-fire) |
| ARTIST | C72-79 | 8 zones (T1-T8) |
| TRACKING | C80-82 | idle/follow/focus |

---

### 1.4 CueEngine Mechanics

**File:** `cue_engine.py`

**Update cycle (50ms interval, daemon thread):**

1. **Read state/energy** from StateManager (ONLY source of truth) — lines 636-646
2. **Calendar bridge** — if "ALL" disabled: hard OFF (kill all musical cues) — lines 654-697
3. **State change detection** — `state_changed = (effective_state != self.last_state)` — line 699
4. **KILL before FIRE** — if state changed: `off_now_for_state(old_state)` — lines 702-713
5. **Module execution** — 7 modules in strict order, each receives (state, energy) — lines 724-746
6. **Family exclusivity** — every 20 ticks (~1s): verify max 1 cue per family — lines 748-751

**`off_now_for_family(family)`** (lines 534-599):
- Immediate kill of ALL cues in family range via `av.kill_pool(ids, priority_boost=True)`
- NO rate limiting, NO dedup window
- Does NOT set `_sent_this_tick` (allows FIRE in same tick)

**`off_now_for_state(state)`** (lines 601-618):
- Maps state to families via `STATE_TO_FAMILY` dict
- Calls `off_now_for_family()` for each mapped family

---

### 1.5 Transport Layer

#### DMX Pulse Mechanism (dmx_state.py)

Both `fire()` and `kill()` produce **identical 2-frame pulses** on the same DMX channel:
- Channel goes to 255 for exactly 2 frames (50ms at 40fps)
- Titan console interprets each pulse as a button toggle
- Multiple rapid pulses on the same channel queue across consecutive frames

**Critical implication:** Fire and kill are the SAME electrical signal. The system relies on **state tracking** in `avolites_config.py` (toggle-safe guards) to ensure fire doesn't toggle OFF and kill doesn't toggle ON.

#### sACN / ArtNet Timing

| Parameter | sACN | ArtNet |
|-----------|------|--------|
| FPS | 40 (configurable 1-44) | 40 (configurable 1-44) |
| Frame interval | 25ms | 25ms |
| Protocol | E1.31 multicast UDP | Art-Net v14 unicast UDP |
| Pulse width | 2 frames = 50ms | 2 frames = 50ms |
| Sequence counter | 0-255 rolling | 1-255 rolling (skip 0 per spec) |

#### HTTP/Titan Queue (Legacy)

| Parameter | Value |
|-----------|-------|
| Rate limit | 60ms between requests |
| KILL priority | Purges oldest FIRE if queue full |
| Dedup window | 50ms |
| Retry | 3 retries (0.05, 0.1, 0.2s) |
| Timeout | 1.2s connect, 1.0s read |
| Critical bypass | C41, C37-39 use `fire_immediate()` |

---

## PART 2 — CURRENT BEHAVIOR ANALYSIS

### 2.1 Why the System Feels "Anxious" (Over-Reactive)

#### Root Cause 1: FAST Preset with Minimal Damping

**Evidence:** `state_manager.py` lines 26-33

```python
"FAST": {
    "min_hold_seconds": 0.8,
    "ema_alpha": 0.5,         # Half weight on new data each tick
    "buffer_size": 2,          # Only 2-frame smoothing
    "stability_window_ms": 120, # Only 120ms to confirm
    "cooldown_seconds": 0.2,   # Only 200ms post-ATAQUE/BRAKE
}
```

The EMA alpha of 0.5 means each new score contributes 50% to the smoothed value — a single loud frame can push a score from 0.2 to 0.6 in two ticks (100ms). Combined with the 2-frame buffer averaging, the smoothing pipeline is:

```
raw_score → 2-frame avg → EMA(0.5) → decision
```

This creates a **total latency of ~3 ticks (150ms)** from audio event to state change, which is fast but means transient spikes in analyzer voting can trigger state changes before the musical context is clear.

#### Root Cause 2: Analyzer Vote Granularity

**Evidence:** `state_manager.py` lines 448-470

Scores are computed as `active_count / total_count`:
- BAJADA: 5 modules → each module = 0.20 score weight
- GOLPE: 10 modules → each module = 0.10 score weight
- ATAQUE: 3 modules → each module = 0.33 score weight
- BRAKE: 3-4 modules → each module = 0.25-0.33 score weight

**Problem:** ATAQUE has only 3 modules. A single analyzer flipping produces a +0.33 score jump. Two analyzers active = 0.66, exceeding the 0.60 threshold. This makes ATAQUE the most trigger-happy state — it takes only 2/3 votes to fire.

Compare: BASE_GOLPE needs 5/10 votes (0.50) to exceed its 0.45 threshold, giving it much more granularity and stability.

#### Root Cause 3: MSE Blending Can Amplify False Positives

**Evidence:** `state_manager.py` lines 472-483

When MSE confidence >= 0.4:
```python
scores[k] = 0.70 * scores[k] + 0.30 * mse_probs.get(k, 0.0)
```

The MSE `StateInference` (state_inference.py lines 87-103) has additive P_ataque rules:
- `e_level > 0.3` → +0.25
- `e_level > 0.5` → +0.15 more
- `e_trend == "RISING"` → +0.20
- `t_dens > 10.0` → +0.15

A moderately energetic track (energy=0.4, rising, transient_density=12) already produces P_ataque = 0.60 before normalization. After normalization, MSE may push ATAQUE probability high even when analyzers say otherwise, creating a 30% bias toward ATAQUE.

#### Root Cause 4: Ultra Stability Layer DISABLED

**Evidence:** `state_manager.py` lines 765-779

```python
# ✅ SPRINT 6: Ultra Stability Layer - TEMPORALMENTE DESACTIVADO
# MOTIVO: Los bloqueos globales causan retención falsa del estado BAJADA
```

The global lock (0.12s post-change) and the requirement for 2/4 frames consistency were disabled because they trapped the system in BAJADA. Without them, the remaining guards (hold + stability_window) are the only brakes on state changes.

### 2.2 Why BASE_GOLPE Sometimes Feels Delayed

#### Root Cause 1: Persistence Requirement

**Evidence:** `state_manager.py` lines 654-657

```python
elif effective_scores["base_golpe"] >= GOLPE_THRESHOLD:
    if sum(self._golpe_persistence) >= 2:  # Need 2/3 frames at >= 0.52
        return self.STATE_BASE_GOLPE
```

BASE_GOLPE requires:
1. Raw smoothed score >= 0.52 for 2 out of 3 frames (persistence buffer)
2. THEN effective score >= 0.45 (after light smoothing + disabled-state zeroing)
3. THEN pass stability window (120ms)
4. THEN pass hold/cooldown/hysteresis

**Total minimum latency:** 2 ticks persistence + 120ms stability + hold from previous state = **minimum 220ms from first qualifying score to state change**. If coming from ATAQUE/BRAKE, add 200ms cooldown → **420ms total**.

#### Root Cause 2: Hysteresis When Leaving BAJADA

**Evidence:** `state_manager.py` lines 90-95

```python
"BAJADA": {"BASE_GOLPE": 0.08, ...}
```

To transition from BAJADA to BASE_GOLPE, the new score must exceed the current BAJADA score by 0.08. If BAJADA score is 0.40 and GOLPE score is 0.46, the transition is blocked even though GOLPE exceeds its 0.45 threshold.

#### Root Cause 3: 10-Module Vote Granularity Slows Response

With 10 modules for GOLPE, score changes in 0.10 increments. Going from 0.30 (3 active) to 0.50 (5 active) requires TWO additional modules to activate — this takes real musical time.

### 2.3 Why BAJADA Previously Had Stuck Cues

#### Root Cause 1 (FIXED): Missing Explicit Kill on EXIT

**Evidence:** `mod_bajada.py` lines 210-219 — the current code does explicit kills:

```python
if self.latched_pos is not None:
    self.av.kill_cue(self.latched_pos)
if self.latched_col is not None:
    self.av.kill_cue(self.latched_col)
```

This is marked as the FIX. Previously, BAJADA relied solely on CueEngine's `off_now_for_state()` which could fail in edge cases (e.g., the state change was detected but the family kill was skipped due to a race condition or the cue was not in the expected range).

#### Root Cause 2: DMX Toggle Symmetry Risk

**Evidence:** `dmx_state.py` — fire() and kill() are IDENTICAL pulses.

If a kill pulse is sent for a cue that's already OFF (e.g., because CueEngine already killed it), the pulse toggles it back ON. This is why the code has `toggle-safe` guards in `avolites_config.py` that check `is_active()` before sending.

**Remaining risk in DMX mode:** `DmxState.get_active_cues()` returns empty set (line 255-260) because pulse mode has no sustained state. This means the toggle-safe guard in `CueOutputAdapter` likely returns `False` always, making it impossible to detect double-kill scenarios in pure DMX mode.

### 2.4 Cooldown Effectiveness Analysis

| Timer | Value | Effective? | Notes |
|-------|-------|------------|-------|
| Hold BAJADA | 0.32s | Marginal | Very short — fast music can re-trigger in <0.5s |
| Hold BASE_GOLPE | 0.48s | Adequate | Matches typical kick patterns |
| Hold ATAQUE | 0.96s | Good | Prevents immediate re-trigger |
| Hold BRAKE | 0.96s | Good | Matches musical breaks |
| Cooldown post-ATAQUE | 0.2s | Weak | Only 200ms before any state can re-enter |
| Cooldown post-BRAKE | 0.2s | Weak | Same — rapid exit→re-enter possible |
| Stability window | 120ms | Marginal | Only 2-3 ticks at 50ms interval |
| Peak lock ATAQUE | 0.18s | Weak | Very narrow anti-bounce window |
| Global lock | 0.12s | DISABLED | Not in effect |
| Inter-state cooldown | 0ms | OFF | Allows rapid state cycling |

**Key finding:** The system has **no effective "settle time"** between state changes. With 0ms inter-state cooldown and only 0.2s post-exit cooldown, the system can cycle: BAJADA→GOLPE→BAJADA in under 700ms (0.32s hold + 120ms stability + 200ms for new state to form).

### 2.5 State Transition Conflicts

#### Conflict 1: ATAQUE Persistence vs. Exit

When ATAQUE persistence >= 2/3 frames (state_manager.py line 757), transitions to anything except BRAKE are blocked. But if the music genuinely changes, this lock can hold ATAQUE for up to 3 ticks (150ms) beyond when scores have already fallen — creating a "stuck in ATAQUE" feeling.

#### Conflict 2: BAJADA Clean Drop vs. Steady State

BAJADA requires "clean drop" — 2/3 frames with smoothed score >= 0.38 (line 660-661). But BAJADA is the default "calm" state. When no strong state qualifies, the system should default to BAJADA, but the clean-drop requirement prevents this. The fallback (line 688) returns `current_state`, keeping whatever state was active.

**Result:** System can get trapped in a non-BAJADA state when the music is genuinely calm but the BAJADA score hasn't formed a clean drop pattern.

#### Conflict 3: Tie-Breaker Zone

The tie-breaker (lines 663-686) activates when scores are within 0.03 of their thresholds. This zone is wide enough that during moderate music, multiple states can hover near their thresholds simultaneously, causing the tie-breaker to select states based on "least recently used" rather than musical content — introducing randomness.

---

## PART 3 — MUSIC STRUCTURE (SECOND LAYER) DESIGN

### 3.1 Current MSE Status

The Music Structure Engine already exists (`core/music_structure_engine/`) with:
- **BeatEngine**: Spectral flux + autocorrelation tempo tracking
- **EnergyEngine**: Multiband RMS + trend detection (8s memory)
- **TransientEngine**: Transient density + spike detection
- **PhraseEngine**: 16-beat phrase tracking (4 bars × 4 beats)
- **DropEngine**: State machine (NONE→BUILD→PRE_DROP→DROP→NONE)
- **StateInference**: Deterministic weighted-sum → P_bajada, P_base, P_ataque, P_brake

**Current integration:** MSE probabilities are blended at 30% into analyzer scores when confidence >= 0.4 (state_manager.py line 476).

### 3.2 What's Missing: Section-Level Awareness

The current MSE operates at **beat/phrase granularity** (~16 beats ≈ 8s at 120 BPM). It cannot detect:

1. **Sections** (intro, verse/groove, build, drop, break, outro) — typically 32-64 bars (1-4 minutes)
2. **Section transitions** — when a section is ending and what's coming next
3. **Energy arc** — the long-term energy trajectory across the entire track
4. **Repetition structure** — recognition that "we've been in this groove for 2 minutes"

### 3.3 Proposed Second Layer: SectionAnalyzer

```
                          ┌──────────────────────────────────┐
                          │   SECTION ANALYZER (NEW)          │
                          │                                    │
  MSE outputs ──────────►│   Inputs:                          │
  (every tick)            │     energy_level, energy_trend     │
                          │     transient_density              │
                          │     drop_state, beat_confidence    │
                          │     phrase_position                │
                          │                                    │
                          │   Computes:                        │
                          │     structure_phase                │
                          │     energy_trend_long              │
                          │     section_confidence             │
                          │     transition_probability         │
                          │     reactivity_modifier            │
                          │                                    │
                          │   Memory: 60s sliding window       │
                          └────────────┬─────────────────────┘
                                       │
                                       ▼
                          Feeds into StateManager BEFORE
                          score calculation (new Phase 0)
```

#### 3.3.1 Outputs

| Output | Type | Range | Description |
|--------|------|-------|-------------|
| `structure_phase` | enum | INTRO, GROOVE, BUILD, DROP, BREAK, OUTRO | Current musical section |
| `energy_trend_long` | enum | ASCENDING, PLATEAU, DESCENDING | 30-60s energy trajectory |
| `section_confidence` | float | [0, 1] | How confident we are about the current section |
| `transition_probability` | float | [0, 1] | Likelihood that the current section is about to end |
| `reactivity_modifier` | float | [0.3, 1.5] | Multiplier for StateManager's responsiveness |
| `suggested_hold_modifier` | float | [0.5, 2.0] | Multiplier for hold durations |

#### 3.3.2 Detection Logic

**INTRO detection:**
- Low energy for > 15s at start of audio
- Low transient density, low beat confidence
- energy_trend_long = ASCENDING (gradual build)

**GROOVE detection:**
- Stable energy for > 20s
- High beat confidence, moderate transient density
- energy_trend_long = PLATEAU
- Drop state = NONE for extended period

**BUILD detection:**
- Energy rising for > 5s after GROOVE
- Increasing transient density
- Drop state = BUILD or PRE_DROP
- Phrase position approaching boundary

**DROP detection:**
- Sudden energy spike after BUILD
- High transient density + spike
- Drop state = DROP
- Very short duration (2-8s)

**BREAK detection:**
- Sudden energy drop from GROOVE or DROP
- Low transient density
- Similar to BRAKE but at section level (longer)

**OUTRO detection:**
- Sustained energy decrease for > 20s
- Decreasing beat confidence
- energy_trend_long = DESCENDING

#### 3.3.3 Reactivity Modifier Logic

The key innovation: the section context shapes HOW reactive the system should be.

| Section | Reactivity Modifier | Hold Modifier | Rationale |
|---------|-------------------|---------------|-----------|
| INTRO | 0.4 | 2.0 | Calm, minimal changes, long holds |
| GROOVE | 0.7 | 1.2 | Steady, moderate changes allowed |
| BUILD | 1.2 | 0.7 | More reactive, shorter holds (building tension) |
| DROP | 1.5 | 0.5 | Maximum reactivity, fast transitions |
| BREAK | 0.3 | 2.0 | Minimal changes, let the silence breathe |
| OUTRO | 0.5 | 1.5 | Winding down, fewer changes |

---

## PART 4 — INTEGRATION DESIGN

### 4.1 Layer Architecture

```
Layer 2 (Structure/New)    Layer 1 (Reactive/Current)
─────────────────────      ────────────────────────────
Section detection           Analyzer voting (45+ modules)
Energy arc tracking         MSE (beat/energy/transient/phrase)
Reactivity shaping          Score calculation + smoothing
                            State decision + validation

        │                              │
        └──────────┬───────────────────┘
                   │
                   ▼
          ┌────────────────┐
          │  Stage Manager  │  (modified to accept reactivity_modifier)
          │                 │
          │  Phase 0: Apply │  section context to tune:
          │  - thresholds   │  (× reactivity_modifier)
          │  - hold times   │  (× hold_modifier)
          │  - stability    │  window (÷ reactivity_modifier)
          │  - cooldowns    │  (× hold_modifier)
          └────────┬───────┘
                   │
                   ▼
           CueEngine (unchanged)
```

### 4.2 Integration Point: Before StateManager Score Calculation

The SectionAnalyzer output feeds into StateManager as a new **Phase 0** that runs before `_calculate_scores_responsive()`:

```python
# In state_manager.py update():

# Phase 0: Section context (NEW)
if self._section_analyzer:
    section = self._section_analyzer.get_state()
    self._reactivity = section.reactivity_modifier
    self._hold_modifier = section.suggested_hold_modifier
else:
    self._reactivity = 1.0
    self._hold_modifier = 1.0

# Phase 1: Score calculation (existing, but thresholds tuned)
# BRAKE_THRESHOLD = 0.65 / self._reactivity  (more reactive = lower threshold)
# STABILITY_WINDOW = 120ms / self._reactivity
# hold_remaining *= self._hold_modifier
```

### 4.3 Interaction Rules

| Scenario | Layer 1 Says | Layer 2 Says | Resolution |
|----------|-------------|-------------|------------|
| Kick in groove | BASE_GOLPE | GROOVE (react=0.7) | Fire BASE_GOLPE but hold 40% longer |
| Transient in break | ATAQUE | BREAK (react=0.3) | Block ATAQUE — hold modifier prevents transition |
| Drop after build | ATAQUE | DROP (react=1.5) | Fire ATAQUE immediately, shorter hold |
| Random noise in intro | BASE_GOLPE | INTRO (react=0.4) | Block — threshold effectively raised to 0.45/0.4 = 1.12 (unreachable) |
| Genuine brake | BRAKE | any | BRAKE always fires (bypasses all modifiers) |

### 4.4 Priority and Conflict Resolution

1. **BRAKE always wins** — Layer 2 NEVER blocks BRAKE (emergency priority preserved)
2. **Layer 2 shapes, never decides** — it modifies thresholds and timing, but the actual state decision remains in Layer 1's priority system
3. **Low confidence = no effect** — when `section_confidence < 0.3`, reactivity_modifier defaults to 1.0
4. **Gradual transitions** — reactivity_modifier changes are EMA-smoothed over 2s to prevent step changes in responsiveness

### 4.5 How This Reduces "Anxiety"

The core problem is that the current system reacts to every micro-event in the audio with equal urgency. The SectionAnalyzer provides temporal context:

1. **During GROOVE (70% of typical set):** Reactivity drops to 0.7, effective thresholds rise ~43%, holds increase 20%. The system settles into the groove and only changes state on clear, sustained musical changes.

2. **During BUILD (5-10% of set):** Reactivity rises to 1.2, the system becomes more responsive to catch the drop moment precisely.

3. **During BREAK (5-10% of set):** Reactivity drops to 0.3, the system becomes nearly inert — only BRAKE can trigger. This prevents the "anxious flashing" during quiet moments.

4. **Net effect:** State changes become aligned with musical structure rather than individual audio events. The number of state transitions per minute drops from ~12-20 (current estimate) to ~4-8 (with section-aware damping), while preserving reactivity at musically important moments.

---

## PART 5 — ROOT CAUSES OF INSTABILITY (SUMMARY)

| # | Issue | Root Cause | File:Line | Severity |
|---|-------|-----------|-----------|----------|
| 1 | Over-reactive state changes | EMA alpha=0.5, buffer=2, stability=120ms | state_manager.py:32-33 | HIGH |
| 2 | ATAQUE triggers too easily | Only 3 modules, each = 0.33 score weight | state_manager.py:463-465 | HIGH |
| 3 | MSE amplifies ATAQUE | Additive P_ataque rules in StateInference | state_inference.py:87-103 | MEDIUM |
| 4 | Ultra Stability Layer disabled | Global lock caused BAJADA trapping | state_manager.py:765-779 | MEDIUM |
| 5 | No inter-state cooldown | 0ms between state changes | state_manager.py:68 | MEDIUM |
| 6 | Post-exit cooldown too short | Only 200ms post-ATAQUE/BRAKE | state_manager.py:80 | LOW |
| 7 | BASE_GOLPE delayed by persistence | 2/3 frame requirement + hysteresis | state_manager.py:654-657 | MEDIUM |
| 8 | BAJADA clean-drop traps system | Non-BAJADA state persists when music is calm | state_manager.py:658-661 | MEDIUM |
| 9 | DMX toggle symmetry risk | fire/kill identical pulses, no state tracking in DMX mode | dmx_state.py:139-191 | LOW |
| 10 | No section-level awareness | All events treated equally regardless of musical context | (missing) | HIGH |
| 11 | Tie-breaker introduces randomness | 0.03 margin zone favors "least used" over musical fit | state_manager.py:663-686 | LOW |

---

## PART 6 — RECOMMENDATIONS (NO CHANGES YET)

### Phase 1: Tuning (minimal risk)
1. Increase ATAQUE module count or reduce its vote weight
2. Tune MSE P_ataque rules to be less additive
3. Increase post-ATAQUE/BRAKE cooldown to 500ms
4. Re-enable global lock with less aggressive parameters

### Phase 2: SectionAnalyzer (new module)
5. Implement SectionAnalyzer in `core/music_structure_engine/section_analyzer.py`
6. Add Phase 0 integration in StateManager
7. Tune reactivity modifiers through live testing

### Phase 3: DMX Safety
8. Add pulse-count parity tracking in DmxState to detect toggle desync
9. Implement periodic "known state" sync frames

---

*End of audit. No code was modified.*

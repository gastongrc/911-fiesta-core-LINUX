# FULL SYSTEM AUDIT + HYBRID ARCHITECTURE DESIGN

**System Baseline:** stable-dmx-cues-v1
**Status:** AUDIT + DESIGN ONLY — NO CODE CHANGES
**Date:** 2026-03-18

---

## TABLE OF CONTENTS

1. [Full Pipeline Trace](#1-full-pipeline-trace)
2. [Current State Manager Logic](#2-current-state-manager-logic)
3. [Limitations of Current Model](#3-limitations-of-current-model)
4. [Hybrid Model Design](#4-hybrid-model-design)
5. [Family Impact Analysis](#5-family-impact-analysis)
6. [Cue Engine Impact](#6-cue-engine-impact)
7. [Music Structure Role](#7-music-structure-role)
8. [Hybrid Integration](#8-hybrid-integration)
9. [Transition Rules](#9-transition-rules)
10. [Risks](#10-risks)
11. [Integration Path](#11-integration-path)

---

## 1. FULL PIPELINE TRACE

### 1.1 Pipeline Diagram

```
 AUDIO INPUT (Sounddevice)
      │
      ▼
 ┌──────────────────────────────────────────┐
 │         AudioEngine (engine_audio.py)     │
 │  DC-Block → HP 30Hz → Notch 50/60Hz     │
 │  → Schmitt Gate → Ring Buffers           │
 │    _raw_filt (3s)  _gated (3s)           │
 └───────┬──────────────────┬───────────────┘
         │                  │
    get_recent()      read_new_for_kick()
         │                  │
         ▼                  ▼
 ┌───────────────┐  ┌──────────────────────┐
 │  ANALYZERS    │  │  KickPulseDetector   │
 │  (38+ modules)│  │  (tempo/kick_det.py) │
 │               │  │  Butterworth 40-120Hz│
 │  Each has:    │  │  Dual-gate + MAD     │
 │  card.is_on() │  │  Debounce 150ms      │
 │  (vote flag)  │  └──────────┬───────────┘
 └───────┬───────┘             │
         │                     ▼
         │            ┌─────────────────┐
         │            │  AutoClock      │
         │            │  (BPM tracking) │
         │            └────────┬────────┘
         │                     │
         ▼                     ▼
 ┌───────────────────────────────────────────────────────┐
 │              MUSIC STRUCTURE ENGINE                    │
 │  (core/music_structure_engine/*)                      │
 │                                                       │
 │  BeatEngine ─────→ tempo, beat_phase, beat_confidence │
 │  EnergyEngine ───→ energy_level, trend, multiband     │
 │  TransientEngine → transient_density, spike           │
 │  PhraseEngine ──→ beat/bar/phrase position             │
 │  DropEngine ────→ NONE/BUILD/PRE_DROP/DROP             │
 │  StateInference → P_bajada, P_base, P_ataque, P_brake│
 └────────────────────────┬──────────────────────────────┘
                          │
    ┌─────────────────────┤
    │                     │
    ▼                     ▼
 ┌──────────────┐  ┌─────────────────────────────────────┐
 │EnergyDetector│  │         STATE MANAGER                │
 │(energy_det.) │  │         (state_manager.py)           │
 │              │  │                                       │
 │ 3 levels:    │  │  Analyzer votes (70%) + MSE (30%)    │
 │ BAJA/MEDIA/  │  │  → EMA smooth → Persistence check   │
 │ ALTA         │  │  → Threshold: BRAKE≥65, ATQ≥60,     │
 │              │  │    GOLPE≥45, BAJADA≥35               │
 │ Auto-calib   │  │  → Hysteresis + Hold + Cooldown      │
 │ P33/P66      │  │  → ONE winner state                  │
 └──────┬───────┘  └──────────────┬──────────────────────┘
        │                         │
        │    get_state()          │    get_energy()
        │    ────────────→        │    ────────────→
        │                         │
        ▼                         ▼
 ┌──────────────────────────────────────────────────────┐
 │                   CUE ENGINE                          │
 │                   (cue_engine.py)                      │
 │                                                        │
 │  1. STATE CHANGED? → off_now_for_state(old)  [KILL]   │
 │  2. Execute modules in order:                          │
 │     control_dimmer(C41) → break(C42-44)               │
 │     → ataque(C37-39) → base_golpe(C1-9,C51-59)       │
 │     → bajada(C10-27) → movimiento(C28-36)             │
 │     → timed(C45-50)                                    │
 │  3. Every 20 ticks: enforce family exclusivity         │
 └───────────────────────┬──────────────────────────────┘
                         │
              fire_cue() / kill_cue()
                         │
                         ▼
 ┌──────────────────────────────────────────────────────┐
 │              TRANSPORT LAYER                          │
 │                                                        │
 │  Path A: DMX Direct (ArtNet/sACN)                     │
 │    cue_adapter → dmx_state → artnet/sacn_engine       │
 │    Pulse: 2 frames × 25ms = 50ms                      │
 │    Frame rate: 40 fps                                  │
 │                                                        │
 │  Path B: HTTP (TitanQueue)                            │
 │    titan_queue → priority queue (KILL=1, FIRE=2)      │
 │    Rate limit: 60ms between requests                   │
 │    Family locks prevent interleaving                   │
 └──────────────────────────────────────────────────────┘
                         │
                         ▼
                   DMX/sACN OUTPUT
                   (Lighting Fixtures)
```

### 1.2 Processing Cadence (main.py)

| Subsystem | Interval | Rate |
|-----------|----------|------|
| Kick detection | Every tick | ~50ms |
| Energy detector | 50ms | 20 Hz |
| Cue engine | 50ms | 20 Hz |
| Full analyzers | 250ms | 4 Hz |
| VU meter | 100ms | 10 Hz |
| Status display | 500ms | 2 Hz |

### 1.3 Total Latency Budget

| Stage | Latency |
|-------|---------|
| Audio capture + filtering | ~25ms (1 blocksize at 44.1kHz) |
| Analyzer processing | ~10-20ms |
| State Manager decision | 120-250ms (stability window + persistence) |
| Cue Engine execution | 50ms (1 tick) |
| Transport (DMX) | 25-50ms (1-2 frames) |
| Transport (HTTP) | 60-120ms |
| **Total (DMX)** | **~250-400ms** |
| **Total (HTTP)** | **~300-500ms** |

---

## 2. CURRENT STATE MANAGER LOGIC

### 2.1 States Are Mutually Exclusive

The StateManager maintains **exactly ONE** active state at all times:

```
self.current_state ∈ {"BAJADA", "BASE_GOLPE", "ATAQUE", "BRAKE"}
```

**Enforcement points:**
- `self.current_state` is a single string (state_manager.py:131-132)
- `_determine_next_state_responsive()` returns exactly one winner
- `_change_state()` atomically replaces old → new (line 826)
- No concept of "secondary" or "overlay" state exists

### 2.2 Transition Decision Flow

```
1. COLLECT VOTES
   ├─ Count active analyzers per category (38+ modules)
   ├─ bajada_score = active_bajada / total_bajada
   ├─ golpe_score = active_golpe / total_golpe
   ├─ ataque_score = active_ataque / total_ataque
   └─ brake_score = active_brake / total_brake

2. BLEND WITH MSE (if mse.confidence ≥ 0.4)
   └─ final = 0.70 × analyzer_vote + 0.30 × mse_probability

3. SMOOTH (EMA α=0.5)
   └─ smooth_score = α × new + (1-α) × prev

4. BUFFER (2 frames in FAST mode)
   └─ Average when buffer full

5. DECIDE (strict priority)
   ├─ IF brake_score ≥ 0.65 → BRAKE
   ├─ ELIF ataque_score ≥ 0.60 (+ margin 0.12 over 2nd) → ATAQUE
   ├─ ELIF golpe_score ≥ 0.45 (+ 2/3 persistence) → BASE_GOLPE
   ├─ ELIF bajada_score ≥ 0.35 (+ clean drop) → BAJADA
   └─ ELSE → stay in current_state

6. VALIDATE
   ├─ Hold not active? (0.3-1.5s depending on state)
   ├─ Cooldown not active? (0.2s in FAST)
   ├─ Hysteresis satisfied? (adaptive matrix 0.04-0.18)
   ├─ Stability window passed? (120ms)
   └─ Min confidence met? (0.50)
```

### 2.3 How ATAQUE Overrides Other States

**Normal path:** ATAQUE needs score ≥ 0.60 with margin ≥ 0.12 over second place.

**Override path (≥80%):** When ataque_score ≥ 0.80:
- Requires ≥2 consecutive frames at 80%+
- Requires ≥200ms since last transition
- Bypasses hold if hold_remaining ≤ 200ms
- Bypasses cooldown (sets own 350ms cooldown)
- Still blocked by BRAKE at ≥80%

**Once inside ATAQUE:**
- Hold: 0.8s minimum duration
- Peak lock: 180ms (no exit except to BRAKE)
- Persistence: if ≥2/3 frames still ATAQUE, block exit except BRAKE

### 2.4 Persistence and Cooldown

| Mechanism | Purpose | Values (FAST) |
|-----------|---------|----------------|
| **Hold** | Min state duration | BAJADA: 0.3s, GOLPE: 0.6s, ATAQUE: 0.8s, BRAKE: 1.5s |
| **Cooldown** | Refractory period | 0.2s (0.35s after ATAQUE override) |
| **Hysteresis** | Anti-flap margin | Adaptive matrix: 0.04-0.18 depending on from→to |
| **Stability window** | Confirm before commit | 120ms |
| **Persistence buffer** | Frame consistency | deque(maxlen=3), needs ≥2/3 |

**Adaptive Hysteresis Matrix:**

| FROM \ TO | BAJADA | BASE_GOLPE | ATAQUE | BRAKE |
|-----------|--------|------------|--------|-------|
| BAJADA | — | 0.08 | 0.12 | 0.10 |
| BASE_GOLPE | 0.06 | — | 0.10 | 0.08 |
| ATAQUE | 0.08 | 0.08 | — | 0.05 |
| BRAKE | 0.18 | 0.15 | 0.12 | — |

Higher margins FROM BRAKE prevent premature exits.

---

## 3. LIMITATIONS OF CURRENT MODEL

### 3.1 Where "Single Active State" Assumption Exists

**In StateManager:**
- `self.current_state` is ONE value (line 131)
- `_determine_next_state_responsive()` picks ONE winner
- All scoring is competitive: states fight for the same slot

**In CueEngine:**
- `off_now_for_state(old_state)` kills ALL families of old state before firing new
- Module execution is gated by `if state == "MY_STATE"` checks
- No concept of two states running simultaneously

**In Modules:**
- `mod_basegolpe.run()`: only fires on `state == "BASE_GOLPE"` entry
- `mod_ataque.run()`: only active during `state == "ATAQUE"`
- `mod_bajada.run()`: only active during `state == "BAJADA"`
- Modules cannot know "I am BAJADA as context, but ATAQUE is happening as overlay"

### 3.2 Why the System Becomes "Anxious"

**Root causes:**

1. **ATAQUE competes with BASE_GOLPE for the same slot.** A brief energy spike forces a full state transition: kill BASE_GOLPE families → fire ATAQUE → hold 0.8s → return to BASE_GOLPE → re-fire. This creates visible lighting disruption for what should be a momentary accent.

2. **State transitions are destructive.** Every change triggers `off_now_for_state()` which kills ALL cues of the exiting state. Even if the new state lasts 0.8s (minimum hold), the audience sees: old look → black/kill → new look → black/kill → old look. Three visual disruptions for one musical event.

3. **EMA smoothing is fast but reactive.** With α=0.5 and buffer=2, the system responds in ~200ms. Good for genuine transitions, but also responsive to noise, brief drops, and energy fluctuations that don't represent real musical changes.

4. **Module votes are binary.** Each analyzer is ON or OFF. No gradation means a 51% active module counts the same as a 99% active one. This creates sharp score changes at threshold boundaries.

5. **MSE at 30% weight is insufficient for musical context.** The MSE can correctly identify that the music is in a groove section (BASE_GOLPE context), but a brief energy spike from the analyzer votes can override this with 70% weight.

### 3.3 Why Cues Flicker or Change Too Often

**Specific mechanisms:**

1. **Score oscillation near thresholds.** When golpe_score oscillates between 0.43 and 0.47 (around the 0.45 threshold), even with hysteresis (0.04-0.08), the state can flip every few seconds.

2. **Energy level flapping.** EnergyDetector uses P33/P66 thresholds with hysteresis=0.05. When RMS hovers near a threshold, energy flaps BAJA↔MEDIA. Since modules select different cues per energy level, the visible cue changes even within the same state.

3. **ATAQUE interruption cycle.** ATAQUE entry → 0.8s hold → exit → BASE_GOLPE entry → 0.6s hold → ATAQUE again if score still high. This creates a 1.4s oscillation cycle.

4. **BRAKE false positives from MSE.** EnergyCliff detection has dual-EMA with confirm window, but when MSE's P_brake contributes 30%, a momentary energy dip can push brake_score above 0.65.

5. **No concept of "minor event within major context."** A hi-hat roll (ATAQUE trigger) during a groove (BASE_GOLPE) causes a full state replacement instead of an overlay.

### 3.4 Legacy HTTP Assumptions

- `transport_quiet_ms` in CueEngine: originally for HTTP rate limiting
- TitanQueue priority system: KILL=1, FIRE=2 — designed for sequential HTTP
- `_sent_this_tick` flag: prevents double-fire per tick, but DMX pulses are stateless
- Family locks: needed for HTTP ordering, redundant for DMX frame-based output
- Some modules check `av.is_http_mode()` for different behavior paths

---

## 4. HYBRID MODEL DESIGN

### 4.1 Core Concept: Context + Event

```
CURRENT MODEL:
  StateManager → ONE state → CueEngine

PROPOSED MODEL:
  StateManager → {context_state, event_state} → CueEngine
```

**Context State (persistent):**
- Represents the MUSICAL SECTION the show is in
- Changes slowly (seconds to minutes)
- Defines the BASE LOOK of the show
- Values: `BAJADA`, `BASE_GOLPE`, `BREAK`

**Event State (transient overlay):**
- Represents a MOMENTARY ACTION
- Can coexist with context
- Does NOT replace context
- Values: `ATAQUE`, `None`

### 4.2 StateManager Output

```python
class HybridState:
    context_state: str      # "BAJADA" | "BASE_GOLPE" | "BREAK"
    event_state: str | None # "ATAQUE" | None
    context_confidence: float
    event_confidence: float
    energy: str             # "BAJA" | "MEDIA" | "ALTA"
```

### 4.3 Coexistence Rules

```
┌─────────────────────────────────────────────────┐
│  CONTEXT LAYER (persistent base look)           │
│                                                  │
│  BAJADA ──── C10-27 (colors + positions)        │
│  BASE_GOLPE ─ C1-9, C51-59 (FX cues)          │
│  BREAK ───── C42-44 (freeze/restore)            │
│                                                  │
│  Rules:                                          │
│  - Only ONE context active                       │
│  - Transitions require sustained confirmation    │
│  - Minimum dwell: 2-5s                          │
│  - Context change → kill old context families    │
├─────────────────────────────────────────────────┤
│  EVENT LAYER (transient overlay)                │
│                                                  │
│  ATAQUE ──── C37-39 (attack FX)                │
│                                                  │
│  Rules:                                          │
│  - Fires ON TOP of context (no kill)            │
│  - Context cues remain active                    │
│  - Event has its own short hold (0.5-1.0s)      │
│  - Event expires → context continues unchanged  │
│  - Sustained event (>5s) → may promote to       │
│    context change                                │
└─────────────────────────────────────────────────┘
```

### 4.4 Conflict Resolution

| Scenario | Resolution |
|----------|-----------|
| Context=BAJADA, Event=ATAQUE | Both active. BAJADA cues stay. ATAQUE cues overlay. |
| Context=BASE_GOLPE, Event=ATAQUE | Both active. BASE_GOLPE cues stay. ATAQUE overlays. |
| Context=BREAK, Event=ATAQUE | BREAK wins. Event suppressed (BREAK is a LOCK). |
| Context→BREAK transition | Event killed. BREAK takes exclusive control. |
| Event sustained >5s | Evaluate: if context should change, transition context. |
| Two events simultaneously | Not possible. ATAQUE is the only event state. |

### 4.5 Priority Hierarchy

```
BREAK (context lock)  >  ATAQUE (event)  >  BASE_GOLPE (context)  >  BAJADA (context)
```

BREAK as a LOCK STATE overrides everything — no events during BREAK.

---

## 5. FAMILY IMPACT ANALYSIS

### 5.1 BASE_GOLPE

**Current behavior:**
- State-exclusive: only runs during `state == "BASE_GOLPE"`
- Fires 1 cue on ENTRY, then NO-OP until state exit
- Energy level selects cue group: ALTA→C1-3, MEDIA→C4-6, BAJA→C7-9
- Killed entirely when state changes away

**Under hybrid model:**
- Becomes a CONTEXT family
- Cues persist as long as `context_state == "BASE_GOLPE"`
- NOT killed when ATAQUE event fires
- Energy changes within context trigger cue rotation (already happens)
- ATAQUE overlay fires C37-39 on top — both visible simultaneously

**Conflicts:**
- DMX channel overlap: if BASE_GOLPE and ATAQUE both control the same fixtures, there could be competition. Need to verify fixture mapping in Titan/Avolites.
- C41 (dimmer): BASE_GOLPE ALTA requests dim_off. If ATAQUE fires simultaneously, dimmer state must be consistent.

**Conceptual adaptation needed:**
- Remove `off_now_for_state("BASE_GOLPE")` when transitioning TO ATAQUE
- BASE_GOLPE module must NOT reset on ATAQUE event
- Energy transitions within BASE_GOLPE continue independently of events

### 5.2 BAJADA

**Current behavior:**
- State-exclusive: only runs during `state == "BAJADA"`
- ENTRY: pauses MOVIMIENTO, fires 1 color + 1 position
- Maintains latch (cues stay active)
- EXIT: restores MOVIMIENTO, kills latched cues

**Under hybrid model:**
- Becomes a CONTEXT family
- Persists through ATAQUE events
- BAJADA cues (colors + positions) remain during ATAQUE overlay
- MOVIMIENTO stays paused during BAJADA regardless of events

**Conflicts:**
- BAJADA position cues vs ATAQUE: both may affect position fixtures
- If ATAQUE fires during BAJADA, the "calm" look (colors/positions) overlaps with "aggressive" FX
- This may actually be DESIRABLE — brief flash on top of calm base

**Conceptual adaptation needed:**
- BAJADA module ignores event_state changes
- BAJADA exit only triggered by context_state change
- MOVIMIENTO pause/restore tied to context, not events

### 5.3 BREAK

**Current behavior:**
- Highest priority state
- ENTRY: snapshots active cues, fires brake cue, optionally kills C41
- EXIT: restores snapshot
- Hold: 1.5s minimum, highest hysteresis to exit (0.15-0.18)

**Under hybrid model:**
- Becomes a LOCK CONTEXT — exclusive, no events allowed
- When BREAK is context:
  - event_state forced to None
  - ATAQUE signals ignored
  - No overlay permitted
- BREAK entry kills ALL families (same as current)
- BREAK exit restores previous context (not just previous cues)

**Conflicts:**
- Current snapshot/restore mechanism assumes returning to previous SINGLE state
- Under hybrid: need to restore previous context_state AND event_state=None

**Conceptual adaptation needed:**
- BREAK saves `prev_context_state` instead of cue snapshot
- BREAK exit triggers context restoration, not cue-level restoration
- Event suppression flag during BREAK

### 5.4 ATAQUE

**Current behavior:**
- State-exclusive: replaces current state entirely
- ENTRY: kills previous state families, fires C37-39
- Hold: 0.8s, then can exit
- Override at ≥80% with margin check

**Under hybrid model:**
- Becomes an EVENT (overlay), NOT a context replacement
- Does NOT kill context families on entry
- Fires C37-39 ON TOP of whatever context is running
- Short hold: 0.5-1.0s
- Expiry: event_state returns to None, context unchanged
- Sustained ATAQUE (>5s continuous): may trigger context evaluation

**Conflicts:**
- Current `off_now_for_state()` kills everything — must NOT happen for events
- ATAQUE module currently assumes it owns the show during its state
- Module execution order: ATAQUE runs before BASE_GOLPE, but under hybrid both should run

**Conceptual adaptation needed:**
- ATAQUE module must be aware it's an overlay, not exclusive
- fire_cue() for ATAQUE must NOT kill context families
- New event lifecycle: fire → hold → expire → no cleanup needed (ATAQUE cues self-expire via pulse)
- Sustained ATAQUE promotion: if event persists >5s, evaluate whether context should shift

### 5.5 AUX (TIMED SEQUENCE)

**Current behavior:**
- Runs in ALL states (state-agnostic)
- Sequential cue firing: C45-50
- Resets index on state change
- Managed by AuxStateManager (separate)

**Under hybrid model:**
- Continues running in all contexts
- Index reset tied to CONTEXT change (not event change)
- ATAQUE event does NOT reset AUX sequence
- BREAK context DOES reset AUX sequence (current behavior preserved)

**Conflicts:** None expected. AUX is already independent.

**Conceptual adaptation needed:**
- Change reset trigger from "any state change" to "context_state change only"

---

## 6. CUE ENGINE IMPACT

### 6.1 Current Execution Order

```
1. Read state + energy from StateManager
2. IF state changed:
   a. off_now_for_state(old_state)    ← KILL all old families
   b. Update tracking
3. Execute modules in order:
   a. control_dimmer (C41)
   b. break (C42-44)
   c. ataque (C37-39)
   d. base_golpe (C1-9, C51-59)
   e. bajada (C10-27)
   f. movimiento (C28-36)
   g. timed (C45-50)
4. Enforce family exclusivity (every 20 ticks)
```

### 6.2 Kill-Before-Fire Analysis

**Current guarantee:** `off_now_for_state()` kills ALL cues of the exiting state BEFORE any module fires new cues. This ensures no DMX toggle conflicts.

**Under hybrid model:**

For **context transitions** (e.g., BAJADA → BASE_GOLPE):
- Kill-before-fire remains: `off_now_for_context(old_context)` kills old context families
- Same guarantee, just scoped to context families

For **event firing** (e.g., ATAQUE overlay):
- NO kill of context families
- ATAQUE's own kill-before-fire within its family still applies (kill C37 before firing C38)
- Context cues remain untouched

### 6.3 Can ATAQUE Overlay Coexist Without Breaking Cleanup?

**YES**, with conditions:

1. **ATAQUE cues (C37-39) don't share DMX channels with context cues.** If they do, the Avolites console handles LTP (Latest Takes Precedence) or HTP (Highest Takes Precedence) merging at the fixture level. This is a lighting design concern, not a software concern.

2. **ATAQUE must NOT trigger `off_now_for_state()`.** The event firing path must bypass the context kill mechanism.

3. **ATAQUE cleanup on expiry:** When event_state returns to None, ATAQUE cues must be killed. But this is just `off_now_for_family("ataque")`, not a full state kill.

### 6.4 Does ATAQUE Need Isolation from off_now_for_state()?

**YES.** This is the key architectural change:

```
CURRENT:
  off_now_for_state("BASE_GOLPE")  ← kills C1-9, C51-59
  // Then fires ATAQUE

PROPOSED:
  // Context stays BASE_GOLPE (no kill)
  fire_event("ATAQUE")  ← fires C37-39 only
  // When event expires:
  off_now_for_event("ATAQUE")  ← kills C37-39 only
```

New function needed: `off_now_for_event()` — kills only event families, not context.

### 6.5 How to Avoid Unintended Kills

| Scenario | Current (broken) | Proposed (safe) |
|----------|-----------------|-----------------|
| BASE_GOLPE + ATAQUE | Kill GOLPE, fire ATAQUE | Keep GOLPE, overlay ATAQUE |
| ATAQUE expires | Kill ATAQUE, re-enter GOLPE | Kill ATAQUE only, GOLPE continues |
| BAJADA → BASE_GOLPE | Kill BAJADA, fire GOLPE | Kill BAJADA context, fire GOLPE context |
| BREAK entry | Kill everything | Kill context + event, fire BREAK |
| BREAK exit | Restore snapshot | Restore previous context |

### 6.6 Proposed CueEngine Update Flow

```
1. Read {context_state, event_state, energy} from StateManager

2. IF context_state changed:
   a. IF entering BREAK:
      - Kill event (if any)
      - Kill previous context
      - Fire BREAK
   b. ELSE:
      - off_now_for_context(old_context)
      - Reset event_state to None
      - Fire new context modules

3. IF event_state changed:
   a. IF event_state == "ATAQUE" and context != BREAK:
      - fire_event_cue(ATAQUE, energy)
      - DO NOT touch context
   b. IF event_state == None (expired):
      - off_now_for_event("ATAQUE")
      - Context continues uninterrupted

4. Execute context modules (always)
5. Execute event modules (if event active)
6. Execute AUX (always)
```

---

## 7. MUSIC STRUCTURE ROLE

### 7.1 Current Role: Bias (30% Weight)

MSE currently acts as a **secondary voter** blended at 30% weight:

```
final_score = 0.70 × analyzer_vote + 0.30 × MSE_probability
```

**Problems:**
- 30% is enough to nudge scores but not enough to establish true musical context
- MSE can correctly identify a groove section, but 70% analyzer weight can override it with transient spikes
- MSE instability (beat tracking jitter, phrase boundary noise) gets amplified into score noise

### 7.2 Proposed Role: Context Authority

Under the hybrid model, MSE should be the **primary driver of context_state**:

```
CONTEXT decision:
  MSE.suggested_state (filtered + smoothed)
  + Analyzer confirmation
  + Temporal persistence requirements

EVENT decision:
  Analyzer votes (responsive, fast)
  + Energy detector
  + Kick detector patterns
```

**Rationale:** MSE understands musical structure (phrases, drops, builds). Analyzers understand momentary audio features. Context needs structure awareness. Events need speed.

### 7.3 Preventing MSE Instability

**Problem:** MSE can be noisy — beat tracking may lose confidence, phrase boundaries are approximate, drop detection can false-trigger.

**Solutions:**

1. **Temporal smoothing on MSE context suggestion:**
   ```
   mse_context_vote = EMA(mse_context_vote, mse.suggested_state, α=0.15)
   ```
   Much slower than current α=0.5 for state scores.

2. **Confirmation window:**
   - MSE must suggest the same context for N consecutive ticks before context changes
   - N = 8-12 ticks (400-600ms) for normal transitions
   - N = 3-4 ticks (150-200ms) for BREAK (emergency)

3. **Confidence gating:**
   - MSE suggestions only count when confidence ≥ 0.5 (currently 0.4)
   - Below threshold: context HOLDS (no change, not "unknown")

4. **Hysteresis on MSE context:**
   - Current context gets a bonus (e.g., +0.15) in scoring
   - New context must exceed current by a margin to trigger change
   - This prevents oscillation when MSE probabilities are close

### 7.4 Preventing Flickering

```
ANTI-FLICKER CHAIN:
  MSE raw probability
    → EMA smooth (α=0.15)
    → Confirmation window (8-12 ticks)
    → Confidence gate (≥0.5)
    → Incumbent bonus (+0.15)
    → Hysteresis margin (0.12)
    → Minimum dwell (2-5s)
    → CONTEXT CHANGE
```

Each layer reduces flicker probability. Combined, they ensure context changes only on genuine musical section boundaries.

---

## 8. HYBRID INTEGRATION

### 8.1 How to Let MSE Drive Context Without Breaking Persistence

**Architecture:**

```
MSE.process() → raw probabilities
    │
    ▼
ContextResolver (NEW component)
    ├─ Smooth MSE probabilities (slow EMA)
    ├─ Apply confirmation window
    ├─ Check confidence threshold
    ├─ Apply incumbent bonus
    ├─ Apply hysteresis
    ├─ Check minimum dwell
    └─ OUTPUT: context_state (changes rarely)

Analyzer votes → EventResolver (NEW component)
    ├─ Fast scoring (current α=0.5)
    ├─ ATAQUE threshold check
    ├─ Margin check (0.12 over baseline)
    ├─ Duration limit (0.5-1.0s default)
    └─ OUTPUT: event_state (changes quickly)
```

**Key principle:** ContextResolver is SLOW and STICKY. EventResolver is FAST and TRANSIENT.

### 8.2 How to Prevent MSE Instability from Causing State Flicker

1. **ContextResolver never uses raw MSE values.** All MSE data passes through the smoothing chain described in Section 7.3.

2. **ContextResolver has a "stay" bias.** When in doubt, context stays the same. Only a strong, sustained signal causes a change.

3. **Analyzer votes validate MSE suggestions.** MSE says "transition to BAJADA" but analyzers still vote 60% BASE_GOLPE → context stays BASE_GOLPE. This cross-validation prevents MSE-only errors.

4. **Dual confirmation:** Both MSE AND analyzers must agree (or at least not contradict) for context to change:
   ```
   context_change = (mse_suggests_new AND analyzer_score_new ≥ 0.30)
                    OR (analyzer_score_new ≥ 0.55 AND mse_not_contradicting)
   ```

### 8.3 How BASE_GOLPE Remains Stable but Aligned with Context

**Current problem:** BASE_GOLPE fires on entry, then does nothing. If state flickers, it re-fires repeatedly.

**Under hybrid:**
- BASE_GOLPE is a context state. Once set, it PERSISTS.
- ATAQUE events don't interrupt BASE_GOLPE at all
- Energy changes within BASE_GOLPE trigger cue rotation (already works)
- BASE_GOLPE context only exits via ContextResolver (slow, confirmed)

**Result:** BASE_GOLPE cue fires once, stays visible, energy variations select different cues within the family. ATAQUE flashes on top. No flickering.

### 8.4 How BAJADA Respects Context Transitions

**Under hybrid:**
- BAJADA is a context state with the highest persistence (minimum dwell: 5s)
- BAJADA entry still pauses MOVIMIENTO (context-level interaction)
- ATAQUE events during BAJADA are allowed but may be visually subtle (BAJADA = low energy → ATAQUE = brief flash)
- BAJADA exit requires sustained energy increase confirmed by both MSE and analyzers
- Transition BAJADA → BASE_GOLPE requires:
  - MSE suggests BASE or ATAQUE for ≥12 ticks
  - Analyzer golpe_score ≥ 0.35
  - Energy not BAJA for ≥8 ticks

### 8.5 How to Improve BREAK Timing Using Both Systems

**Current problem:** Both systems detect BREAK but with delay.

**Proposed dual-path BREAK detection:**

```
FAST PATH (EnergyCliff / analyzer):
  - Detects dB drop within ~200ms
  - Sets break_alert = True
  - Does NOT change context yet

CONFIRM PATH (MSE):
  - Detects energy trend FALLING + low transient density
  - Confirms within ~300ms

COMBINED:
  - IF break_alert AND mse_confirms:
    → BREAK context immediately (skip normal confirmation window)
  - IF break_alert AND NOT mse_confirms after 500ms:
    → Timeout, cancel alert (was noise)
  - IF mse_suggests_break AND NOT break_alert:
    → Wait for alert (MSE alone insufficient)
```

**Result:** BREAK detection ~200-300ms faster than current, with fewer false positives.

---

## 9. TRANSITION RULES

### 9.1 When Does Context Change?

| From | To | Condition |
|------|----|-----------|
| BAJADA | BASE_GOLPE | MSE ≥8 ticks + analyzer golpe ≥0.35 + energy not BAJA ≥8 ticks |
| BAJADA | BREAK | Dual-path confirmed (Section 8.5) |
| BASE_GOLPE | BAJADA | MSE ≥12 ticks + analyzer bajada ≥0.30 + energy BAJA ≥10 ticks |
| BASE_GOLPE | BREAK | Dual-path confirmed |
| BREAK | (previous) | BREAK hold expired (1.5s) + energy rising + analyzer not brake |
| BREAK | BAJADA | Default exit if previous unknown |

**Minimum dwell times:**

| Context | Min Dwell |
|---------|-----------|
| BAJADA | 3.0s |
| BASE_GOLPE | 2.0s |
| BREAK | 1.5s (then locked until release conditions) |

### 9.2 When Does ATAQUE Persist?

ATAQUE event persists (stays active beyond initial hold) when:
- Analyzer ataque_score remains ≥ 0.55 after hold expires
- Re-evaluated every tick
- Maximum event duration: 8s (forced expiry → evaluate context change)
- If ATAQUE persists >5s continuously: flag `sustained_ataque = True`
  - ContextResolver evaluates whether context should shift (e.g., BAJADA → BASE_GOLPE)

### 9.3 When Is ATAQUE Ignored?

| Condition | Action |
|-----------|--------|
| context == BREAK | Event suppressed entirely |
| Context transition in progress | Event queued until transition completes |
| ATAQUE expired <300ms ago | Refractory period (debounce) |
| ataque_score < margin over baseline | Not enough contrast |

### 9.4 BREAK Lock Behavior

BREAK operates as a **LOCK STATE** with strict rules:

```
ENTRY:
  - Dual-path confirmed
  - Kill ALL (context + event)
  - Set break_lock = True
  - Set break_hold = 1.5s

DURING LOCK:
  - event_state forced to None
  - No ATAQUE allowed
  - No context changes allowed
  - AUX sequence paused

EXIT CONDITIONS (ALL must be true):
  - break_hold expired (1.5s elapsed)
  - Energy trend = RISING or STABLE (not still FALLING)
  - brake_score < 0.40 (strong disconfirmation)
  - MSE P_brake < 0.30

FAILED EXIT:
  - If conditions not met → extend hold by 0.5s
  - Re-evaluate
  - Maximum lock: 10s (forced exit to BAJADA)
```

---

## 10. RISKS

### 10.1 Implementation Risks

| Risk | Severity | Description |
|------|----------|-------------|
| **DMX channel conflict** | HIGH | ATAQUE + context cues on same fixtures → unpredictable LTP/HTP behavior in Avolites |
| **Double-fire on overlay** | MEDIUM | ATAQUE fire + context fire in same tick → DMX pulse collision |
| **Stale context on BREAK exit** | MEDIUM | Restoring previous context that no longer matches music |
| **ATAQUE promotion lag** | LOW | 5s sustained ATAQUE before context evaluation → delayed response |
| **MSE confidence drop** | MEDIUM | During complex music, MSE confidence may stay below threshold → context frozen indefinitely |

### 10.2 Race Conditions

| Condition | Scenario | Mitigation |
|-----------|----------|------------|
| **Context + event simultaneous change** | MSE suggests context change at same tick ATAQUE fires | Process context first, then event. If context changed, suppress event for 1 tick. |
| **BREAK entry during ATAQUE** | ATAQUE active when BREAK detected | BREAK kills event immediately. Event module must handle forced cleanup. |
| **Event expiry during context transition** | ATAQUE expires at same tick context changes | Context transition takes priority. Event cleanup is implicit (off_now_for_context covers all). |
| **Module execution order** | ATAQUE module fires before BASE_GOLPE module checks state | Modules must be event-aware. Context modules skip if event_state is active for their family. |

### 10.3 Double-Trigger Risks

| Scenario | Risk | Mitigation |
|----------|------|------------|
| ATAQUE fires C37, context BASE_GOLPE also fires C4 | Both pulse in same frame | Allowed — different DMX channels. Verify in cue mapping. |
| ATAQUE expires, context re-fires | Context was never killed, no re-fire needed | Context module tracks own state. No re-fire on event expiry. |
| BREAK exit → context restore → event check | Could fire context + event in same tick | Add 1-tick delay between context restore and event evaluation. |

### 10.4 DMX Pulse Conflicts

| Conflict | Description | Mitigation |
|----------|-------------|------------|
| **Toggle-safe violation** | Killing a cue that wasn't fired (toggle ON) | Maintain separate `active_context_cues` and `active_event_cues` tracking |
| **Pulse overlap** | Two pulses on same channel in same frame | DMX state machine already handles: max(values) per frame |
| **Kill-fire-kill sequence** | Context kill + event fire + event kill in rapid succession | Minimum 2-frame gap between operations on same cue |

---

## 11. INTEGRATION PATH

### Phase 0: Preparation (No behavioral change)

**Goal:** Add infrastructure without changing any behavior.

1. Add `context_state` and `event_state` properties to StateManager that mirror `current_state`:
   ```
   context_state → current_state (passthrough)
   event_state → None (always)
   ```
2. Add `HybridState` data class (context, event, energy)
3. Add `get_hybrid_state()` method to StateManager (returns current behavior wrapped in new structure)
4. Add logging for hybrid state to verify parity with current behavior
5. **Validate:** Run for 2+ sessions. Hybrid output must exactly match current behavior.

### Phase 1: Split Scoring (Behavioral change: minimal)

**Goal:** Separate context scoring from event scoring internally, but still output single state.

1. Internally calculate `context_scores` (MSE-weighted, slow EMA) and `event_scores` (analyzer-weighted, fast)
2. Final decision still picks ONE winner (current behavior)
3. Log both scores for comparison
4. **Validate:** Scores diverge in interesting cases but final state is unchanged.

### Phase 2: ATAQUE as Event (First real behavioral change)

**Goal:** ATAQUE becomes an overlay instead of replacing context.

1. When ATAQUE would win as state:
   - Set `event_state = "ATAQUE"` instead of `current_state = "ATAQUE"`
   - Context remains unchanged
2. CueEngine: skip `off_now_for_state()` when only event changes
3. Fire ATAQUE cues without killing context cues
4. On event expiry: kill ATAQUE cues only
5. **Validate:** BASE_GOLPE cues persist during ATAQUE. Visual improvement confirmed. No DMX conflicts.

**Rollback:** Feature flag `HYBRID_ATAQUE_OVERLAY = False` reverts to current behavior.

### Phase 3: Context Persistence (Major stability improvement)

**Goal:** Context changes become slow and sticky.

1. Implement ContextResolver with smoothing chain
2. Replace direct state transition with context evaluation
3. Increase minimum dwell times for context
4. MSE drives context suggestion; analyzers validate
5. **Validate:** Context changes less frequently. No flickering. Musical sections correctly tracked.

**Rollback:** Feature flag `HYBRID_CONTEXT_RESOLVER = False` bypasses ContextResolver.

### Phase 4: BREAK Lock (Timing improvement)

**Goal:** BREAK uses dual-path detection and lock behavior.

1. Implement dual-path BREAK detection (fast alert + MSE confirm)
2. BREAK entry kills event + context
3. BREAK lock prevents all changes until exit conditions met
4. BREAK exit restores previous context
5. **Validate:** BREAK timing improved. No false triggers. Clean exit.

**Rollback:** Feature flag `HYBRID_BREAK_LOCK = False` reverts to current BREAK logic.

### Phase 5: Full Integration (Target state)

**Goal:** All components working together.

1. Remove legacy single-state code paths
2. Clean up feature flags (all enabled by default)
3. Tune parameters based on live testing
4. Document final architecture
5. **Validate:** Full session testing with multiple DJs and genres.

### Rollback Strategy

Each phase has an independent feature flag:
```python
HYBRID_FLAGS = {
    "ATAQUE_OVERLAY": True/False,      # Phase 2
    "CONTEXT_RESOLVER": True/False,    # Phase 3
    "BREAK_LOCK": True/False,          # Phase 4
}
```

Any flag can be disabled independently. System falls back to current behavior for that component. Flags stored in config, changeable at runtime without restart.

---

## APPENDIX A: CURRENT FILE MAP

```
state_manager.py          StateManager (1100+ lines) — single state machine
cue_engine.py             CueEngine — fire/kill/update orchestration
engine_audio.py           AudioEngine — capture + ring buffers
avolites_config.py        AvolitesController — hardware bridge

mod_basegolpe.py          BASE_GOLPE module (C1-9, C51-59)
mod_bajada.py             BAJADA module (C10-27)
mod_movimiento.py         MOVIMIENTO module (C28-36)
mod_ataque.py             ATAQUE module (C37-39)
mod_break.py              BRAKE module (C42-44)
mod_control_dimmer.py     C41 dimmer control
mod_timed_sequence.py     AUX sequence (C45-50)

aux_state_manager.py      AUX state tracking
module_config.py          Module enable/disable + thresholds

analyzers/                38+ analyzer modules (vote for states)
  energy_detector.py      3-level energy (BAJA/MEDIA/ALTA)
  energy_cliff.py         BRAKE detection via dB drop
  beat_steady.py          Cadence/onset detection
  bpm_detector.py         Multi-method BPM consensus

tempo/
  kick_detector.py        V18 kick detection (40-120Hz)
  auto_clock.py           BPM tracking
  tap_bridge.py           Manual tap input

core/
  audio_monitor.py        Alert system
  system_bridge.py        Calendar gating
  cues/
    family_manager.py     Extended families (C60-82)
    cue_map.py            Cue → DMX mapping
  transport/
    titan_queue.py        HTTP async queue
    dmx_state.py          DMX pulse state machine
    sacn_engine.py        sACN output
    artnet_engine.py      ArtNet output
    cue_output_adapter.py Adapter layer
  music_structure_engine/
    music_structure_engine.py  Main orchestrator
    beat_engine.py        Tempo + phase
    energy_engine.py      Multiband energy
    transient_engine.py   Transient detection
    phrase_engine.py      Phrase tracking
    drop_engine.py        Build/drop FSM
    state_inference.py    Final probabilities
    buffers.py            Ring buffers
    math_utils.py         DSP utilities
```

## APPENDIX B: CUE MAP REFERENCE

```
C1-C3:    BASE_GOLPE FX_DIMMER (ALTA)
C4-C6:    BASE_GOLPE FX_BEAM (MEDIA)
C7-C9:    BASE_GOLPE FX_COLOR (BAJA)
C10-C18:  BAJADA colores (3 groups × 3)
C19-C27:  BAJADA posiciones (3 groups × 3)
C28-C36:  MOVIMIENTO (3 subgroups × 3)
C37-C39:  ATAQUE (LOW/MID/HIGH)
C41:      CONTROL DIMMER
C42-C44:  BRAKE (BAJA/MEDIA/ALTA)
C45-C50:  AUX timed sequence
C51-C59:  BASE_GOLPE variants
C60-C63:  CLIMA
C64-C66:  HAZE
C67-C71:  DJ (5 zones)
C72-C79:  ARTIST (8 presets)
C80-C82:  TRACKING
```

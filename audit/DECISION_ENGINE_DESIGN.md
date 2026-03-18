# DECISION ENGINE DESIGN

**Baseline:** stable-dmx-cues-v1
**Status:** DESIGN ONLY — NO CODE CHANGES
**Date:** 2026-03-18
**Builds on:** `audit/HYBRID_ARCHITECTURE_AUDIT.md`

---

## TABLE OF CONTENTS

1. [Decision Engine](#1-decision-engine)
2. [Time-Based Rules](#2-time-based-rules)
3. [ATAQUE Lifecycle](#3-ataque-lifecycle)
4. [BASE_GOLPE Protection](#4-base_golpe-protection)
5. [BREAK Strategy](#5-break-strategy)
6. [Integration Plan](#6-integration-plan)

---

## 1. DECISION ENGINE

### 1.1 Position in the Pipeline

```
                     ┌─────────────────────┐
                     │   MUSIC STRUCTURE    │
                     │   ENGINE (MSE)       │
                     │                      │
                     │  P_bajada            │
                     │  P_base              │
                     │  P_ataque            │
                     │  P_brake             │
                     │  confidence          │
                     │  drop_state          │
                     │  energy_trend        │
                     │  beat_confidence     │
                     └──────────┬───────────┘
                                │
                                ▼
┌───────────────┐    ┌──────────────────────────────────────┐
│ STATE MANAGER │    │         DECISION ENGINE               │
│ (current)     │───▶│         (NEW LAYER)                   │
│               │    │                                        │
│ current_state │    │  Inputs:                               │
│ scores{}      │    │    MSE: probabilities + signals        │
│ energy        │    │    SM:  current_state, scores, energy  │
│               │    │                                        │
│               │    │  Outputs:                              │
│               │    │    context_state: str                  │
│               │    │    event_state: str | None             │
│               │    │    context_confidence: float           │
│               │    │    event_confidence: float             │
│               │    │    energy: str                         │
└───────────────┘    └────────────┬─────────────────────────┘
                                  │
                                  ▼
                     ┌──────────────────────┐
                     │     CUE ENGINE       │
                     │  (reads hybrid state)│
                     └──────────────────────┘
```

The Decision Engine sits BETWEEN the existing StateManager/MSE and the CueEngine. It does NOT replace StateManager. It consumes both inputs and produces a hybrid output.

### 1.2 Inputs

**From Music Structure Engine:**

| Signal | Type | Used For |
|--------|------|----------|
| `P_bajada` | float [0,1] | Context: BAJADA probability |
| `P_base` | float [0,1] | Context: BASE_GOLPE probability |
| `P_ataque` | float [0,1] | Event: ATAQUE probability |
| `P_brake` | float [0,1] | Context: BREAK probability |
| `confidence` | float [0,1] | Gate: trust level of MSE output |
| `energy_trend` | RISING/STABLE/FALLING | Context: direction of energy |
| `drop_state` | NONE/BUILD/PRE_DROP/DROP | Event: imminent drop detection |
| `beat_confidence` | float [0,1] | Stability: how rhythmic the audio is |
| `transient_density` | float | Energy: hits per second |
| `transient_spike` | bool | Event: sudden energy burst |

**From State Manager:**

| Signal | Type | Used For |
|--------|------|----------|
| `current_state` | str | Baseline: what SM currently thinks |
| `scores` | dict | Raw: analyzer vote percentages |
| `energy` | BAJA/MEDIA/ALTA | Direct: energy level passthrough |
| `time_in_state` | float | Persistence: how long in current state |

### 1.3 Outputs

```python
class DecisionOutput:
    context_state: str       # "BAJADA" | "BASE_GOLPE" | "BREAK"
    event_state: str | None  # "ATAQUE" | None
    context_confidence: float  # [0, 1]
    event_confidence: float    # [0, 1] (0 if no event)
    energy: str              # "BAJA" | "MEDIA" | "ALTA"
```

### 1.4 Internal Architecture

The Decision Engine contains two independent resolvers:

```
┌─────────────────────────────────────────────────────┐
│                  DECISION ENGINE                     │
│                                                      │
│  ┌─────────────────────────────────────────────┐    │
│  │           CONTEXT RESOLVER                   │    │
│  │                                               │    │
│  │  MSE probabilities (primary)                  │    │
│  │  + Analyzer validation (secondary)            │    │
│  │  + Time guards                                │    │
│  │                                               │    │
│  │  → Slow EMA (α=0.12)                         │    │
│  │  → Confirmation window (8-15 ticks)          │    │
│  │  → Incumbent bonus (+0.15)                   │    │
│  │  → Minimum dwell (2-5s)                      │    │
│  │                                               │    │
│  │  OUTPUT: context_state                        │    │
│  └─────────────────────────────────────────────┘    │
│                                                      │
│  ┌─────────────────────────────────────────────┐    │
│  │           EVENT RESOLVER                     │    │
│  │                                               │    │
│  │  Analyzer scores (primary)                    │    │
│  │  + MSE drop_state / spike (secondary)         │    │
│  │  + Context awareness                          │    │
│  │                                               │    │
│  │  → Fast threshold (no EMA delay)             │    │
│  │  → Margin check (0.12 over baseline)         │    │
│  │  → Lifecycle tracking (trigger→sustain→decay)│    │
│  │  → Context suppression rules                  │    │
│  │                                               │    │
│  │  OUTPUT: event_state                          │    │
│  └─────────────────────────────────────────────┘    │
│                                                      │
│  ┌─────────────────────────────────────────────┐    │
│  │           CONFLICT ARBITER                   │    │
│  │                                               │    │
│  │  IF context == BREAK → event = None           │    │
│  │  IF context transitioning → event deferred    │    │
│  │  IF event sustained > promotion_s → evaluate  │    │
│  │                                               │    │
│  │  OUTPUT: final {context, event}               │    │
│  └─────────────────────────────────────────────┘    │
│                                                      │
└─────────────────────────────────────────────────────┘
```

### 1.5 Priority Rules

**Absolute priority order:**

```
1. BREAK (context lock)      — overrides everything
2. Context persistence       — resists change by default
3. ATAQUE (event overlay)    — fires without disrupting context
4. Context transition        — only on sustained, confirmed change
```

**Detailed rules:**

| Rule | Description |
|------|-------------|
| **BREAK supremacy** | When BREAK is context, event_state is ALWAYS None. No exceptions. |
| **Context inertia** | Current context gets +0.15 bonus in scoring. Change must overcome this. |
| **Event independence** | Event fires/expires without touching context. Context is unaware of events. |
| **Event suppression** | Event is suppressed during BREAK, during context transition (1-tick window), and during event refractory (300ms after last event expired). |
| **Promotion** | Sustained event (>5s) triggers context re-evaluation, but does NOT force context change. |

### 1.6 Conflict Resolution

| Conflict | Resolution | Rationale |
|----------|-----------|-----------|
| Context=BAJADA, Event=ATAQUE | Both active | BAJADA cues stay. ATAQUE overlays. Brief flash on calm base. |
| Context=BASE_GOLPE, Event=ATAQUE | Both active | GOLPE cues stay. ATAQUE adds energy accent. Natural feel. |
| Context=BREAK, ATAQUE triggers | Event suppressed | BREAK is a lock. No visual noise during intentional pause. |
| Context changing + ATAQUE fires | Event deferred 1 tick | Context cleanup must complete first to avoid kill races. |
| ATAQUE active + BREAK detected | Kill event, enter BREAK | BREAK priority. Immediate cleanup. |
| MSE says BAJADA, Analyzers say GOLPE | Context stays current | Disagreement = no change. Inertia wins. |
| MSE says BAJADA, Analyzers agree | Context evaluates BAJADA | Agreement accelerates transition (reduce confirmation to 6 ticks). |

### 1.7 How Persistence Is Enforced

**Context persistence** is enforced through a chain of 5 guards, each independent:

```
Guard 1: Slow EMA (α=0.12)
  Raw MSE probability is smoothed heavily.
  A spike in P_bajada from 0.2 to 0.8 takes ~15 ticks to reach 0.6.
  Prevents impulse responses.

Guard 2: Confirmation Window
  Smoothed probability must exceed threshold for N consecutive ticks.
  N varies by target state (see Section 2).
  A single tick below threshold resets the counter.

Guard 3: Incumbent Bonus (+0.15)
  Current context_state gets automatic +0.15 added to its smoothed score.
  New state must win by >0.15 in smoothed domain.
  This is ON TOP of hysteresis.

Guard 4: Minimum Dwell
  Hard timer. Cannot leave current context until dwell expires.
  Only BREAK bypasses dwell (emergency).

Guard 5: Cross-Validation
  MSE suggestion must not be contradicted by analyzers.
  If MSE says BAJADA but analyzer bajada_score < 0.20 → blocked.
  Minimum analyzer agreement: 0.20 for the suggested state.
```

**Event persistence** is minimal by design:

```
- No EMA on event scoring (raw analyzer values)
- No confirmation window for event trigger (immediate)
- Short hold (0.8s from current system, preserved)
- Decay after hold: re-evaluate every tick
- Hard expiry at 8s (forced kill)
```

---

## 2. TIME-BASED RULES

### 2.1 Context Minimum Dwell

These are HARD minimums. No context change permitted before dwell expires (except BREAK emergency entry).

| Context State | Min Dwell | Rationale |
|---------------|-----------|-----------|
| **BAJADA** | 3.0s | Low energy section. Frequent exits destroy calm aesthetic. |
| **BASE_GOLPE** | 2.0s | Groove section. Must establish visual rhythm before changing. |
| **BREAK** | 1.5s | Intentional pause. Must hold long enough to register visually. |

**Comparison with current system:**

| State | Current Hold | Proposed Dwell | Change |
|-------|-------------|----------------|--------|
| BAJADA | 0.24s (0.8 × 0.3) | 3.0s | +12.5x longer |
| BASE_GOLPE | 0.48s (0.8 × 0.6) | 2.0s | +4.2x longer |
| BRAKE | 0.96s (0.8 × 1.2) | 1.5s | +1.6x longer |
| ATAQUE | 0.96s (0.8 × 1.2) | N/A (becomes event) | — |

The dramatic increase in BAJADA and BASE_GOLPE dwell is the KEY behavioral change. Current system changes context in under 500ms, causing anxiety. Proposed system requires 2-3s minimum, creating visual stability.

### 2.2 Context Confirmation Windows

After dwell expires, a context change still requires sustained confirmation:

| Transition | Confirmation Ticks | At 50ms/tick | Total Wait |
|-----------|-------------------|--------------|------------|
| BAJADA → BASE_GOLPE | 12 ticks | 600ms | dwell(3.0) + 0.6 = 3.6s minimum |
| BAJADA → BREAK | 4 ticks (fast path) | 200ms | dwell(3.0) + 0.2 = 3.2s minimum |
| BASE_GOLPE → BAJADA | 15 ticks | 750ms | dwell(2.0) + 0.75 = 2.75s minimum |
| BASE_GOLPE → BREAK | 4 ticks (fast path) | 200ms | dwell(2.0) + 0.2 = 2.2s minimum |
| BREAK → BAJADA | 10 ticks | 500ms | dwell(1.5) + 0.5 = 2.0s minimum |
| BREAK → BASE_GOLPE | 10 ticks | 500ms | dwell(1.5) + 0.5 = 2.0s minimum |

**Accelerated confirmation:** When MSE AND analyzers agree on the target state (cross-validated), confirmation ticks are reduced by 40%:

| Transition | Normal | Accelerated |
|-----------|--------|-------------|
| BAJADA → BASE_GOLPE | 12 ticks | 7 ticks (350ms) |
| BASE_GOLPE → BAJADA | 15 ticks | 9 ticks (450ms) |

### 2.3 Persistence Rules by State

#### BAJADA Persistence

```
ENTRY CONDITIONS:
  context_score_bajada (smoothed) > context_score_golpe + 0.15 (incumbent bonus)
  confirmation: 15 ticks sustained (or 9 if cross-validated)
  analyzer bajada_score ≥ 0.20 (cross-validation floor)
  energy = BAJA for ≥ 10 consecutive ticks (500ms)

PERSISTENCE RULES:
  - Minimum dwell: 3.0s
  - After dwell: needs golpe/break score to exceed bajada + 0.15 for 12+ ticks
  - Energy rising alone does NOT exit BAJADA (needs score confirmation)
  - ATAQUE events are allowed (overlay) but do not interrupt

EXIT CONDITIONS (ALL required):
  - Dwell expired (3.0s)
  - Target state confirmed (12-15 ticks)
  - Current bajada_score (smoothed) < target_score - 0.15
  - Energy not BAJA for ≥ 8 ticks (400ms)
  OR
  - BREAK emergency (bypasses all, see Section 5)
```

#### BASE_GOLPE Persistence

```
ENTRY CONDITIONS:
  context_score_golpe (smoothed) > context_score_bajada + 0.15
  confirmation: 12 ticks sustained (or 7 if cross-validated)
  analyzer golpe_score ≥ 0.25
  beat_confidence > 0.25 (some rhythmic content)

PERSISTENCE RULES:
  - Minimum dwell: 2.0s
  - Default fallback: if no other context qualifies, stay in BASE_GOLPE
  - ATAQUE events overlay freely (primary use case)
  - Energy changes within GOLPE trigger cue rotation (existing behavior preserved)

EXIT CONDITIONS (ALL required):
  - Dwell expired (2.0s)
  - Target state confirmed (15 ticks for BAJADA, 4 for BREAK)
  - golpe_score (smoothed) < target_score - 0.15
  - If exiting to BAJADA: energy BAJA for ≥ 10 ticks
  OR
  - BREAK emergency (bypasses all)
```

#### BREAK Persistence

```
ENTRY CONDITIONS:
  See Section 5 (dual-path detection)

PERSISTENCE RULES:
  - Minimum dwell: 1.5s (HARD LOCK)
  - Event suppression: event_state forced to None
  - AUX sequence: paused
  - No other context can take over during lock

EXIT CONDITIONS (ALL required, very strict):
  - Dwell expired (1.5s)
  - brake_score (smoothed) < 0.35
  - MSE P_brake < 0.30
  - energy_trend != FALLING (must be STABLE or RISING)
  - At least ONE of: analyzer golpe_score > 0.30 OR analyzer bajada_score > 0.25
    (confirmed destination exists)

FAILED EXIT:
  - Extend lock by 500ms
  - Re-evaluate
  - Maximum total lock: 8.0s
  - After 8.0s forced exit → BASE_GOLPE (safe default)
```

### 2.4 Cooldown After Context Transition

| Transition Type | Cooldown |
|----------------|----------|
| Any → BREAK | 0ms (immediate entry, BREAK is emergency) |
| BREAK → any | 500ms (prevent re-entry oscillation) |
| BAJADA → BASE_GOLPE | 300ms |
| BASE_GOLPE → BAJADA | 300ms |

During cooldown, no new context transition is evaluated. Events continue independently.

---

## 3. ATAQUE LIFECYCLE

### 3.1 State Diagram

```
                    trigger conditions met
         ┌──────────────────────────────────────┐
         │                                       │
         ▼                                       │
   ┌──────────┐    hold expires    ┌──────────┐  │   score drops
   │ TRIGGER  │──────────────────▶│ SUSTAIN  │──┴──────────────▶ DECAY
   │          │                    │          │                      │
   │ fire cue │                    │ re-eval  │                      │
   │ set hold │                    │ each tick│                      ▼
   └──────────┘                    └──────────┘               ┌──────────┐
                                        │                     │  DECAY   │
                                        │ >8s                 │          │
                                        ▼                     │ kill cue │
                                  ┌──────────┐               │ cooldown │
                                  │ PROMOTE  │               └────┬─────┘
                                  │ EVALUATE │                    │
                                  │          │                    ▼
                                  │ re-eval  │               ┌──────────┐
                                  │ context  │               │  IDLE    │
                                  └──────────┘               │          │
                                                              │ no event │
                                                              └──────────┘
```

### 3.2 Trigger Condition

ATAQUE fires when ALL of the following are true:

```
1. event_state == None (no current event)
   OR event refractory expired (≥300ms since last ATAQUE decay)

2. context_state != BREAK (not in lock)

3. context_state is not transitioning (no pending context change)

4. Analyzer ataque_score ≥ 0.55
   (Lowered from current 0.60 because ATAQUE no longer competes
    for the state slot — it only needs to be "notable")

5. Margin check: ataque_score - max(bajada_score, golpe_score) ≥ 0.10
   (Must clearly exceed baseline activity. Prevents false triggers
    when all scores are elevated together.)

6. Persistence: ataque_score ≥ 0.55 for ≥ 2 of last 3 ticks
   (Preserved from current _atk_persistence logic)
```

**Additional fast-trigger (override):**

```
IF ataque_score ≥ 0.80 for ≥ 2 consecutive ticks:
  Skip margin check (condition 5)
  Skip persistence (condition 6)
  Fire immediately
  (Preserved from current atk_override_threshold logic)
```

### 3.3 Sustain

After trigger, ATAQUE enters hold:

```
Hold duration: 0.8s (preserved from current: min_hold_seconds × 1.2 = 0.96 ≈ 0.8)

During hold:
  - ATAQUE cue stays active
  - Context cues ALSO stay active (new: no kill)
  - No re-evaluation of trigger conditions
  - Peak lock: 180ms sub-hold (first 180ms cannot decay, preserved)
```

After hold expires, ATAQUE enters sustain:

```
Sustain evaluation (every tick, 50ms):
  IF ataque_score ≥ 0.45:
    → ATAQUE continues (stay in SUSTAIN)
  ELIF ataque_score < 0.45:
    → Begin DECAY

Sustain threshold (0.45) is LOWER than trigger threshold (0.55).
This creates hysteresis: harder to trigger, easier to maintain.
```

### 3.4 Decay

```
Decay trigger: ataque_score < 0.45 after hold expired

Decay action:
  1. Set event_state = None
  2. Kill ATAQUE family cues (C37-39) via off_now_for_family("ataque")
  3. Start refractory timer: 300ms
  4. Context is UNAFFECTED (no re-fire needed, cues were never killed)

Refractory:
  During 300ms after decay, no new ATAQUE can trigger.
  Prevents oscillation when score hovers around threshold.
```

### 3.5 Ignore Conditions

ATAQUE is completely ignored (never fires) when:

| Condition | Reason |
|-----------|--------|
| context == BREAK | Lock state, no events |
| Context transition pending | Avoid race with context cleanup |
| Refractory active (< 300ms since last decay) | Anti-oscillation |
| ataque_score < 0.55 | Below trigger threshold |
| Margin < 0.10 over baseline (unless override) | Not distinct enough from baseline |
| System disabled states include ATAQUE | Calendar gating |

### 3.6 When ATAQUE Becomes Context (Promotion)

ATAQUE can signal a context change, but it NEVER becomes a context itself:

```
Promotion evaluation:
  IF ATAQUE sustained > 5.0s continuously:
    flag: sustained_ataque = True

    Context Resolver re-evaluates with boosted weights:
      golpe_score_boosted = golpe_score + 0.10
      (Sustained ATAQUE implies high energy → BASE_GOLPE context likely correct)

    IF context == BAJADA AND golpe_score_boosted > bajada_score + 0.10:
      → Trigger context transition BAJADA → BASE_GOLPE
      → (Normal confirmation window, but accelerated to 6 ticks)

    IF context already BASE_GOLPE:
      → No change needed. ATAQUE continues as event until decay.

  IF ATAQUE sustained > 8.0s:
    → Forced decay (hard expiry)
    → Context re-evaluation forced (one-time)
```

ATAQUE never becomes `context_state = "ATAQUE"`. It is always an event or it promotes the context to BASE_GOLPE.

---

## 4. BASE_GOLPE PROTECTION

### 4.1 Role: Default Fallback

BASE_GOLPE is the system's HOME STATE. When no other context qualifies with confidence, the system defaults to BASE_GOLPE.

```
Fallback logic in Context Resolver:

  IF no context_score exceeds threshold:
    → context_state = BASE_GOLPE (fallback)

  IF BREAK exit and no clear target:
    → context_state = BASE_GOLPE (safe default)

  IF system startup and no audio analyzed yet:
    → context_state = BASE_GOLPE (initial state)

  IF MSE confidence < 0.3 and analyzer scores all < 0.40:
    → context_state = BASE_GOLPE (uncertainty default)
```

### 4.2 Persistent Base Layer

BASE_GOLPE cues represent the "default look" of the show. Under the hybrid model:

```
BASE_GOLPE cues (C1-9, C51-59) are ALWAYS ACTIVE when context = BASE_GOLPE.
They are:
  - NOT killed when ATAQUE fires (event overlay)
  - NOT killed when energy changes (cue rotation within family)
  - NOT interrupted by MSE score fluctuations (dwell protection)
  - ONLY killed on genuine context transition (to BAJADA or BREAK)
```

### 4.3 When BASE_GOLPE Is Overridden

| Scenario | Override? | What Happens |
|----------|-----------|-------------|
| ATAQUE event fires | **NO** | ATAQUE overlays. GOLPE cues stay. |
| Energy changes MEDIA→ALTA | **NO** (context) | Cue rotates within GOLPE family. |
| MSE briefly suggests BAJADA | **NO** | Smoothing + confirmation blocks it. |
| MSE sustained BAJADA for 2.75s+ | **YES** (context transition) | GOLPE families killed, BAJADA fires. |
| BREAK detected (dual-path confirmed) | **YES** (emergency) | GOLPE killed. BREAK takes over. |
| Calendar disables BASE_GOLPE | **YES** (external) | System falls to BAJADA. |

### 4.4 When BASE_GOLPE Returns

| Scenario | Return Path |
|----------|------------|
| After ATAQUE event decays | Immediate — GOLPE was never killed. No re-fire needed. |
| After BREAK exit (was previous context) | Context Resolver restores. GOLPE families re-fired. Confirmation window reduced to 4 ticks. |
| After BAJADA context with rising energy | Normal transition: 12 ticks confirmation, dwell respected. |
| After system uncertainty | Fallback: if no state qualifies, return to GOLPE. |

### 4.5 BASE_GOLPE Stability Guarantees

```
GUARANTEE 1: No kill on event
  ATAQUE overlay never triggers off_now_for_family("base_golpe").
  CueEngine only calls off_now_for_context() on CONTEXT changes.
  Event changes bypass context kill path entirely.

GUARANTEE 2: Minimum visibility
  Once BASE_GOLPE fires, minimum dwell of 2.0s ensures
  the audience sees a stable look for at least 2 seconds.
  ATAQUE events during this time ADD to the look, don't replace it.

GUARANTEE 3: Fallback safety
  If Context Resolver encounters uncertainty (MSE low confidence,
  conflicting analyzer votes), it defaults to BASE_GOLPE.
  The system never enters "no context" state.

GUARANTEE 4: Energy continuity
  Energy level changes (BAJA→MEDIA→ALTA) within BASE_GOLPE
  trigger cue rotation via the module's existing run() logic.
  This happens independently of the Decision Engine.
  The Decision Engine does NOT interfere with within-state behavior.
```

---

## 5. BREAK STRATEGY

### 5.1 Early Detection Signals

BREAK uses a dual-path detection to combine speed with accuracy:

```
┌───────────────────────────────────────────┐
│  FAST PATH (Analyzer-driven)              │
│                                            │
│  Source: EnergyCliff (energy_cliff.py)     │
│  + Analyzer brake votes                    │
│                                            │
│  Signal: brake_alert                       │
│  Latency: ~150-200ms from energy drop      │
│  Method:                                   │
│    e_short vs e_long divergence > threshold│
│    OR brake analyzer votes ≥ 0.50          │
│                                            │
│  Output: brake_alert = True/False          │
│  Confidence: LOW (speed over accuracy)     │
└────────────────────┬──────────────────────┘
                     │
                     │  AND
                     │
┌────────────────────┴──────────────────────┐
│  CONFIRM PATH (MSE-driven)                │
│                                            │
│  Source: MSE StateInference                │
│  + Energy trend                            │
│                                            │
│  Signal: brake_confirm                     │
│  Latency: ~200-400ms from energy drop      │
│  Method:                                   │
│    MSE P_brake > 0.40                      │
│    AND energy_trend == FALLING             │
│    AND transient_density < 3.0             │
│                                            │
│  Output: brake_confirm = True/False        │
│  Confidence: MEDIUM (accuracy over speed)  │
└────────────────────┬──────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│  DECISION LOGIC                            │
│                                            │
│  IF brake_alert AND brake_confirm:         │
│    → BREAK confirmed, enter immediately    │
│    → Skip normal context confirmation      │
│    → Latency: ~200-300ms (improvement)     │
│                                            │
│  IF brake_alert AND NOT brake_confirm:     │
│    → Wait up to 400ms for confirm          │
│    → IF confirm arrives: enter BREAK       │
│    → IF timeout (400ms): cancel alert      │
│                                            │
│  IF brake_confirm AND NOT brake_alert:     │
│    → Treat as weak signal                  │
│    → Wait for alert (up to 300ms)          │
│    → Usually means gradual energy decrease │
│    → May transition to BAJADA instead      │
│                                            │
│  IF strong_brake (both scores ≥ 0.70):     │
│    → Skip all confirmation                 │
│    → BREAK immediately                      │
│    → Maximum urgency path                  │
└────────────────────────────────────────────┘
```

### 5.2 BREAK Confirmation Logic

```
CONFIRMED BREAK triggers the following ATOMIC sequence:

  1. Set context_state = BREAK
  2. Set event_state = None (kill any active ATAQUE)
  3. Set break_lock = True
  4. Set break_dwell_remaining = 1.5s
  5. Record previous_context for restoration
  6. CueEngine: off_now_for_context(previous_context)
  7. CueEngine: off_now_for_event() (if ATAQUE was active)
  8. Fire BREAK cue (C42/43/44 per energy)

ALL steps in a single tick. No interleaving possible.
```

### 5.3 Exit Rules (Very Strict)

BREAK exit requires passing through THREE gates sequentially:

```
GATE 1: DWELL (hard timer)
  break_dwell_remaining must reach 0
  Starts at 1.5s, counts down every tick
  CANNOT be bypassed by any score or signal
  Purpose: guarantee minimum visual break

GATE 2: DISCONFIRMATION (scores must drop)
  ALL of the following must be true:
    - Analyzer brake_score < 0.35 (current BRAKE_EXIT_THRESHOLD)
    - MSE P_brake < 0.30
    - EnergyCliff brake_alert = False
  Purpose: ensure the musical break is genuinely over,
           not just a brief recovery within the break

GATE 3: DESTINATION (must have somewhere to go)
  At least ONE of:
    - Analyzer golpe_score > 0.30 → exit to BASE_GOLPE
    - Analyzer bajada_score > 0.25 → exit to BAJADA
    - Beat_confidence > 0.25 → exit to BASE_GOLPE (rhythm detected)
  If none: stay in BREAK (extend)
  Purpose: never exit BREAK into uncertainty

EXTENSION LOGIC:
  IF Gate 1 passed but Gate 2 OR Gate 3 failed:
    Extend break_dwell_remaining by 500ms
    Re-evaluate after extension
    Log: "BREAK extended: gate2={pass/fail}, gate3={pass/fail}"

  MAXIMUM total BREAK duration: 8.0s
    After 8.0s: forced exit to BASE_GOLPE (safe fallback)
    Log: "BREAK forced exit after 8.0s"
```

### 5.4 BREAK Timing Improvement

**Current system:** Both StateManager and MSE detect BREAK but with combined latency of ~400-600ms.

**Proposed dual-path:** By running analyzer-fast-path and MSE-confirm-path in parallel and requiring both to agree, we get:

| Metric | Current | Proposed | Improvement |
|--------|---------|----------|-------------|
| Detection latency | 400-600ms | 200-300ms | ~50% faster |
| False positive rate | ~5% | ~2% (dual-path AND) | ~60% fewer |
| Exit latency | ~300ms | ~500ms (stricter gates) | Intentionally slower |
| Visual hold | 0.96s | 1.5s minimum | +56% longer |

The tradeoff: slower exits for faster, more confident entries. This matches the musical intent — a BREAK should be a definitive visual pause, not a brief flicker.

---

## 6. INTEGRATION PLAN

### Phase 0: Observability Layer (Zero behavioral change)

**Goal:** Add the Decision Engine as a PASSIVE OBSERVER that logs what it WOULD decide, without affecting any real behavior.

```
Steps:
  1. Create DecisionEngine class with resolve() method
  2. Wire it to receive MSE state and SM state (read-only)
  3. On every tick, compute:
     - would_context = ContextResolver.evaluate()
     - would_event = EventResolver.evaluate()
  4. Log to file: decision_engine_shadow.log
     Format: "[DE] tick=N ctx_would=X event_would=Y actual=Z match={yes/no}"
  5. NO changes to CueEngine, StateManager, or any module

Validation:
  - Run 3+ live sessions
  - Analyze shadow log: how often does DE agree with SM?
  - Identify cases where DE differs — are those improvements?
  - Measure: context change frequency (should be lower)
  - Measure: ATAQUE overlay frequency (should be higher than current ATAQUE state transitions)

Duration: 2-4 sessions
Rollback: Delete DecisionEngine instantiation. Zero risk.
```

### Phase 1: ATAQUE Overlay (First real change, smallest scope)

**Goal:** ATAQUE becomes an event overlay instead of replacing context.

```
Steps:
  1. DecisionEngine.resolve() output feeds CueEngine (not shadow)
  2. CueEngine reads event_state from DE instead of checking SM state == "ATAQUE"
  3. When event_state == "ATAQUE":
     - Skip off_now_for_state() (do NOT kill context families)
     - Fire ATAQUE cue (C37-39) via existing module
     - Context modules continue running (their cues stay active)
  4. When event_state returns to None:
     - Kill ATAQUE family (C37-39)
     - Context modules unaffected
  5. StateManager still runs — its ATAQUE state is logged but CueEngine ignores it for ATAQUE.
     SM still handles BAJADA/GOLPE/BRAKE as before.

Validation:
  - BASE_GOLPE cues MUST persist during ATAQUE (verify with DMX monitor)
  - BAJADA cues MUST persist during ATAQUE
  - ATAQUE cues MUST fire and expire correctly
  - No DMX toggle glitches (verify pulse patterns)
  - Visual quality: brief accent ON TOP of base look, not replacement
  - Timing: ATAQUE response time same or better than current

Feature flag: HYBRID_ATAQUE_OVERLAY (in config)
  True  → DE controls ATAQUE as event
  False → SM controls ATAQUE as state (current behavior)

Rollback: Set flag to False. Immediate revert. Zero state to clean up.
Duration: 1-2 sessions to validate.
```

### Phase 2: Context Persistence (Major stability change)

**Goal:** ContextResolver takes over context decisions. Longer dwell, slower transitions.

```
Steps:
  1. ContextResolver activated (reads from MSE + SM scores)
  2. CueEngine reads context_state from DE instead of SM for BAJADA/BASE_GOLPE
  3. SM continues running internally (scores computed, logged)
  4. Context changes now require:
     - Slow EMA smoothing (α=0.12)
     - Confirmation window (8-15 ticks)
     - Minimum dwell (2.0-3.0s)
  5. off_now_for_context() replaces off_now_for_state() for context transitions

Validation:
  - Context change frequency MUST decrease (measure: transitions per minute)
  - Visual stability: base look persists for seconds, not sub-seconds
  - Musical alignment: context changes at section boundaries, not random
  - ATAQUE overlay from Phase 1 still works correctly on new context layer
  - No "stuck" states: system must still respond to genuine section changes

Feature flag: HYBRID_CONTEXT_RESOLVER (in config)
  True  → DE ContextResolver drives context
  False → SM drives context (current behavior)

Combined with Phase 1 flag:
  Both False → fully current behavior
  ATAQUE only → overlay but SM context
  Both True → full hybrid

Rollback: Set flag to False. SM resumes control. Context cues may flash once on revert.
Duration: 2-3 sessions to validate across different music genres.
```

### Phase 3: BREAK Lock (Timing improvement)

**Goal:** Dual-path BREAK detection with strict lock behavior.

```
Steps:
  1. Add brake_alert tracking in DE (fast path from EnergyCliff + analyzer scores)
  2. Add brake_confirm tracking in DE (confirm path from MSE P_brake + energy_trend)
  3. BREAK entry logic: dual-path AND (both must agree)
  4. BREAK lock behavior:
     - event_state forced to None
     - Context frozen
     - Strict 3-gate exit
  5. CueEngine: BREAK entry triggers full kill (context + event)
  6. CueEngine: BREAK exit restores previous context via ContextResolver

Validation:
  - BREAK detection latency improved (measure with timestamp logging)
  - False positive rate decreased (measure: BREAK entries per session)
  - BREAK visual hold feels intentional (1.5s minimum)
  - BREAK exit is clean: no oscillation back into BREAK
  - Previous context resumes smoothly after BREAK

Feature flag: HYBRID_BREAK_LOCK (in config)
  True  → DE dual-path BREAK
  False → SM BRAKE logic (current behavior)

Rollback: Set flag to False. SM BRAKE logic resumes.
Duration: 2-3 sessions. Test with music that has frequent breaks/drops.
```

### Phase 4: Full Integration + Tuning

**Goal:** All phases active. Tune parameters. Remove legacy paths.

```
Steps:
  1. All three flags enabled by default
  2. SM internal scoring still runs (for comparison logging)
  3. Fine-tune based on live feedback:
     - Adjust dwell times per genre
     - Adjust ATAQUE trigger threshold
     - Adjust BREAK detection sensitivity
     - Adjust confirmation windows
  4. Once stable for 5+ sessions:
     - Remove feature flags (always-on)
     - Remove SM scoring for states DE handles
     - SM retains: energy detection, analyzer coordination, preset system
  5. Document final parameters

Validation:
  - Full session without any flag toggling
  - System behaves well across techno, house, ambient, drum & bass
  - Context changes are musically appropriate
  - ATAQUE feels like an accent, not a disruption
  - BREAK is reliable and well-timed
  - No DMX conflicts or toggle glitches
  - Latency within budget (250-400ms audio to DMX)

Duration: 5+ sessions for confidence.
```

### Summary: Risk Profile Per Phase

| Phase | Risk | Blast Radius | Rollback |
|-------|------|-------------|----------|
| 0: Observer | ZERO | None (shadow only) | Delete instantiation |
| 1: ATAQUE Overlay | LOW | ATAQUE cues only | Feature flag |
| 2: Context Persistence | MEDIUM | All context transitions | Feature flag |
| 3: BREAK Lock | LOW-MEDIUM | BREAK detection/exit | Feature flag |
| 4: Full Integration | LOW (validated) | Everything | Revert to Phase 3 |

Each phase is independently reversible. No phase depends on a later phase. Phases can be deployed in isolation for testing.

---

## APPENDIX: PARAMETER REFERENCE

All tunable parameters in the Decision Engine, with proposed values and the current system value they replace:

### Context Resolver

| Parameter | Proposed | Current Equivalent | Change Rationale |
|-----------|----------|-------------------|-----------------|
| `ctx_ema_alpha` | 0.12 | 0.5 (SM ema_alpha) | 4x slower smoothing for context stability |
| `ctx_confirm_bajada` | 15 ticks | 2 frames (SM buffer) | 7.5x longer confirmation |
| `ctx_confirm_golpe` | 12 ticks | 2 frames | 6x longer confirmation |
| `ctx_confirm_break` | 4 ticks | immediate (SM) | 2x slower but dual-path compensates |
| `ctx_incumbent_bonus` | 0.15 | 0.04-0.07 (SM hysteresis) | 2-4x stronger inertia |
| `ctx_dwell_bajada` | 3.0s | 0.24s (SM hold) | 12.5x longer minimum |
| `ctx_dwell_golpe` | 2.0s | 0.48s (SM hold) | 4.2x longer minimum |
| `ctx_dwell_break` | 1.5s | 0.96s (SM hold) | 1.6x longer minimum |
| `ctx_cross_validation_floor` | 0.20 | N/A (new) | Prevent MSE-only false transitions |
| `ctx_accelerate_ratio` | 0.60 | N/A (new) | Cross-validated confirmations 40% faster |
| `ctx_mse_confidence_gate` | 0.45 | 0.40 (SM) | Slightly stricter MSE trust |
| `ctx_cooldown_post_break` | 500ms | 200ms (SM cooldown) | Prevent BREAK re-entry |
| `ctx_cooldown_normal` | 300ms | 200ms (SM cooldown) | Slightly more refractory |

### Event Resolver

| Parameter | Proposed | Current Equivalent | Change Rationale |
|-----------|----------|-------------------|-----------------|
| `evt_trigger_threshold` | 0.55 | 0.60 (SM ATAQUE_THRESHOLD) | Lower: ATAQUE doesn't compete for state slot |
| `evt_margin_required` | 0.10 | 0.12 (SM atk_margin) | Slightly more permissive |
| `evt_override_threshold` | 0.80 | 0.80 (SM atk_override) | Preserved exactly |
| `evt_hold_duration` | 0.8s | 0.96s (SM hold × 1.2) | Slightly shorter: overlay, not takeover |
| `evt_sustain_threshold` | 0.45 | N/A (new) | Hysteresis below trigger |
| `evt_peak_lock` | 180ms | 180ms (SM _atk_peak_lock) | Preserved exactly |
| `evt_refractory` | 300ms | 200ms (SM cooldown) | Slightly longer anti-oscillation |
| `evt_max_duration` | 8.0s | 8.0s (SM ataque_timer) | Preserved exactly |
| `evt_promotion_threshold` | 5.0s | N/A (new) | When to evaluate context boost |
| `evt_persistence_frames` | 3 | 3 (SM _atk_persistence) | Preserved exactly |

### BREAK Detector

| Parameter | Proposed | Current Equivalent | Change Rationale |
|-----------|----------|-------------------|-----------------|
| `brk_alert_analyzer_threshold` | 0.50 | 0.52 (SM BRAKE_ENTRY) | Slightly more sensitive fast path |
| `brk_confirm_mse_threshold` | 0.40 | 0.40 (blended at 30%) | Now direct MSE value, no blending |
| `brk_confirm_transient_max` | 3.0 | N/A (in MSE state_inference) | Low transient density confirms silence |
| `brk_strong_threshold` | 0.70 | N/A (new) | Immediate entry, no dual-path wait |
| `brk_alert_timeout` | 400ms | N/A (new) | Cancel unconfirmed alert |
| `brk_exit_analyzer` | 0.35 | 0.35 (SM BRAKE_EXIT) | Preserved exactly |
| `brk_exit_mse` | 0.30 | N/A (new) | MSE must also agree on exit |
| `brk_exit_destination_floor` | 0.25 | N/A (new) | Must have somewhere to go |
| `brk_extend_increment` | 500ms | N/A (new) | Extend if exit gates fail |
| `brk_max_duration` | 8.0s | 4.0s (SM brake_timer) | 2x longer maximum before forced exit |

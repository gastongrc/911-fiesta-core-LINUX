# 911 Fiesta - Motor Musical V12 Documentation

## Overview

The 911 Fiesta system is an audio-reactive lighting control system that analyzes music in real-time and triggers lighting cues via Avolites Titan HTTP transport.

---

## State Machine

The system operates on a 4-state machine:

| State | Description | Visual Style |
|-------|-------------|--------------|
| **BAJADA** | Low energy, ambient, breakdown sections | Soft, atmospheric lighting |
| **BASE_GOLPE** | Rhythmic foundation, steady beat | Pulsing, beat-synced effects |
| **ATAQUE** | High intensity, drops, builds | Intense strobes, fast movements |
| **BRAKE** | Sudden stop, tension, silence | Dramatic cuts, holds |

### State Priority (highest to lowest)
1. BRAKE (emergency stop)
2. ATAQUE (high energy)
3. BASE_GOLPE (rhythmic)
4. BAJADA (ambient)

---

## Analyzer Organization (V12)

### Motor Real (Active Analyzers)
These analyzers drive the state machine voting system.

#### BAJADA (5 analyzers)
- **NoHits**: Detects absence of percussive hits
- **DeepListener**: Monitors low-frequency energy
- **SoftPeaks**: Identifies soft transients
- **RampDown**: Detects energy decline
- **BreakSpotter**: Identifies musical breaks

#### BASE_GOLPE (10 analyzers - V11 pipeline)
- **YesHits**: Detects percussive hits
- **AccentCatcher**: Identifies accented beats
- **GrooveKeeper**: Monitors rhythmic consistency
- **PatternLock**: Detects repeating patterns
- **CadenceSpotter**: Identifies musical cadences
- **FlowMonitor**: Tracks energy flow
- **DynamicPulse**: Monitors dynamic range
- **PulseFinderAnalyzer**: Advanced beat detection
- **RhythmHighlighter**: Highlights rhythmic elements
- **BurstSharpness**: Detects explosive transients

#### ATAQUE (3 analyzers)
- **SnareRoll**: Detects snare rolls/fills
- **HiRoll**: Detects hi-hat rolls
- **BurstSharpness**: Detects explosive energy (shared with BASE_GOLPE)

#### BRAKE (4 analyzers)
- **EnergyCliff**: Detects sudden energy drops
- **WidebandBlackout**: Detects full-spectrum silence
- **RhythmVoid**: Detects absence of rhythm
- **BrakeAnalyzer**: Comprehensive brake detection

### Legacy Analyzers
These analyzers are available for monitoring/experimentation but do NOT participate in voting:

- HighSilence, LoopDissolver, DynamicFlattener, TextureCleaner, AmbientConfirmator (from BAJADA)
- BurstContinuity (from ATAQUE)

---

## Voting System

### How Voting Works
1. Each analyzer has a `.card.is_on()` method that returns True when its condition is met
2. Votes are counted per state category
3. Score = (active_votes / total_analyzers) for each state

### V12 Thresholds
| State | Threshold | Description |
|-------|-----------|-------------|
| BRAKE | 65% | 2-3 of 4 analyzers |
| ATAQUE | 68% | 2-3 of 3 analyzers |
| BASE_GOLPE | 40% | 4+ of 10 analyzers (V12: was 52%) |
| BAJADA | 35% | 2+ of 5 analyzers |

### Additional Requirements
- **BASE_GOLPE**: Requires 2+ frames of persistence
- **ATAQUE**: Requires clean rise (scores increasing over 3 frames) or already in ATAQUE
- **BAJADA**: Requires sustained drop (2+ frames)
- **BRAKE**: No additional requirements (emergency priority)

---

## Stability Mechanisms (V12)

### 1. Stability Window (350ms)
A proposed state change must be consistent for 350ms before being applied.
- Prevents jitter and false transitions
- BRAKE bypasses this for emergency stops

### 2. Inter-State Cooldown (500ms)
Minimum time between state changes.
- Prevents rapid bouncing between states
- BRAKE bypasses this for emergency stops

### 3. EMA Smoothing
Exponential Moving Average applied to scores.
- Alpha = 0.3 (30% new, 70% old)
- Smooths out noise in analyzer outputs

### 4. Hysteresis
Score must exceed current state by margin (0.12) to transition.
- Prevents oscillation at threshold boundaries
- Adaptive based on source/target state

### 5. Hold Timers
Minimum time to stay in a state after entering:
- BAJADA: 0.48s (40% of min_hold)
- BASE_GOLPE: 0.72s (60% of min_hold)
- ATAQUE: 1.44s (120% of min_hold)
- BRAKE: 1.44s (120% of min_hold)

---

## Calibrating for POPE (Production Environment)

### Audio Input
1. Use a high-quality audio interface
2. Set input gain to avoid clipping (-6dB headroom)
3. Use the stereo mix from the DJ/sound system

### Threshold Tuning
Access via the UI Config tab:

| Parameter | Default | Adjustment |
|-----------|---------|------------|
| `min_hold_seconds` | 1.2 | Increase for slower transitions |
| `hysteresis_margin` | 0.12 | Increase for more stability |
| `cooldown_seconds` | 2.0 | Increase to reduce transitions |

### Energy Detector
The EnergyDetector classifies audio into BAJA/MEDIA/ALTA levels.
- Run calibration at the start of each event
- Calibration samples 10 seconds of audio to set thresholds

### Testing Procedure
1. Start with known music tracks
2. Verify BAJADA triggers during breakdowns
3. Verify BASE_GOLPE triggers during steady beats
4. Verify ATAQUE triggers during drops/builds
5. Verify BRAKE triggers during sudden stops

---

## Cue Anti-Repeat System

### V11.1 Global Anti-Repeat
The system prevents repeating the same cue when returning to a state:

1. **Energy-specific tracking**: Last cue per energy level (BAJA/MEDIA/ALTA)
2. **Global tracking**: Last cue across all selections
3. **Previous latched tracking**: Saves cue before deactivation

### Tern A/B Alternation
BASE_GOLPE uses 6 cues per energy level in two groups (Tern A and Tern B):
- Entry 1: Tern A
- Entry 2: Tern B
- Entry 3: Tern A (but anti-repeat prevents same cue)

### Bridge System (UNION V1)
After 2 complete cycles in the same family/energy, the system fires 1 cue from the neighbor family before returning to normal rotation.

---

## Automatic vs UI-Configurable

### Automatic (No UI adjustment)
- Analyzer voting logic
- State transitions
- Cue anti-repeat
- EMA smoothing

### UI-Configurable
- `min_hold_seconds`: Minimum hold time in state
- `hysteresis_margin`: Score margin for transitions
- `cooldown_seconds`: Cooldown after ATAQUE/BRAKE exit
- Energy thresholds (via calibration)
- Individual analyzer enable/disable
- Preset save/load

---

## Titan HTTP Transport

### Configuration
- Console IP: Default 10.0.0.1
- Console Port: Default 4430
- Local Interface: Auto-detected or manual

### Commands
- Fire Cue: `POST /titan/script/Playback/FireCue?userNumber={cue}`
- Kill Cue: `POST /titan/script/Playback/KillPlayback?userNumber={cue}`
- Kill All: `POST /titan/script/Playback/KillAll`

### TAP Tempo Bridge
The TapBridge sends TAP tempo commands to Titan for BPM sync:
- Triggered when BASE_GOLPE votes >= 4
- AutoClock provides clock ticks for tempo tracking

---

## Performance Metrics

Access via StateMonitor widget "Performance Info" button:

- Buffer Fill: Stability buffer utilization
- Hold Active: Currently in hold period
- Cooldown Active: Currently in cooldown
- Time Since Transition: Seconds since last state change
- Override Count: ATAQUE override activations
- Blocked Counts: Transitions blocked by hold/cooldown/confidence

---

## Troubleshooting

### State Not Changing
1. Check analyzer cards are active (green borders)
2. Verify audio input is connected
3. Check VU meter shows signal
4. Review blocked counts in Performance Info

### Too Many Transitions
1. Increase `hysteresis_margin`
2. Increase `min_hold_seconds`
3. Increase `cooldown_seconds`

### Cue Repeat Issues
1. Check V11.1 anti-repeat is active in mod_basegolpe.py
2. Verify families have 6+ cues per energy level
3. Check console log for anti-repeat messages

### Titan Connection Issues
1. Verify console IP is correct
2. Check local interface selection
3. Ensure Titan HTTP API is enabled
4. Check firewall settings

---

## Version History

- **V12**: Stability window (350ms), inter-state cooldown (500ms), BASE_GOLPE threshold 40%, Motor Real/Legacy organization, Neon Pro UI
- **V11.1**: Global anti-repeat tracking for state re-entry
- **V11**: 10-flag voting system, analyzer pipeline reconnection
- **V10**: PulseFinder integration
- **V9**: BurstSharpness reintegration
- **V8.1**: Legacy compatibility
- **V8**: TITAN HTTP Transport

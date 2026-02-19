# Titan Tap Tempo Integration (v3.0 — Stable Burst Sender)

## v2.0 → v3.0 regression fix

v2.0 introduced a regression: `wake.set()` called from `update()` every 40ms
starved the worker's `_interruptible_wait()`, causing it to spin instead of
sleep. GIL contention slowed the Qt main thread, degrading the kick detector
and AutoClock. LOCK rarely achieved; taps fired at wrong intervals.

v3.0 fix:
- **NO shared Event** between Qt thread and worker
- Worker uses `time.monotonic()` for tap spacing + `_stop.wait(timeout)` for idle polling
- `update()` is O(1): writes 2 values under a lock, nothing else
- Removed keepalive (send only on lock-achieved and tempo-change)

## Kill Switch

```bash
# Disable all sending (zero HTTP traffic, zero side effects)
TAP_SENDER_ENABLED=0

# Enable (default)
TAP_SENDER_ENABLED=1
```

When disabled, the worker thread sleeps and does nothing. The object exists but
is inert. No code changes needed.

## Endpoint

```
GET http://{TITAN_IP}:{TITAN_PORT}/titan/script/2/Macros/Run?macroId={TAP_MACRO_ID}
```

Default: `http://192.168.1.45:4430/titan/script/2/Macros/Run?macroId=Avolites.Macros.TapBPM1`

## Behavior

```
IDLE ──(LOCK achieved)──► BURST(N taps) ──► IDLE
IDLE ──(tempo changed while LOCKED)──► BURST(N taps) ──► IDLE
BURST ──(LOCK lost)──► IDLE (abort immediately)
```

| Trigger | Action |
|---------|--------|
| Lock achieved | Burst of 3 taps at `interval_ms` spacing |
| Tempo changed (>12ms or >3%) | Burst of 3 taps at new `interval_ms` spacing |
| Lock lost | Abort burst, go IDLE |
| Not locked | Zero HTTP traffic |

## Threading Model

```
Qt thread (40ms timer)          Worker thread (daemon)
───────────────────             ────────────────────────
update(lock, interval)          _worker():
  with lock:                      polls every 200ms
    write 2 values                reads shared state
  return  ← O(1)                  if burst needed:
                                    send taps via monotonic scheduler
                                    (200ms cancel chunks)
```

- `update()` NEVER does I/O, NEVER sleeps, NEVER blocks
- All HTTP happens on worker thread only
- Worker polls at 200ms when idle — zero coupling with tick rate
- Burst waits use `time.monotonic()` for precise beat spacing
- Cancel latency: ≤200ms (chunk size)

## Configuration (env vars)

| Var | Default | Description |
|-----|---------|-------------|
| `TAP_SENDER_ENABLED` | `1` | Kill switch: `0` disables all sending |
| `TITAN_IP` | `192.168.1.45` | Titan console IP |
| `TITAN_PORT` | `4430` | Titan WebAPI port |
| `TAP_MACRO_ID` | `Avolites.Macros.TapBPM1` | Macro to run for tap |
| `TAP_BURST_COUNT` | `3` | Taps per burst |
| `TAP_DIFF_MS` | `12` | Min ms difference for tempo change |
| `TAP_DIFF_RATIO` | `0.03` | Min ratio difference (3%) |

## Log Format

```
# Startup
[TapSender] v3.0 ENABLED → 192.168.1.45:4430 macro=... burst=3 diff=12ms/3%

# Burst on lock
[TapSender] BURST bpm=128.2 interval_ms=468.0 count=3 reason=LOCKED

# Burst on tempo change
[TapSender] BURST bpm=130.0 interval_ms=461.5 count=3 reason=CHANGE

# Lock lost during burst
[TapSender] ABORT reason=LOCK_LOST

# HTTP error
[TapSender] FAIL HTTP 500
[TapSender] FAIL ConnectionError(...)
```

No per-beat logging. No spam.

## Manual Test

```bash
curl -s "http://192.168.1.45:4430/titan/script/2/Macros/Run?macroId=Avolites.Macros.TapBPM1"
# Expected: true
```

## Files

| File | Change |
|------|--------|
| `tempo/tap_sender.py` | v3.0: Fix v2.0 regression, monotonic scheduler, kill switch |
| `main.py` | Version string v2→v3 |
| `docs/titan_tap_tempo.md` | This file |

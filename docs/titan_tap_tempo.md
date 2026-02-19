# Titan Tap Tempo Integration (v2.0 — Transport Clock)

## Endpoint

```
GET http://{TITAN_IP}:{TITAN_PORT}/titan/script/2/Macros/Run?macroId={TAP_MACRO_ID}
```

Default: `http://192.168.1.45:4430/titan/script/2/Macros/Run?macroId=Avolites.Macros.TapBPM1`

Returns `true` on success (HTTP 200).

## Why Transport Clock (v2)

Titan's TapBPM macro needs **periodic taps** to maintain BPM sync.
v1 only sent taps on tempo change — Titan lost sync within seconds.
v2 sends keep-alive taps every N beats while LOCKED.

## State Machine

```
             lock achieved
   IDLE ──────────────────► SYNC_BURST ──(done)──► KEEPALIVE
                                                      │  ▲
                                            tempo     │  │ done
                                            changed   ▼  │
                                                 CHANGE_BURST

   ANY ──(lock lost)──► IDLE
```

| State | Action | Tap rate |
|-------|--------|----------|
| IDLE | Sleep, zero HTTP traffic | 0 |
| SYNC_BURST | 3 taps at 1-beat intervals | 1 per beat |
| KEEPALIVE | 1 tap every 4 beats (1 bar) | 1 per bar |
| CHANGE_BURST | 3 taps at 1-beat intervals | 1 per beat |

## Architecture

```
AutoClock (Qt thread, 40ms timer)
    │
    │ get_ui_state() → lock_state + interval_ms
    │
    ▼
TapTempoSender.update(lock_state, interval_ms)
    │  (writes shared state under lock, wakes worker)
    │
    ▼
Worker thread (persistent daemon, sleeps between taps)
    │
    ├─ IDLE: sleep until woken
    ├─ SYNC_BURST: tap-wait-tap-wait-tap → KEEPALIVE
    ├─ KEEPALIVE: wait 4 beats → tap → repeat
    └─ CHANGE_BURST: tap-wait-tap-wait-tap → KEEPALIVE
         │
         └──GET──► Titan Macro Run
```

- **1 persistent daemon thread** (not ephemeral threads per burst)
- Own `requests.Session` (not shared with TitanQueue)
- Interruptible waits (500ms chunks) for fast lock-loss response
- Anti-spam: never faster than 1 tap per beat interval

## Firing Rules

1. **Gate**: Only when `lock_state == "LOCKED"`
2. **Initial sync**: SYNC_BURST of 3 taps on lock achieved
3. **Keep-alive**: 1 tap every `beats_per_tap` beats (default 4)
4. **Tempo change**: CHANGE_BURST when `abs(interval - last_sent) >= max(12ms, last_sent * 3%)`
5. **Lock lost**: Immediate cancel → IDLE (zero traffic)

## Configuration (env vars)

| Var | Default | Description |
|-----|---------|-------------|
| `TITAN_IP` | `192.168.1.45` | Titan console IP |
| `TITAN_PORT` | `4430` | Titan WebAPI port |
| `TAP_MACRO_ID` | `Avolites.Macros.TapBPM1` | Macro to run for tap |
| `TAP_BURST_COUNT` | `3` | Taps per burst (sync + change) |
| `TAP_BEATS_PER_TAP` | `4` | Beats between keep-alive taps (4 = 1 bar) |
| `TAP_DIFF_MS` | `12` | Min ms difference for "tempo changed" |
| `TAP_DIFF_RATIO` | `0.03` | Min ratio difference (3%) |

## Example Timeline (128 BPM = 468ms/beat)

```
t=0.0s   LOCKED achieved
t=0.0s   [SYNC_BURST] Tap 1 → Titan
t=0.47s  [SYNC_BURST] Tap 2 → Titan
t=0.94s  [SYNC_BURST] Tap 3 → Titan  → KEEPALIVE
t=2.81s  [KEEPALIVE]  Tap 4 → Titan  (4 beats later)
t=4.68s  [KEEPALIVE]  Tap 5 → Titan  (4 beats later)
t=5.50s  DJ changes to 130 BPM (461ms)
t=6.55s  [CHANGE_BURST] Tap 6 → Titan
t=7.01s  [CHANGE_BURST] Tap 7 → Titan
t=7.47s  [CHANGE_BURST] Tap 8 → Titan  → KEEPALIVE
t=9.31s  [KEEPALIVE]  Tap 9 → Titan
...
```

## Manual Test (curl)

```bash
# Single tap
curl -s "http://192.168.1.45:4430/titan/script/2/Macros/Run?macroId=Avolites.Macros.TapBPM1"
# Expected: true

# Simulate 128 BPM burst (468ms interval)
curl -s "http://192.168.1.45:4430/titan/script/2/Macros/Run?macroId=Avolites.Macros.TapBPM1" && \
sleep 0.468 && \
curl -s "http://192.168.1.45:4430/titan/script/2/Macros/Run?macroId=Avolites.Macros.TapBPM1" && \
sleep 0.468 && \
curl -s "http://192.168.1.45:4430/titan/script/2/Macros/Run?macroId=Avolites.Macros.TapBPM1"
```

## Test from 911 Fiesta

1. Set env vars in `systemd/911fiesta.env`:
   ```
   TITAN_IP=192.168.1.45
   TITAN_PORT=4430
   ```

2. Reload and restart:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart 911fiesta.service
   ```

3. Play music with clear kick. Wait for LOCKED (green LED in Tap Tempo tab).

4. Watch logs:
   ```bash
   journalctl -u 911fiesta.service -f | grep TapSender
   ```

5. Expected output:
   ```
   [TapSender] v2.0 transport clock → 192.168.1.45:4430 ...
   [TapSender] SYNC_BURST interval=468.2ms bpm=128.2 taps=3
   [TapSender] CHANGE_BURST interval=461.5ms bpm=130.0 taps=3
   ```

6. Verify in Titan that BPM master stays synced continuously.

## Files

| File | Change |
|------|--------|
| `tempo/tap_sender.py` | v2.0: Transport clock with IDLE/BURST/KEEPALIVE state machine |
| `tempo/__init__.py` | Added SenderState export |
| `main.py` | Comment + version string updated |
| `docs/titan_tap_tempo.md` | This file (updated for v2) |

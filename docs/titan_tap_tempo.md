# Titan Tap Tempo Integration

## Endpoint

```
GET http://{TITAN_IP}:{TITAN_PORT}/titan/script/2/Macros/Run?macroId={TAP_MACRO_ID}
```

Default: `http://192.168.1.45:4430/titan/script/2/Macros/Run?macroId=Avolites.Macros.TapBPM1`

Returns `true` on success (HTTP 200).

## Architecture

```
AutoClock (Qt thread, 40ms timer)
    │
    │ get_ui_state() → lock_state + interval_ms
    │
    ▼
TapTempoSender.update(lock_state, interval_ms)
    │
    ├─ NOT LOCKED → cancel burst, return
    ├─ cooldown < 3s → return
    ├─ diff < threshold → return
    │
    └─ FIRE BURST (daemon thread)
         ├─ Tap 1  ──GET──► Titan
         ├─ wait interval_ms
         ├─ Tap 2  ──GET──► Titan
         ├─ wait interval_ms
         └─ Tap 3  ──GET──► Titan
```

- Own daemon thread for HTTP (never blocks Qt/audio)
- Own `requests.Session` (not shared with TitanQueue)
- Burst cancellable on lock loss

## Firing Rules

1. **Gate**: Only when `lock_state == "LOCKED"`
2. **Tempo changed**: `abs(interval_ms - last_sent) >= max(12ms, last_sent * 3%)`
3. **Cooldown**: Minimum 3s between bursts
4. **Lock lost**: Cancel in-flight burst immediately

## Configuration (env vars)

| Var | Default | Description |
|-----|---------|-------------|
| `TITAN_IP` | `192.168.1.45` | Titan console IP |
| `TITAN_PORT` | `4430` | Titan WebAPI port |
| `TAP_MACRO_ID` | `Avolites.Macros.TapBPM1` | Macro to run for tap |
| `TAP_DIFF_MS` | `12` | Min ms difference for "tempo changed" |
| `TAP_DIFF_RATIO` | `0.03` | Min ratio difference (3%) |
| `TAP_COOLDOWN_S` | `3.0` | Seconds between bursts |
| `TAP_BURST_COUNT` | `3` | Taps per burst |

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

5. Expected output on tempo change:
   ```
   [TapSender] BURST interval=468.2ms bpm=128.2 count=3 cooldown=3.0s
   ```

6. Verify in Titan that BPM master updated.

## Files

| File | Change |
|------|--------|
| `tempo/tap_sender.py` | New: TapTempoSender class |
| `tempo/__init__.py` | Added exports |
| `main.py` | Import + init + update() call in tick |

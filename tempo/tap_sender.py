# tempo/tap_sender.py
# TapTempoSender v3.0 — Stable burst sender for Titan BPM sync
#
# v2.0 regression: wake.set() every 40ms from update() starved
# _interruptible_wait(), causing the worker to spin instead of sleep.
# GIL contention slowed Qt thread → detector/clock degraded → no LOCK.
# Taps fired at wrong intervals → Titan converged to wrong BPM.
#
# v3.0 fix: NO shared Event between Qt thread and worker.
# Worker uses time.monotonic() scheduler — zero coupling with tick rate.
# update() is O(1): writes 2 floats under a lock, nothing else.
# Worker polls shared state at its own cadence, never spins.
#
# Kill switch: TAP_SENDER_ENABLED=0 → sender created but worker is no-op.
#
# Endpoint: GET http://{ip}:{port}/titan/script/2/Macros/Run?macroId={macro}

import os
import time
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import requests
from requests.adapters import HTTPAdapter


class SenderState(Enum):
    IDLE = "IDLE"
    BURST = "BURST"


@dataclass
class TapSenderConfig:
    """Configuration — all overridable via env vars."""
    titan_ip: str = os.environ.get("TITAN_IP", "192.168.1.45")
    titan_port: int = int(os.environ.get("TITAN_PORT", "4430"))
    macro_id: str = os.environ.get("TAP_MACRO_ID", "Avolites.Macros.TapBPM1")

    # Burst config
    burst_count: int = int(os.environ.get("TAP_BURST_COUNT", "4"))

    # Fixed tap spacing in burst (milliseconds) — NOT derived from BPM
    tap_spacing_ms: float = float(os.environ.get("TAP_SPACING_MS", "100"))

    # Tempo change detection thresholds (2% triggers immediate burst)
    diff_ms: float = float(os.environ.get("TAP_DIFF_MS", "8"))
    diff_ratio: float = float(os.environ.get("TAP_DIFF_RATIO", "0.02"))

    # BPM scale factor: 0.5 = console receives half the detected BPM
    # e.g. 100 BPM detected → 50 BPM sent to console
    bpm_scale_factor: float = float(os.environ.get("TAP_BPM_SCALE", "0.5"))

    # HTTP timeouts (seconds)
    connect_timeout: float = 0.8
    read_timeout: float = 0.8

    # Kill switch: "0" disables all sending
    enabled: bool = os.environ.get("TAP_SENDER_ENABLED", "1") != "0"


class TapTempoSender:
    """
    Tempo → Titan Burst Sender v3.0

    Behavior:
      - IDLE while not LOCKED (zero traffic)
      - On LOCK achieved: BURST of N taps spaced at interval_ms
      - On tempo change while LOCKED: BURST of N taps at new interval_ms
      - On LOCK lost: abort any in-progress burst immediately

    Threading:
      - update() called from Qt thread: O(1), writes 2 values, NO I/O
      - _worker() on daemon thread: polls state every 200ms when idle,
        uses time.monotonic() for precise tap spacing during burst
      - NO shared Event — worker sleeps independently of tick rate
    """

    # Worker poll interval when idle (seconds)
    _POLL_S = 0.05  # 50ms poll for fast tempo change detection

    def __init__(self, config: Optional[TapSenderConfig] = None):
        self._cfg = config or TapSenderConfig()

        # --- Shared state (Qt thread writes, worker reads) ---
        self._lock = threading.Lock()
        self._lock_state: str = "UNLOCKED"
        self._interval_ms: float = 0.0
        self._prev_interval_ms: float = 0.0  # For change detection in update()

        # --- Worker-only state ---
        self._sender_state = SenderState.IDLE
        self._was_locked: bool = False
        self._last_sent_interval_ms: float = 0.0
        self._burst_remaining: int = 0

        # --- Thread control ---
        self._stop = threading.Event()
        self._wake = threading.Event()  # Wakes worker immediately on tempo change

        # --- HTTP session ---
        self._session = requests.Session()
        adapter = HTTPAdapter(pool_connections=1, pool_maxsize=1, max_retries=0)
        self._session.mount("http://", adapter)
        self._session.headers["Connection"] = "keep-alive"

        # --- Stats ---
        self._taps_ok: int = 0
        self._taps_fail: int = 0
        self._bursts: int = 0

        self._url = (
            f"http://{self._cfg.titan_ip}:{self._cfg.titan_port}"
            f"/titan/script/2/Macros/Run?macroId={self._cfg.macro_id}"
        )

        # Start worker
        self._thread = threading.Thread(
            target=self._worker, name="TapSender", daemon=True
        )
        self._thread.start()

        status = "ENABLED" if self._cfg.enabled else "DISABLED (TAP_SENDER_ENABLED=0)"
        print(
            f"[TapSender] v3.3 {status} → {self._cfg.titan_ip}:{self._cfg.titan_port} "
            f"macro={self._cfg.macro_id} burst={self._cfg.burst_count} "
            f"spacing={self._cfg.tap_spacing_ms}ms "
            f"diff={self._cfg.diff_ms}ms/{self._cfg.diff_ratio*100:.0f}% "
            f"bpm_scale={self._cfg.bpm_scale_factor}"
        )

    # =================================================================
    # Public API — called from Qt thread, every ~40ms
    # MUST be O(1), NO I/O, NO sleep, NO blocking
    # =================================================================

    def update(self, lock_state: str, interval_ms: float):
        """Write state for worker. O(1), never blocks.
        Wakes worker immediately if tempo changed >2% while LOCKED."""
        wake_needed = False
        with self._lock:
            self._lock_state = lock_state
            self._interval_ms = interval_ms
            # Detect significant change while locked → wake worker
            if (lock_state == "LOCKED" and self._prev_interval_ms > 0
                    and interval_ms > 0):
                diff = abs(interval_ms - self._prev_interval_ms)
                threshold = self._prev_interval_ms * self._cfg.diff_ratio
                if diff >= max(threshold, self._cfg.diff_ms):
                    wake_needed = True
            self._prev_interval_ms = interval_ms
        if wake_needed:
            self._wake.set()

    def stop(self):
        """Graceful shutdown."""
        self._stop.set()
        self._wake.set()  # Unblock worker if waiting
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)
        try:
            self._session.close()
        except Exception:
            pass

    def get_stats(self) -> dict:
        return {
            "state": self._sender_state.value,
            "enabled": self._cfg.enabled,
            "bursts": self._bursts,
            "taps_ok": self._taps_ok,
            "taps_fail": self._taps_fail,
        }

    # =================================================================
    # Worker thread — polls shared state, sends HTTP on its own schedule
    # =================================================================

    def _worker(self):
        while not self._stop.is_set():
            # Kill switch check
            if not self._cfg.enabled:
                self._stop.wait(timeout=2.0)
                continue

            # Clear wake flag (consume any pending wake)
            self._wake.clear()

            # Read shared state (single lock acquire per iteration)
            with self._lock:
                lock_state = self._lock_state
                interval_ms = self._interval_ms

            locked = (lock_state == "LOCKED")

            # --- LOCK LOST → IDLE ---
            if not locked:
                if self._was_locked and self._sender_state == SenderState.BURST:
                    print("[TapSender] ABORT reason=LOCK_LOST")
                self._sender_state = SenderState.IDLE
                self._was_locked = False
                self._burst_remaining = 0
                # Wait on wake OR stop (wake allows instant response)
                self._wake.wait(timeout=self._POLL_S)
                if self._stop.is_set():
                    break
                continue

            # --- LOCK JUST ACHIEVED → BURST ---
            if locked and not self._was_locked:
                self._was_locked = True
                self._start_burst(interval_ms, "LOCKED")
                self._execute_burst(interval_ms)
                continue

            # --- LOCKED steady state: check for tempo change ---
            if self._tempo_changed(interval_ms):
                self._start_burst(interval_ms, "CHANGE")
                self._execute_burst(interval_ms)
                continue

            # --- LOCKED, no change: wait for wake or poll timeout ---
            self._wake.wait(timeout=self._POLL_S)
            if self._stop.is_set():
                break

    def _start_burst(self, interval_ms: float, reason: str):
        """Initialize a burst. Worker-only."""
        self._sender_state = SenderState.BURST
        self._burst_remaining = self._cfg.burst_count
        self._last_sent_interval_ms = interval_ms
        self._bursts += 1
        bpm = 60000.0 / interval_ms if interval_ms > 0 else 0
        scale = self._cfg.bpm_scale_factor
        scaled_bpm = bpm * scale if scale > 0 else bpm
        print(
            f"[TapSender] BURST detected={bpm:.1f}BPM → console={scaled_bpm:.1f}BPM "
            f"(scale={scale}) count={self._cfg.burst_count} reason={reason}"
        )

    def _execute_burst(self, interval_ms: float):
        """
        Send burst_count taps spaced at FIXED tap_spacing_ms using monotonic clock.
        Fixed spacing ensures <1s console BPM update regardless of detected BPM.
        Cancels immediately on lock loss or stop.
        """
        # Fixed tap spacing — NOT derived from BPM interval
        wait_s = self._cfg.tap_spacing_ms / 1000.0

        while self._burst_remaining > 0 and not self._stop.is_set():
            t0 = time.monotonic()

            # Check lock before sending
            with self._lock:
                if self._lock_state != "LOCKED":
                    print("[TapSender] ABORT reason=LOCK_LOST")
                    self._burst_remaining = 0
                    self._sender_state = SenderState.IDLE
                    return

            ok = self._send_tap()
            self._burst_remaining -= 1

            if not ok:
                self._burst_remaining = 0
                self._sender_state = SenderState.IDLE
                return

            # Precise monotonic wait for next tap (except after last)
            if self._burst_remaining > 0:
                elapsed = time.monotonic() - t0
                remaining = wait_s - elapsed
                if remaining > 0:
                    # Sleep in <=200ms chunks to allow fast cancellation
                    deadline = time.monotonic() + remaining
                    while time.monotonic() < deadline and not self._stop.is_set():
                        chunk = min(deadline - time.monotonic(), 0.2)
                        if chunk > 0:
                            self._stop.wait(timeout=chunk)
                        # Check lock during wait
                        with self._lock:
                            if self._lock_state != "LOCKED":
                                print("[TapSender] ABORT reason=LOCK_LOST")
                                self._burst_remaining = 0
                                self._sender_state = SenderState.IDLE
                                return

        self._sender_state = SenderState.IDLE

    # =================================================================
    # Tempo change detection
    # =================================================================

    def _tempo_changed(self, interval_ms: float) -> bool:
        if self._last_sent_interval_ms <= 0:
            return False  # Never sent → wait for first burst via LOCKED edge
        diff = abs(interval_ms - self._last_sent_interval_ms)
        threshold = max(self._cfg.diff_ms,
                        self._last_sent_interval_ms * self._cfg.diff_ratio)
        return diff >= threshold

    # =================================================================
    # HTTP — always on worker thread, never on Qt thread
    # =================================================================

    def _send_tap(self) -> bool:
        try:
            resp = self._session.get(
                self._url,
                timeout=(self._cfg.connect_timeout, self._cfg.read_timeout),
            )
            if resp.status_code == 200:
                self._taps_ok += 1
                return True
            self._taps_fail += 1
            print(f"[TapSender] FAIL HTTP {resp.status_code}")
            return False
        except Exception as e:
            self._taps_fail += 1
            print(f"[TapSender] FAIL {e}")
            return False

    def __del__(self):
        try:
            self.stop()
        except Exception:
            pass


__all__ = ["TapTempoSender", "TapSenderConfig", "SenderState"]

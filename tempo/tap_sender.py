# tempo/tap_sender.py
# TapTempoSender v2.0 - Transport Clock for Titan BPM sync
#
# Architecture:
# - Persistent daemon worker thread (sleeps between taps)
# - Qt thread calls update() every ~40ms → sets shared state
# - Worker reads shared state → sends taps at beat-aligned intervals
# - State machine: IDLE → SYNC_BURST → KEEPALIVE ↔ CHANGE_BURST
#
# Why transport clock:
# Titan's TapBPM macro needs periodic taps to maintain BPM.
# A burst-only-on-change design loses sync within seconds.
# This V2 sends keep-alive taps every N beats while LOCKED.
#
# Endpoint: GET http://{ip}:{port}/titan/script/2/Macros/Run?macroId={macro}

import os
import time
import threading
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import requests
from requests.adapters import HTTPAdapter

logger = logging.getLogger("TapTempoSender")


class SenderState(Enum):
    IDLE = "IDLE"
    SYNC_BURST = "SYNC_BURST"
    CHANGE_BURST = "CHANGE_BURST"
    KEEPALIVE = "KEEPALIVE"


@dataclass
class TapSenderConfig:
    """Configuration — all overridable via env vars."""
    titan_ip: str = os.environ.get("TITAN_IP", "192.168.1.45")
    titan_port: int = int(os.environ.get("TITAN_PORT", "4430"))
    macro_id: str = os.environ.get("TAP_MACRO_ID", "Avolites.Macros.TapBPM1")

    # Burst config
    burst_count: int = int(os.environ.get("TAP_BURST_COUNT", "3"))

    # Keep-alive: send 1 tap every N beats (default 4 = 1 bar)
    beats_per_tap: int = int(os.environ.get("TAP_BEATS_PER_TAP", "4"))

    # Tempo change detection
    diff_ms: float = float(os.environ.get("TAP_DIFF_MS", "12"))
    diff_ratio: float = float(os.environ.get("TAP_DIFF_RATIO", "0.03"))

    # HTTP
    connect_timeout: float = 1.0
    read_timeout: float = 1.0


class TapTempoSender:
    """
    Tempo → Titan Transport Clock v2.0

    State machine:
      IDLE ──(lock achieved)──► SYNC_BURST ──(done)──► KEEPALIVE
      KEEPALIVE ──(tempo changed)──► CHANGE_BURST ──(done)──► KEEPALIVE
      ANY ──(lock lost)──► IDLE

    Thread model:
      - update() called from Qt thread every ~40ms: writes shared state
      - _worker() runs on persistent daemon thread: reads state, sends taps
      - Anti-spam: never sends faster than 1 tap per beat interval
    """

    def __init__(self, config: Optional[TapSenderConfig] = None):
        self._cfg = config or TapSenderConfig()

        # --- Shared state (written by Qt thread, read by worker) ---
        self._state_lock = threading.Lock()
        self._lock_state: str = "UNLOCKED"
        self._interval_ms: float = 0.0
        self._was_locked: bool = False

        # --- Worker-owned state (only touched by worker thread) ---
        self._sender_state = SenderState.IDLE
        self._last_sent_interval_ms: float = 0.0
        self._burst_remaining: int = 0

        # --- Worker thread control ---
        self._wake = threading.Event()
        self._stop_event = threading.Event()

        # --- HTTP session (own session, not shared with TitanQueue) ---
        self._session = requests.Session()
        adapter = HTTPAdapter(pool_connections=1, pool_maxsize=2, max_retries=0)
        self._session.mount("http://", adapter)
        self._session.headers.update({
            "Connection": "keep-alive",
            "User-Agent": "911Fiesta-TapSender/2.0",
        })

        # --- Stats ---
        self._bursts_sent: int = 0
        self._taps_ok: int = 0
        self._taps_failed: int = 0

        self._url = (
            f"http://{self._cfg.titan_ip}:{self._cfg.titan_port}"
            f"/titan/script/2/Macros/Run?macroId={self._cfg.macro_id}"
        )

        # Start persistent worker
        self._worker_thread = threading.Thread(
            target=self._worker,
            name="TapSender-Worker",
            daemon=True,
        )
        self._worker_thread.start()

        print(
            f"[TapSender] v2.0 transport clock → {self._cfg.titan_ip}:{self._cfg.titan_port} "
            f"macro={self._cfg.macro_id} burst={self._cfg.burst_count} "
            f"keepalive=every {self._cfg.beats_per_tap} beats "
            f"diff={self._cfg.diff_ms}ms/{self._cfg.diff_ratio*100:.0f}%"
        )

    # =================================================================
    # Public API (called from Qt thread, every ~40ms)
    # =================================================================

    def update(self, lock_state: str, interval_ms: float):
        """
        Called every tick (~40ms) from Qt thread.
        Writes shared state for worker to consume. Never blocks.
        """
        with self._state_lock:
            self._lock_state = lock_state
            self._interval_ms = interval_ms
        # Wake worker so it can react to state changes
        self._wake.set()

    def stop(self):
        """Stop worker thread and close HTTP session."""
        self._stop_event.set()
        self._wake.set()
        if self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)
        try:
            self._session.close()
        except Exception:
            pass

    def get_stats(self) -> dict:
        return {
            "state": self._sender_state.value,
            "bursts_sent": self._bursts_sent,
            "taps_ok": self._taps_ok,
            "taps_failed": self._taps_failed,
            "last_sent_interval_ms": self._last_sent_interval_ms,
        }

    # =================================================================
    # Worker thread (persistent, sleeps between taps)
    # =================================================================

    def _worker(self):
        """
        Persistent worker loop. Runs on daemon thread.
        Reads shared state, manages state machine, sends taps.
        """
        while not self._stop_event.is_set():
            # Read shared state
            with self._state_lock:
                lock_state = self._lock_state
                interval_ms = self._interval_ms

            locked = (lock_state == "LOCKED")

            # === LOCK LOST → IDLE ===
            if not locked:
                if self._sender_state != SenderState.IDLE:
                    if self._was_locked:
                        print("[TapSender] lock lost → IDLE")
                    self._sender_state = SenderState.IDLE
                    self._burst_remaining = 0
                self._was_locked = False
                # Sleep until woken by update()
                self._wake.wait(timeout=1.0)
                self._wake.clear()
                continue

            # === LOCK JUST ACHIEVED → SYNC_BURST ===
            if locked and not self._was_locked:
                self._was_locked = True
                self._sender_state = SenderState.SYNC_BURST
                self._burst_remaining = self._cfg.burst_count
                self._last_sent_interval_ms = interval_ms
                bpm = 60000.0 / interval_ms if interval_ms > 0 else 0
                self._bursts_sent += 1
                print(
                    f"[TapSender] SYNC_BURST interval={interval_ms:.1f}ms "
                    f"bpm={bpm:.1f} taps={self._cfg.burst_count}"
                )

            # === KEEPALIVE: check for tempo change ===
            if self._sender_state == SenderState.KEEPALIVE:
                if self._tempo_changed(interval_ms):
                    self._sender_state = SenderState.CHANGE_BURST
                    self._burst_remaining = self._cfg.burst_count
                    self._last_sent_interval_ms = interval_ms
                    bpm = 60000.0 / interval_ms if interval_ms > 0 else 0
                    self._bursts_sent += 1
                    print(
                        f"[TapSender] CHANGE_BURST interval={interval_ms:.1f}ms "
                        f"bpm={bpm:.1f} taps={self._cfg.burst_count}"
                    )

            # === Execute current state ===
            if self._sender_state in (SenderState.SYNC_BURST, SenderState.CHANGE_BURST):
                self._do_burst(interval_ms)
            elif self._sender_state == SenderState.KEEPALIVE:
                self._do_keepalive(interval_ms)
            else:
                # Shouldn't get here while locked, but safety
                self._wake.wait(timeout=0.5)
                self._wake.clear()

    def _do_burst(self, interval_ms: float):
        """Send remaining burst taps, 1 per beat interval."""
        while self._burst_remaining > 0 and not self._stop_event.is_set():
            # Check lock still held
            with self._state_lock:
                if self._lock_state != "LOCKED":
                    return

            ok = self._send_tap()
            self._burst_remaining -= 1

            if not ok:
                # Abort burst on HTTP failure
                self._burst_remaining = 0
                self._sender_state = SenderState.KEEPALIVE
                return

            # Wait 1 beat between taps (except after last)
            if self._burst_remaining > 0:
                wait_s = interval_ms / 1000.0
                if self._interruptible_wait(wait_s):
                    return  # Stopped or lock lost

        # Burst complete → KEEPALIVE
        self._sender_state = SenderState.KEEPALIVE

    def _do_keepalive(self, interval_ms: float):
        """Wait N beats, send 1 tap, repeat."""
        # Wait beats_per_tap beats
        wait_s = (interval_ms * self._cfg.beats_per_tap) / 1000.0
        if self._interruptible_wait(wait_s):
            return  # Stopped or lock lost or tempo changed

        # Re-check lock + read fresh interval
        with self._state_lock:
            if self._lock_state != "LOCKED":
                return
            fresh_interval = self._interval_ms

        # Check for tempo change before sending
        if self._tempo_changed(fresh_interval):
            self._sender_state = SenderState.CHANGE_BURST
            self._burst_remaining = self._cfg.burst_count
            self._last_sent_interval_ms = fresh_interval
            bpm = 60000.0 / fresh_interval if fresh_interval > 0 else 0
            self._bursts_sent += 1
            print(
                f"[TapSender] CHANGE_BURST interval={fresh_interval:.1f}ms "
                f"bpm={bpm:.1f} taps={self._cfg.burst_count}"
            )
            return  # Will handle burst on next loop iteration

        self._send_tap()

    def _interruptible_wait(self, seconds: float) -> bool:
        """
        Sleep for `seconds` but wake early if stop or wake event fires.
        Returns True if interrupted (caller should re-evaluate state).
        """
        # Split into small chunks to detect lock loss / tempo change quickly
        # Max chunk = 0.5s so we react within 500ms
        remaining = seconds
        while remaining > 0 and not self._stop_event.is_set():
            chunk = min(remaining, 0.5)
            self._wake.wait(timeout=chunk)
            self._wake.clear()
            remaining -= chunk

            if self._stop_event.is_set():
                return True

            # Check if lock lost
            with self._state_lock:
                if self._lock_state != "LOCKED":
                    return True

        return self._stop_event.is_set()

    # =================================================================
    # Tempo change detection
    # =================================================================

    def _tempo_changed(self, interval_ms: float) -> bool:
        """True if interval_ms differs enough from last sent."""
        if self._last_sent_interval_ms <= 0:
            return True
        diff = abs(interval_ms - self._last_sent_interval_ms)
        threshold = max(self._cfg.diff_ms,
                        self._last_sent_interval_ms * self._cfg.diff_ratio)
        return diff >= threshold

    # =================================================================
    # HTTP
    # =================================================================

    def _send_tap(self) -> bool:
        """Single HTTP GET to Titan Macro Run. Returns True on success."""
        try:
            resp = self._session.get(
                self._url,
                timeout=(self._cfg.connect_timeout, self._cfg.read_timeout),
                verify=False,
            )
            if resp.status_code == 200:
                self._taps_ok += 1
                return True
            else:
                self._taps_failed += 1
                print(f"[TapSender] FAIL HTTP {resp.status_code}")
                return False
        except Exception as e:
            self._taps_failed += 1
            print(f"[TapSender] FAIL {e}")
            return False

    # =================================================================
    # Cleanup
    # =================================================================

    def __del__(self):
        try:
            self.stop()
        except Exception:
            pass


__all__ = ["TapTempoSender", "TapSenderConfig", "SenderState"]

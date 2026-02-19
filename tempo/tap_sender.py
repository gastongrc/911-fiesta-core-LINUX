# tempo/tap_sender.py
# TapTempoSender v1.0 - Sends tempo taps to Titan via Macro Run
#
# Architecture:
# - Own daemon thread with scheduling (never blocks Qt/audio)
# - Observes AutoClock state via poll (called from Qt timer)
# - Sends burst of N taps spaced by interval_ms on tempo change
# - Only operates when AutoClock is LOCKED
# - Cancels pending burst on lock loss
#
# Endpoint: GET http://{ip}:{port}/titan/script/2/Macros/Run?macroId={macro}
# Tested: returns "true" on success

import os
import time
import threading
import logging
from dataclasses import dataclass
from typing import Optional

import requests
from requests.adapters import HTTPAdapter

logger = logging.getLogger("TapTempoSender")


@dataclass
class TapSenderConfig:
    """Configuration — all overridable via env vars."""
    titan_ip: str = os.environ.get("TITAN_IP", "192.168.1.45")
    titan_port: int = int(os.environ.get("TITAN_PORT", "4430"))
    macro_id: str = os.environ.get("TAP_MACRO_ID", "Avolites.Macros.TapBPM1")

    # Firing rules
    diff_ms: float = float(os.environ.get("TAP_DIFF_MS", "12"))
    diff_ratio: float = float(os.environ.get("TAP_DIFF_RATIO", "0.03"))
    cooldown_s: float = float(os.environ.get("TAP_COOLDOWN_S", "3.0"))
    burst_count: int = int(os.environ.get("TAP_BURST_COUNT", "3"))

    # HTTP
    connect_timeout: float = 1.0
    read_timeout: float = 1.0


class TapTempoSender:
    """
    Tempo → Titan Tap Sender.

    Sends taps to Avolites Titan via Macro Run when:
    - AutoClock is LOCKED
    - Tempo changed beyond threshold
    - Cooldown has elapsed

    Thread model:
    - update() is called from Qt thread (every ~40ms)
    - Burst scheduling runs on own daemon thread
    - HTTP requests happen on the daemon thread (never blocks UI)
    """

    def __init__(self, config: Optional[TapSenderConfig] = None):
        self._cfg = config or TapSenderConfig()

        # State tracking
        self._last_sent_interval_ms: float = 0.0
        self._last_sent_ts: float = 0.0
        self._last_lock_state: str = "UNLOCKED"

        # Burst scheduling
        self._burst_lock = threading.Lock()
        self._burst_cancel = threading.Event()
        self._burst_thread: Optional[threading.Thread] = None

        # HTTP session (own session, not shared with TitanQueue)
        self._session = requests.Session()
        adapter = HTTPAdapter(pool_connections=1, pool_maxsize=2, max_retries=0)
        self._session.mount("http://", adapter)
        self._session.headers.update({
            "Connection": "keep-alive",
            "User-Agent": "911Fiesta-TapSender/1.0",
        })

        # Stats
        self._bursts_sent: int = 0
        self._taps_ok: int = 0
        self._taps_failed: int = 0

        self._url = (
            f"http://{self._cfg.titan_ip}:{self._cfg.titan_port}"
            f"/titan/script/2/Macros/Run?macroId={self._cfg.macro_id}"
        )

        print(
            f"[TapSender] v1.0 init → {self._cfg.titan_ip}:{self._cfg.titan_port} "
            f"macro={self._cfg.macro_id} burst={self._cfg.burst_count} "
            f"cooldown={self._cfg.cooldown_s}s diff={self._cfg.diff_ms}ms/{self._cfg.diff_ratio*100:.0f}%"
        )

    # === Public API (called from Qt thread) ===

    def update(self, lock_state: str, interval_ms: float):
        """
        Called every tick (~40ms) from Qt thread.
        Decides whether to fire a burst. Never blocks.

        Args:
            lock_state: "UNLOCKED" / "LOCKING" / "LOCKED"
            interval_ms: Current interval in ms from AutoClock
        """
        # Lock lost → cancel any pending burst
        if lock_state != "LOCKED":
            if self._last_lock_state == "LOCKED":
                self._cancel_burst()
            self._last_lock_state = lock_state
            return

        self._last_lock_state = lock_state

        # Cooldown check
        now = time.monotonic()
        if (now - self._last_sent_ts) < self._cfg.cooldown_s:
            return

        # Tempo change check
        if self._last_sent_interval_ms > 0:
            diff = abs(interval_ms - self._last_sent_interval_ms)
            threshold = max(self._cfg.diff_ms,
                            self._last_sent_interval_ms * self._cfg.diff_ratio)
            if diff < threshold:
                return

        # Fire burst (non-blocking — schedules on daemon thread)
        self._fire_burst(interval_ms)

    def stop(self):
        """Cancel pending burst and close session."""
        self._cancel_burst()
        try:
            self._session.close()
        except Exception:
            pass

    def get_stats(self) -> dict:
        return {
            "bursts_sent": self._bursts_sent,
            "taps_ok": self._taps_ok,
            "taps_failed": self._taps_failed,
            "last_sent_interval_ms": self._last_sent_interval_ms,
            "last_sent_ts": self._last_sent_ts,
        }

    # === Internal ===

    def _fire_burst(self, interval_ms: float):
        """Schedule a burst of taps on daemon thread."""
        with self._burst_lock:
            # Cancel any in-flight burst
            self._burst_cancel.set()
            if self._burst_thread and self._burst_thread.is_alive():
                self._burst_thread.join(timeout=0.5)

            # Record send
            self._last_sent_interval_ms = interval_ms
            self._last_sent_ts = time.monotonic()
            self._bursts_sent += 1

            bpm = 60000.0 / interval_ms if interval_ms > 0 else 0
            print(
                f"[TapSender] BURST interval={interval_ms:.1f}ms "
                f"bpm={bpm:.1f} count={self._cfg.burst_count} "
                f"cooldown={self._cfg.cooldown_s}s"
            )

            # Launch daemon thread for the burst
            self._burst_cancel = threading.Event()
            cancel = self._burst_cancel
            count = self._cfg.burst_count
            delay_s = interval_ms / 1000.0

            self._burst_thread = threading.Thread(
                target=self._burst_worker,
                args=(count, delay_s, cancel),
                name="TapSender-Burst",
                daemon=True,
            )
            self._burst_thread.start()

    def _burst_worker(self, count: int, delay_s: float, cancel: threading.Event):
        """Send N taps spaced by delay_s. Runs on daemon thread."""
        for i in range(count):
            if cancel.is_set():
                return

            ok = self._send_tap()
            if not ok:
                return  # Abort burst on failure

            # Wait interval before next tap (except after last)
            if i < count - 1:
                if cancel.wait(timeout=delay_s):
                    return  # Cancelled during wait

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

    def _cancel_burst(self):
        """Cancel in-flight burst."""
        self._burst_cancel.set()


__all__ = ["TapTempoSender", "TapSenderConfig"]

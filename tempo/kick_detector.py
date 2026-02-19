# tempo/kick_detector.py
# KickPulseDetector V18 - Butterworth band-pass 40-120Hz + real timestamps
# V18: Replaces moving-avg LP@150Hz with Butterworth 2nd-order band-pass 40-120Hz (SOS).
#      Isolates kick drum fundamental, rejects hi-hats/snares/cymbals.
# V17: k=2.0, ratio=2.0, warmup=3. Adaptive threshold decay when blind >4s (floor 50%).
# V16: baseline×R dual-gate, warmup/k/ratio configurable via env, logs OFF by default
# V14: Sample-accurate timestamps using block_start_ts + sample_idx/sr
# For 911 Fiesta TapTempo robust implementation

import os
import time
import threading
import numpy as np
from typing import Optional, Deque, Tuple
from collections import deque

try:
    from scipy.signal import sosfilt, sosfilt_zi, butter as _butter_sos
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False


class KickPulseDetector:
    """
    V18 Kick Pulse Detector with:
    - Butterworth 2nd-order band-pass 40-120Hz (replaces moving-avg LP@150Hz)
    - Sample-accurate timestamps (block_start_ts + sample_idx/sr)
    - Adaptive threshold using MAD (Median Absolute Deviation)
    - Percentile-based peak tracking
    - Debounce with configurable interval
    - Thread-safe event queue for cross-thread communication

    Thread Safety:
    - process_audio() can be called from audio thread
    - pop_kick() can be called from main thread
    - Internal queue handles thread synchronization
    """

    # Configuration
    DEFAULT_DEBOUNCE_MS = 150.0     # Min interval between kicks (150ms = 400 BPM max)
    DEFAULT_THRESHOLD_K = 2.0       # V17: was 2.5 — 2.0 works out-of-box on real shows
    DEFAULT_LP_CUTOFF_HZ = 150.0    # Low-pass cutoff for kick band
    DEFAULT_HISTORY_SIZE = 50       # Number of energy samples for MAD calculation

    # V17: Blind fallback — prefer detecting over staying dead
    BLIND_TIMEOUT_S = 4.0           # Seconds without kick before decay activates
    BLIND_DECAY_RATE = 0.1          # Threshold reduction per second beyond timeout
    BLIND_FLOOR = 0.5               # Minimum decay (never go below 50% of computed threshold)

    def __init__(
        self,
        debounce_ms: float = DEFAULT_DEBOUNCE_MS,
        threshold_k: float = DEFAULT_THRESHOLD_K,
        lp_cutoff_hz: float = DEFAULT_LP_CUTOFF_HZ,
        history_size: int = DEFAULT_HISTORY_SIZE
    ):
        """
        Initialize kick detector.

        Args:
            debounce_ms: Minimum interval between kicks in milliseconds
            threshold_k: MAD multiplier for adaptive threshold
            lp_cutoff_hz: Low-pass cutoff frequency for kick band
            history_size: Number of samples for energy history (MAD calculation)
        """
        self._debounce_ms = debounce_ms
        self._lp_cutoff_hz = lp_cutoff_hz
        self._history_size = history_size

        # V17: Env-configurable params — hardcoded show-ready defaults
        # Env vars override these; without env, works out-of-box on real audio.
        self._threshold_k = float(os.environ.get("KICK_K", "2.0"))
        self._baseline_ratio = float(os.environ.get("KICK_RATIO", "2.0"))
        self._warmup_min = int(os.environ.get("KICK_WARMUP", "3"))

        # Energy history for MAD calculation
        self._energy_history: Deque[float] = deque(maxlen=history_size)

        # Timing
        self._last_kick_ts: float = 0.0

        # Thread-safe kick event queue
        self._kick_queue: Deque[float] = deque(maxlen=32)  # Max 32 pending kicks
        self._queue_lock = threading.Lock()

        # Stats
        self._total_kicks: int = 0
        self._last_energy: float = 0.0
        self._last_threshold: float = 0.0
        self._last_baseline: float = 0.0

        # V17: Blind fallback timer (initialized to now — gives 4s grace before decay)
        self._last_kick_mono: float = time.monotonic()

        # FIX 3: Butterworth 2nd-order band-pass 40-120Hz (replaces moving-avg LP)
        self._bp_lo = 40.0
        self._bp_hi = 120.0
        self._sos = None
        self._sos_zi = None
        self._bp_sr = 0  # sample rate when filter was last computed

        # V16: Debug diagnostics (DEBUG_KICK=1), logs OFF by default
        self._debug_kick = os.environ.get("DEBUG_KICK", "0") == "1"
        self._debug_recent: Deque[float] = deque()
        self._debug_last_log: float = 0.0

        bp_str = f"bp={self._bp_lo:.0f}-{self._bp_hi:.0f}Hz(SOS)" if _HAS_SCIPY else f"lp={lp_cutoff_hz:.0f}Hz(fallback)"
        print(f"[KickDetector] V18 init (debounce={debounce_ms:.0f}ms, k={self._threshold_k:.1f}, ratio={self._baseline_ratio:.1f}, warmup={self._warmup_min}, {bp_str}, blind_timeout={self.BLIND_TIMEOUT_S:.0f}s, debug={'ON' if self._debug_kick else 'off'})")

    def _init_bandpass(self, sr: int):
        """FIX 3: Initialize Butterworth 2nd-order band-pass SOS filter."""
        if not _HAS_SCIPY or sr == self._bp_sr:
            return
        nyq = sr / 2.0
        lo = max(0.01, self._bp_lo / nyq)
        hi = min(0.99, self._bp_hi / nyq)
        if lo >= hi:
            return
        try:
            self._sos = _butter_sos(2, [lo, hi], btype='band', output='sos')
            # Zero initial conditions (no prior signal)
            n_sections = self._sos.shape[0]
            self._sos_zi = np.zeros((n_sections, 2), dtype=np.float64)
            self._bp_sr = sr
        except Exception:
            self._sos = None
            self._sos_zi = None

    def process_audio(self, block: np.ndarray, sr: int, block_start_ts: float = None) -> bool:
        """
        V16: Dual-gate kick detection.

        HIT requires BOTH:
          1. energy > MAD threshold  (adaptive to history)
          2. energy > baseline × R   (relative to THIS block's floor)

        Args:
            block: Audio samples (mono or stereo)
            sr: Sample rate
            block_start_ts: Monotonic timestamp at start of block.
                           If None, uses time.monotonic() (legacy).

        Returns:
            bool: True if kick was detected
        """
        if block is None or len(block) == 0:
            return False

        if block_start_ts is None:
            block_start_ts = time.monotonic()

        # Convert to mono float32
        x = np.asarray(block, dtype=np.float32)
        if x.ndim == 2:
            x = x.mean(axis=1)

        if len(x) == 0:
            return False

        block_len = len(x)

        # FIX 3: Butterworth 2nd-order band-pass 40-120Hz (isolates kick fundamental)
        self._init_bandpass(sr)
        if self._sos is not None:
            x_bp, self._sos_zi = sosfilt(self._sos, x, zi=self._sos_zi)
            x_bp = x_bp.astype(np.float32)
        else:
            # Fallback: no scipy — use raw signal (original behavior)
            x_bp = x

        # Envelope: abs of band-passed signal + 10ms smoothing
        env = np.abs(x_bp)
        win_samples = max(1, int(sr * 0.010))  # 10ms window

        if len(env) < win_samples:
            return False

        kernel = np.ones(win_samples, dtype=np.float32) / win_samples
        if len(env) > len(kernel):
            env_smooth = np.convolve(env, kernel, mode='valid')
            peak_idx_in_conv = int(np.argmax(env_smooth))
            sample_idx_peak = peak_idx_in_conv + (win_samples // 2)
            energy = float(env_smooth[peak_idx_in_conv])
            baseline = float(np.median(env_smooth))
        else:
            sample_idx_peak = int(np.argmax(env))
            energy = float(np.max(env))
            baseline = float(np.median(env))

        self._last_energy = energy
        self._last_baseline = baseline

        # Add to history
        self._energy_history.append(energy)

        # V16: Configurable warmup (default 5, was 10)
        if len(self._energy_history) < self._warmup_min:
            return False

        # MAD-based threshold
        history_arr = np.array(self._energy_history)
        median = float(np.median(history_arr))
        mad = float(np.median(np.abs(history_arr - median)))

        threshold = median + self._threshold_k * 1.4826 * max(mad, 1e-6)
        self._last_threshold = threshold

        # Sample-accurate kick timestamp
        kick_ts = block_start_ts + (sample_idx_peak / sr)

        # Debounce
        dt_ms = (kick_ts - self._last_kick_ts) * 1000.0 if self._last_kick_ts > 0 else 9999.0

        # Dual-gate thresholds
        baseline_thresh = baseline * self._baseline_ratio

        # V17: Blind fallback — adaptive decay when no kicks for too long
        now_mono = time.monotonic()
        blind_s = now_mono - self._last_kick_mono
        decay = 1.0
        if blind_s > self.BLIND_TIMEOUT_S:
            decay = max(self.BLIND_FLOOR,
                        1.0 - (blind_s - self.BLIND_TIMEOUT_S) * self.BLIND_DECAY_RATE)
            threshold *= decay
            baseline_thresh *= decay

        # Dual-gate — BOTH conditions required
        hit = (energy > threshold
               and energy > baseline_thresh
               and dt_ms >= self._debounce_ms)

        # Debug diagnostics every 2s (fires even without kick — shows why it's blind)
        if self._debug_kick:
            if hit:
                self._debug_recent.append(now_mono)
            cutoff = now_mono - 2.0
            while self._debug_recent and self._debug_recent[0] < cutoff:
                self._debug_recent.popleft()
            if now_mono - self._debug_last_log >= 2.0:
                self._debug_last_log = now_mono
                decay_str = f" decay={decay:.2f}" if decay < 1.0 else ""
                print(f"[KickDetector] energy={energy:.4f} base={baseline:.4f} med={median:.4f} mad={mad:.5f} thr={threshold:.4f} bR={baseline_thresh:.4f} kicks_2s={len(self._debug_recent)} blind={blind_s:.1f}s{decay_str}")

        if hit:
            self._last_kick_ts = kick_ts
            self._last_kick_mono = now_mono  # V17: reset blind timer
            self._total_kicks += 1
            with self._queue_lock:
                self._kick_queue.append(kick_ts)
            return True

        return False

    def pop_kick(self) -> Optional[float]:
        """
        Pop oldest kick timestamp from queue.

        Thread-safe: can be called from main thread.

        Returns:
            float: Monotonic timestamp of kick, or None if queue empty
        """
        with self._queue_lock:
            if self._kick_queue:
                return self._kick_queue.popleft()
        return None

    def pop_all_kicks(self) -> list:
        """
        Pop all pending kicks from queue.

        Thread-safe: can be called from main thread.

        Returns:
            list[float]: List of kick timestamps (oldest first)
        """
        with self._queue_lock:
            kicks = list(self._kick_queue)
            self._kick_queue.clear()
        return kicks

    def has_kicks(self) -> bool:
        """Check if there are pending kicks in queue."""
        with self._queue_lock:
            return len(self._kick_queue) > 0

    def get_last_kick_ts(self) -> float:
        """Get timestamp of last detected kick."""
        return self._last_kick_ts

    def get_stats(self) -> dict:
        """Get detector statistics."""
        return {
            "total_kicks": self._total_kicks,
            "last_energy": self._last_energy,
            "last_threshold": self._last_threshold,
            "last_kick_ts": self._last_kick_ts,
            "queue_size": len(self._kick_queue),
            "history_size": len(self._energy_history),
            "debounce_ms": self._debounce_ms,
            "threshold_k": self._threshold_k,
        }

    def set_param(self, name: str, value: float) -> bool:
        """
        Set detector parameter at runtime.

        Supported params:
        - debounce_ms: Minimum interval between kicks
        - threshold_k: MAD multiplier for adaptive threshold

        Args:
            name: Parameter name
            value: New value

        Returns:
            bool: True if param was set, False if unknown param
        """
        old_value = None
        if name == "debounce_ms":
            old_value = self._debounce_ms
            self._debounce_ms = float(value)
        elif name == "threshold_k":
            old_value = self._threshold_k
            self._threshold_k = float(value)
        elif name == "lp_cutoff_hz":
            old_value = self._lp_cutoff_hz
            self._lp_cutoff_hz = float(value)
        else:
            return False

        if old_value is not None:
            print(f"[KickDetector] PARAM {name}={value:.2f} (was {old_value:.2f})")
        return True

    def reset(self) -> None:
        """Reset detector state."""
        self._energy_history.clear()
        self._last_kick_ts = 0.0
        self._last_kick_mono = time.monotonic()
        self._total_kicks = 0
        with self._queue_lock:
            self._kick_queue.clear()
        print("[KickDetector] Reset")


__all__ = ['KickPulseDetector']

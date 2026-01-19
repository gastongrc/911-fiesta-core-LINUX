# tempo/kick_detector.py
# KickPulseDetector V14 - Sample-accurate kick detection with MAD threshold
# V14: Sample-accurate timestamps using block_start_ts + sample_idx/sr
# For 911 Fiesta TapTempo robust implementation

import time
import threading
import numpy as np
from typing import Optional, Deque, Tuple
from collections import deque


class KickPulseDetector:
    """
    V14 Kick Pulse Detector with:
    - Sample-accurate timestamps (block_start_ts + sample_idx/sr)
    - Low-band energy detection (<150Hz)
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
    DEFAULT_THRESHOLD_K = 2.5       # MAD multiplier for threshold
    DEFAULT_LP_CUTOFF_HZ = 150.0    # Low-pass cutoff for kick band
    DEFAULT_HISTORY_SIZE = 50       # Number of energy samples for MAD calculation

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
        self._threshold_k = threshold_k
        self._lp_cutoff_hz = lp_cutoff_hz
        self._history_size = history_size

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

        print(f"[KickDetector] V14 init (debounce={debounce_ms:.0f}ms, k={threshold_k:.1f}, lp={lp_cutoff_hz:.0f}Hz)")

    def process_audio(self, block: np.ndarray, sr: int, block_start_ts: float = None) -> bool:
        """
        Process audio block to detect kick onsets.

        V14: Sample-accurate timestamps using block_start_ts + sample_idx/sr.

        Uses low-band energy with MAD-based adaptive threshold.
        Thread-safe: can be called from audio thread.

        Args:
            block: Audio samples (mono or stereo)
            sr: Sample rate
            block_start_ts: Monotonic timestamp at start of block (for sample-accurate timing)
                           If None, uses time.monotonic() (legacy behavior)

        Returns:
            bool: True if kick was detected
        """
        if block is None or len(block) == 0:
            return False

        # V14: Capture fallback timestamp early if not provided
        if block_start_ts is None:
            block_start_ts = time.monotonic()

        # Convert to mono float32
        x = np.asarray(block, dtype=np.float32)
        if x.ndim == 2:
            x = x.mean(axis=1)

        if len(x) == 0:
            return False

        block_len = len(x)
        block_ms = (block_len / sr) * 1000.0

        # Simple low-pass for kick detection
        # Moving average with window ~lp_cutoff_hz
        win_samples = max(1, int(sr / self._lp_cutoff_hz))

        if len(x) < win_samples:
            return False

        # Compute envelope: abs + smoothing
        env = np.abs(x)

        # Simple moving average for low-pass effect
        kernel = np.ones(win_samples, dtype=np.float32) / win_samples
        if len(env) > len(kernel):
            env_smooth = np.convolve(env, kernel, mode='valid')
            # V14: Track peak sample index for sample-accurate timing
            peak_idx_in_conv = int(np.argmax(env_smooth))
            # Adjust for convolution offset (mode='valid' shifts by kernel_size//2)
            sample_idx_peak = peak_idx_in_conv + (win_samples // 2)
            energy = float(env_smooth[peak_idx_in_conv])
        else:
            sample_idx_peak = int(np.argmax(env))
            energy = float(np.max(env))

        self._last_energy = energy

        # Add to history
        self._energy_history.append(energy)

        # Need at least 10 samples for MAD
        if len(self._energy_history) < 10:
            return False

        # Calculate MAD-based threshold
        history_arr = np.array(self._energy_history)
        median = float(np.median(history_arr))
        mad = float(np.median(np.abs(history_arr - median)))

        # Robust threshold: median + k * 1.4826 * MAD
        # 1.4826 converts MAD to sigma-equivalent for normal distribution
        threshold = median + self._threshold_k * 1.4826 * max(mad, 1e-6)
        self._last_threshold = threshold

        # V14: Sample-accurate kick timestamp
        kick_ts = block_start_ts + (sample_idx_peak / sr)

        # Check for kick (energy above threshold)
        dt_ms = (kick_ts - self._last_kick_ts) * 1000.0 if self._last_kick_ts > 0 else 9999.0

        if energy > threshold and dt_ms >= self._debounce_ms:
            self._last_kick_ts = kick_ts
            self._total_kicks += 1

            # Push to thread-safe queue
            with self._queue_lock:
                self._kick_queue.append(kick_ts)

            print(f"[KickDetector] KICK ts={kick_ts:.3f} idx={sample_idx_peak} block_start={block_start_ts:.3f} block_ms={block_ms:.1f}")
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
        self._total_kicks = 0
        with self._queue_lock:
            self._kick_queue.clear()
        print("[KickDetector] Reset")


__all__ = ['KickPulseDetector']

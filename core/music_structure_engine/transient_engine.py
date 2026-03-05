# transient_engine.py — Transient density and spike detection
#
# Computes:
#   - transient_density: how many transients per second (smoothed) [0, ~20]
#   - transient_spike: True if a strong transient just happened
#
# Memory: 2 seconds (~50 ticks at 40ms)

import numpy as np
from .buffers import RingBuffer
from .math_utils import ema


# Threshold for counting a sample-level peak as a transient
_TRANSIENT_THRESHOLD = 0.15
# Spike: single-frame RMS jump
_SPIKE_RATIO = 3.0


class TransientEngine:

    def __init__(self):
        self._density_buf = RingBuffer(capacity=50)  # 2s
        self._transient_density = 0.0
        self._transient_spike = False
        self._prev_rms = 0.0

    def process(self, block: np.ndarray, sr: int):
        """Process one audio block. Updates density + spike."""
        if block.size < 64 or sr <= 0:
            return

        abs_block = np.abs(block)

        # Count threshold crossings (simple transient proxy)
        crossings = int(np.sum(abs_block > _TRANSIENT_THRESHOLD))
        # Normalize to approximate transients/second
        duration = block.size / sr
        rate = crossings / max(duration, 0.001)

        self._density_buf.push(rate)

        # Smooth density over buffer
        data = self._density_buf.get_all()
        self._transient_density = float(np.mean(data)) if data.size > 0 else 0.0

        # Spike detection: sudden RMS jump
        curr_rms = float(np.sqrt(np.mean(np.square(block, dtype=np.float64))))
        if self._prev_rms > 1e-6:
            ratio = curr_rms / self._prev_rms
            self._transient_spike = ratio >= _SPIKE_RATIO
        else:
            self._transient_spike = curr_rms > 0.1
        self._prev_rms = curr_rms

    # --- Public getters ---

    @property
    def transient_density(self) -> float:
        return self._transient_density

    @property
    def transient_spike(self) -> bool:
        return self._transient_spike

    def get_state(self) -> dict:
        return {
            "transient_density": round(self._transient_density, 2),
            "transient_spike": self._transient_spike,
        }

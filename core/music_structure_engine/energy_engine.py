# energy_engine.py — Multiband energy analysis + trend detection
#
# Computes:
#   - energy_level: overall RMS [0, 1]
#   - energy_trend: RISING / FALLING / STABLE
#   - low_energy:  20-250 Hz
#   - mid_energy:  250-4000 Hz
#   - high_energy: 4000-16000 Hz
#
# Memory: 8 seconds (~200 ticks at 40ms)

import numpy as np
from .buffers import RingBuffer
from .math_utils import rms, bandpass_energy, ema


# Band definitions (Hz)
_LOW_BAND = (20.0, 250.0)
_MID_BAND = (250.0, 4000.0)
_HIGH_BAND = (4000.0, 16000.0)

# Trend detection
_TREND_WINDOW = 50  # ticks (~2s)
_TREND_THRESHOLD = 0.03  # minimum slope to count as rising/falling


class EnergyEngine:

    def __init__(self):
        self._energy_buf = RingBuffer(capacity=200)  # 8s
        self._low_buf = RingBuffer(capacity=200)
        self._mid_buf = RingBuffer(capacity=200)
        self._high_buf = RingBuffer(capacity=200)

        self._energy_level = 0.0
        self._low_energy = 0.0
        self._mid_energy = 0.0
        self._high_energy = 0.0
        self._energy_trend = "STABLE"

    def process(self, block: np.ndarray, sr: int):
        """Process one audio block. Updates energy + trend."""
        if block.size < 64 or sr <= 0:
            return

        # Overall energy (RMS, smoothed)
        raw_rms = rms(block)
        self._energy_level = ema(self._energy_level, raw_rms, 0.3)
        self._energy_buf.push(self._energy_level)

        # Band energies
        lo = bandpass_energy(block, sr, *_LOW_BAND)
        mi = bandpass_energy(block, sr, *_MID_BAND)
        hi = bandpass_energy(block, sr, *_HIGH_BAND)

        self._low_energy = ema(self._low_energy, lo, 0.25)
        self._mid_energy = ema(self._mid_energy, mi, 0.25)
        self._high_energy = ema(self._high_energy, hi, 0.25)

        self._low_buf.push(self._low_energy)
        self._mid_buf.push(self._mid_energy)
        self._high_buf.push(self._high_energy)

        # Trend detection
        self._compute_trend()

    def _compute_trend(self):
        """Linear regression over recent energy to detect rising/falling."""
        data = self._energy_buf.get_last(_TREND_WINDOW)
        n = data.size
        if n < 10:
            self._energy_trend = "STABLE"
            return

        # Simple slope: (mean of second half - mean of first half) / half_len
        half = n // 2
        first_half = float(np.mean(data[:half]))
        second_half = float(np.mean(data[half:]))
        slope = second_half - first_half

        if slope > _TREND_THRESHOLD:
            self._energy_trend = "RISING"
        elif slope < -_TREND_THRESHOLD:
            self._energy_trend = "FALLING"
        else:
            self._energy_trend = "STABLE"

    # --- Public getters ---

    @property
    def energy_level(self) -> float:
        return self._energy_level

    @property
    def energy_trend(self) -> str:
        return self._energy_trend

    @property
    def low_energy(self) -> float:
        return self._low_energy

    @property
    def mid_energy(self) -> float:
        return self._mid_energy

    @property
    def high_energy(self) -> float:
        return self._high_energy

    def get_state(self) -> dict:
        return {
            "energy_level": round(self._energy_level, 4),
            "energy_trend": self._energy_trend,
            "low_energy": round(self._low_energy, 4),
            "mid_energy": round(self._mid_energy, 4),
            "high_energy": round(self._high_energy, 4),
        }

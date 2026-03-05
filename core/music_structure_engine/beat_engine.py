# beat_engine.py — Tempo detection, beat phase tracking, beat confidence
#
# Strategy:
#   1. Compute onset envelope via spectral flux (full-band, works with weak kicks)
#   2. Accumulate onsets in a 16s ring buffer
#   3. Autocorrelate to find dominant period -> tempo
#   4. Track beat phase via cross-correlation with ideal pulse train
#   5. Output: tempo, beat_phase [0,1), beat_confidence [0,1], beat_index (int)
#
# Works with: weak kick, mid/high groove, syncopation, latin rhythms.

import numpy as np
from .buffers import RingBuffer
from .math_utils import onset_envelope_frame, autocorrelate, ema


# BPM search range
_MIN_BPM = 70.0
_MAX_BPM = 180.0

# Onset envelope hop size
_HOP = 512


class BeatEngine:

    def __init__(self):
        # 16s of onset envelope at ~86 Hz (sr=44100, hop=512)
        self._onset_buf = RingBuffer(capacity=1400)  # ~16s
        self._tempo = 0.0
        self._beat_phase = 0.0
        self._beat_confidence = 0.0
        self._beat_index = 0
        self._samples_since_beat = 0
        self._period_samples = 0  # current beat period in onset-frames
        self._prev_tempo = 0.0
        self._tempo_smooth = 0.0
        self._onset_rate = 0.0  # onsets per second (set on first process)
        self._tick_count = 0

    def process(self, block: np.ndarray, sr: int):
        """Process one audio block (~250ms). Updates tempo/phase/confidence."""
        if block.size < 1024 or sr <= 0:
            return

        # Onset envelope for this block
        env = onset_envelope_frame(block, sr, hop=_HOP)
        self._onset_buf.push_array(env)
        self._onset_rate = sr / _HOP  # onset frames per second
        self._tick_count += 1

        # Advance phase by number of new onset frames
        if self._period_samples > 0:
            self._samples_since_beat += env.size
            while self._samples_since_beat >= self._period_samples:
                self._samples_since_beat -= self._period_samples
                self._beat_index += 1
            self._beat_phase = self._samples_since_beat / self._period_samples

        # Recompute tempo every ~8 ticks (~320ms) to save CPU
        if self._tick_count % 8 != 0:
            return

        self._estimate_tempo()

    def _estimate_tempo(self):
        """Autocorrelation-based tempo estimation from onset buffer."""
        data = self._onset_buf.get_all()
        if data.size < 200:  # need ~2.3s minimum
            return

        rate = self._onset_rate
        if rate <= 0:
            return

        # Lag range for BPM search
        min_lag = max(1, int(rate * 60.0 / _MAX_BPM))
        max_lag = min(data.size // 2, int(rate * 60.0 / _MIN_BPM))
        if max_lag <= min_lag:
            return

        acf = autocorrelate(data, max_lag + 1)
        search = acf[min_lag:max_lag + 1]
        if search.size == 0:
            return

        peak_idx = int(np.argmax(search))
        peak_val = float(search[peak_idx])
        lag = peak_idx + min_lag

        if lag <= 0 or peak_val < 0.05:
            self._beat_confidence = ema(self._beat_confidence, 0.0, 0.15)
            return

        raw_bpm = (rate * 60.0) / lag

        # Octave correction: prefer range [85, 165]
        while raw_bpm < 85.0 and raw_bpm > 0:
            raw_bpm *= 2.0
        while raw_bpm > 165.0:
            raw_bpm /= 2.0

        # Smooth tempo (slow EMA to avoid jitter)
        if self._tempo_smooth <= 0:
            self._tempo_smooth = raw_bpm
        else:
            # If new tempo is close to current (<8%), smooth. Otherwise jump.
            ratio = raw_bpm / self._tempo_smooth if self._tempo_smooth > 0 else 1.0
            if 0.92 < ratio < 1.08:
                self._tempo_smooth = ema(self._tempo_smooth, raw_bpm, 0.12)
            else:
                self._tempo_smooth = ema(self._tempo_smooth, raw_bpm, 0.4)

        self._tempo = self._tempo_smooth
        self._period_samples = int(round(rate * 60.0 / self._tempo)) if self._tempo > 0 else 0

        # Confidence from autocorrelation peak strength
        raw_conf = min(1.0, peak_val / 0.4)
        self._beat_confidence = ema(self._beat_confidence, raw_conf, 0.2)

    # --- Public getters ---

    @property
    def tempo(self) -> float:
        return self._tempo

    @property
    def beat_phase(self) -> float:
        return self._beat_phase

    @property
    def beat_confidence(self) -> float:
        return self._beat_confidence

    @property
    def beat_index(self) -> int:
        return self._beat_index

    def get_state(self) -> dict:
        return {
            "tempo": round(self._tempo, 1),
            "beat_phase": round(self._beat_phase, 3),
            "beat_confidence": round(self._beat_confidence, 3),
            "beat_index": self._beat_index,
        }

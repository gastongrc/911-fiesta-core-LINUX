# phrase_engine.py — Musical phrase tracking
#
# Assumes standard dance music structure:
#   4 beats per bar, 4 bars per phrase (16 beats per phrase)
#
# Computes:
#   - beat_index: global beat counter
#   - bar_index: beat within current bar [0..3]
#   - phrase_index: bar within current phrase [0..3]
#   - phrase_position: [0, 1) position within phrase
#   - phrase_boundary_probability: likelihood we're near a phrase boundary
#
# Memory: 64 beats

import time
from .buffers import RingBuffer
from .math_utils import ema


_BEATS_PER_BAR = 4
_BARS_PER_PHRASE = 4
_BEATS_PER_PHRASE = _BEATS_PER_BAR * _BARS_PER_PHRASE  # 16


class PhraseEngine:

    def __init__(self):
        self._beat_index = 0
        self._prev_beat_index = 0
        self._bar_index = 0       # beat within bar [0..3]
        self._phrase_index = 0    # bar within phrase [0..3]
        self._phrase_position = 0.0
        self._phrase_boundary_prob = 0.0
        self._energy_at_beat = RingBuffer(capacity=64)
        self._last_beat_time = 0.0

    def update(self, beat_index: int, beat_phase: float, beat_confidence: float,
               energy_level: float):
        """Call every tick with current beat state. Detects new beats and tracks phrase."""

        # Detect new beat (beat_index incremented)
        if beat_index > self._prev_beat_index and beat_confidence > 0.2:
            beats_advanced = beat_index - self._prev_beat_index
            self._prev_beat_index = beat_index
            self._last_beat_time = time.monotonic()

            for _ in range(beats_advanced):
                self._beat_index += 1
                self._energy_at_beat.push(energy_level)

            self._bar_index = self._beat_index % _BEATS_PER_BAR
            self._phrase_index = (self._beat_index // _BEATS_PER_BAR) % _BARS_PER_PHRASE

        # Phrase position: combine bar + beat phase for smooth [0, 1)
        beat_in_phrase = (self._phrase_index * _BEATS_PER_BAR + self._bar_index)
        self._phrase_position = (beat_in_phrase + beat_phase) / _BEATS_PER_PHRASE

        # Phrase boundary probability: high near phrase_position ~0.0 or ~1.0
        dist_to_boundary = min(self._phrase_position, 1.0 - self._phrase_position)
        # Gaussian-like: high when dist < 0.1 (within ~1.6 beats of boundary)
        if dist_to_boundary < 0.15:
            raw_prob = 1.0 - (dist_to_boundary / 0.15)
        else:
            raw_prob = 0.0
        self._phrase_boundary_prob = ema(self._phrase_boundary_prob, raw_prob, 0.3)

    # --- Public getters ---

    @property
    def beat_index(self) -> int:
        return self._beat_index

    @property
    def bar_index(self) -> int:
        return self._bar_index

    @property
    def phrase_index(self) -> int:
        return self._phrase_index

    @property
    def phrase_position(self) -> float:
        return self._phrase_position

    @property
    def phrase_boundary_probability(self) -> float:
        return self._phrase_boundary_prob

    def get_state(self) -> dict:
        return {
            "beat_index": self._beat_index,
            "bar_index": self._bar_index,
            "phrase_index": self._phrase_index,
            "phrase_position": round(self._phrase_position, 3),
            "phrase_boundary_probability": round(self._phrase_boundary_prob, 3),
        }

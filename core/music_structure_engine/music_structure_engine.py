# music_structure_engine.py — Main orchestrator
#
# MusicStructureEngine.process(block, sr) runs:
#   BeatEngine -> EnergyEngine -> TransientEngine -> PhraseEngine -> DropEngine -> StateInference
#
# Produces MusicStructureState with tempo, phase, energy, probabilities, etc.
# CPU target: < 12% total.

from .beat_engine import BeatEngine
from .energy_engine import EnergyEngine
from .transient_engine import TransientEngine
from .phrase_engine import PhraseEngine
from .drop_engine import DropEngine
from .state_inference import StateInference, MusicStructureState


class MusicStructureEngine:
    """
    Music Structure Engine — real audio analysis with temporal memory.

    Replaces MIL-Lite. Processes the same mono float32 block that analyzers receive.
    Call process(block, sr) every tick (~33-40ms).
    """

    def __init__(self):
        self._beat = BeatEngine()
        self._energy = EnergyEngine()
        self._transient = TransientEngine()
        self._phrase = PhraseEngine()
        self._drop = DropEngine()
        self._inference = StateInference()
        self._state = MusicStructureState()
        self._tick_count = 0
        print("[MSE] MusicStructureEngine initialized")

    def process(self, block, sr: int):
        """Process one audio block (mono float32, ~11025 samples at 44100 Hz).

        This is the main entry point, called from _process_modules_limited().
        """
        import numpy as np
        if block is None:
            return
        arr = np.asarray(block)
        if arr.size == 0 or sr <= 0:
            return

        self._tick_count += 1

        # 1. Beat analysis (spectral flux + autocorrelation)
        self._beat.process(arr, sr)

        # 2. Energy analysis (multiband RMS + trend)
        self._energy.process(arr, sr)

        # 3. Transient analysis (density + spike)
        self._transient.process(arr, sr)

        # 4. Phrase tracking (uses beat state)
        self._phrase.update(
            beat_index=self._beat.beat_index,
            beat_phase=self._beat.beat_phase,
            beat_confidence=self._beat.beat_confidence,
            energy_level=self._energy.energy_level,
        )

        # 5. Drop prediction (uses energy + transient + phrase)
        self._drop.update(
            energy_level=self._energy.energy_level,
            energy_trend=self._energy.energy_trend,
            transient_density=self._transient.transient_density,
            transient_spike=self._transient.transient_spike,
            phrase_boundary_prob=self._phrase.phrase_boundary_probability,
            phrase_position=self._phrase.phrase_position,
        )

        # 6. State inference (combine all into probabilities)
        self._state = self._inference.infer(
            beat=self._beat.get_state(),
            energy=self._energy.get_state(),
            transient=self._transient.get_state(),
            phrase=self._phrase.get_state(),
            drop=self._drop.get_state(),
        )

    def get_state(self) -> MusicStructureState:
        """Return current MusicStructureState snapshot."""
        return self._state

    def get_status(self) -> dict:
        """Return full status dict for UI/debug."""
        return {
            "tick": self._tick_count,
            **self._state.to_dict(),
        }

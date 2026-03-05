# drop_engine.py — Drop prediction engine
#
# States: NONE -> BUILD -> PRE_DROP -> DROP -> NONE
#
# Detection logic:
#   BUILD:    energy rising + transient density increasing + mid-phrase
#   PRE_DROP: energy high + near phrase boundary + build sustained
#   DROP:     sudden energy spike after PRE_DROP or BUILD
#   NONE:     default / energy stable or falling without build context
#
# All rules are deterministic (thresholds + state machine).

from .math_utils import ema

# States
NONE = "NONE"
BUILD = "BUILD"
PRE_DROP = "PRE_DROP"
DROP = "DROP"

# Timing
_BUILD_MIN_TICKS = 25   # ~1s minimum build duration
_DROP_HOLD_TICKS = 50   # ~2s hold after drop detected
_PRE_DROP_MAX_TICKS = 75  # ~3s max pre-drop before timeout


class DropEngine:

    def __init__(self):
        self._state = NONE
        self._ticks_in_state = 0
        self._build_energy_start = 0.0
        self._drop_confidence = 0.0

    def update(self, energy_level: float, energy_trend: str,
               transient_density: float, transient_spike: bool,
               phrase_boundary_prob: float, phrase_position: float):
        """Call every tick. Updates drop state machine."""

        self._ticks_in_state += 1

        if self._state == NONE:
            # Transition to BUILD if energy is rising with some transient activity
            if (energy_trend == "RISING" and
                    transient_density > 5.0 and
                    energy_level > 0.05):
                self._state = BUILD
                self._ticks_in_state = 0
                self._build_energy_start = energy_level

        elif self._state == BUILD:
            # Check if build conditions still hold
            if energy_trend == "FALLING" and self._ticks_in_state > _BUILD_MIN_TICKS:
                # Build collapsed — might be a fake build
                self._state = NONE
                self._ticks_in_state = 0
                return

            # Transition to PRE_DROP near phrase boundary
            if (self._ticks_in_state >= _BUILD_MIN_TICKS and
                    phrase_boundary_prob > 0.5 and
                    energy_level > self._build_energy_start * 1.3):
                self._state = PRE_DROP
                self._ticks_in_state = 0
                return

            # Direct DROP on sudden spike during build
            if transient_spike and self._ticks_in_state >= _BUILD_MIN_TICKS:
                self._state = DROP
                self._ticks_in_state = 0
                self._drop_confidence = min(1.0, energy_level * 3.0)

        elif self._state == PRE_DROP:
            # Timeout
            if self._ticks_in_state > _PRE_DROP_MAX_TICKS:
                self._state = NONE
                self._ticks_in_state = 0
                return

            # DROP on transient spike or phrase boundary cross
            if transient_spike or (phrase_boundary_prob < 0.1 and self._ticks_in_state > 5):
                self._state = DROP
                self._ticks_in_state = 0
                self._drop_confidence = min(1.0, energy_level * 3.0)

        elif self._state == DROP:
            # Hold for _DROP_HOLD_TICKS then return to NONE
            if self._ticks_in_state > _DROP_HOLD_TICKS:
                self._state = NONE
                self._ticks_in_state = 0
                self._drop_confidence = 0.0

        # Smooth confidence
        target_conf = 0.0
        if self._state == BUILD:
            target_conf = 0.3 + 0.3 * min(1.0, self._ticks_in_state / _BUILD_MIN_TICKS)
        elif self._state == PRE_DROP:
            target_conf = 0.7
        elif self._state == DROP:
            target_conf = self._drop_confidence
        self._drop_confidence = ema(self._drop_confidence, target_conf, 0.2)

    # --- Public getters ---

    @property
    def state(self) -> str:
        return self._state

    @property
    def confidence(self) -> float:
        return self._drop_confidence

    def get_state(self) -> dict:
        return {
            "drop_state": self._state,
            "drop_confidence": round(self._drop_confidence, 3),
        }

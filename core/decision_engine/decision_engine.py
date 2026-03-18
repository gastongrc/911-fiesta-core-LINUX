# decision_engine.py — Phase 0: SHADOW MODE (Observability Only)
# ================================================================
# STRICT RULES:
#   - NO fire_cue(), NO kill_cue()
#   - NO state_manager mutation
#   - NO cue_engine mutation
#   - NO module mutation
#   - 100% PASSIVE — read-only observation + logging
# ================================================================

import time
import os
import threading


class DecisionEngine:
    """
    Phase 0 Decision Engine — SHADOW MODE.

    Runs in parallel with the real system, logging what it WOULD decide
    without affecting any behavior. Produces shadow logs for offline
    comparison against actual StateManager decisions.
    """

    def __init__(self, log_path: str = "logs/decision_engine_shadow.log"):
        self._log_path = log_path
        self._tick = 0

        # Buffered logging: accumulate lines, flush periodically
        self._log_buffer = []
        self._flush_interval = 20  # flush every 20 ticks (~1s at 50ms)
        self._lock = threading.Lock()

        # Ensure log directory exists
        log_dir = os.path.dirname(self._log_path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        # Write header on init
        try:
            with open(self._log_path, "a") as f:
                f.write(f"# DecisionEngine Shadow Log — started {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        except Exception:
            pass

    def resolve(self, mse_state: dict, sm_state: dict) -> dict:
        """
        Determine what the Decision Engine WOULD decide.

        Args:
            mse_state: Music Structure Engine probabilities
                {P_bajada, P_base, P_ataque, P_brake, confidence, energy_trend}
            sm_state: Current StateManager snapshot
                {current_state, energy, scores, time_in_state}

        Returns:
            dict with context_state, event_state, confidence

        NOTE: This is a Phase 0 placeholder. Returns current SM state
        with zero confidence to indicate no independent decision yet.
        """
        return {
            "context_state": sm_state.get("current_state"),
            "event_state": None,
            "confidence": 0.0,
        }

    def shadow_tick(self, real_state: str, real_energy: str,
                    mse_state: dict, sm_state: dict) -> None:
        """
        Called every CueEngine tick. Runs resolve(), logs result,
        detects mismatches. ZERO side effects.

        Args:
            real_state: The effective state CueEngine is actually using
            real_energy: The energy level CueEngine is actually using
            mse_state: MSE probability snapshot
            sm_state: StateManager snapshot
        """
        self._tick += 1
        t_ms = time.time() * 1000

        decision = self.resolve(mse_state, sm_state)

        de_ctx = decision.get("context_state", "?")
        de_event = decision.get("event_state")
        de_conf = decision.get("confidence", 0.0)

        line = (
            f"[TICK] t={t_ms:.0f} "
            f"REAL: state={real_state} energy={real_energy} "
            f"DE:   ctx={de_ctx} event={de_event} conf={de_conf:.2f}"
        )

        # Mismatch detection
        if de_ctx is not None and de_ctx != real_state:
            line += f"\n⚠ MISMATCH: real={real_state} vs de={de_ctx}"

        with self._lock:
            self._log_buffer.append(line)

            # Flush buffer periodically
            if self._tick % self._flush_interval == 0:
                self._flush()

    def _flush(self):
        """Write buffered lines to log file. Called with lock held."""
        if not self._log_buffer:
            return
        try:
            with open(self._log_path, "a") as f:
                f.write("\n".join(self._log_buffer))
                f.write("\n")
            self._log_buffer.clear()
        except Exception:
            # Shadow mode must never crash the system
            self._log_buffer.clear()

    def flush(self):
        """Public flush for shutdown scenarios."""
        with self._lock:
            self._flush()

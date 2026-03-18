# decision_engine.py — Phase 1: ATAQUE as Evidence-Driven Overlay
# ================================================================
# ARCHITECTURE:
#   CONTEXT LAYER (persistent, mutually exclusive):
#     - BAJADA, BASE_GOLPE, BRAKE
#   EVENT LAYER (transient overlay):
#     - ATAQUE (evidence-driven, does NOT replace context)
#
# THIS MODULE:
#   - Computes context_state (excluding ATAQUE from context)
#   - Computes event_state (ATAQUE overlay based on score evidence)
#   - Logs all decisions for observability
#   - Does NOT call fire_cue/kill_cue (CueEngine does that)
# ================================================================

import time
import os
import threading


# --- ATAQUE overlay thresholds ---
ATAQUE_ENTRY_SCORE = 0.60       # Score to activate ATAQUE event
ATAQUE_HOLD_SCORE = 0.35        # Score to sustain ATAQUE (lower than entry)
ATAQUE_EXIT_TICKS = 3           # Consecutive ticks below hold to deactivate


class DecisionEngine:
    """
    Phase 1 Decision Engine — ATAQUE as Evidence-Driven Overlay.

    Separates the state model into:
    - context_state: BAJADA / BASE_GOLPE / BRAKE (persistent)
    - event_state: ATAQUE or None (transient overlay)

    ATAQUE does not replace context. It overlays while musical evidence
    (ataque score) remains above hold threshold.
    """

    def __init__(self, log_path: str = "logs/decision_engine_shadow.log"):
        self._log_path = log_path
        self._tick = 0

        # Buffered logging: accumulate lines, flush periodically
        self._log_buffer = []
        self._flush_interval = 20  # flush every 20 ticks (~1s at 50ms)
        self._lock = threading.Lock()

        # --- ATAQUE overlay state ---
        self._ataque_active = False
        self._ataque_since = 0.0          # timestamp when ATAQUE activated
        self._below_hold_count = 0        # consecutive ticks below hold threshold
        self._last_ataque_score = 0.0

        # --- Context tracking ---
        # Tracks the last known non-ATAQUE context so we can recover it
        # when StateManager reports ATAQUE as its current_state.
        self._last_context = "BAJADA"     # safe default

        # Ensure log directory exists
        log_dir = os.path.dirname(self._log_path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        # Write header on init
        try:
            with open(self._log_path, "a") as f:
                f.write(f"# DecisionEngine Phase 1 (ATAQUE overlay) — started {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        except Exception:
            pass

    def resolve(self, sm_state: dict) -> dict:
        """
        Compute context_state + event_state from StateManager snapshot.

        Args:
            sm_state: {current_state, energy, scores, time_in_state}
                scores: {bajada: float, base_golpe: float, ataque: float, brake: float}

        Returns:
            {context_state, event_state, ataque_score, confidence}
        """
        raw_state = sm_state.get("current_state", "UNKNOWN")
        scores = sm_state.get("scores", {})
        ataque_score = scores.get("ataque", 0.0)

        # --- Derive context (excluding ATAQUE) ---
        context = self._derive_context(raw_state, scores)

        # --- Evaluate ATAQUE event overlay ---
        event = self._evaluate_ataque(ataque_score, context)

        return {
            "context_state": context,
            "event_state": event,
            "ataque_score": ataque_score,
            "confidence": ataque_score if event == "ATAQUE" else 0.0,
        }

    def _derive_context(self, raw_state: str, scores: dict) -> str:
        """
        Derive the context state, excluding ATAQUE.

        If StateManager says ATAQUE, we infer the underlying context
        from the highest non-ataque score, falling back to last known context.
        """
        if raw_state != "ATAQUE":
            # Normal context state — track it
            if raw_state in ("BAJADA", "BASE_GOLPE", "BRAKE"):
                self._last_context = raw_state
            return raw_state

        # StateManager says ATAQUE — infer underlying context
        # Use the highest scoring non-ataque state
        context_scores = {
            "BAJADA": scores.get("bajada", 0.0),
            "BASE_GOLPE": scores.get("base_golpe", 0.0),
            "BRAKE": scores.get("brake", 0.0),
        }
        best_ctx = max(context_scores, key=context_scores.get)
        best_score = context_scores[best_ctx]

        # Only use inferred context if it has meaningful signal
        if best_score >= 0.20:
            self._last_context = best_ctx
            return best_ctx

        # Fall back to last known context
        return self._last_context

    def _evaluate_ataque(self, ataque_score: float, context: str) -> str:
        """
        Evidence-driven ATAQUE overlay evaluation.

        Entry: ataque_score >= ATAQUE_ENTRY_SCORE and context != BRAKE
        Hold:  ataque_score >= ATAQUE_HOLD_SCORE (persists while evidence exists)
        Exit:  ataque_score < ATAQUE_HOLD_SCORE for ATAQUE_EXIT_TICKS consecutive ticks
        BRAKE blocks: ATAQUE cannot be active during BRAKE context
        """
        now = time.time()
        self._last_ataque_score = ataque_score

        # BRAKE blocks ATAQUE unconditionally
        if context == "BRAKE":
            if self._ataque_active:
                self._log_event("exit", ataque_score, context, reason="BRAKE_BLOCK")
                self._ataque_active = False
                self._below_hold_count = 0
            return None

        # --- ATAQUE currently active ---
        if self._ataque_active:
            if ataque_score >= ATAQUE_HOLD_SCORE:
                # Evidence continues — sustain
                self._below_hold_count = 0
                return "ATAQUE"
            else:
                # Evidence dropping
                self._below_hold_count += 1
                if self._below_hold_count >= ATAQUE_EXIT_TICKS:
                    # Evidence gone for N ticks — exit
                    self._log_event("exit", ataque_score, context,
                                    reason=f"evidence_lost ({self._below_hold_count} ticks)")
                    self._ataque_active = False
                    self._below_hold_count = 0
                    return None
                # Still in grace period
                return "ATAQUE"

        # --- ATAQUE not active: check entry ---
        if ataque_score >= ATAQUE_ENTRY_SCORE:
            self._ataque_active = True
            self._ataque_since = now
            self._below_hold_count = 0
            self._log_event("entry", ataque_score, context)
            return "ATAQUE"

        return None

    @property
    def ataque_active(self) -> bool:
        """Public read-only access to ATAQUE overlay state."""
        return self._ataque_active

    @property
    def last_context(self) -> str:
        """Public read-only access to last known context."""
        return self._last_context

    def _log_event(self, event_type: str, score: float, context: str,
                   reason: str = "") -> None:
        """Log ATAQUE event transitions."""
        reason_str = f" reason={reason}" if reason else ""
        line = f"[ATAQUE EVENT] {event_type} score={score:.2f} ctx={context}{reason_str}"
        print(line)
        with self._lock:
            self._log_buffer.append(line)

    def tick(self, real_state: str, real_energy: str,
             sm_state: dict) -> dict:
        """
        Called every CueEngine tick. Computes and logs context/event decision.

        Args:
            real_state: Raw state from StateManager
            real_energy: Energy level from StateManager
            sm_state: Full StateManager snapshot

        Returns:
            dict with context_state, event_state, ataque_score
        """
        self._tick += 1
        t_ms = time.time() * 1000

        decision = self.resolve(sm_state)

        ctx = decision["context_state"]
        event = decision["event_state"]
        a_score = decision["ataque_score"]

        # Build log line
        line = (
            f"[TICK] t={t_ms:.0f} "
            f"SM: state={real_state} energy={real_energy} "
            f"DE:   ctx={ctx} event={event} a_score={a_score:.2f}"
        )

        # Log sustain when ATAQUE is active (throttled: every 10 ticks)
        if event == "ATAQUE" and self._tick % 10 == 0:
            duration = time.time() - self._ataque_since
            line += f" [sustain {duration:.1f}s]"

        with self._lock:
            self._log_buffer.append(line)
            if self._tick % self._flush_interval == 0:
                self._flush()

        return decision

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
            self._log_buffer.clear()

    def flush(self):
        """Public flush for shutdown scenarios."""
        with self._lock:
            self._flush()

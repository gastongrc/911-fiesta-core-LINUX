# mod_control_dimmer.py — CONTROL DIMMER: C41 PASSIVE CANONICAL
# ===========================================================================
# BIBLIA 911 FIESTA — CANON ABSOLUTO
#
# NATURALEZA:
#   - CONTROL_DIMMER es 100% PASIVO
#   - NUNCA dispara C41 por sí mismo
#   - NUNCA detecta kills externos
#   - NUNCA hace auto-recovery
#
# COMPORTAMIENTO:
#   - Solo responde a request_dim_off() y release_dim_off()
#   - request_dim_off() → kill C41
#   - release_dim_off() → fire C41 (solo si no quedan razones)
#
# CALLERS VÁLIDOS:
#   - BASE_GOLPE (FX_DIMMER): request/release_dim_off("FX_DIMMER")
#   - BRAKE (C44): request/release_dim_off("BREAK_C44")
#
# PROHIBICIONES:
#   - NO fire C41 en __init__
#   - NO polling de is_active()
#   - NO timers
#   - NO auto-recovery
#   - NO detección de kills externos
# ===========================================================================

from typing import Dict, Any, List, Set

REASON_FX_DIMMER = "FX_DIMMER"
REASON_BREAK_C44 = "BREAK_C44"


class ControlDimmerModule:
    """
    CONTROL_DIMMER: Módulo 100% PASIVO.

    - Solo responde a request_dim_off() y release_dim_off()
    - NUNCA dispara C41 por iniciativa propia
    - NUNCA hace auto-recovery
    """

    def __init__(self, avolites, aux_manager=None):
        self.av = avolites

        # Razones activas para dim_off
        self._reasons: Set[str] = set()

        # Estado lógico (NO hardware state)
        self._is_dim_off: bool = False

        print("[CONTROL_DIMMER] init (PASSIVE canonical)")

    def request_dim_off(self, reason: str) -> None:
        """
        Agrega una razón para mantener C41 OFF.
        Solo acepta razones válidas: FX_DIMMER, BREAK_C44
        """
        if reason not in (REASON_FX_DIMMER, REASON_BREAK_C44):
            return

        was_empty = len(self._reasons) == 0
        self._reasons.add(reason)

        # Transición: sin razones → con razones = KILL C41
        if was_empty and len(self._reasons) > 0:
            try:
                self.av.kill_cue(41)
                self._is_dim_off = True
                print(f"[CONTROL_DIMMER] C41 OFF (reason: {reason})")
            except Exception:
                pass

    def release_dim_off(self, reason: str) -> None:
        """
        Libera una razón para C41 OFF.
        Si no quedan razones, dispara C41.
        """
        if reason not in self._reasons:
            return

        self._reasons.discard(reason)

        # Transición: con razones → sin razones = FIRE C41
        if len(self._reasons) == 0 and self._is_dim_off:
            try:
                self.av.fire_cue(41)
                self._is_dim_off = False
                print(f"[CONTROL_DIMMER] C41 ON (released: {reason})")
            except Exception:
                pass

    def has_c41_reasons(self) -> bool:
        """Returns True if there are active reasons to keep C41 OFF."""
        return len(self._reasons) > 0

    def ensure_c41_on(self) -> None:
        """
        Watchdog: Re-fire C41 if no reasons exist and Titan reports it inactive.
        Called periodically (~10s) from CueEngine to recover from Titan reconnects.
        """
        if not self.has_c41_reasons():
            try:
                if not self.av.is_active(41):
                    self.av.fire_cue(41)
                    self._is_dim_off = False
                    print("[CONTROL_DIMMER] WATCHDOG: C41 re-fired (was inactive)")
            except Exception:
                pass

    def run(self, state: str, energy: str) -> None:
        """
        NO-OP.
        CONTROL_DIMMER es pasivo y no actúa por tick.
        """
        pass

    def get_active_cues(self) -> List[int]:
        """Retorna C41 si está lógicamente encendido."""
        return [] if self._is_dim_off else [41]

    def get_status(self) -> Dict[str, Any]:
        """Telemetría."""
        return {
            "mode": "PASSIVE",
            "reasons": list(self._reasons),
            "is_dim_off": self._is_dim_off,
            "c41_logical_state": "OFF" if self._is_dim_off else "ON",
        }

    def reset(self) -> None:
        """Reset del módulo."""
        # Si estaba en dim_off, restaurar C41
        if self._is_dim_off:
            try:
                self.av.fire_cue(41)
            except Exception:
                pass

        self._reasons.clear()
        self._is_dim_off = False
        print("[CONTROL_DIMMER] Reset")

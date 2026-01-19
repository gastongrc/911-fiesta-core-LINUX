# aux_state_manager.py — TABLA DE ESTADO: Solo datos, sin hardware
# ===========================================================================
# QUÉ HACE:
#   - Mantiene tabla de razones para C41 (FX_DIMMER, BREAK_C44)
#   - Mantiene índice global de secuencia auxiliar (C45-50)
#   - Provee consultas de estado para otros módulos
#
# QUÉ NO HACE:
#   - NO hace fire/kill de cues (eso es de los módulos)
#   - NO decide estados (eso es del StateManager)
#   - NO controla hardware (solo tabla de estado)
#
# INPUTS: add_c41_reason(), remove_c41_reason(), increment_aux_index()
# OUTPUTS: has_c41_reasons(), get_aux_index(), get_status()
#
# CONSUMIDORES:
#   - ControlDimmerModule (razones C41)
#   - TimedSequenceModule (índice auxiliar)
# ===========================================================================

import time
from typing import Dict, Any, List, Set, Optional


class AuxStateManager:
    """
    AUX-V2: Tabla de Estado Centralizada para 911 Fiesta.

    SOLO mantiene estado, NO controla hardware:
    - C41: Tabla de razones para dim_off (FX_DIMMER, BREAK_C44)
    - C44: Flag booleano de activación
    - C45-C50: Índice global de secuencia

    Los módulos ControlDimmer, Break y TimedSequence consultan
    este estado para tomar decisiones, pero ELLOS hacen fire/kill.
    """

    def __init__(self):
        """Inicializa la tabla de estado."""

        # ===== C41 (DIMMER) - Solo tabla de razones =====
        self._c41_reasons: Set[str] = set()
        self._c41_reason_timestamps: Dict[str, float] = {}

        # ===== C45-C50 (SECUENCIA) - Solo índice y config =====
        self._aux_sequence: List[int] = [45, 46, 47, 48, 49, 50]
        self._aux_enabled: bool = True
        self._aux_global_index: int = 0

        print("[AUX] AuxStateManager v3.0 inicializado (tabla de estado limpia)")

    # =================================================================
    # C41 (DIMMER) - Tabla de razones
    # =================================================================

    def request_c41_off(self, reason: str) -> bool:
        """
        Registra una razón para mantener C41 OFF.
        NO hace fire/kill - solo guarda en tabla.

        Args:
            reason: "FX_DIMMER" o "BREAK_C44"

        Returns:
            bool: True si la razón fue agregada
        """
        if reason not in ("FX_DIMMER", "BREAK_C44"):
            return False

        if reason not in self._c41_reasons:
            self._c41_reasons.add(reason)
            self._c41_reason_timestamps[reason] = time.time()
            print(f"[AUX] C41 reason added: {reason}")
            return True
        return False

    def release_c41_off(self, reason: str) -> bool:
        """
        Libera una razón para C41 OFF.
        NO hace fire/kill - solo quita de tabla.

        Args:
            reason: Razón a liberar

        Returns:
            bool: True si la razón fue liberada
        """
        if reason in self._c41_reasons:
            self._c41_reasons.discard(reason)
            self._c41_reason_timestamps.pop(reason, None)
            print(f"[AUX] C41 reason removed: {reason}")
            return True
        return False

    def has_c41_reasons(self) -> bool:
        """Retorna True si hay razones activas para C41 OFF."""
        return len(self._c41_reasons) > 0

    def get_c41_reasons(self) -> List[str]:
        """Retorna lista de razones activas."""
        return list(self._c41_reasons)

    # =================================================================
    # C45-C50 (SECUENCIA) - Solo índice
    # =================================================================

    def get_aux_sequence(self) -> List[int]:
        """Retorna la secuencia de cues auxiliares."""
        return self._aux_sequence[:]

    def set_aux_sequence(self, cues: List[int]):
        """Configura la secuencia de cues auxiliares."""
        if cues:
            self._aux_sequence = list(cues)

    def is_aux_enabled(self) -> bool:
        """Retorna si la secuencia está habilitada."""
        return self._aux_enabled

    def set_aux_enabled(self, enabled: bool):
        """Habilita/deshabilita la secuencia."""
        self._aux_enabled = bool(enabled)

    def get_aux_index(self) -> int:
        """Retorna el índice global actual."""
        return self._aux_global_index

    def increment_aux_index(self) -> int:
        """
        Incrementa el índice global y retorna el nuevo valor.
        NO hace fire/kill - solo incrementa contador.
        """
        self._aux_global_index += 1
        return self._aux_global_index

    def reset_aux_index(self, value: int = 0):
        """Resetea el índice global."""
        self._aux_global_index = max(0, int(value))

    def get_current_aux_cue(self) -> Optional[int]:
        """
        Retorna el cue actual según el índice.
        NO dispara nada - solo calcula cuál sería.
        """
        if not self._aux_sequence or not self._aux_enabled:
            return None
        return self._aux_sequence[self._aux_global_index % len(self._aux_sequence)]

    # =================================================================
    # ESTADO GLOBAL
    # =================================================================

    def get_status(self) -> Dict[str, Any]:
        """Retorna estado completo de la tabla."""
        now = time.time()

        return {
            "version": "3.0",
            "type": "state_table_only",
            # C41
            "c41": {
                "reasons": list(self._c41_reasons),
                "reason_count": len(self._c41_reasons),
                "has_reasons": self.has_c41_reasons(),
                "reason_ages_ms": {
                    r: int((now - ts) * 1000)
                    for r, ts in self._c41_reason_timestamps.items()
                },
            },
            # Secuencia auxiliar
            "aux_sequence": {
                "enabled": self._aux_enabled,
                "sequence": self._aux_sequence[:],
                "global_index": self._aux_global_index,
                "current_cue": self.get_current_aux_cue(),
            },
        }

    def reset(self):
        """Resetea toda la tabla a estado inicial."""
        self._c41_reasons.clear()
        self._c41_reason_timestamps.clear()
        self._aux_global_index = 0
        print("[AUX] State table reset")

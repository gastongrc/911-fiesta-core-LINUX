# ============================================================================
# cue_output_adapter.py v2.0 - ADAPTADOR CUE → DMX (PULSE MODE)
# ============================================================================
# Traduce eventos del CueEngine (fire/kill) a operaciones DMX.
#
# CueEngine NO conoce DMX. Este adaptador es la capa intermedia:
#   CueEngine → CueOutputAdapter → DmxState → SacnEngine/ArtNetEngine
#
# Pulse mode: fire() triggers a 1-frame pulse. kill() is a no-op.
#
# Interface idéntica a la que espera AvolitesController:
#   adapter.fire(cue_id)
#   adapter.kill(cue_id)      ← no-op in pulse mode
#   adapter.kill_pool(cue_ids) ← no-op in pulse mode
# ============================================================================

from __future__ import annotations

import logging
from typing import List, Optional, Set

from .dmx_state import DmxState

logger = logging.getLogger("CueOutputAdapter")


class CueOutputAdapter:
    """
    Adaptador CueEngine → DMX (pulse mode).

    Traduce fire de cues a pulsos DMX de 1 frame.
    kill() is a no-op — channels auto-reset after snapshot.

    Uso:
        adapter = CueOutputAdapter(dmx_state)
        adapter.fire(41)   # dmx_state channel 41 = 255 for 1 frame
        adapter.kill(41)   # no-op (auto-reset)
    """

    def __init__(self, dmx_state: DmxState):
        self._dmx = dmx_state

        # Stats
        self._fires = 0
        self._kills = 0
        self._unmapped = 0

        logger.info("[CueOutputAdapter] Inicializado")

    def fire(self, cue_id: int) -> bool:
        """
        Pulse trigger: channel = 255 for 1 frame, then auto-reset to 0.

        Args:
            cue_id: ID del cue

        Returns:
            True si el cue tiene mapeo DMX
        """
        result = self._dmx.fire(cue_id)
        if result:
            self._fires += 1
        else:
            self._unmapped += 1
        return result

    def kill(self, cue_id: int) -> bool:
        """
        No-op in pulse mode. Channels auto-reset after 1 frame.
        Kept for API compatibility.

        Returns:
            True si el cue tiene mapeo DMX
        """
        result = self._dmx.kill(cue_id)
        if result:
            self._kills += 1
        return result

    def kill_pool(self, cue_ids: List[int]) -> int:
        """
        Desactiva múltiples cues.

        Args:
            cue_ids: Lista de IDs a desactivar

        Returns:
            Número de kills exitosos
        """
        count = 0
        for cue_id in cue_ids:
            if self.kill(cue_id):
                count += 1
        return count

    def kill_all(self) -> None:
        """Blackout: apaga todos los canales DMX."""
        self._dmx.kill_all()
        self._kills += 1

    def get_active_cues(self) -> Set[int]:
        """Returns empty set — pulse mode has no sustained active cues."""
        return self._dmx.get_active_cues()

    def is_active(self, cue_id: int) -> bool:
        """Always False in pulse mode — cues are momentary."""
        return False

    def get_stats(self) -> dict:
        """Retorna estadísticas del adaptador."""
        return {
            "fires": self._fires,
            "kills": self._kills,
            "unmapped": self._unmapped,
            "dmx": self._dmx.get_stats(),
        }


__all__ = ["CueOutputAdapter"]

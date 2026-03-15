# ============================================================================
# cue_output_adapter.py v1.0 - ADAPTADOR CUE → DMX
# ============================================================================
# Traduce eventos del CueEngine (fire/kill) a operaciones DMX.
#
# CueEngine NO conoce DMX. Este adaptador es la capa intermedia:
#   CueEngine → CueOutputAdapter → DmxState → ArtNetEngine
#
# Interface idéntica a la que espera AvolitesController:
#   adapter.fire(cue_id)
#   adapter.kill(cue_id)
#   adapter.kill_pool(cue_ids)
# ============================================================================

from __future__ import annotations

import logging
from typing import List, Optional, Set

from .dmx_state import DmxState

logger = logging.getLogger("CueOutputAdapter")


class CueOutputAdapter:
    """
    Adaptador CueEngine → DMX.

    Traduce fire/kill de cues a operaciones sobre DmxState.
    CueEngine llama a este adaptador sin saber que es DMX.

    Uso:
        adapter = CueOutputAdapter(dmx_state)
        adapter.fire(41)   # dmx_state channel 41 = 255
        adapter.kill(41)   # dmx_state channel 41 = 0
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
        Activa un cue en DMX (canal = 255).

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
        Desactiva un cue en DMX (canal = 0).

        Args:
            cue_id: ID del cue

        Returns:
            True si el cue tiene mapeo DMX
        """
        result = self._dmx.kill(cue_id)
        if result:
            self._kills += 1
        else:
            self._unmapped += 1
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
        """Retorna cues activos en DMX."""
        return self._dmx.get_active_cues()

    def is_active(self, cue_id: int) -> bool:
        """Verifica si un cue está activo."""
        return cue_id in self._dmx.get_active_cues()

    def get_stats(self) -> dict:
        """Retorna estadísticas del adaptador."""
        return {
            "fires": self._fires,
            "kills": self._kills,
            "unmapped": self._unmapped,
            "dmx": self._dmx.get_stats(),
        }


__all__ = ["CueOutputAdapter"]

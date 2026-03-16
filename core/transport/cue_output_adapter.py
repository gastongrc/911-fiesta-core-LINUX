# ============================================================================
# cue_output_adapter.py v3.0 - ADAPTADOR CUE → DMX (DUAL PULSE MODE)
# ============================================================================
# Traduce eventos del CueEngine (fire/kill) a pulsos DMX.
#
# CueEngine NO conoce DMX. Este adaptador es la capa intermedia:
#   CueEngine → CueOutputAdapter → DmxState → SacnEngine/ArtNetEngine
#
# Dual pulse mode mirrors HTTP transport semantics:
#   fire(cue_id) → pulse on fire channel   (ch N)
#   kill(cue_id) → pulse on kill channel   (ch N + offset)
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
    Adaptador CueEngine → DMX (dual pulse mode).

    Both fire() and kill() generate 1-frame pulses on separate channels.
    Mirrors HTTP transport: fire = explicit ON event, kill = explicit OFF event.

    Uso:
        adapter = CueOutputAdapter(dmx_state)
        adapter.fire(41)   # pulse ch 41 = 255 for 1 frame
        adapter.kill(41)   # pulse ch 123 = 255 for 1 frame (41 + 82)
    """

    def __init__(self, dmx_state: DmxState):
        self._dmx = dmx_state

        # Stats
        self._fires = 0
        self._kills = 0
        self._unmapped = 0

        logger.info("[CueOutputAdapter] v3.0 DUAL PULSE mode")

    def fire(self, cue_id: int) -> bool:
        """
        Pulse trigger for fire: channel = 255 for 1 frame, then auto-reset.

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
        Pulse trigger for kill: kill_channel = 255 for 1 frame, then auto-reset.
        Kill channel = fire channel + kill_channel_offset.

        Args:
            cue_id: ID del cue

        Returns:
            True si el cue tiene mapeo DMX
        """
        print(f"[KILL ADAPTER] cue={cue_id}")
        result = self._dmx.kill(cue_id)
        if result:
            self._kills += 1
        else:
            self._unmapped += 1
        return result

    def kill_pool(self, cue_ids: List[int]) -> int:
        """
        Kill pulse para múltiples cues.

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
        """Blackout: fuerza todos los canales a 0 inmediatamente."""
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

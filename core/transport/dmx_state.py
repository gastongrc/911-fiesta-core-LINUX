# ============================================================================
# dmx_state.py v1.0 - CONSOLA DMX VIRTUAL
# ============================================================================
# Mantiene el estado persistente de 512 canales DMX.
#
# Semántica:
#   fire(cue_id) → canal(es) mapeado(s) = on_value (255)
#   kill(cue_id) → canal(es) mapeado(s) = off_value (0)
#   snapshot()   → copia atómica de los 512 canales
#
# El estado se mantiene hasta que se cambie explícitamente.
# No hay pulsos ni timeouts — DMX es estado sostenido.
#
# Thread-safe: todas las operaciones usan lock.
# ============================================================================

from __future__ import annotations

import json
import logging
import threading
from typing import Dict, List, Optional

logger = logging.getLogger("DmxState")

DMX_CHANNELS = 512
DMX_ON_VALUE = 255
DMX_OFF_VALUE = 0


class DmxState:
    """
    Consola DMX virtual — mantiene estado persistente de 512 canales.

    Uso:
        state = DmxState(cue_channel_map={1: [1], 41: [41]})
        state.fire(41)      # ch41 = 255
        state.kill(41)      # ch41 = 0
        frame = state.snapshot()  # bytearray(512)
    """

    def __init__(
        self,
        cue_channel_map: Optional[Dict[int, List[int]]] = None,
        on_value: int = DMX_ON_VALUE,
        off_value: int = DMX_OFF_VALUE,
    ):
        self._channels = bytearray(DMX_CHANNELS)
        self._lock = threading.Lock()
        self._on_value = max(0, min(255, on_value))
        self._off_value = max(0, min(255, off_value))

        # cue_id (int) → lista de canales DMX (0-indexed internamente, 1-indexed en config)
        self._cue_map: Dict[int, List[int]] = {}
        if cue_channel_map:
            self._load_map(cue_channel_map)

        # Tracking de cues activos
        self._active_cues: set = set()

        logger.info(
            f"[DmxState] Inicializado: {len(self._cue_map)} cues mapeados, "
            f"on={self._on_value} off={self._off_value}"
        )

    def _load_map(self, raw_map: Dict) -> None:
        """Carga el mapeo cue→canales, aceptando keys string o int."""
        for key, channels in raw_map.items():
            if str(key).startswith("_"):
                continue
            cue_id = int(key)
            if isinstance(channels, list):
                self._cue_map[cue_id] = channels
            else:
                self._cue_map[cue_id] = [int(channels)]

    @classmethod
    def from_json(cls, path: str, on_value: int = DMX_ON_VALUE, off_value: int = DMX_OFF_VALUE) -> "DmxState":
        """Crea DmxState desde un archivo cue_map.json."""
        with open(path, "r") as f:
            raw = json.load(f)
        return cls(cue_channel_map=raw, on_value=on_value, off_value=off_value)

    def fire(self, cue_id: int) -> bool:
        """
        Activa un cue: pone canal(es) mapeado(s) a on_value (255).
        El valor se mantiene hasta kill().

        Args:
            cue_id: ID del cue a activar

        Returns:
            True si el cue tiene mapeo DMX, False si no está mapeado
        """
        channels = self._cue_map.get(cue_id)
        if not channels:
            print(f"[DmxState] fire(C{cue_id}): NO DMX MAPPING — cue not in cue_map")
            return False

        with self._lock:
            for ch in channels:
                idx = ch - 1  # DMX channels 1-512 → array index 0-511
                if 0 <= idx < DMX_CHANNELS:
                    self._channels[idx] = self._on_value
            self._active_cues.add(cue_id)
            non_zero = sum(1 for v in self._channels if v > 0)

        print(f"[DmxState] FIRE C{cue_id} → ch{channels} = {self._on_value} | active_cues={len(self._active_cues)} nonzero_ch={non_zero}")
        return True

    def kill(self, cue_id: int) -> bool:
        """
        Desactiva un cue: pone canal(es) mapeado(s) a off_value (0).
        El valor se mantiene hasta fire().

        Args:
            cue_id: ID del cue a desactivar

        Returns:
            True si el cue tiene mapeo DMX, False si no está mapeado
        """
        channels = self._cue_map.get(cue_id)
        if not channels:
            print(f"[DmxState] kill(C{cue_id}): NO DMX MAPPING — cue not in cue_map")
            return False

        with self._lock:
            for ch in channels:
                idx = ch - 1
                if 0 <= idx < DMX_CHANNELS:
                    self._channels[idx] = self._off_value
            self._active_cues.discard(cue_id)
            non_zero = sum(1 for v in self._channels if v > 0)

        print(f"[DmxState] KILL C{cue_id} → ch{channels} = {self._off_value} | active_cues={len(self._active_cues)} nonzero_ch={non_zero}")
        return True

    def kill_all(self) -> None:
        """Apaga todos los canales (blackout)."""
        with self._lock:
            for i in range(DMX_CHANNELS):
                self._channels[i] = self._off_value
            self._active_cues.clear()

        print("[DmxState] KILL ALL (blackout) — all 512 channels → 0")

    def set_channel(self, channel: int, value: int) -> None:
        """
        Setea un canal DMX directamente (bypass cue map).

        Args:
            channel: Canal DMX (1-512)
            value: Valor (0-255)
        """
        idx = channel - 1
        if 0 <= idx < DMX_CHANNELS:
            with self._lock:
                self._channels[idx] = max(0, min(255, value))

    def get_channel(self, channel: int) -> int:
        """Lee el valor actual de un canal DMX (1-512)."""
        idx = channel - 1
        if 0 <= idx < DMX_CHANNELS:
            with self._lock:
                return self._channels[idx]
        return 0

    def snapshot(self) -> bytearray:
        """
        Devuelve copia atómica de los 512 canales.
        Usada por ArtNetEngine para construir cada frame.
        """
        with self._lock:
            return bytearray(self._channels)

    def get_active_cues(self) -> set:
        """Retorna set de cue IDs activos."""
        with self._lock:
            return self._active_cues.copy()

    def get_cue_map(self) -> Dict[int, List[int]]:
        """Retorna copia del mapeo cue→canales."""
        return dict(self._cue_map)

    def update_cue_map(self, cue_channel_map: Dict) -> None:
        """Actualiza el mapeo cue→canales en caliente."""
        new_map: Dict[int, List[int]] = {}
        for key, channels in cue_channel_map.items():
            if str(key).startswith("_"):
                continue
            cue_id = int(key)
            if isinstance(channels, list):
                new_map[cue_id] = channels
            else:
                new_map[cue_id] = [int(channels)]
        self._cue_map = new_map
        logger.info(f"[DmxState] Cue map actualizado: {len(new_map)} cues")

    def get_stats(self) -> dict:
        """Retorna estadísticas del estado DMX."""
        with self._lock:
            non_zero = sum(1 for v in self._channels if v > 0)
            return {
                "active_cues": len(self._active_cues),
                "active_channels": non_zero,
                "total_channels": DMX_CHANNELS,
                "mapped_cues": len(self._cue_map),
            }


__all__ = ["DmxState", "DMX_CHANNELS", "DMX_ON_VALUE", "DMX_OFF_VALUE"]

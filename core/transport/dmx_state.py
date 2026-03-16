# ============================================================================
# dmx_state.py v3.0 - CONSOLA DMX VIRTUAL (DUAL PULSE MODE)
# ============================================================================
# Pulse-based DMX state for Titan. Both fire and kill are explicit events,
# each generating a 1-frame pulse on separate DMX channels.
#
# Semántica:
#   fire(cue_id) → pulse on fire channel(s)     [channels 1-256]
#   kill(cue_id) → pulse on kill channel(s)      [channels 257-512]
#   snapshot()   → atomic copy + auto-reset all pulsed channels
#
# Channel layout (kill_channel_offset = max fire channel):
#   With 82 cues on channels 1-82:
#     fire cue 41 → pulse ch 41  (fire channel)
#     kill cue 41 → pulse ch 123 (kill channel = 41 + 82)
#     Layout: 1-82 fire, 83-164 kill
#
# Mirrors HTTP transport semantics exactly:
#   HTTP fire_cue(41) → POST /fire  → cue ON
#   HTTP kill_cue(41) → POST /kill  → cue OFF
#   DMX  fire_cue(41) → pulse ch 41  → Titan sees fire trigger
#   DMX  kill_cue(41) → pulse ch 123 → Titan sees kill trigger
#
# Thread-safe: todas las operaciones usan lock.
# ============================================================================

from __future__ import annotations

import json
import logging
import threading
from typing import Dict, List, Optional, Set

logger = logging.getLogger("DmxState")

DMX_CHANNELS = 512
DMX_ON_VALUE = 255
DMX_OFF_VALUE = 0
DEFAULT_KILL_CHANNEL_OFFSET = 0  # 0 = auto-compute from max fire channel


class DmxState:
    """
    Consola DMX virtual — dual pulse mode para Titan.

    fire() and kill() both generate 1-frame pulses on separate channels.
    snapshot() returns current state and atomically resets all pulsed channels.

    Uso:
        state = DmxState(cue_channel_map={1: [1], 41: [41]})
        state.fire(41)           # pulse ch 41 = 255 for 1 frame
        state.kill(41)           # pulse ch 297 = 255 for 1 frame (41 + 256)
        frame = state.snapshot() # captures pulses, resets to 0
    """

    def __init__(
        self,
        cue_channel_map: Optional[Dict[int, List[int]]] = None,
        on_value: int = DMX_ON_VALUE,
        off_value: int = DMX_OFF_VALUE,
        kill_channel_offset: int = DEFAULT_KILL_CHANNEL_OFFSET,
    ):
        self._channels = bytearray(DMX_CHANNELS)
        self._lock = threading.Lock()
        self._on_value = max(0, min(255, on_value))
        self._off_value = max(0, min(255, off_value))

        # Pulse queue: set of 0-indexed channel indices pending auto-reset
        self._pending_resets: Set[int] = set()

        # cue_id (int) → lista de fire channels DMX (1-indexed in config)
        self._cue_map: Dict[int, List[int]] = {}
        if cue_channel_map:
            self._load_map(cue_channel_map)

        # kill_channel_offset: 0 means auto-compute from max fire channel
        if kill_channel_offset > 0:
            self._kill_channel_offset = kill_channel_offset
        else:
            self._kill_channel_offset = self._compute_kill_offset()

        # Stats
        self._total_fire_pulses = 0
        self._total_kill_pulses = 0

        logger.info(
            f"[DmxState] v3.0 DUAL PULSE: {len(self._cue_map)} cues, "
            f"kill_offset={self._kill_channel_offset}, on={self._on_value} off={self._off_value}"
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

    def _compute_kill_offset(self) -> int:
        """Compute kill offset = max fire channel from cue map.

        With cues 1-82 on channels 1-82, offset = 82.
        Kill channels: 83-164. Compact, no gaps.
        """
        max_ch = 0
        for channels in self._cue_map.values():
            for ch in channels:
                if ch > max_ch:
                    max_ch = ch
        return max_ch if max_ch > 0 else 1

    @classmethod
    def from_json(
        cls,
        path: str,
        on_value: int = DMX_ON_VALUE,
        off_value: int = DMX_OFF_VALUE,
        kill_channel_offset: int = DEFAULT_KILL_CHANNEL_OFFSET,
    ) -> "DmxState":
        """Crea DmxState desde un archivo cue_map.json."""
        with open(path, "r") as f:
            raw = json.load(f)
        return cls(
            cue_channel_map=raw,
            on_value=on_value,
            off_value=off_value,
            kill_channel_offset=kill_channel_offset,
        )

    def _pulse_channels(self, indices: List[int]) -> int:
        """Set channels to on_value and mark for auto-reset. Returns count pulsed."""
        pulsed = 0
        for idx in indices:
            if 0 <= idx < DMX_CHANNELS:
                self._channels[idx] = self._on_value
                self._pending_resets.add(idx)
                pulsed += 1
        return pulsed

    def fire(self, cue_id: int) -> bool:
        """
        Pulse trigger for fire event: sets fire channel(s) to 255 for 1 frame.
        Channel resets to 0 automatically on next snapshot().

        Args:
            cue_id: ID del cue a disparar

        Returns:
            True si el cue tiene mapeo DMX, False si no está mapeado
        """
        channels = self._cue_map.get(cue_id)
        if not channels:
            print(f"[DmxState] fire(C{cue_id}): NO DMX MAPPING — cue not in cue_map")
            return False

        indices = [ch - 1 for ch in channels]

        with self._lock:
            self._pulse_channels(indices)
            self._total_fire_pulses += 1
            pending = len(self._pending_resets)

        print(f"[DmxState] FIRE PULSE C{cue_id} → ch{channels} = {self._on_value} (1 frame) | pending={pending}")
        return True

    def kill(self, cue_id: int) -> bool:
        """
        Pulse trigger for kill event: sets kill channel(s) to 255 for 1 frame.
        Kill channel = fire channel + kill_channel_offset.

        Args:
            cue_id: ID del cue a matar

        Returns:
            True si el cue tiene mapeo DMX, False si no está mapeado
        """
        channels = self._cue_map.get(cue_id)
        if not channels:
            print(f"[DmxState] kill(C{cue_id}): NO DMX MAPPING — cue not in cue_map")
            return False

        kill_channels = [ch + self._kill_channel_offset for ch in channels]
        indices = [ch - 1 for ch in kill_channels]

        with self._lock:
            self._pulse_channels(indices)
            self._total_kill_pulses += 1
            pending = len(self._pending_resets)

        print(
            f"[DmxState] KILL PULSE C{cue_id} → ch{kill_channels} = {self._on_value} (1 frame) | pending={pending}"
        )
        return True

    def kill_all(self) -> None:
        """Blackout inmediato: fuerza todos los canales a 0."""
        with self._lock:
            for i in range(DMX_CHANNELS):
                self._channels[i] = self._off_value
            self._pending_resets.clear()

        print("[DmxState] KILL ALL (blackout) — all 512 channels → 0")

    def set_channel(self, channel: int, value: int) -> None:
        """
        Setea un canal DMX directamente (bypass cue map).
        NOT a pulse — stays until changed. Use for diagnostic/test modes.

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
        Atomic snapshot + pulse reset.

        Returns the current 512-channel state, then resets all pulsed
        channels to 0. This guarantees exactly 1 frame of 255 per pulse.

        Called by SacnEngine/ArtNetEngine every frame (~25ms at 40fps).
        """
        with self._lock:
            data = bytearray(self._channels)
            if self._pending_resets:
                for idx in self._pending_resets:
                    self._channels[idx] = self._off_value
                self._pending_resets.clear()
            return data

    def get_active_cues(self) -> set:
        """
        Returns empty set — pulse mode has no sustained active cues.
        Kept for API compatibility.
        """
        return set()

    def get_cue_map(self) -> Dict[int, List[int]]:
        """Retorna copia del mapeo cue→canales (fire channels)."""
        return dict(self._cue_map)

    def get_kill_channel_offset(self) -> int:
        """Retorna el offset usado para calcular kill channels."""
        return self._kill_channel_offset

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
                "mode": "dual_pulse",
                "kill_channel_offset": self._kill_channel_offset,
                "pending_resets": len(self._pending_resets),
                "active_channels": non_zero,
                "total_channels": DMX_CHANNELS,
                "mapped_cues": len(self._cue_map),
                "total_fire_pulses": self._total_fire_pulses,
                "total_kill_pulses": self._total_kill_pulses,
            }


__all__ = [
    "DmxState",
    "DMX_CHANNELS",
    "DMX_ON_VALUE",
    "DMX_OFF_VALUE",
    "DEFAULT_KILL_CHANNEL_OFFSET",
]

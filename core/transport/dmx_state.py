# ============================================================================
# dmx_state.py v4.1 - CONSOLA DMX VIRTUAL (SINGLE-CHANNEL TOGGLE)
# ============================================================================
# Pulse-based DMX state for Avolites Titan Remote.
#
# Each DMX channel is a virtual button. A 1-frame pulse (255 → 0) toggles
# the corresponding cue on the Titan console:
#
#   fire(cue_id) → pulse channel N → Titan toggles cue ON
#   kill(cue_id) → pulse channel N → Titan toggles cue OFF
#
# Both fire and kill use the SAME channel — the pulse is identical.
# Titan interprets each pulse as a button press (toggle).
#
# Pulse queue: each channel has a pending pulse counter. Multiple rapid
# triggers on the same channel are preserved across consecutive frames:
#
#   fire(41)  → _pulse_counts[40] = 1
#   kill(41)  → _pulse_counts[40] = 2
#   snapshot() → frame with ch41=255, counter decrements to 1, ch stays 255
#   snapshot() → frame with ch41=255, counter decrements to 0, ch resets to 0
#   snapshot() → frame with ch41=0
#
# Channel layout (1 cue = 1 channel, up to 512 cues):
#   cue 1  → ch 1
#   cue 41 → ch 41
#   cue 82 → ch 82
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
    Consola DMX virtual — single-channel toggle mode para Titan.

    fire() and kill() both generate identical 1-frame pulses on the same channel.
    Multiple rapid pulses on the same channel are queued and emitted across
    consecutive frames (one pulse per frame per channel).

    snapshot() returns current state and decrements pulse counters. Channels
    with remaining pulses stay at on_value; channels whose counter reaches 0
    are reset to off_value.

    Uso:
        state = DmxState(cue_channel_map={1: [1], 41: [41]})
        state.fire(41)           # pulse ch 41 = 255, counter = 1
        state.kill(41)           # pulse ch 41 = 255, counter = 2
        frame1 = state.snapshot() # ch41=255, counter → 1
        frame2 = state.snapshot() # ch41=255, counter → 0, reset to 0
        frame3 = state.snapshot() # ch41=0
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

        # Per-channel pulse counter: index → remaining pulse count
        # When > 0, channel emits on_value. Each snapshot() decrements by 1.
        # When counter reaches 0, channel resets to off_value.
        self._pulse_counts: Dict[int, int] = {}

        # cue_id (int) → lista de DMX channels (1-indexed in config)
        self._cue_map: Dict[int, List[int]] = {}
        if cue_channel_map:
            self._load_map(cue_channel_map)

        # Stats
        self._total_fire_pulses = 0
        self._total_kill_pulses = 0

        logger.info(
            f"[DmxState] v4.1 TOGGLE: {len(self._cue_map)} cues, "
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
    def from_json(
        cls,
        path: str,
        on_value: int = DMX_ON_VALUE,
        off_value: int = DMX_OFF_VALUE,
    ) -> "DmxState":
        """Crea DmxState desde un archivo cue_map.json."""
        with open(path, "r") as f:
            raw = json.load(f)
        return cls(
            cue_channel_map=raw,
            on_value=on_value,
            off_value=off_value,
        )

    def _pulse_channels(self, indices: List[int]) -> int:
        """Set channels to on_value and increment pulse counter. Returns count pulsed."""
        pulsed = 0
        for idx in indices:
            if 0 <= idx < DMX_CHANNELS:
                self._channels[idx] = self._on_value
                self._pulse_counts[idx] = self._pulse_counts.get(idx, 0) + 1
                pulsed += 1
        return pulsed

    def fire(self, cue_id: int) -> bool:
        """
        Pulse trigger for fire event: sets channel(s) to 255 for 1 frame.
        If channel already has a pending pulse, the new pulse is queued
        and will be emitted in the next available frame.

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
            pending = sum(self._pulse_counts.values())

        print(f"[DmxState] FIRE PULSE C{cue_id} → ch{channels} = {self._on_value} (1 frame) | pending={pending}")
        return True

    def kill(self, cue_id: int) -> bool:
        """
        Pulse trigger for kill event: sets channel(s) to 255 for 1 frame.
        Uses the SAME channel as fire() — Titan treats the pulse as a toggle.
        If channel already has a pending pulse, the new pulse is queued.

        Args:
            cue_id: ID del cue a matar

        Returns:
            True si el cue tiene mapeo DMX, False si no está mapeado
        """
        channels = self._cue_map.get(cue_id)
        if not channels:
            print(f"[DmxState] kill(C{cue_id}): NO DMX MAPPING — cue not in cue_map")
            return False

        indices = [ch - 1 for ch in channels]

        with self._lock:
            self._pulse_channels(indices)
            self._total_kill_pulses += 1
            pending = sum(self._pulse_counts.values())

        print(f"[DmxState] KILL PULSE C{cue_id} → ch{channels} = {self._on_value} (1 frame) | pending={pending}")
        return True

    def kill_all(self) -> None:
        """Blackout inmediato: fuerza todos los canales a 0."""
        with self._lock:
            for i in range(DMX_CHANNELS):
                self._channels[i] = self._off_value
            self._pulse_counts.clear()

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
        Atomic snapshot + pulse decrement.

        Returns the current 512-channel state, then processes pulse counters:
        - Channels with counter > 1: decrement counter, channel stays at on_value
          (next snapshot will emit another pulse frame)
        - Channels with counter == 1: decrement to 0, reset channel to off_value
          (pulse fully consumed)
        - Channels with counter == 0: not in dict, no action

        This guarantees exactly 1 frame of 255 per pulse event, with multiple
        rapid pulses on the same channel spread across consecutive frames.

        Called by SacnEngine/ArtNetEngine every frame (~25ms at 40fps).
        """
        with self._lock:
            data = bytearray(self._channels)
            if self._pulse_counts:
                done = []
                for idx, count in self._pulse_counts.items():
                    if count <= 1:
                        self._channels[idx] = self._off_value
                        done.append(idx)
                    else:
                        self._pulse_counts[idx] = count - 1
                for idx in done:
                    del self._pulse_counts[idx]
            return data

    def get_active_cues(self) -> set:
        """
        Returns empty set — pulse mode has no sustained active cues.
        Kept for API compatibility.
        """
        return set()

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
                "mode": "toggle",
                "pending_pulses": sum(self._pulse_counts.values()),
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
]

# ============================================================================
# artnet_engine.py v1.0 - MOTOR ART-NET (EMISOR CONTINUO)
# ============================================================================
# Emite frames Art-Net OpDmx continuamente via UDP.
#
# Protocolo:
#   Art-Net 4 (port 6454), paquete OpDmx (0x5000)
#   512 canales DMX por frame
#   Frecuencia configurable (default 40 fps)
#
# El motor lee de DmxState.snapshot() cada tick y envía el frame UDP.
# El estado DMX se mantiene estable — no hay pulsos.
#
# Thread independiente, daemon.
# ============================================================================

from __future__ import annotations

import json
import logging
import socket
import struct
import threading
import time
from typing import Optional

from .dmx_state import DmxState, DMX_CHANNELS

logger = logging.getLogger("ArtNetEngine")

# Art-Net constants
ARTNET_HEADER = b"Art-Net\x00"
ARTNET_OPCODE_DMX = 0x5000
ARTNET_PROTOCOL_VERSION = 14
ARTNET_PORT = 6454


def build_artnet_dmx_packet(
    dmx_data: bytearray,
    universe: int = 0,
    sequence: int = 0,
    physical: int = 0,
) -> bytes:
    """
    Construye un paquete Art-Net OpDmx.

    Estructura (total 18 + 512 = 530 bytes):
        Bytes 0-7:    "Art-Net\\0"        (8 bytes, header)
        Bytes 8-9:    0x0050             (OpCode OpDmx, little-endian)
        Bytes 10-11:  0x000E             (Protocol version 14, big-endian)
        Byte 12:      sequence           (0-255, rolling counter)
        Byte 13:      physical           (physical port, 0)
        Bytes 14-15:  universe           (little-endian)
        Bytes 16-17:  length             (512, big-endian)
        Bytes 18-529: DMX data           (512 bytes)

    Args:
        dmx_data: 512 bytes de datos DMX
        universe: Universo Art-Net (0-32767)
        sequence: Contador de secuencia (0-255, 0=disable)
        physical: Puerto físico (0)

    Returns:
        bytes: Paquete Art-Net completo (530 bytes)
    """
    universe_lo = universe & 0xFF
    universe_hi = (universe >> 8) & 0x7F
    length = len(dmx_data)

    packet = bytearray()
    packet.extend(ARTNET_HEADER)                                # 8 bytes
    packet.extend(struct.pack("<H", ARTNET_OPCODE_DMX))         # 2 bytes, little-endian
    packet.extend(struct.pack(">H", ARTNET_PROTOCOL_VERSION))   # 2 bytes, big-endian
    packet.append(sequence & 0xFF)                              # 1 byte
    packet.append(physical & 0xFF)                              # 1 byte
    packet.append(universe_lo)                                  # 1 byte
    packet.append(universe_hi)                                  # 1 byte
    packet.extend(struct.pack(">H", length))                    # 2 bytes, big-endian
    packet.extend(dmx_data[:DMX_CHANNELS])                      # 512 bytes

    return bytes(packet)


class ArtNetEngine:
    """
    Motor Art-Net — emite frames DMX continuamente via UDP.

    Lee de DmxState.snapshot() y envía paquetes OpDmx a la IP configurada.
    Corre en thread daemon independiente.

    Uso:
        engine = ArtNetEngine(dmx_state, target_ip="192.168.1.80")
        engine.start()
        # ... dmx_state.fire(41) ...
        engine.stop()
    """

    def __init__(
        self,
        dmx_state: DmxState,
        target_ip: str = "2.255.255.255",
        port: int = ARTNET_PORT,
        universe: int = 0,
        fps: int = 40,
    ):
        self._dmx_state = dmx_state
        self._target_ip = target_ip
        self._port = port
        self._universe = universe
        self._fps = max(1, min(44, fps))
        self._interval = 1.0 / self._fps

        # Socket UDP
        self._sock: Optional[socket.socket] = None

        # Thread control
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False

        # Sequence counter (0-255 rolling, 0=disabled en spec)
        self._sequence = 1

        # Stats
        self._frames_sent = 0
        self._errors = 0
        self._last_send_ts = 0.0
        self._start_ts = 0.0

        logger.info(
            f"[ArtNetEngine] Inicializado: target={target_ip}:{port} "
            f"universe={universe} fps={fps}"
        )

    def _setup_socket(self) -> None:
        """Crea socket UDP con soporte broadcast."""
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def start(self) -> bool:
        """
        Inicia el motor Art-Net (thread daemon).

        Returns:
            True si inició correctamente
        """
        if self._running:
            return True

        self._setup_socket()
        self._stop_event.clear()
        self._running = True
        self._start_ts = time.time()

        self._thread = threading.Thread(
            target=self._run_loop,
            name="ArtNetEngine",
            daemon=True,
        )
        self._thread.start()

        logger.info(
            f"[ArtNetEngine] Started: {self._target_ip}:{self._port} "
            f"universe={self._universe} @ {self._fps}fps"
        )
        print(
            f"[ArtNetEngine] RUNNING → {self._target_ip}:{self._port} "
            f"universe={self._universe} @ {self._fps}fps"
        )
        return True

    def stop(self) -> None:
        """Detiene el motor Art-Net."""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

        logger.info(
            f"[ArtNetEngine] Stopped after {self._frames_sent} frames, "
            f"{self._errors} errors"
        )
        print(f"[ArtNetEngine] STOPPED ({self._frames_sent} frames sent)")

    def _run_loop(self) -> None:
        """Loop principal: envía frames Art-Net a la frecuencia configurada."""
        logger.info("[ArtNetEngine] Worker started")

        while not self._stop_event.is_set():
            frame_start = time.monotonic()

            try:
                self._send_frame()
            except Exception as e:
                self._errors += 1
                if self._errors <= 5 or self._errors % 100 == 0:
                    logger.error(f"[ArtNetEngine] Send error #{self._errors}: {e}")

            # Dormir el tiempo restante del tick
            elapsed = time.monotonic() - frame_start
            sleep_time = self._interval - elapsed
            if sleep_time > 0:
                self._stop_event.wait(sleep_time)

        logger.info("[ArtNetEngine] Worker stopped")

    def _send_frame(self) -> None:
        """Construye y envía un frame Art-Net."""
        if not self._sock:
            return

        # Snapshot atómico del estado DMX
        dmx_data = self._dmx_state.snapshot()

        # Construir paquete
        packet = build_artnet_dmx_packet(
            dmx_data=dmx_data,
            universe=self._universe,
            sequence=self._sequence,
        )

        # Enviar UDP
        self._sock.sendto(packet, (self._target_ip, self._port))

        # Actualizar stats
        self._frames_sent += 1
        self._last_send_ts = time.time()

        # Rolling sequence (1-255, 0 está reservado)
        self._sequence = (self._sequence % 255) + 1

    @classmethod
    def from_json(cls, config_path: str, dmx_state: DmxState) -> "ArtNetEngine":
        """
        Crea ArtNetEngine desde artnet_config.json.

        Args:
            config_path: Ruta al archivo artnet_config.json
            dmx_state: Instancia de DmxState

        Returns:
            ArtNetEngine configurado
        """
        with open(config_path, "r") as f:
            config = json.load(f)

        return cls(
            dmx_state=dmx_state,
            target_ip=config.get("target_ip", "2.255.255.255"),
            port=config.get("port", ARTNET_PORT),
            universe=config.get("universe", 0),
            fps=config.get("fps", 40),
        )

    # ===== CONFIG EN CALIENTE =====

    def update_config(
        self,
        target_ip: Optional[str] = None,
        port: Optional[int] = None,
        universe: Optional[int] = None,
        fps: Optional[int] = None,
    ) -> None:
        """Actualiza configuración (aplica en el siguiente frame)."""
        if target_ip is not None:
            self._target_ip = target_ip
        if port is not None:
            self._port = port
        if universe is not None:
            self._universe = universe
        if fps is not None:
            self._fps = max(1, min(44, fps))
            self._interval = 1.0 / self._fps

        logger.info(
            f"[ArtNetEngine] Config updated: {self._target_ip}:{self._port} "
            f"universe={self._universe} fps={self._fps}"
        )

    # ===== STATS =====

    def get_stats(self) -> dict:
        """Retorna estadísticas del motor."""
        uptime = time.time() - self._start_ts if self._start_ts else 0
        actual_fps = self._frames_sent / uptime if uptime > 0 else 0

        return {
            "running": self._running,
            "target_ip": self._target_ip,
            "port": self._port,
            "universe": self._universe,
            "configured_fps": self._fps,
            "actual_fps": round(actual_fps, 1),
            "frames_sent": self._frames_sent,
            "errors": self._errors,
            "uptime_s": round(uptime, 1),
            "last_send_ts": self._last_send_ts,
        }

    @property
    def running(self) -> bool:
        return self._running

    def __del__(self):
        try:
            self.stop()
        except Exception:
            pass


__all__ = ["ArtNetEngine", "build_artnet_dmx_packet", "ARTNET_PORT"]

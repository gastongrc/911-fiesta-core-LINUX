# ============================================================================
# sacn_engine.py v1.0 - MOTOR sACN / E1.31 (EMISOR CONTINUO MULTICAST)
# ============================================================================
# Emite frames sACN (Streaming ACN / E1.31) continuamente via UDP multicast.
#
# Protocolo:
#   sACN E1.31 (port 5568), universo configurable
#   512 canales DMX por frame
#   Frecuencia configurable (default 40 fps)
#   Destino multicast estándar: 239.255.0.<universe>
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
import uuid
from typing import Optional

from .dmx_state import DmxState, DMX_CHANNELS

logger = logging.getLogger("SacnEngine")

# sACN constants
SACN_PORT = 5568
SACN_MULTICAST_BASE = "239.255.0."

# E1.31 protocol
E131_VECTOR_ROOT = 0x00000004
E131_VECTOR_FRAME = 0x00000002
E131_VECTOR_DMP = 0x02

# ACN packet identifiers
ACN_PACKET_IDENTIFIER = b"\x00\x10\x00\x00\x41\x53\x43\x2d\x45\x31\x2e\x31\x37\x00\x00\x00"

# Node identity
NODE_SOURCE_NAME = "911 Fiesta sACN Engine"


def _generate_cid() -> bytes:
    """Generate a 16-byte CID (Component Identifier) for this source."""
    return uuid.uuid4().bytes


def build_sacn_packet(
    dmx_data: bytearray,
    universe: int = 1,
    sequence: int = 0,
    priority: int = 100,
    cid: bytes = b"\x00" * 16,
    source_name: str = NODE_SOURCE_NAME,
) -> bytes:
    """
    Construye un paquete sACN E1.31 Data Packet.

    Estructura (Root Layer + Framing Layer + DMP Layer):
        Root Layer:
            Preamble Size (2 bytes): 0x0010
            Postamble Size (2 bytes): 0x0000
            ACN Packet Identifier (16 bytes)
            Flags + Length (2 bytes)
            Vector (4 bytes): 0x00000004
            CID (16 bytes)
        Framing Layer:
            Flags + Length (2 bytes)
            Vector (4 bytes): 0x00000002
            Source Name (64 bytes, null-terminated)
            Priority (1 byte)
            Synchronization Address (2 bytes): 0x0000
            Sequence Number (1 byte)
            Options (1 byte): 0x00
            Universe (2 bytes)
        DMP Layer:
            Flags + Length (2 bytes)
            Vector (1 byte): 0x02
            Address Type & Data Type (1 byte): 0xa1
            First Property Address (2 bytes): 0x0000
            Address Increment (2 bytes): 0x0001
            Property value count (2 bytes): 513 (start code + 512)
            Property values: Start code (1 byte: 0x00) + DMX data (512 bytes)

    Args:
        dmx_data: 512 bytes de datos DMX
        universe: Universo sACN (1-63999)
        sequence: Contador de secuencia (0-255)
        priority: Prioridad (0-200, default 100)
        cid: Component Identifier (16 bytes)
        source_name: Nombre del source (max 64 chars)

    Returns:
        bytes: Paquete sACN completo
    """
    # Property values: start code (0x00) + DMX data
    prop_values = bytearray(1) + dmx_data[:DMX_CHANNELS]  # 513 bytes
    prop_count = len(prop_values)  # 513

    # DMP Layer (length = 10 + prop_count = 523)
    dmp_length = 10 + prop_count
    dmp = bytearray()
    dmp.extend(struct.pack(">H", 0x7000 | dmp_length))  # Flags + Length
    dmp.append(E131_VECTOR_DMP)                           # Vector: 0x02
    dmp.append(0xA1)                                      # Address Type & Data Type
    dmp.extend(struct.pack(">H", 0x0000))                 # First Property Address
    dmp.extend(struct.pack(">H", 0x0001))                 # Address Increment
    dmp.extend(struct.pack(">H", prop_count))             # Property value count
    dmp.extend(prop_values)                               # Property values

    # Framing Layer (length = 77 + len(dmp))
    frame_length = 77 + len(dmp)
    frame = bytearray()
    frame.extend(struct.pack(">H", 0x7000 | frame_length))  # Flags + Length
    frame.extend(struct.pack(">I", E131_VECTOR_FRAME))       # Vector
    # Source Name (64 bytes, null-terminated)
    name_bytes = source_name.encode("utf-8", errors="replace")[:63]
    frame.extend(name_bytes.ljust(64, b"\x00"))
    frame.append(min(200, max(0, priority)))                 # Priority
    frame.extend(struct.pack(">H", 0x0000))                  # Sync Address
    frame.append(sequence & 0xFF)                            # Sequence
    frame.append(0x00)                                       # Options
    frame.extend(struct.pack(">H", universe))                # Universe
    frame.extend(dmp)

    # Root Layer (length = 22 + len(frame))
    root_length = 22 + len(frame)
    root = bytearray()
    root.extend(struct.pack(">H", 0x0010))                  # Preamble Size
    root.extend(struct.pack(">H", 0x0000))                  # Postamble Size
    root.extend(ACN_PACKET_IDENTIFIER)                       # ACN Packet Identifier
    root.extend(struct.pack(">H", 0x7000 | root_length))    # Flags + Length
    root.extend(struct.pack(">I", E131_VECTOR_ROOT))         # Vector
    root.extend(cid[:16].ljust(16, b"\x00"))                 # CID
    root.extend(frame)

    return bytes(root)


def multicast_ip_for_universe(universe: int) -> str:
    """
    Calcula la dirección multicast estándar para un universo sACN.

    E1.31 spec: 239.255.<universe_hi>.<universe_lo>
    Universe 1 → 239.255.0.1
    Universe 256 → 239.255.1.0

    Args:
        universe: Universo sACN (1-63999)

    Returns:
        Dirección multicast (ej: "239.255.0.1")
    """
    universe = max(1, min(63999, universe))
    hi = (universe >> 8) & 0xFF
    lo = universe & 0xFF
    return f"239.255.{hi}.{lo}"


class SacnEngine:
    """
    Motor sACN E1.31 v1.0 — emite frames DMX via UDP multicast.

    Thread daemon que lee snapshot() de DmxState y emite paquetes
    sACN a la frecuencia configurada.

    Uso:
        engine = SacnEngine(dmx_state, universe=1)
        engine.start()
        # ... dmx_state.fire(41) ...
        engine.stop()
    """

    def __init__(
        self,
        dmx_state: DmxState,
        universe: int = 1,
        fps: int = 40,
        multicast_ip: Optional[str] = None,
        port: int = SACN_PORT,
        priority: int = 100,
        source_name: str = NODE_SOURCE_NAME,
    ):
        self._dmx_state = dmx_state
        self._universe = max(1, min(63999, universe))
        self._fps = max(1, min(44, fps))
        self._interval = 1.0 / self._fps
        self._multicast_ip = multicast_ip or multicast_ip_for_universe(self._universe)
        self._port = port
        self._priority = max(0, min(200, priority))
        self._source_name = source_name

        # CID (persistent per instance)
        self._cid = _generate_cid()

        # Socket
        self._sock: Optional[socket.socket] = None

        # Thread control
        self._send_thread: Optional[threading.Thread] = None
        self._running = False

        # Sequence counter (0-255 rolling)
        self._sequence = 0

        # Stats
        self._frames_sent = 0
        self._errors = 0
        self._last_send_ts = 0.0
        self._start_ts = 0.0
        self._last_diag_ts = 0.0

        logger.info(
            f"[SacnEngine] v1.0 Inicializado: multicast={self._multicast_ip}:{port} "
            f"universe={self._universe} fps={fps} priority={self._priority}"
        )

    def _setup_socket(self) -> None:
        """Crea socket UDP multicast para envío sACN."""
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Set multicast TTL (1 = local network only)
        self._sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)

    def start(self) -> bool:
        """
        Inicia el motor sACN (sender thread).

        Returns:
            True si inició correctamente
        """
        if self._running:
            return True

        self._setup_socket()
        self._running = True
        self._start_ts = time.time()

        self._send_thread = threading.Thread(
            target=self._send_loop,
            name="sACN-Sender",
            daemon=True,
        )
        self._send_thread.start()

        logger.info(
            f"[SacnEngine] Started: {self._multicast_ip}:{self._port} "
            f"universe={self._universe} @ {self._fps}fps "
            f"priority={self._priority}"
        )
        print(
            f"[SacnEngine] RUNNING → {self._multicast_ip}:{self._port} "
            f"universe={self._universe} @ {self._fps}fps "
            f"priority={self._priority}"
        )
        return True

    def stop(self) -> None:
        """Detiene el motor sACN."""
        if not self._running:
            return

        self._running = False

        if self._send_thread and self._send_thread.is_alive():
            self._send_thread.join(timeout=2.0)

        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

        logger.info(
            f"[SacnEngine] Stopped: {self._frames_sent} frames, "
            f"{self._errors} errors"
        )
        print(
            f"[SacnEngine] STOPPED ({self._frames_sent} frames sent)"
        )

    # ===== SENDER LOOP =====

    def _send_loop(self) -> None:
        """Loop de emisión: envía frames sACN a la frecuencia configurada."""
        logger.info(f"[SacnEngine] Sender started: interval={self._interval*1000:.1f}ms")

        while self._running:
            frame_start = time.time()

            try:
                self._send_frame()
            except Exception as e:
                self._errors += 1
                if self._errors <= 5 or self._errors % 100 == 0:
                    logger.error(f"[SacnEngine] Send error #{self._errors}: {e}")

            elapsed = time.time() - frame_start
            sleep_time = self._interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        logger.info("[SacnEngine] Sender stopped")

    def _send_frame(self) -> None:
        """Construye y envía un frame sACN."""
        if not self._sock:
            return

        # Snapshot atómico del estado DMX
        dmx_data = self._dmx_state.snapshot()

        # Construir paquete
        packet = build_sacn_packet(
            dmx_data=dmx_data,
            universe=self._universe,
            sequence=self._sequence,
            priority=self._priority,
            cid=self._cid,
            source_name=self._source_name,
        )

        # Enviar UDP multicast
        self._sock.sendto(packet, (self._multicast_ip, self._port))

        # Actualizar stats
        self._frames_sent += 1
        self._last_send_ts = time.time()

        # Rolling sequence (0-255)
        self._sequence = (self._sequence + 1) & 0xFF

        # Diagnostic: log non-zero channels every ~1 second
        now = time.time()
        if now - self._last_diag_ts >= 1.0:
            self._last_diag_ts = now
            nonzero = [(i + 1, dmx_data[i]) for i in range(DMX_CHANNELS) if dmx_data[i] > 0]
            if nonzero:
                ch_list = ", ".join(f"ch{ch}={val}" for ch, val in nonzero[:20])
                print(f"[sACN DIAG] frame#{self._frames_sent} → {len(nonzero)} nonzero channels: [{ch_list}]")
            else:
                print(f"[sACN DIAG] frame#{self._frames_sent} → ALL ZEROS (no active cues)")

    # ===== FACTORY =====

    @classmethod
    def from_config(cls, config: dict, dmx_state: DmxState) -> "SacnEngine":
        """
        Crea SacnEngine desde un dict de configuración.

        Args:
            config: Dict con keys: universe, fps, multicast_ip, port, priority
            dmx_state: Instancia de DmxState

        Returns:
            SacnEngine configurado
        """
        return cls(
            dmx_state=dmx_state,
            universe=config.get("universe", 1),
            fps=config.get("fps", 40),
            multicast_ip=config.get("multicast_ip"),
            port=config.get("port", SACN_PORT),
            priority=config.get("priority", 100),
            source_name=config.get("source_name", NODE_SOURCE_NAME),
        )

    # ===== CONFIG EN CALIENTE =====

    def update_config(
        self,
        universe: Optional[int] = None,
        fps: Optional[int] = None,
        multicast_ip: Optional[str] = None,
        port: Optional[int] = None,
        priority: Optional[int] = None,
    ) -> None:
        """Actualiza configuración (aplica en el siguiente frame)."""
        if universe is not None:
            self._universe = max(1, min(63999, universe))
            if multicast_ip is None:
                self._multicast_ip = multicast_ip_for_universe(self._universe)
        if fps is not None:
            self._fps = max(1, min(44, fps))
            self._interval = 1.0 / self._fps
        if multicast_ip is not None:
            self._multicast_ip = multicast_ip
        if port is not None:
            self._port = port
        if priority is not None:
            self._priority = max(0, min(200, priority))

        logger.info(
            f"[SacnEngine] Config updated: {self._multicast_ip}:{self._port} "
            f"universe={self._universe} fps={self._fps} priority={self._priority}"
        )

    # ===== STATS =====

    def get_stats(self) -> dict:
        """Retorna estadísticas del motor."""
        uptime = time.time() - self._start_ts if self._start_ts else 0
        actual_fps = self._frames_sent / uptime if uptime > 0 else 0

        return {
            "running": self._running,
            "multicast_ip": self._multicast_ip,
            "port": self._port,
            "universe": self._universe,
            "priority": self._priority,
            "configured_fps": self._fps,
            "actual_fps": round(actual_fps, 1),
            "frames_sent": self._frames_sent,
            "errors": self._errors,
            "source_name": self._source_name,
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


__all__ = [
    "SacnEngine",
    "build_sacn_packet",
    "multicast_ip_for_universe",
    "SACN_PORT",
]

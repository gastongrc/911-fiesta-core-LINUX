# ============================================================================
# artnet_engine.py v2.0 - MOTOR ART-NET (EMISOR CONTINUO + ARTPOLL)
# ============================================================================
# Emite frames Art-Net OpDmx continuamente via UDP.
# Responde ArtPoll con ArtPollReply para ser visible como nodo.
#
# Protocolo:
#   Art-Net 4 (port 6454), paquete OpDmx (0x5000)
#   512 canales DMX por frame
#   Frecuencia configurable (default 40 fps)
#
# v2.0:
#   - Fix timing loop: time.sleep() en lugar de Event.wait()
#   - ArtPoll listener en thread separado
#   - ArtPollReply con datos del nodo
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
from typing import Optional, Tuple

from .dmx_state import DmxState, DMX_CHANNELS

logger = logging.getLogger("ArtNetEngine")

# Art-Net constants
ARTNET_HEADER = b"Art-Net\x00"
ARTNET_OPCODE_DMX = 0x5000
ARTNET_OPCODE_POLL = 0x2000
ARTNET_OPCODE_POLL_REPLY = 0x2100
ARTNET_PROTOCOL_VERSION = 14
ARTNET_PORT = 6454

# Node identity
NODE_SHORT_NAME = "911Fiesta"
NODE_LONG_NAME = "911 Fiesta DMX Engine"
NODE_OEM = 0x0000        # Generic OEM
NODE_ESTA = 0x0000       # No ESTA manufacturer code


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


def build_artpoll_reply(
    ip_address: str,
    port: int,
    universe: int,
    short_name: str = NODE_SHORT_NAME,
    long_name: str = NODE_LONG_NAME,
) -> bytes:
    """
    Construye un paquete ArtPollReply (239 bytes).

    Spec Art-Net 4, Table 3 — ArtPollReply.

    Args:
        ip_address: IP del nodo (ej: "192.168.1.100")
        port: Puerto Art-Net (6454)
        universe: Universo activo
        short_name: Nombre corto (max 18 chars)
        long_name: Nombre largo (max 64 chars)

    Returns:
        bytes: Paquete ArtPollReply
    """
    packet = bytearray()

    # Header (8 bytes)
    packet.extend(ARTNET_HEADER)

    # OpCode ArtPollReply (2 bytes, little-endian)
    packet.extend(struct.pack("<H", ARTNET_OPCODE_POLL_REPLY))

    # IP Address (4 bytes) — nodo IP
    ip_parts = ip_address.split(".")
    for part in ip_parts:
        packet.append(int(part) & 0xFF)

    # Port (2 bytes, little-endian)
    packet.extend(struct.pack("<H", port))

    # Version Info Hi/Lo (2 bytes)
    packet.extend(struct.pack(">H", 0x0200))  # v2.0

    # NetSwitch (1 byte) — bits 14-8 of universe
    packet.append((universe >> 8) & 0x7F)

    # SubSwitch (1 byte) — bits 7-4 of universe
    packet.append((universe >> 4) & 0x0F)

    # OEM Hi/Lo (2 bytes)
    packet.extend(struct.pack(">H", NODE_OEM))

    # Ubea Version (1 byte)
    packet.append(0)

    # Status1 (1 byte) — indicator state normal, port-address programming authority
    packet.append(0xD0)  # RDM capable, indicator normal, port addr set by front panel

    # ESTA Manufacturer Lo/Hi (2 bytes, little-endian)
    packet.extend(struct.pack("<H", NODE_ESTA))

    # Short Name (18 bytes, null-terminated)
    short_bytes = short_name.encode("ascii", errors="replace")[:17]
    packet.extend(short_bytes.ljust(18, b"\x00"))

    # Long Name (64 bytes, null-terminated)
    long_bytes = long_name.encode("ascii", errors="replace")[:63]
    packet.extend(long_bytes.ljust(64, b"\x00"))

    # Node Report (64 bytes, null-terminated)
    report = "#0001 [0001] 911Fiesta OK"
    report_bytes = report.encode("ascii", errors="replace")[:63]
    packet.extend(report_bytes.ljust(64, b"\x00"))

    # NumPorts Hi/Lo (2 bytes) — 1 output port
    packet.extend(struct.pack(">H", 1))

    # Port Types (4 bytes) — port 0 = DMX512 output
    packet.append(0x80)  # Port 0: output, DMX512
    packet.append(0x00)  # Port 1: unused
    packet.append(0x00)  # Port 2: unused
    packet.append(0x00)  # Port 3: unused

    # GoodInput (4 bytes)
    packet.extend(b"\x00" * 4)

    # GoodOutputA (4 bytes) — port 0 transmitting
    packet.append(0x80)  # Port 0: data is being transmitted
    packet.append(0x00)
    packet.append(0x00)
    packet.append(0x00)

    # SwIn (4 bytes) — input universe per port (not used)
    packet.extend(b"\x00" * 4)

    # SwOut (4 bytes) — output universe per port
    packet.append(universe & 0x0F)  # Port 0: low nibble of universe
    packet.append(0x00)
    packet.append(0x00)
    packet.append(0x00)

    # AcnPriority (1 byte) — sACN priority, not used
    packet.append(0x00)

    # SwMacro (1 byte)
    packet.append(0x00)

    # SwRemote (1 byte)
    packet.append(0x00)

    # Spare (3 bytes)
    packet.extend(b"\x00" * 3)

    # Style (1 byte) — StNode (0x00)
    packet.append(0x00)

    # MAC Address (6 bytes) — use zeros (optional)
    packet.extend(b"\x00" * 6)

    # BindIp (4 bytes) — same as node IP
    for part in ip_parts:
        packet.append(int(part) & 0xFF)

    # BindIndex (1 byte)
    packet.append(1)

    # Status2 (1 byte) — supports 15-bit port-address, Art-Net 3/4
    packet.append(0x08)

    # GoodOutputB (4 bytes)
    packet.extend(b"\x00" * 4)

    # Status3 (1 byte)
    packet.append(0x00)

    # DefaultRespUID (6 bytes)
    packet.extend(b"\x00" * 6)

    # Pad to 239 bytes minimum
    if len(packet) < 239:
        packet.extend(b"\x00" * (239 - len(packet)))

    return bytes(packet)


def _get_local_ip() -> str:
    """Obtiene IP local del nodo (best effort)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "0.0.0.0"


def _is_artpoll(data: bytes) -> bool:
    """Verifica si un paquete es ArtPoll (OpCode 0x2000)."""
    if len(data) < 12:
        return False
    if data[0:8] != ARTNET_HEADER:
        return False
    opcode = struct.unpack_from("<H", data, 8)[0]
    return opcode == ARTNET_OPCODE_POLL


class ArtNetEngine:
    """
    Motor Art-Net v2.0 — emite frames DMX + responde ArtPoll.

    Dos threads daemon:
    1. Sender: emite OpDmx a la frecuencia configurada (40fps default)
    2. Listener: recibe ArtPoll y responde ArtPollReply

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
        node_name: str = NODE_SHORT_NAME,
        node_long_name: str = NODE_LONG_NAME,
    ):
        self._dmx_state = dmx_state
        self._target_ip = target_ip
        self._port = port
        self._universe = universe
        self._fps = max(1, min(44, fps))
        self._interval = 1.0 / self._fps
        self._node_name = node_name
        self._node_long_name = node_long_name

        # Sockets
        self._send_sock: Optional[socket.socket] = None
        self._recv_sock: Optional[socket.socket] = None

        # Thread control
        self._send_thread: Optional[threading.Thread] = None
        self._recv_thread: Optional[threading.Thread] = None
        self._running = False

        # Sequence counter (1-255 rolling, 0 = disabled in spec)
        self._sequence = 1

        # Stats
        self._frames_sent = 0
        self._errors = 0
        self._polls_received = 0
        self._replies_sent = 0
        self._last_send_ts = 0.0
        self._start_ts = 0.0
        self._last_diag_ts = 0.0  # Diagnostic logging throttle

        # Local IP (resolved on start)
        self._local_ip = "0.0.0.0"

        logger.info(
            f"[ArtNetEngine] v2.0 Inicializado: target={target_ip}:{port} "
            f"universe={universe} fps={fps}"
        )

    def _setup_send_socket(self) -> None:
        """Crea socket UDP para envío con soporte broadcast."""
        self._send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def _setup_recv_socket(self) -> None:
        """Crea socket UDP para recepción de ArtPoll en puerto 6454."""
        self._recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except (AttributeError, OSError):
            pass  # SO_REUSEPORT not available on all platforms
        self._recv_sock.bind(("0.0.0.0", self._port))
        self._recv_sock.settimeout(1.0)  # 1s timeout for clean shutdown

    def start(self) -> bool:
        """
        Inicia el motor Art-Net (sender + listener threads).

        Returns:
            True si inició correctamente
        """
        if self._running:
            return True

        # Resolve local IP
        self._local_ip = _get_local_ip()

        # Setup sockets
        self._setup_send_socket()
        try:
            self._setup_recv_socket()
        except OSError as e:
            logger.warning(f"[ArtNetEngine] Could not bind listener on :{self._port}: {e}")
            self._recv_sock = None

        self._running = True
        self._start_ts = time.time()

        # Sender thread — emite OpDmx a fps configurados
        self._send_thread = threading.Thread(
            target=self._send_loop,
            name="ArtNet-Sender",
            daemon=True,
        )
        self._send_thread.start()

        # Listener thread — responde ArtPoll
        if self._recv_sock:
            self._recv_thread = threading.Thread(
                target=self._recv_loop,
                name="ArtNet-Listener",
                daemon=True,
            )
            self._recv_thread.start()

        logger.info(
            f"[ArtNetEngine] Started: {self._target_ip}:{self._port} "
            f"universe={self._universe} @ {self._fps}fps "
            f"local_ip={self._local_ip} "
            f"listener={'ON' if self._recv_sock else 'OFF'}"
        )
        print(
            f"[ArtNetEngine] RUNNING → {self._target_ip}:{self._port} "
            f"universe={self._universe} @ {self._fps}fps "
            f"node={self._node_name} ip={self._local_ip}"
        )
        return True

    def stop(self) -> None:
        """Detiene el motor Art-Net."""
        if not self._running:
            return

        self._running = False

        # Wait for threads
        if self._send_thread and self._send_thread.is_alive():
            self._send_thread.join(timeout=2.0)
        if self._recv_thread and self._recv_thread.is_alive():
            self._recv_thread.join(timeout=2.0)

        # Close sockets
        for sock in (self._send_sock, self._recv_sock):
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass
        self._send_sock = None
        self._recv_sock = None

        logger.info(
            f"[ArtNetEngine] Stopped: {self._frames_sent} frames, "
            f"{self._polls_received} polls, {self._errors} errors"
        )
        print(
            f"[ArtNetEngine] STOPPED ({self._frames_sent} frames, "
            f"{self._polls_received} polls answered)"
        )

    # ===== SENDER LOOP (OpDmx @ configured fps) =====

    def _send_loop(self) -> None:
        """
        Loop de emisión: envía frames Art-Net a la frecuencia configurada.

        Usa time.sleep() para timing preciso.
        """
        logger.info(f"[ArtNetEngine] Sender started: interval={self._interval*1000:.1f}ms")

        while self._running:
            frame_start = time.time()

            try:
                self._send_frame()
            except Exception as e:
                self._errors += 1
                if self._errors <= 5 or self._errors % 100 == 0:
                    logger.error(f"[ArtNetEngine] Send error #{self._errors}: {e}")

            # Timing: sleep el tiempo restante del tick
            elapsed = time.time() - frame_start
            sleep_time = self._interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        logger.info("[ArtNetEngine] Sender stopped")

    def _send_frame(self) -> None:
        """Construye y envía un frame Art-Net OpDmx."""
        if not self._send_sock:
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
        self._send_sock.sendto(packet, (self._target_ip, self._port))

        # Actualizar stats
        self._frames_sent += 1
        self._last_send_ts = time.time()

        # Rolling sequence (1-255, 0 está reservado en spec)
        self._sequence = (self._sequence % 255) + 1

        # Diagnostic: log non-zero channels every ~1 second
        now = time.time()
        if now - self._last_diag_ts >= 1.0:
            self._last_diag_ts = now
            nonzero = [(i + 1, dmx_data[i]) for i in range(DMX_CHANNELS) if dmx_data[i] > 0]
            if nonzero:
                ch_list = ", ".join(f"ch{ch}={val}" for ch, val in nonzero[:20])
                print(f"[ArtNet DIAG] frame#{self._frames_sent} → {len(nonzero)} nonzero channels: [{ch_list}]")
            else:
                print(f"[ArtNet DIAG] frame#{self._frames_sent} → ALL ZEROS (no active cues)")

    # ===== RECEIVER LOOP (ArtPoll listener) =====

    def _recv_loop(self) -> None:
        """
        Loop de recepción: escucha ArtPoll y responde ArtPollReply.

        Socket con timeout 1s para permitir shutdown limpio.
        """
        logger.info("[ArtNetEngine] Listener started on port 6454")

        while self._running:
            try:
                data, addr = self._recv_sock.recvfrom(1024)
            except socket.timeout:
                continue
            except OSError:
                if self._running:
                    self._errors += 1
                break

            if _is_artpoll(data):
                self._handle_artpoll(addr)

        logger.info("[ArtNetEngine] Listener stopped")

    def _handle_artpoll(self, sender_addr: Tuple[str, int]) -> None:
        """
        Responde a un ArtPoll con ArtPollReply.

        Args:
            sender_addr: (ip, port) del solicitante
        """
        self._polls_received += 1

        # Construir reply
        reply = build_artpoll_reply(
            ip_address=self._local_ip,
            port=self._port,
            universe=self._universe,
            short_name=self._node_name,
            long_name=self._node_long_name,
        )

        # Responder al sender (unicast)
        try:
            if self._send_sock:
                self._send_sock.sendto(reply, sender_addr)
                self._replies_sent += 1
                logger.info(
                    f"[ArtNetEngine] ArtPollReply → {sender_addr[0]}:{sender_addr[1]} "
                    f"(node={self._node_name} universe={self._universe})"
                )
        except Exception as e:
            self._errors += 1
            logger.error(f"[ArtNetEngine] ArtPollReply error: {e}")

    # ===== FACTORY =====

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
            node_name=config.get("node_name", NODE_SHORT_NAME),
            node_long_name=config.get("node_long_name", NODE_LONG_NAME),
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
            "polls_received": self._polls_received,
            "replies_sent": self._replies_sent,
            "local_ip": self._local_ip,
            "node_name": self._node_name,
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
    "ArtNetEngine",
    "build_artnet_dmx_packet",
    "build_artpoll_reply",
    "ARTNET_PORT",
]

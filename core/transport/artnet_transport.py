# ============================================================================
# artnet_transport.py v1.0 - ArtNet DMX TRANSPORT
# ============================================================================
# ArtNet cue transport for 911 Fiesta.
#
# Sends cue triggers via ArtNet (DMX512 over UDP).
# Maintains a persistent 512-channel DMX buffer.
# Transmits the full universe continuously at configurable refresh rate.
#
# Trigger strategy: latch mode
#   FIRE: dmx_data[cue_id - 1] = 255
#   KILL: dmx_data[cue_id - 1] = 0
#
# No user_number_offset applied — DMX channel = cue_id directly.
# Titan maps DMX input channels to playback executors internally.
#
# Interface matches TitanTransport:
#   send_fire(cue_id) -> bool
#   send_kill(cue_id) -> bool
#   ping() -> bool
#   update_config(**kwargs) -> None
#   get_stats() -> Dict
#   close() -> None
# ============================================================================

from __future__ import annotations

import socket
import struct
import time
import logging
import threading
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass, field

logger = logging.getLogger("ArtNetTransport")

# ArtNet constants
ARTNET_PORT = 6454
ARTNET_HEADER = b"Art-Net\x00"
ARTNET_OPCODE_DMX = 0x5000
ARTNET_PROTOCOL_VERSION = 14
ARTNET_DMX_CHANNELS = 512


@dataclass
class ArtNetConfig:
    """Configuration for ArtNet transport."""
    target_ip: str = "255.255.255.255"  # broadcast default
    artnet_net: int = 0                  # 0-127
    artnet_subnet: int = 0              # 0-15
    artnet_universe: int = 0            # 0-15
    broadcast: bool = True              # True=broadcast, False=unicast
    refresh_rate_hz: int = 40           # Continuous transmit rate


@dataclass
class ArtNetStats:
    """Statistics for ArtNet transport."""
    fires_sent: int = 0
    fires_ok: int = 0
    fires_failed: int = 0
    kills_sent: int = 0
    kills_ok: int = 0
    kills_failed: int = 0
    retries_total: int = 0
    last_latency_ms: float = 0.0
    last_error: Optional[str] = None
    last_success_ts: float = 0.0
    last_error_ts: float = 0.0
    packets_sent: int = 0
    sequence_number: int = 0


class ArtNetTransport:
    """
    ArtNet DMX Transport v1.0

    Sends cue triggers via ArtNet DMX512 over UDP.
    Maintains a persistent 512-channel DMX buffer and transmits
    the full universe continuously at the configured refresh rate.

    Trigger model (latch):
        FIRE cue_id -> dmx_data[cue_id - 1] = 255
        KILL cue_id -> dmx_data[cue_id - 1] = 0

    No offset applied. DMX channel = cue_id.
    """

    def __init__(
        self,
        config: Optional[ArtNetConfig] = None,
        on_success: Optional[Callable[[str, int], None]] = None,
        on_failure: Optional[Callable[[str, int, str], None]] = None,
    ):
        self.config = config or ArtNetConfig()
        self.stats = ArtNetStats()
        self._on_success = on_success
        self._on_failure = on_failure

        # Persistent DMX buffer — 512 channels, all zero
        self._dmx_data = bytearray(ARTNET_DMX_CHANNELS)
        self._dmx_lock = threading.Lock()

        # ArtNet sequence counter (1-255, wraps, 0 = disable sequencing)
        self._sequence = 1

        # UDP socket
        self._socket: Optional[socket.socket] = None

        # Continuous transmit thread
        self._tx_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Initialize
        self._setup_socket()
        self._start_tx_thread()

        logger.info(
            f"[ArtNetTransport] Initialized | "
            f"target={self.config.target_ip} | "
            f"mode={'broadcast' if self.config.broadcast else 'unicast'} | "
            f"net={self.config.artnet_net} sub={self.config.artnet_subnet} "
            f"univ={self.config.artnet_universe} | "
            f"refresh={self.config.refresh_rate_hz}Hz"
        )

    # ===== SOCKET SETUP =====

    def _setup_socket(self):
        """Create and configure UDP socket for ArtNet."""
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if self.config.broadcast:
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        # Non-blocking not needed — sendto is fast for UDP
        logger.debug("[ArtNetTransport] UDP socket created")

    # ===== CONTINUOUS TRANSMIT THREAD =====

    def _start_tx_thread(self):
        """Start the continuous universe transmission thread."""
        if self._tx_thread and self._tx_thread.is_alive():
            return

        self._stop_event.clear()
        self._tx_thread = threading.Thread(
            target=self._tx_loop,
            name="ArtNet-TX",
            daemon=True,
        )
        self._tx_thread.start()
        logger.debug("[ArtNetTransport] TX thread started")

    def _tx_loop(self):
        """Continuously transmit the DMX universe at the configured rate."""
        interval = 1.0 / max(1, self.config.refresh_rate_hz)

        while not self._stop_event.is_set():
            try:
                self._send_universe()
            except Exception as e:
                logger.error(f"[ArtNetTransport] TX error: {e}")
                self.stats.last_error = str(e)
                self.stats.last_error_ts = time.time()

            # Sleep for the remainder of the interval
            self._stop_event.wait(timeout=interval)

        logger.debug("[ArtNetTransport] TX thread stopped")

    # ===== ArtNet PACKET CONSTRUCTION =====

    def _build_artnet_dmx_packet(self) -> bytes:
        """
        Build an Art-Net DMX (ArtDmx / OpOutput) packet.

        Packet structure (530 bytes for 512 channels):
          Bytes  0-7:   "Art-Net\0" (8 bytes)
          Bytes  8-9:   OpCode 0x5000 (little-endian)
          Bytes 10-11:  Protocol version 14 (big-endian)
          Byte  12:     Sequence (1-255, 0=disable)
          Byte  13:     Physical port (0)
          Bytes 14-15:  Universe (SubUni + Net, little-endian)
          Bytes 16-17:  Length (big-endian, 512)
          Bytes 18-529: DMX data (512 bytes)
        """
        # Compute sub-universe and net bytes
        # SubUni = (subnet << 4) | universe
        # Net = net
        sub_uni = ((self.config.artnet_subnet & 0x0F) << 4) | (self.config.artnet_universe & 0x0F)
        net_byte = self.config.artnet_net & 0x7F

        with self._dmx_lock:
            dmx_snapshot = bytes(self._dmx_data)

        packet = bytearray()
        # Header
        packet.extend(ARTNET_HEADER)                              # 8 bytes
        packet.extend(struct.pack("<H", ARTNET_OPCODE_DMX))       # 2 bytes LE
        packet.extend(struct.pack(">H", ARTNET_PROTOCOL_VERSION)) # 2 bytes BE
        packet.append(self._sequence & 0xFF)                      # 1 byte
        packet.append(0)                                          # Physical port
        packet.append(sub_uni)                                    # SubUni (LE low)
        packet.append(net_byte)                                   # Net (LE high)
        packet.extend(struct.pack(">H", ARTNET_DMX_CHANNELS))    # 2 bytes BE
        packet.extend(dmx_snapshot)                               # 512 bytes

        # Advance sequence (1-255, skip 0)
        self._sequence = (self._sequence % 255) + 1

        return bytes(packet)

    def _send_universe(self):
        """Send the full DMX universe as an ArtNet packet."""
        if not self._socket:
            return

        packet = self._build_artnet_dmx_packet()

        try:
            self._socket.sendto(packet, (self.config.target_ip, ARTNET_PORT))
            self.stats.packets_sent += 1
            self.stats.sequence_number = self._sequence
        except Exception as e:
            logger.warning(f"[ArtNetTransport] sendto failed: {e}")
            self.stats.last_error = str(e)
            self.stats.last_error_ts = time.time()

    # ===== PUBLIC INTERFACE (matches TitanTransport) =====

    def send_fire(self, cue_id: int) -> bool:
        """
        Fire a cue via ArtNet: set DMX channel to 255.

        Args:
            cue_id: Logical cue ID (1-512). DMX channel = cue_id.

        Returns:
            bool: True (ArtNet is fire-and-forget, state updated immediately)
        """
        if cue_id < 1 or cue_id > ARTNET_DMX_CHANNELS:
            self.stats.fires_failed += 1
            error = f"cue_id {cue_id} out of range (1-{ARTNET_DMX_CHANNELS})"
            logger.warning(f"[ArtNetTransport] FIRE rejected: {error}")
            if self._on_failure:
                try:
                    self._on_failure("FIRE", cue_id, error)
                except Exception:
                    pass
            return False

        start_ts = time.time()
        channel_index = cue_id - 1

        with self._dmx_lock:
            self._dmx_data[channel_index] = 255

        elapsed_ms = (time.time() - start_ts) * 1000
        self.stats.fires_sent += 1
        self.stats.fires_ok += 1
        self.stats.last_latency_ms = elapsed_ms
        self.stats.last_success_ts = time.time()

        logger.debug(f"[ArtNetTransport] FIRE C{cue_id} -> DMX CH{cue_id}=255 ({elapsed_ms:.1f}ms)")

        if self._on_success:
            try:
                self._on_success("FIRE", cue_id)
            except Exception:
                pass

        return True

    def send_kill(self, cue_id: int) -> bool:
        """
        Kill a cue via ArtNet: set DMX channel to 0.

        Args:
            cue_id: Logical cue ID (1-512). DMX channel = cue_id.

        Returns:
            bool: True (ArtNet is fire-and-forget, state updated immediately)
        """
        if cue_id < 1 or cue_id > ARTNET_DMX_CHANNELS:
            self.stats.kills_failed += 1
            error = f"cue_id {cue_id} out of range (1-{ARTNET_DMX_CHANNELS})"
            logger.warning(f"[ArtNetTransport] KILL rejected: {error}")
            if self._on_failure:
                try:
                    self._on_failure("KILL", cue_id, error)
                except Exception:
                    pass
            return False

        start_ts = time.time()
        channel_index = cue_id - 1

        with self._dmx_lock:
            self._dmx_data[channel_index] = 0

        elapsed_ms = (time.time() - start_ts) * 1000
        self.stats.kills_sent += 1
        self.stats.kills_ok += 1
        self.stats.last_latency_ms = elapsed_ms
        self.stats.last_success_ts = time.time()

        logger.debug(f"[ArtNetTransport] KILL C{cue_id} -> DMX CH{cue_id}=0 ({elapsed_ms:.1f}ms)")

        if self._on_success:
            try:
                self._on_success("KILL", cue_id)
            except Exception:
                pass

        return True

    def ping(self) -> bool:
        """
        ArtNet has no ACK mechanism.
        Returns True if the socket and TX thread are operational.
        """
        return (
            self._socket is not None
            and self._tx_thread is not None
            and self._tx_thread.is_alive()
        )

    def get_active_playbacks(self) -> Optional[Dict[str, Any]]:
        """
        ArtNet does not support querying active playbacks.
        Returns None (TitanStateSync should be disabled in ArtNet mode).
        """
        return None

    def update_config(
        self,
        console_ip: Optional[str] = None,
        console_port: Optional[int] = None,
        transport: Optional[str] = None,
        user_number_offset: Optional[int] = None,
        **kwargs,
    ):
        """
        Update ArtNet configuration.

        Accepts the same kwargs as TitanTransport.update_config() for
        compatibility, but only applies ArtNet-relevant parameters.
        Additional ArtNet-specific kwargs:
            target_ip, artnet_net, artnet_subnet, artnet_universe,
            broadcast, refresh_rate_hz
        """
        changed = False

        # ArtNet-specific params
        if "target_ip" in kwargs:
            self.config.target_ip = kwargs["target_ip"]
            changed = True
        if "artnet_net" in kwargs:
            self.config.artnet_net = int(kwargs["artnet_net"]) & 0x7F
            changed = True
        if "artnet_subnet" in kwargs:
            self.config.artnet_subnet = int(kwargs["artnet_subnet"]) & 0x0F
            changed = True
        if "artnet_universe" in kwargs:
            self.config.artnet_universe = int(kwargs["artnet_universe"]) & 0x0F
            changed = True
        if "broadcast" in kwargs:
            self.config.broadcast = bool(kwargs["broadcast"])
            changed = True
        if "refresh_rate_hz" in kwargs:
            self.config.refresh_rate_hz = max(1, min(44, int(kwargs["refresh_rate_hz"])))
            changed = True

        # TitanTransport-compatible params (partial mapping)
        if console_ip and not kwargs.get("target_ip"):
            # Use console_ip as unicast target if no explicit target_ip
            self.config.target_ip = console_ip
            changed = True

        if changed:
            self._setup_socket()
            logger.info(
                f"[ArtNetTransport] Config updated | "
                f"target={self.config.target_ip} | "
                f"mode={'broadcast' if self.config.broadcast else 'unicast'} | "
                f"net={self.config.artnet_net} sub={self.config.artnet_subnet} "
                f"univ={self.config.artnet_universe}"
            )

    def get_stats(self) -> Dict[str, Any]:
        """Return transport statistics."""
        return {
            "transport_type": "artnet",
            "fires_sent": self.stats.fires_sent,
            "fires_ok": self.stats.fires_ok,
            "fires_failed": self.stats.fires_failed,
            "kills_sent": self.stats.kills_sent,
            "kills_ok": self.stats.kills_ok,
            "kills_failed": self.stats.kills_failed,
            "retries_total": self.stats.retries_total,
            "last_latency_ms": self.stats.last_latency_ms,
            "last_error": self.stats.last_error,
            "last_success_ts": self.stats.last_success_ts,
            "last_error_ts": self.stats.last_error_ts,
            "packets_sent": self.stats.packets_sent,
            "sequence_number": self.stats.sequence_number,
            "target_ip": self.config.target_ip,
            "broadcast": self.config.broadcast,
            "artnet_net": self.config.artnet_net,
            "artnet_subnet": self.config.artnet_subnet,
            "artnet_universe": self.config.artnet_universe,
            "refresh_rate_hz": self.config.refresh_rate_hz,
            "success_rate_fire": (
                self.stats.fires_ok / self.stats.fires_sent * 100
                if self.stats.fires_sent > 0 else 100.0
            ),
            "success_rate_kill": (
                self.stats.kills_ok / self.stats.kills_sent * 100
                if self.stats.kills_sent > 0 else 100.0
            ),
        }

    def reset_stats(self):
        """Reset statistics."""
        self.stats = ArtNetStats()

    def close(self):
        """Shutdown ArtNet transport: stop TX thread and close socket."""
        logger.info("[ArtNetTransport] Closing...")

        # Stop TX thread
        self._stop_event.set()
        if self._tx_thread and self._tx_thread.is_alive():
            self._tx_thread.join(timeout=2.0)
        self._tx_thread = None

        # Close socket
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None

        logger.info("[ArtNetTransport] Closed")

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


__all__ = ["ArtNetTransport", "ArtNetConfig", "ArtNetStats"]

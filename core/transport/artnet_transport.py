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
ARTNET_OPCODE_POLL = 0x2000
ARTNET_OPCODE_POLL_REPLY = 0x2100
ARTNET_PROTOCOL_VERSION = 14
ARTNET_DMX_CHANNELS = 512
ARTNET_POLL_REPLY_LENGTH = 239
ARTNET_STYLE_NODE = 0x00


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
    polls_received: int = 0
    poll_replies_sent: int = 0


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

        # Single shared UDP socket (TX + RX on port 6454)
        self._socket: Optional[socket.socket] = None

        # Threads
        self._tx_thread: Optional[threading.Thread] = None
        self._rx_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Local IP cache for ArtPollReply
        self._local_ip: Optional[str] = None

        # Initialize
        self._setup_socket()
        self._start_tx_thread()
        self._start_poll_listener()

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
        """
        Create a single shared UDP socket bound to 0.0.0.0:6454.

        This socket is used by both:
          - TX thread: sendto() for ArtDMX packets
          - RX thread: recvfrom() for ArtPoll listening + sendto() for ArtPollReply
        """
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._socket.settimeout(1.0)  # Allow periodic stop_event checks in RX loop
        self._socket.bind(("0.0.0.0", ARTNET_PORT))
        logger.debug(f"[ArtNet] Socket bound to 0.0.0.0:{ARTNET_PORT}")

    # ===== ArtPoll LISTENER =====

    def _start_poll_listener(self):
        """Start the ArtPoll listener thread."""
        if self._socket is None:
            logger.warning("[ArtNet] Poll listener not started — socket unavailable")
            return
        if self._rx_thread and self._rx_thread.is_alive():
            return

        self._rx_thread = threading.Thread(
            target=self._rx_loop,
            name="ArtNet-RX",
            daemon=True,
        )
        self._rx_thread.start()
        logger.info("[ArtNet] Poll listener started on 0.0.0.0:6454")

    def _rx_loop(self):
        """Listen for incoming ArtNet packets and handle ArtPoll."""
        while not self._stop_event.is_set():
            try:
                data, addr = self._socket.recvfrom(1024)
                self._handle_poll_packet(data, addr)
            except socket.timeout:
                continue
            except OSError:
                if self._stop_event.is_set():
                    break
                logger.debug("[ArtNet] RX socket error, retrying...")
                continue
            except Exception as e:
                logger.error(f"[ArtNet] RX loop error: {e}")

        logger.debug("[ArtNet] RX thread stopped")

    def _handle_poll_packet(self, data: bytes, addr: tuple):
        """
        Check if incoming packet is ArtPoll and respond with ArtPollReply.

        ArtPoll minimum structure (14 bytes):
          Bytes 0-7:   "Art-Net\0"
          Bytes 8-9:   OpCode 0x2000 (little-endian)
          Bytes 10-11: ProtVer (big-endian, >= 14)
          Byte  12:    TalkToMe flags
          Byte  13:    Priority
        """
        # Minimum ArtPoll length
        if len(data) < 14:
            return

        # Validate Art-Net header
        if data[:8] != ARTNET_HEADER:
            return

        # Extract opcode (little-endian)
        opcode = struct.unpack_from("<H", data, 8)[0]

        if opcode == ARTNET_OPCODE_POLL:
            sender_ip = addr[0]
            self.stats.polls_received += 1
            logger.info(f"[ArtNet] Poll received from {sender_ip}")
            self._send_poll_reply(addr)

    # ===== ArtPollReply =====

    def _get_local_ip(self) -> str:
        """Detect the local IP address used to reach the network."""
        if self._local_ip:
            return self._local_ip

        try:
            # Connect to a remote address to determine the outbound interface
            # (no actual packet is sent for DGRAM)
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                target = self.config.target_ip
                if target == "255.255.255.255":
                    target = "10.255.255.255"
                probe.connect((target, 6454))
                ip = probe.getsockname()[0]
            finally:
                probe.close()
            self._local_ip = ip
            return ip
        except Exception:
            return "0.0.0.0"

    def _build_poll_reply(self) -> bytes:
        """
        Build an ArtPollReply packet (239 bytes).

        Packet layout per Art-Net 4 specification:
          [0-7]     ID: "Art-Net\0"
          [8-9]     OpCode: 0x2100 LE
          [10-13]   IP Address (4 bytes, network order)
          [14-15]   Port: 0x1936 LE (6454)
          [16-17]   VersInfo HiLo
          [18]      NetSwitch
          [19]      SubSwitch
          [20-21]   OEM HiLo
          [22]      Ubea Version
          [23]      Status1
          [24-25]   EstaMan LE
          [26-43]   ShortName (18 bytes null-padded)
          [44-107]  LongName (64 bytes null-padded)
          [108-171] NodeReport (64 bytes null-padded)
          [172-173] NumPorts HiLo
          [174-177] PortTypes[4]
          [178-181] GoodInput[4]
          [182-185] GoodOutput[4]
          [186-189] SwIn[4]
          [190-193] SwOut[4]
          [194]     SwVideo
          [195]     SwMacro
          [196]     SwRemote
          [197-199] Spare (3 bytes)
          [200]     Style
          [201-206] MAC Hi-Lo (6 bytes)
          [207-210] BindIp (4 bytes)
          [211]     BindIndex
          [212]     Status2
          [213-238] Filler (26 bytes)
        """
        packet = bytearray(ARTNET_POLL_REPLY_LENGTH)

        local_ip = self._get_local_ip()
        ip_bytes = socket.inet_aton(local_ip)

        # [0-7] ID
        packet[0:8] = ARTNET_HEADER

        # [8-9] OpCode 0x2100 LE
        struct.pack_into("<H", packet, 8, ARTNET_OPCODE_POLL_REPLY)

        # [10-13] IP address (network order)
        packet[10:14] = ip_bytes

        # [14-15] Port 6454 LE
        struct.pack_into("<H", packet, 14, ARTNET_PORT)

        # [16-17] Version Hi.Lo
        packet[16] = 0  # Version Hi
        packet[17] = ARTNET_PROTOCOL_VERSION  # Version Lo

        # [18] NetSwitch — bits 14:8 of the 15-bit port-address
        packet[18] = self.config.artnet_net & 0x7F

        # [19] SubSwitch — bits 7:4 of the port-address
        packet[19] = self.config.artnet_subnet & 0x0F

        # [20-21] OEM (0x0000)
        # [22] Ubea (0)

        # [23] Status1: bit 1 = RDM capable (0), bits 5:4 = indicator normal
        packet[23] = 0x00

        # [24-25] ESTA Manufacturer LE (0x0000 = unknown)
        # leave zero

        # [26-43] ShortName (18 bytes, null-padded)
        short_name = b"911Fiesta"
        packet[26:26 + len(short_name)] = short_name

        # [44-107] LongName (64 bytes, null-padded)
        long_name = b"911 Fiesta Lighting Controller"
        packet[44:44 + len(long_name)] = long_name

        # [108-171] NodeReport (64 bytes, null-padded)
        node_report = b"911Fiesta ArtNet Node"
        packet[108:108 + len(node_report)] = node_report

        # [172-173] NumPorts (Hi, Lo) — 1 output port
        packet[172] = 0
        packet[173] = 1

        # [174-177] PortTypes[4] — port 0 = DMX512 output (0x80)
        packet[174] = 0x80  # Can output DMX512

        # [178-181] GoodInput[4] — all zero (no input)

        # [182-185] GoodOutput[4] — port 0: data transmitting (bit 7)
        packet[182] = 0x80

        # [186-189] SwIn[4] — all zero (no input mapping)

        # [190-193] SwOut[4] — port 0: universe
        packet[190] = self.config.artnet_universe & 0x0F

        # [194] SwVideo, [195] SwMacro, [196] SwRemote — all zero

        # [197-199] Spare

        # [200] Style = StNode
        packet[200] = ARTNET_STYLE_NODE

        # [201-206] MAC address
        try:
            import uuid
            mac_int = uuid.getnode()
            for i in range(6):
                packet[201 + i] = (mac_int >> (8 * (5 - i))) & 0xFF
        except Exception:
            pass  # leave as zeros

        # [207-210] BindIp = same as node IP
        packet[207:211] = ip_bytes

        # [211] BindIndex = 1
        packet[211] = 1

        # [212] Status2: bit 3 = supports 15-bit port-address (Art-Net 3+)
        packet[212] = 0x08

        # [213-238] Filler — already zero

        return bytes(packet)

    def _send_poll_reply(self, addr: tuple):
        """Send ArtPollReply to the address that sent the ArtPoll."""
        try:
            reply = self._build_poll_reply()
            target = (addr[0], ARTNET_PORT)
            self._socket.sendto(reply, target)
            self.stats.poll_replies_sent += 1
            logger.info(f"[ArtNet] PollReply sent to {addr[0]}")
        except Exception as e:
            logger.error(f"[ArtNet] Failed to send PollReply: {e}")

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

        # ---- Pre-send diagnostic: log DMX payload on EVERY packet ----
        dmx_payload = packet[18:]  # DMX data starts at byte 18
        nonzero_count = sum(1 for v in dmx_payload if v > 0)
        first20 = list(dmx_payload[:20])
        universe = self.config.artnet_universe
        print(
            f"[ArtNet-TX] universe={universe} nonzero={nonzero_count} "
            f"channels={first20} id={id(self)}"
        )

        try:
            self._socket.sendto(packet, (self.config.target_ip, ARTNET_PORT))
            self.stats.packets_sent += 1
            self.stats.sequence_number = self._sequence

        except socket.timeout:
            pass  # sendto should not block, but ignore if it does
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
            # Snapshot non-zero count for diagnostic
            nonzero_count = sum(1 for v in self._dmx_data if v > 0)
            sample = [(i + 1, v) for i, v in enumerate(self._dmx_data) if v > 0][:8]

        elapsed_ms = (time.time() - start_ts) * 1000
        self.stats.fires_sent += 1
        self.stats.fires_ok += 1
        self.stats.last_latency_ms = elapsed_ms
        self.stats.last_success_ts = time.time()

        # Diagnostic: confirm buffer write with non-zero summary and instance id
        print(f"[ArtNet] FIRE cue={cue_id} channel={channel_index} id={id(self)}")
        print(f"[ArtNet-TX] non-zero={nonzero_count} sample={sample}")

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
            nonzero_count = sum(1 for v in self._dmx_data if v > 0)

        elapsed_ms = (time.time() - start_ts) * 1000
        self.stats.kills_sent += 1
        self.stats.kills_ok += 1
        self.stats.last_latency_ms = elapsed_ms
        self.stats.last_success_ts = time.time()

        # Diagnostic: confirm buffer write
        print(f"[ArtNet] KILL cue={cue_id} channel={channel_index} non-zero={nonzero_count}")

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
        if console_ip and not kwargs.get("target_ip") and not self.config.broadcast:
            # Use console_ip as unicast target only if NOT in broadcast mode
            self.config.target_ip = console_ip
            changed = True

        if changed:
            self._local_ip = None  # Invalidate cached IP
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
            "polls_received": self.stats.polls_received,
            "poll_replies_sent": self.stats.poll_replies_sent,
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
        """Shutdown ArtNet transport: stop TX/RX threads and close socket."""
        logger.info("[ArtNetTransport] Closing...")

        # Signal all threads to stop
        self._stop_event.set()

        # Stop TX thread
        if self._tx_thread and self._tx_thread.is_alive():
            self._tx_thread.join(timeout=2.0)
        self._tx_thread = None

        # Stop RX thread
        if self._rx_thread and self._rx_thread.is_alive():
            self._rx_thread.join(timeout=2.0)
        self._rx_thread = None

        # Close shared socket
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
